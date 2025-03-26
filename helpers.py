import logging
from os import getenv
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

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

async def get_conversation_context(event, client, limit=CONTEXT_MESSAGE_LIMIT):
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