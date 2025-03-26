from telethon import TelegramClient, events
from src.config import Config
from src.utils.logger import logger
from src.telegram.handlers import handle_ai_command

def create_client():
    """Create and configure the Telegram client"""
    client = TelegramClient(
        Config.TG_SESSION_NAME, 
        Config.TG_API_ID, 
        Config.TG_API_HASH
    )
    
    # Register event handlers
    @client.on(events.NewMessage(outgoing=True))
    async def message_handler(event):
        try:
            event_text = getattr(event, 'text', '')
            is_ai_command = any(event_text.startswith(prefix) for prefix in Config.COMMAND_PREFIXES)
            
            if is_ai_command:
                # Check if message is not forwarded from self
                is_self_forward = bool(event.fwd_from and event.fwd_from.from_id and 
                                      hasattr(event.fwd_from.from_id, 'user_id') and 
                                      event.fwd_from.from_id.user_id == event.sender_id)
                                      
                if not is_self_forward:
                    await handle_ai_command(event, client)
                
        except Exception as e:
            logger.error(f"Error in message handler: {str(e)}")
            logger.exception(e)
    
    return client