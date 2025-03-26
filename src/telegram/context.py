from src.config import Config
from src.utils.logger import logger

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
    except Exception as e:
        logger.error(f"Error getting chat info: {str(e)}")
        return None

async def get_conversation_context(event, client, limit=None):
    """Fetch recent messages from the conversation to provide context."""
    if limit is None:
        limit = Config.CONTEXT_MESSAGE_LIMIT
        
    context = []
    chat = await event.get_chat()
    
    chat_id = getattr(chat, 'id', 'unknown')
    logger.info(f"Fetching conversation context from chat {chat_id}, limit: {limit}")
    
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
        logger.info(f"Retrieved {len(messages)} messages for context")
        
        for message in messages:
            sender = await message.get_sender()
            sender_info = await get_user_info(sender)
            
            text = getattr(message, 'text', '')
            caption = getattr(message, 'caption', '')
            message_text = text or caption or "[Media без тексту]"
            
            context_entry = f"{sender_info}: {message_text}"
            context.append(context_entry)
        
        return context
    except Exception as e:
        logger.error(f"Error getting conversation context: {str(e)}")
        return []