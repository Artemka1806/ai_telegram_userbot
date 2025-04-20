from src.config import Config
from src.utils.logger import logger
import time

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
    """Fetch recent messages from the conversation to provide context.
    
    Returns JSON-formatted data containing message details instead of plain text strings.
    JSON format: [{"message_id": 12345, "reply_to": 67890, "timestamp": 1650345600, 
                   "text": "hello", "author": {"user_id": 54321, "username": "username", "name": "Name"},
                   "chat": {"chat_id": 98765, "name": "Group Name"}}]
    """
    if limit is None:
        limit = Config.CONTEXT_MESSAGE_LIMIT
        
    context = []
    chat = await event.get_chat()
    
    # Get chat information
    chat_id = getattr(chat, 'id', 'unknown')
    chat_title = getattr(chat, 'title', None)
    chat_username = getattr(chat, 'username', None)
    
    # For private chats, use the user's name as title if available
    if not chat_title and hasattr(chat, 'first_name'):
        chat_parts = []
        if hasattr(chat, 'first_name') and chat.first_name:
            chat_parts.append(chat.first_name)
        if hasattr(chat, 'last_name') and chat.last_name:
            chat_parts.append(chat.last_name)
        chat_title = " ".join(chat_parts) or "Приватний чат"
    
    chat_info = {
        "chat_id": chat_id,
        "name": chat_title or "Невідомий чат",
        "username": chat_username,
        "type": getattr(chat, 'type', None) or ("private" if hasattr(chat, 'first_name') else "group")
    }
    
    logger.info(f"Fetching conversation context from chat {chat_info['name']} (ID: {chat_id}), limit: {limit}")
    
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
            # Get basic message information
            message_id = getattr(message, 'id', None)
            reply_to = getattr(message, 'reply_to_msg_id', None)
            
            # Convert date to timestamp
            message_date = getattr(message, 'date', None)
            timestamp = int(message_date.timestamp()) if message_date else int(time.time())
            
            # Get message text or caption
            text = getattr(message, 'text', '')
            caption = getattr(message, 'caption', '')
            message_text = text or caption or "[Media без тексту]"
            
            # Get sender information
            sender = await message.get_sender()
            user_id = getattr(sender, 'id', None)
            username = getattr(sender, 'username', '')
            
            first_name = getattr(sender, 'first_name', '')
            last_name = getattr(sender, 'last_name', '')
            full_name = " ".join(filter(None, [first_name, last_name])) if (first_name or last_name) else "Невідоме ім'я"
            
            # Determine message type
            message_type = "text"
            media_info = {}
            
            if hasattr(message, 'photo') and message.photo:
                message_type = "photo"
            elif hasattr(message, 'document') and message.document:
                message_type = "document"
                if hasattr(message.document, 'mime_type'):
                    media_info["mime_type"] = message.document.mime_type
                if hasattr(message.document, 'file_name'):
                    media_info["file_name"] = message.document.file_name
            elif hasattr(message, 'voice') and message.voice:
                message_type = "voice"
                if hasattr(message.voice, 'duration'):
                    media_info["duration"] = message.voice.duration
            elif hasattr(message, 'sticker') and message.sticker:
                message_type = "sticker"
                if hasattr(message.sticker, 'emoji'):
                    media_info["emoji"] = message.sticker.emoji
            
            # Create structured message object
            message_obj = {
                "message_id": message_id,
                "reply_to": reply_to,
                "timestamp": timestamp,
                "text": message_text,
                "type": message_type,
                "author": {
                    "user_id": user_id,
                    "username": username,
                    "name": full_name
                },
                "chat": chat_info
            }
            
            # Add media info if exists
            if media_info:
                message_obj["media_info"] = media_info
                
            # Add forwarded info if message is forwarded
            if getattr(message, 'fwd_from', None):
                fwd_from = message.fwd_from
                fwd_sender = None
                
                if hasattr(fwd_from, 'from_id') and fwd_from.from_id:
                    if hasattr(fwd_from.from_id, 'user_id'):
                        fwd_sender = fwd_from.from_id.user_id
                    elif hasattr(fwd_from.from_id, 'channel_id'):
                        fwd_sender = fwd_from.from_id.channel_id
                
                message_obj["forwarded"] = {
                    "sender_id": fwd_sender,
                    "date": int(fwd_from.date.timestamp()) if hasattr(fwd_from, 'date') and fwd_from.date else None,
                    "name": getattr(fwd_from, 'from_name', None)
                }
            
            context.append(message_obj)
        
        return context
    except Exception as e:
        logger.error(f"Error getting conversation context: {str(e)}")
        logger.exception(e)
        return []