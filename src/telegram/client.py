from telethon import TelegramClient, events
from src.config import Config
from src.utils.logger import logger
from src.telegram.handlers import handle_ai_command, handle_ai_auto_response

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
            
            # Handle toggle_ai command
            if event_text.strip() == "/toggle_ai":
                await handle_toggle_ai(event, client)
                return
                
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
    
    # Register handler for incoming messages (auto-response)
    @client.on(events.NewMessage(incoming=True))
    async def auto_response_handler(event):
        try:
            if not Config.AUTO_RESPONSE_ENABLED:
                return
                
            # Get the list of chats where auto-response is enabled
            auto_response_chats = Config.get_auto_response_chats()
            chat_id = event.chat_id
            
            # Skip if auto-response is not enabled for this chat
            if chat_id not in auto_response_chats:
                return
                
            # Get the sender and me 
            me = await client.get_me()
            sender = await event.get_sender()
            
            # Skip messages from myself
            if sender.id == me.id:
                return
                
            # For private chats, respond to all messages
            is_private = event.is_private
            
            # For group chats, respond only when mentioned or when replying to my message
            was_mentioned = False
            is_reply_to_me = False
            
            if not is_private:
                # Check if I was mentioned
                if hasattr(event.message, 'mentioned') and event.message.mentioned:
                    was_mentioned = True
                    
                # Check if message text contains my username or first name
                event_text = getattr(event.message, 'text', '')
                if me.username and f"@{me.username}" in event_text:
                    was_mentioned = True
                    
                # Check if it's a reply to my message
                if hasattr(event.message, 'reply_to') and event.message.reply_to:
                    reply_msg = await event.get_reply_message()
                    if reply_msg and reply_msg.sender_id == me.id:
                        is_reply_to_me = True
            
            # Process message if it meets the criteria
            if is_private or was_mentioned or is_reply_to_me:
                await handle_ai_auto_response(event, client)
                
        except Exception as e:
            logger.error(f"Error in auto-response handler: {str(e)}")
            logger.exception(e)
    
    return client

async def handle_toggle_ai(event, client):
    """Toggle auto-response for the current chat"""
    try:
        chat_id = event.chat_id
        auto_response_chats = Config.get_auto_response_chats()
        
        if chat_id in auto_response_chats:
            # Disable auto-response for this chat
            auto_response_chats.remove(chat_id)
            message = "🤖 **Автовідповіді ШІ вимкнено** для цього чату"
        else:
            # Enable auto-response for this chat
            auto_response_chats.append(chat_id)
            
            # Determine chat type for appropriate message
            chat = await event.get_chat()
            is_private = event.is_private
            
            if is_private:
                message = "🤖 **Автовідповіді ШІ увімкнено** для цього приватного чату\n\nТепер я відповідатиму на всі ваші повідомлення."
            else:
                message = "🤖 **Автовідповіді ШІ увімкнено** для цього групового чату\n\nТепер я відповідатиму на повідомлення, коли:\n- Мене згадають (@username)\n- Хтось відповість на моє повідомлення"
        
        # Save updated chats list
        Config.save_auto_response_chats(auto_response_chats)
        
        # Send confirmation message
        await event.reply(message)
        
    except Exception as e:
        logger.error(f"Error in toggle_ai handler: {str(e)}")
        logger.exception(e)
        await event.reply("❌ Помилка при зміні налаштувань автовідповідей")