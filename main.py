from os import getenv

from telethon import TelegramClient, events
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

api_id = int(getenv("TG_API_ID"))
api_hash = getenv("TG_API_HASH")

session_name = getenv("TG_SESSION_NAME")

client = TelegramClient(session_name, api_id, api_hash)

openai_api_key = getenv("OPENAI_API_KEY")

openai = OpenAI(api_key=openai_api_key)

async def get_ai_response(prompt):
    """Get response from OpenAI API."""
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
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
    user_id = f"ID: {user.id}" if hasattr(user, 'id') else ""
    
    return f"{full_name} ({username}, {user_id})"

async def get_chat_info(event):
    """Get information about the chat where the message was sent."""
    try:
        chat = await event.get_chat()
        if hasattr(chat, 'title'):
            return f"Чат: {chat.title}"
        return None
    except:
        return None

@client.on(events.NewMessage(outgoing=True))
async def handler(event):
    if event.text.startswith("/gpt") or event.text.startswith("/гпт"):
        async with client.action(event.chat_id, 'typing'):
            command_text = event.text[len("/gpt"):].strip() if event.text.startswith("/gpt") else event.text[len("/гпт"):].strip()
            
            reply_data = {}
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

            if command_text or reply_data:
                prompt = "Дай відповідь на запитання:"
                if command_text:
                    prompt += f"\n{command_text}"
                
                if reply_data:
                    prompt += f"\n\nКонтекст повідомлення: {reply_data.get('text', '')}"
                    prompt += f"\nАвтор повідомлення: {reply_data.get('user_info', '')}"
                    if reply_data.get('chat_info'):
                        prompt += f"\n{reply_data.get('chat_info')}"
                
                thinking_message = await event.reply("⏳")
                
                ai_response = await get_ai_response(prompt)

                await thinking_message.edit(f"🤖 **GPT-4o**:\n{ai_response}", parse_mode='md')
            else:
                await event.delete()
                return

client.start()
print("Userbot is running and listening to your messages...")
client.run_until_disconnected()