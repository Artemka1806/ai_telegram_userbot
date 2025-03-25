from os import getenv
import logging
from telethon import TelegramClient, events
from openai import OpenAI
from dotenv import load_dotenv

# Configure logging
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

openai_api_key = getenv("OPENAI_API_KEY")

openai = OpenAI(api_key=openai_api_key)

model = getenv("OPENAI_MODEL", "gpt-4o-mini-2024-07-18")

CONTEXT_MESSAGE_LIMIT = int(getenv("CONTEXT_MESSAGE_LIMIT", 5))


async def get_ai_response(prompt, user_info):
    """Get response from OpenAI API."""
    logging.info(f"Getting AI response for prompt: {prompt}")
    try:
        response = openai.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": f"""You are an AI assistant integrated into a Telegram chat, but responding AS THE USER ({user_info}).
                 You are generating responses that will be sent FROM the user's account to others in the chat.
                 Keep your responses concise, direct, and conversational in the user's voice.
                 You can use markdown formatting in your responses.
                 You should NOT identify yourself as an AI. Act as if you ARE the human user.
                 Match the user's native language (Ukrainian or Russian if evident from context).
                 When answering questions, maintain the user's tone and perspective.
                 Avoid formal or robotic language, and use simple, natural expressions as a human would.
                 Remember that you are creating responses that the user wants to send in their name."""},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )
        return getattr(response.choices[0].message, 'content', "No response received")
    except Exception as e:
        return f"Error getting AI response: {str(e)}"


async def get_user_info(user):
    """Extract user information in a formatted string."""
    if not user:
        return "Невідомий користувач"
    
    user_info = []
    first_name = getattr(user, 'first_name', '')
    last_name = getattr(user, 'last_name', '')
    
    if first_name:
        user_info.append(first_name)
    if last_name:
        user_info.append(last_name)
    
    full_name = " ".join(user_info) if user_info else "Невідоме ім'я"
    
    username = getattr(user, 'username', None)
    username_str = f"@{username}" if username else "без юзернейму"
    
    return f"{full_name} (юзернейм: {username_str})"


async def get_chat_info(event):
    """Get information about the chat where the message was sent."""
    try:
        chat = await event.get_chat()
        title = getattr(chat, 'title', None)
        return f"Чат: {title}" if title else None
    except:
        return None


async def get_conversation_context(event, limit=CONTEXT_MESSAGE_LIMIT):
    """Fetch recent messages from the conversation to provide context."""
    context = []
    chat = await event.get_chat()
    
    chat_id = getattr(chat, 'id', 'unknown')
    logging.info(f"Fetching conversation context from chat {chat_id}, limit: {limit}")
    
    try:
        messages = []
        async for message in client.iter_messages(
            entity=chat,
            limit=limit + 1,
            offset_date=getattr(event, 'date', None),
            reverse=False
        ):
            if message.id != event.id:
                messages.append(message)
            
            if len(messages) >= limit:
                break
        
        messages.reverse()
        
        logging.info(f"Retrieved {len(messages)} messages for context")
        
        for message in messages:
            sender = await message.get_sender()
            sender_info = await get_user_info(sender)
            
            text = getattr(message, 'text', '')
            caption = getattr(message, 'caption', '')
            message_text = text or caption or "[Media без тексту]"
            
            context_entry = f"{sender_info}: {message_text}"
            context.append(context_entry)
            logging.info(f"Added to context: {context_entry[:50]}...")
        
        return context
    except Exception as e:
        logging.error(f"Error getting conversation context: {str(e)}")
        logging.exception(e)
        return []


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
                
                conversation_history = await get_conversation_context(event)
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
                        reply_context = await get_conversation_context(reply_message)
                        if reply_context:
                            prompt += "\n\nПопередня переписка повідомлення, на яке відповідали (від старіших до новіших):"
                            for msg in reply_context:
                                prompt += f"\n{msg}"
                    
                    logging.info(f"Final prompt length: {len(prompt)} characters")
                    if reply_message:
                        thinking_message = await reply_message.reply("⏳")
                        await event.delete()
                    else:
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