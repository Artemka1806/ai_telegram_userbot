from src.utils.logger import logger
from src.config import Config
from src.ai.client import get_ai_response
from src.ai.prompts import build_prompt
from src.telegram.context import get_user_info, get_chat_info, get_conversation_context
from src.utils.image import process_image, cleanup_resources

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
        
        # Process images if any
        await process_command_images(event, reply_message, contents, images_to_close, temp_files_to_remove)
        
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
    current_chunk = ""
    
    # Split by paragraphs or sentences if possible
    paragraphs = ai_response.split("\n\n")
    
    for para in paragraphs:
        # If a single paragraph is longer than max_length, we need to split it further
        if len(para) > max_length:
            sentences = para.split(". ")
            for sentence in sentences:
                if len(current_chunk + sentence + ". ") > max_length and current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = sentence + ". "
                else:
                    current_chunk += sentence + ". "
        else:
            if len(current_chunk + para + "\n\n") > max_length and current_chunk:
                chunks.append(current_chunk)
                current_chunk = para + "\n\n"
            else:
                current_chunk += para + "\n\n"
    
    # Add the last chunk if it's not empty
    if current_chunk:
        chunks.append(current_chunk)
    
    # Send chunks as separate messages
    logger.info(f"Splitting response into {len(chunks)} chunks")
    
    # First chunk replaces thinking message
    first_chunk = f"{header}{chunks[0]}"
    if len(chunks) > 1:
        first_chunk += f"\n\n(1/{len(chunks)})"
    await thinking_message.edit(first_chunk)
    
    # Send remaining chunks as new messages
    for i, chunk in enumerate(chunks[1:], 2):
        message_text = f"{chunk}\n\n({i}/{len(chunks)})"
        await original_event.respond(message_text)

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

async def process_command_images(event, reply_message, contents, images_to_close, temp_files_to_remove):
    """Process and add images from command and reply to contents"""
    # Add images from command message if any
    if getattr(event.message, 'photo', None):
        file_path = await event.download_media()
        if file_path:
            img = await process_image(file_path)
            if img:
                contents.append(img)
                images_to_close.append(img)
                temp_files_to_remove.append(file_path)

    # Add images from reply message if any
    if reply_message and getattr(reply_message, 'photo', None):
        file_path = await reply_message.download_media()
        if file_path:
            img = await process_image(file_path)
            if img:
                contents.append(img)
                images_to_close.append(img)
                temp_files_to_remove.append(file_path)

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