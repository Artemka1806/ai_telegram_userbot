from os import getenv
import logging
from telethon import TelegramClient, events
from dotenv import load_dotenv

from helpers import get_ai_response, get_user_info, get_chat_info, get_conversation_context

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

load_dotenv()

api_id = int(getenv("TG_API_ID"))
api_hash = getenv("TG_API_HASH")
session_name = getenv("TG_SESSION_NAME")
client = TelegramClient(session_name, api_id, api_hash)

CONTEXT_MESSAGE_LIMIT = int(getenv("CONTEXT_MESSAGE_LIMIT", 5))
model = getenv("OPENAI_MODEL", "gpt-4o-mini-2024-07-18")

@client.on(events.NewMessage(outgoing=True))
async def handler(event):
    try:
        command_prefixes = [".ші", ".аі", ".ai", ".ии", ".gpt", ".гпт"]
        event_text = getattr(event, 'text', '')
        is_ai_command = any(event_text.startswith(prefix) for prefix in command_prefixes)
        
        if is_ai_command:
            async with client.action(event.chat_id, 'typing'):
                command_text = event_text[4:].strip()
                
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
                
                if command_text or reply_data or conversation_history:
                    prompt = "Напиши повідомлення від мого імені:"
                    if command_text:
                        prompt += f"\nЗавдання: {command_text}"
                    
                    if reply_data:
                        prompt += f"\n\nЦе відповідь на повідомлення: {reply_data.get('text', '')}"
                        prompt += f"\nАвтор повідомлення: {reply_data.get('user_info', '')}"
                        if reply_data.get('chat_info'):
                            prompt += f"\n{reply_data.get('chat_info')}"
                    
                    if conversation_history:
                        prompt += "\n\nПопередня переписка (від старіших до новіших повідомлень):"
                        for msg in conversation_history:
                            prompt += f"\n{msg}"
                    
                    if reply_message:
                        if abs(reply_message.id - event.id) >= 5:
                            reply_context = await get_conversation_context(reply_message, client)
                            if reply_context:
                                prompt += "\n\nПопередня переписка повідомлення, на яке відповідали (від старіших до новіших):"
                                for msg in reply_context:
                                    prompt += f"\n{msg}"
                        else:
                            logging.info("Reply message is too close to the event message, skipping context.")
                    logging.info(f"Final prompt length: {len(prompt)} characters")
                    if reply_message:
                        thinking_message = await reply_message.reply("⏳")
                        await event.delete()
                    else:
                        if not command_text:
                            await event.delete()
                        thinking_message = await event.reply("⏳")
                    
                    ai_response = await get_ai_response(prompt, my_info)

                    await thinking_message.edit(f"**🤖 {model}**\n{ai_response}")
                else:
                    await event.delete()
                    return
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