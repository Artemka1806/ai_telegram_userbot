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


async def get_ai_response(prompt):
    """Get response from OpenAI API."""
    logging.info(f"Getting AI response for prompt: {prompt}")
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {"role": "system", "content": """You are a helpful assistant integrated into a Telegram chat.
                 You're responding to users in a messaging environment.
                 Keep your responses concise, direct, and conversational.
                 You can use markdown formatting in your responses.
                 You may reference usernames when appropriate and maintain a friendly, chat-like tone.
                 Remember that users are having real-time conversations, so be practical and to the point.
                 When answering questions, consider the casual context of messaging.
                 Avoid overly technical explanations and use simple language where possible."""},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error getting AI response: {str(e)}"


async def get_user_info(user):
    """Extract user information in a formatted string."""
    if not user:
        return "Невідомий користувач"
    
    user_info = []
    if hasattr(user, 'first_name') and user.first_name:
        user_info.append(user.first_name)
    if hasattr(user, 'last_name') and user.last_name:
        user_info.append(user.last_name)
    
    full_name = " ".join(user_info) if user_info else "Невідоме ім'я"
    
    username = f"@{user.username}" if hasattr(user, 'username') and user.username else "без юзернейму"
    
    return f"{full_name} (юзернейм :{username})"


async def get_chat_info(event):
    """Get information about the chat where the message was sent."""
    try:
        chat = await event.get_chat()
        if hasattr(chat, 'title'):
            return f"Чат: {chat.title}"
        return None
    except:
        return None


async def get_conversation_context(event, limit=CONTEXT_MESSAGE_LIMIT):
    """Fetch recent messages from the conversation to provide context."""
    context = []
    chat = await event.get_chat()
    
    logging.info(f"Fetching conversation context from chat {chat.id}, limit: {limit}")
    
    try:
        messages = []
        async for message in client.iter_messages(
            entity=chat,
            limit=limit + 1,
            offset_date=event.date,
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
            
            message_text = message.text or message.caption or "[Media без тексту]"
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
    command_prefixes = [".ші", ".аі", ".ai", ".ии", ".gpt", ".гпт"]
    is_ai_command = any(event.text.startswith(prefix) for prefix in command_prefixes)
    if is_ai_command:
        async with client.action(event.chat_id, 'typing'):
            command_text = event.text[len("/gpt"):].strip() if event.text.startswith("/gpt") else event.text[len("/гпт"):].strip()
            
            logging.info(f"Processing AI command: {command_text[:50]}...")
            
            reply_data = {}
            reply_message = None
            if event.reply_to_msg_id:
                reply_message = await event.get_reply_message()
                
                if reply_message.text:
                    reply_data["text"] = reply_message.text
                elif reply_message.caption:
                    reply_data["text"] = f"[Media з підписом]: {reply_message.caption}"
                else:
                    reply_data["text"] = "[Media без підпису]"
                
                sender = await reply_message.get_sender()
                reply_data["user_info"] = await get_user_info(sender)
                
                reply_data["chat_info"] = await get_chat_info(reply_message)
            
            conversation_history = await get_conversation_context(event)
            logging.info(f"Got {len(conversation_history)} messages for conversation context")
            
            if command_text or reply_data or conversation_history:
                prompt = "Дай відповідь на запитання:"
                if command_text:
                    prompt += f"\n{command_text}"
                
                if reply_data:
                    prompt += f"\n\nКонтекст повідомлення: {reply_data.get('text', '')}"
                    prompt += f"\nАвтор повідомлення: {reply_data.get('user_info', '')}"
                    if reply_data.get('chat_info'):
                        prompt += f"\n{reply_data.get('chat_info')}"
                
                if conversation_history:
                    prompt += "\n\nПопередня переписка (від старіших до новіших повідомлень):"
                    for msg in conversation_history:
                        prompt += f"\n{msg}"
                
                logging.info(f"Final prompt length: {len(prompt)} characters")
                if reply_message:
                    thinking_message = await reply_message.reply("⏳")
                    await event.delete()
                else:
                    thinking_message = await event.reply("⏳")
                
                ai_response = await get_ai_response(prompt)

                await thinking_message.edit(f"🤖 **{model}**:\n{ai_response}", parse_mode='md')
            else:
                await event.delete()
                return


client.start()
logging.info("Userbot is running and listening to your messages...")
client.run_until_disconnected()