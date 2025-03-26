from os import getenv, remove
import logging
from PIL import Image
from telethon import TelegramClient, events
from dotenv import load_dotenv

from helpers import get_ai_response, get_user_info, get_chat_info, get_conversation_context

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

load_dotenv()

def process_image(image_path):
    """Process image for Gemini API using PIL"""
    return Image.open(image_path)

api_id = int(getenv("TG_API_ID"))
api_hash = getenv("TG_API_HASH")
session_name = getenv("TG_SESSION_NAME")
client = TelegramClient(session_name, api_id, api_hash)

CONTEXT_MESSAGE_LIMIT = int(getenv("CONTEXT_MESSAGE_LIMIT", 5))
model = getenv("GEMINI_MODEL", "gemini-2.0-flash")

@client.on(events.NewMessage(outgoing=True))
async def handler(event):
    try:
        command_prefixes = [".", ".ші", ".аі", ".ai", ".ии", ".gpt", ".гпт", ".gem"]
        event_text = getattr(event, 'text', '')
        is_ai_command = any(event_text.startswith(prefix) for prefix in command_prefixes)
        
        if is_ai_command:
            async with client.action(event.chat_id, 'typing'):
                # Find the prefix that matched and get its length
                prefix_length = 0
                for prefix in command_prefixes:
                    if event_text.startswith(prefix):
                        prefix_length = len(prefix)
                        break
                        
                command_text = event_text[prefix_length:].strip()
                logging.info(f"Processing AI command: {command_text[:50]}...")
                
                me = await client.get_me()
                my_info = await get_user_info(me)
                
                reply_data = {}
                reply_message = None
                if getattr(event, 'reply_to_msg_id', None):
                    reply_message = await event.get_reply_message()
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
                
                conversation_history = await get_conversation_context(event, client)
                logging.info(f"Got {len(conversation_history)} messages for context")
                
                contents = []
                
                # Add text content first
                prompt_text = "Напиши повідомлення від мого імені:"
                if command_text:
                    prompt_text += f"\nЗавдання: {command_text}"
                
                if reply_data:
                    prompt_text += f"\n\nЦе відповідь на повідомлення: {reply_data.get('text', '')}"
                    prompt_text += f"\nАвтор повідомлення: {reply_data.get('user_info', '')}"
                    if reply_data.get('chat_info'):
                        prompt_text += f"\n{reply_data.get('chat_info')}"
                
                if conversation_history:
                    prompt_text += "\n\nПопередня переписка (від старіших до новіших повідомлень):"
                    for msg in conversation_history:
                        prompt_text += f"\n{msg}"
                
                if reply_message:
                    if abs(reply_message.id - event.id) >= 5:
                        reply_context = await get_conversation_context(reply_message, client)
                        if reply_context:
                            prompt_text += "\n\nПопередня переписка повідомлення, на яке відповідали (від старіших до новіших):"
                            for msg in reply_context:
                                prompt_text += f"\n{msg}"
                    else:
                        logging.info("Reply message is too close to the event message, skipping context.")
                
                logging.info(f"Final prompt length: {len(prompt_text)} characters")
                
                # Add text as first element in contents
                contents.append(prompt_text)
                
                # Track images to close them after API call
                images_to_close = []
                temp_files_to_remove = []
                
                # Add images if any
                if getattr(event.message, 'photo', None):
                    file_path = await event.download_media()
                    if file_path:
                        try:
                            img = process_image(file_path)
                            contents.append(img)
                            images_to_close.append(img)
                            temp_files_to_remove.append(file_path)
                        except Exception as e:
                            logging.error(f"Error processing image: {str(e)}")
                            try:
                                remove(file_path)
                            except:
                                pass

                if reply_message and getattr(reply_message, 'photo', None):
                    file_path = await reply_message.download_media()
                    if file_path:
                        try:
                            img = process_image(file_path)
                            contents.append(img)
                            images_to_close.append(img)
                            temp_files_to_remove.append(file_path)
                        except Exception as e:
                            logging.error(f"Error processing reply image: {str(e)}")
                            try:
                                remove(file_path)
                            except:
                                pass
                
                try:
                    if command_text or reply_data or conversation_history:
                        if reply_message:
                            thinking_message = await reply_message.reply("⏳")
                        else:
                            if not command_text:
                                await event.delete()
                            thinking_message = await event.reply("⏳")
                        
                        ai_response = await get_ai_response(contents, my_info)
                        await thinking_message.edit(f"**🤖 {model}**\n{ai_response}")
                    else:
                        await event.delete()
                        return
                finally:
                    # Clean up resources
                    for img in images_to_close:
                        try:
                            img.close()
                        except Exception as e:
                            logging.warning(f"Error closing image: {str(e)}")
                    
                    # Small delay before removing files
                    import time
                    time.sleep(0.1)
                    
                    for file_path in temp_files_to_remove:
                        try:
                            remove(file_path)
                        except Exception as e:
                            logging.warning(f"Could not remove file {file_path}: {str(e)}")
    except Exception as e:
        logging.error(f"Error in handler: {str(e)}")
        logging.exception(e)
        if hasattr(event, 'reply_to_msg_id'):
            await event.reply("❌ Виникла помилка під час обробки запиту.")
        else:
            await event.delete()

client.start()
logging.info("Userbot is running and listening to your messages...")
client.run_until_disconnected()