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
                reply_context = await get_conversation_context(reply_message, client)
                logger.info(f"Got {len(reply_context)} messages for reply context")
        
        # Get conversation history
        conversation_history = await get_conversation_context(event, client)
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
                await thinking_message.edit(f"**🤖 {Config.GEMINI_MODEL}**\n{ai_response}")
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