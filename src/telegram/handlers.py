import os

from src.utils.logger import logger
from src.config import Config
from src.ai.client import get_ai_response, get_ai_image_response
from src.ai.prompts import build_prompt
from src.telegram.context import get_user_info, get_chat_info, get_conversation_context
from src.utils.image import process_image, cleanup_resources
from google import genai

client = genai.Client(api_key=Config.GEMINI_API_KEY)

async def handle_ai_command(event, client):
    """Handle AI command messages"""
    try:
        # Get prefix length for command
        prefix_length = 0
        for prefix in Config.COMMAND_PREFIXES:
            if event.text.startswith(prefix):
                prefix_length = len(prefix)
                break
                
        command_text = event.text[prefix_length:].strip()
        
        # Check if this is an image generation request
        is_image_request = command_text.startswith("img ") or command_text.startswith("image ")
        
        if is_image_request:
            # Remove the "img " or "image " prefix from the command
            if command_text.startswith("img "):
                command_text = command_text[4:].strip()
            else:
                command_text = command_text[6:].strip()
            
            await handle_image_generation(event, client, command_text)
            return
        
        # Check for context limit in command (e.g., ".20" or ". 20")
        context_limit = Config.CONTEXT_MESSAGE_LIMIT  # Default value
        
        if command_text:
            # Try to extract a number at the beginning
            parts = command_text.split(maxsplit=1)
            first_part = parts[0]
            
            if first_part.isdigit():
                try:
                    context_limit = int(first_part)
                    if context_limit > 1000:  # Set a reasonable upper limit
                        context_limit = 1000
                    elif context_limit < 1:  # Set a reasonable lower limit
                        context_limit = 1
                        
                    # Remove the number from command text
                    command_text = parts[1] if len(parts) > 1 else ""
                    logger.info(f"Custom context limit set: {context_limit}")
                except ValueError:
                    logger.warning(f"Invalid context limit format: {first_part}, using default")
        
        logger.info(f"Processing AI command: {command_text[:50]}...")
        
        # Get user info
        me = await client.get_me()
        my_info = await get_user_info(me)
        
        # Process reply if available
        reply_data = {}
        reply_message = None
        reply_context = []
        
        if getattr(event, 'reply_to_msg_id', None):
            reply_message = await event.get_reply_message()
            reply_data = await process_reply_message(reply_message)
            
            # Get context around the reply if needed
            if abs(reply_message.id - event.id) >= 5:
                reply_context = await get_conversation_context(reply_message, client, context_limit)
                logger.info(f"Got {len(reply_context)} messages for reply context")
        
        # Get conversation history with the specified context limit
        conversation_history = await get_conversation_context(event, client, context_limit)
        logger.info(f"Got {len(conversation_history)} messages for context")
        
        # Build prompt and prepare content for AI
        prompt_text = await build_prompt(
            command_text, 
            reply_data, 
            conversation_history,
            reply_context
        )
        
        logger.info(f"Final prompt length: {len(prompt_text)} characters")
        
        # Prepare content for AI (text and images)
        contents = [prompt_text]
        images_to_close = []
        temp_files_to_remove = []
        
        # Process images and voice messages if any
        await process_command_media(event, reply_message, contents, images_to_close, temp_files_to_remove)
        
        try:
            # Send thinking indicator and get AI response
            if command_text or reply_data or conversation_history:
                thinking_message = await send_thinking_message(event, reply_message, command_text)
                
                ai_response = await get_ai_response(contents, my_info)
                
                # Split and send large responses in chunks
                await send_chunked_response(ai_response, thinking_message, client, event)
            else:
                await event.delete()
                return
                
        finally:
            # Clean up resources
            await cleanup_resources(images_to_close, temp_files_to_remove)
            
    except Exception as e:
        logger.error(f"Error in AI command handler: {str(e)}")
        logger.exception(e)
        await handle_error(event)

async def handle_image_generation(event, client, prompt_text):
    """Handle AI image generation/editing commands"""
    try:
        logger.info(f"Processing image generation request: {prompt_text[:50]}...")
        
        # Get user info
        me = await client.get_me()
        my_info = await get_user_info(me)
        
        # Process reply if available to get source image for editing
        reply_message = None
        images_to_close = []
        temp_files_to_remove = []
        
        # Send thinking indicator
        thinking_message = await event.reply("🎨 Generating image...")
        
        # Prepare contents for AI
        contents = [prompt_text]
        
        if getattr(event, 'reply_to_msg_id', None):
            reply_message = await event.get_reply_message()
            
            # Check if reply has an image for editing
            if getattr(reply_message, 'photo', None) or (hasattr(reply_message, 'sticker') and reply_message.sticker):
                file_path = await reply_message.download_media()
                if file_path:
                    img = await process_image(file_path)
                    if img:
                        contents.append(img)
                        images_to_close.append(img)
                        temp_files_to_remove.append(file_path)
                        logger.info(f"Source image for editing: {file_path}")
        
        try:
            # Get AI response with image generation
            result = await get_ai_image_response(contents, my_info)
            
            # Send the generated images and text response
            if result["images"]:
                for i, image_path in enumerate(result["images"]):
                    caption = result["text"] if i == 0 and result["text"] else None
                    await client.send_file(
                        event.chat_id,
                        image_path,
                        caption=caption,
                        reply_to=event.reply_to_msg_id if i == 0 else None
                    )
                # Edit the thinking message to indicate completion
                await thinking_message.edit("✅ Image generation complete!")
            else:
                # No images were generated, send error message
                await thinking_message.edit(f"❌ {result['text'] or 'Failed to generate image'}")
                
        finally:
            # Clean up resources
            await cleanup_resources(images_to_close, temp_files_to_remove)
            
            # Also clean up generated images after sending
            for image_path in result.get("images", []):
                try:
                    if os.path.exists(image_path):
                        os.remove(image_path)
                except Exception as e:
                    logger.warning(f"Could not remove generated image {image_path}: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error in image generation handler: {str(e)}")
        logger.exception(e)
        await event.reply("❌ Error generating image")

async def send_chunked_response(ai_response, thinking_message, client, original_event):
    """Split and send large responses in multiple messages if needed"""
    # Maximum message length (Telegram limit is around 4096, using less to be safe)
    max_length = 4000
    header = f"**🤖 {Config.GEMINI_MODEL}**\n"
    
    if len(ai_response) <= max_length:
        # Response fits in one message
        await thinking_message.edit(f"{header}{ai_response}")
        return
        
    # Response is too large, split into chunks
    chunks = []
    
    # Improved chunking algorithm that preserves content better
    remaining_text = ai_response
    while remaining_text:
        # If remaining text fits in a chunk, add it and break
        if len(remaining_text) <= max_length:
            chunks.append(remaining_text)
            break
            
        # Find a good split point (paragraph break, sentence break, or word break)
        # Look for paragraph break within limits
        split_pos = remaining_text[:max_length].rfind("\n\n")
        
        # If no paragraph break, try sentence break
        if split_pos == -1 or split_pos < max_length // 2:
            # Look for sentence break (handling multiple punctuation marks)
            for punct in [". ", "! ", "? ", ".\n", "!\n", "?\n"]:
                pos = remaining_text[:max_length].rfind(punct)
                if pos > max_length // 2:  # Only use if at least halfway through the chunk
                    split_pos = pos + len(punct) - 1  # Include the punctuation but not the space
                    break
                    
        # If no good sentence break, split at a word boundary
        if split_pos == -1 or split_pos < max_length // 2:
            split_pos = remaining_text[:max_length].rfind(" ")
            if split_pos == -1:  # No spaces found, force split
                split_pos = max_length - 1
        
        # Add chunk and continue with remaining text
        chunks.append(remaining_text[:split_pos + 1])
        remaining_text = remaining_text[split_pos + 1:].strip()
    
    # Log the chunking results
    logger.info(f"Split response into {len(chunks)} chunks (total length: {len(ai_response)} chars)")
    
    # First chunk replaces thinking message
    first_chunk = f"{header}{chunks[0]}"
    if len(chunks) > 1:
        first_chunk += f"\n\n(1/{len(chunks)})"
    await thinking_message.edit(first_chunk)
    
    # Send remaining chunks as new messages
    for i, chunk in enumerate(chunks[1:], 2):
        chunk_text = f"{chunk}\n\n({i}/{len(chunks)})"
        try:
            await original_event.respond(chunk_text)
            # Add a small delay between messages to avoid rate limiting
            import asyncio
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Error sending chunk {i}/{len(chunks)}: {str(e)}")
            # Try to send error message
            try:
                await original_event.respond(f"❌ Помилка при відправці частини відповіді ({i}/{len(chunks)})")
            except:
                pass

async def process_reply_message(reply_message):
    """Process a reply message and extract relevant data"""
    reply_data = {}
    
    if reply_message:
        text = getattr(reply_message, 'text', '')
        caption = getattr(reply_message, 'caption', '')
        
        if text:
            reply_data["text"] = text
        elif caption:
            reply_data["text"] = f"[Media з підписом]: {caption}"
        else:
            reply_data["text"] = "[Media без підпису]"
        
        sender = await reply_message.get_sender()
        reply_data["user_info"] = await get_user_info(sender)
        reply_data["chat_info"] = await get_chat_info(reply_message)
    
    return reply_data

async def process_command_media(event, reply_message, contents, images_to_close, temp_files_to_remove):
    """Process and add media (images, stickers, and voice messages) from command and reply to contents"""
    # Add images from command message if any
    if getattr(event.message, 'photo', None):
        file_path = await event.download_media()
        if file_path:
            img = await process_image(file_path)
            if img:
                contents.append(img)
                images_to_close.append(img)
                temp_files_to_remove.append(file_path)
    
    # Add stickers from command message
    if hasattr(event.message, 'sticker') and event.message.sticker:
        file_path = await event.download_media()
        if file_path:
            img = await process_image(file_path)
            if img:
                contents.append(img)
                images_to_close.append(img)
                temp_files_to_remove.append(file_path)
                logger.info(f"Sticker processed from command: {file_path}")
    
    # Add voice message from command message if any
    if hasattr(event.message, 'voice') and event.message.voice:
        file_path = await event.download_media()
        if file_path:
            # Upload voice file to Gemini using client.files.upload
            try:
                voice_file = client.files.upload(file=file_path)
                contents.append(voice_file)
                # No need to close file objects like images, but we still need to clean up the temp file
                temp_files_to_remove.append(file_path)
                # Add instruction for voice processing
                contents.insert(0, "Transcribe and respond to this voice message")
                logger.info(f"Voice message uploaded from command: {file_path}")
            except Exception as e:
                logger.error(f"Error uploading voice file: {str(e)}")

    # Add media from reply message if any
    if reply_message:
        # Handle images in reply
        if getattr(reply_message, 'photo', None):
            file_path = await reply_message.download_media()
            if file_path:
                img = await process_image(file_path)
                if img:
                    contents.append(img)
                    images_to_close.append(img)
                    temp_files_to_remove.append(file_path)
        
        # Handle stickers in reply
        if hasattr(reply_message, 'sticker') and reply_message.sticker:
            file_path = await reply_message.download_media()
            if file_path:
                img = await process_image(file_path)
                if img:
                    contents.append(img)
                    images_to_close.append(img)
                    temp_files_to_remove.append(file_path)
                    logger.info(f"Sticker processed from reply: {file_path}")
        
        # Handle voice messages in reply
        if hasattr(reply_message, 'voice') and reply_message.voice:
            file_path = await reply_message.download_media()
            if file_path:
                try:
                    voice_file = client.files.upload(file=file_path)
                    contents.append(voice_file)
                    temp_files_to_remove.append(file_path)
                    # Add instruction for voice processing if it's not already there
                    if not any(isinstance(c, str) and "voice message" in c.lower() for c in contents):
                        contents.insert(0, "Transcribe and respond to this voice message")
                    logger.info(f"Voice message uploaded from reply: {file_path}")
                except Exception as e:
                    logger.error(f"Error uploading reply voice file: {str(e)}")

async def send_thinking_message(event, reply_message, command_text):
    """Send a thinking indicator message"""
    if not command_text:
            await event.delete()
    if reply_message:
        return await reply_message.reply("⏳")
    else:
        return await event.reply("⏳")

async def handle_error(event):
    """Handle errors in command processing"""
    if hasattr(event, 'reply_to_msg_id'):
        await event.reply("❌ Виникла помилка під час обробки запиту.")
    else:
        await event.delete()