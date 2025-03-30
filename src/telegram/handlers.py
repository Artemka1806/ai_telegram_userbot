import os
from src.utils.logger import logger
from src.config import Config
from src.ai.client import get_default_response, get_helpful_response , get_transcription_response, get_image_response, get_history_summary, get_summary_response, get_code_response, get_grounded_response
from src.ai.prompts import build_prompt, get_mode_prompt
from src.telegram.context import get_user_info, get_chat_info, get_conversation_context
from src.utils.image import process_image, cleanup_resources
from google import genai

client = genai.Client(api_key=Config.GEMINI_API_KEY)

async def handle_ai_command(event, client):
    """Handle AI command messages with multiple modes"""
    try:
        text = getattr(event, 'text', '').strip()
        
        # Identify command mode
        mode = identify_command_mode(text)
        if not mode:
            return
            
        logger.info(f"Command mode identified: {mode}")
        
        # Extract context limit and command text
        context_limit, command_text = extract_command_parameters(text, mode)
        
        logger.info(f"Raw command text: '{text}'")
        logger.info(f"Identified mode: {mode}")
        logger.info(f"Extracted command text: '{command_text}'")
        # Process command based on mode
        if mode == "image":
            await handle_image_mode(event, client, command_text, enhance_prompt=False)
            return
        elif mode == "image_enhanced":
            await handle_image_mode(event, client, command_text, enhance_prompt=True)
            return
        elif mode == "history":
            await handle_history_mode(event, client, context_limit)
            return 
        elif mode == "help":
            await handle_help_mode(event)
            return
        elif mode == "grounding":
            await handle_grounding_mode(event, client, command_text)
            return
        else:
            # Handle text-based modes (default, helpful, transcription, code, summary)
            await handle_text_mode(event, client, mode, context_limit, command_text)
            return
            
    except Exception as e:
        logger.error(f"Error in AI command handler: {str(e)}")
        logger.exception(e)
        await handle_error(event)
            
def identify_command_mode(text):
    """Визначає режим команди за префіксом рядка, використовуючи dict.get()"""
    text = text.strip()
    
    if not text.startswith('.'):
        return None

    if text.startswith('.i+'):
        return "image_enhanced"
        
    modes = {
        '.i': "image",
        '.h': "helpful",
        '.t': "transcription",
        '.m': "history",
        '.c': "code",
        '.s': "summary",
        '.g': "grounding",
        '.?': "help"
    }

    return modes.get(text[:2], "default")


def extract_command_parameters(text, mode):
    """Extract context limit and command text from the input"""
    # Remove the mode prefix
    if mode == "default":
        text = text[1:].strip()  # Remove "."
    elif mode == "image_enhanced":
        # Handle special case for .i+ command
        if len(text) > 3 and text[3] == ' ':
            text = text[4:].strip()  # Remove ".i+ "
        else:
            text = ""  # Just the command with no parameters
    else:
        # Handle case where there's only the prefix (like ".c" with no additional text)
        if len(text) > 2 and text[2] == ' ':
            text = text[3:].strip()  # Remove ".x " where x is the mode letter
        else:
            text = ""  # Just the command with no parameters
    
    # Check for context limit
    context_limit = Config.CONTEXT_MESSAGE_LIMIT  # Default value
    
    if text:
        parts = text.split(maxsplit=1)
        first_part = parts[0] if parts else ""
        
        if first_part.isdigit():
            try:
                context_limit = int(first_part)
                if context_limit > 10000:
                    context_limit = 10000
                elif context_limit < 1:
                    context_limit = 1
                    
                # Remove the number from command text
                command_text = parts[1] if len(parts) > 1 else ""
                logger.info(f"Custom context limit set: {context_limit}")
            except ValueError:
                command_text = text
                logger.warning(f"Invalid context limit format: {first_part}, using default")
        else:
            command_text = text
    else:
        command_text = ""
    
    return context_limit, command_text

async def handle_text_mode(event, client, mode, context_limit, command_text):
    """Handle text-based AI modes with enhanced reply context handling"""
    # Get user info
    me = await client.get_me()
    my_info = await get_user_info(me)
    
    # Process reply if available
    reply_data = {}
    reply_message = None
    reply_context = []
    
    # Enhanced reply processing
    if getattr(event, 'reply_to_msg_id', None):
        reply_message = await event.get_reply_message()
        reply_data = await process_reply_message(reply_message)
        
        # Log that we're working with a reply
        logger.info(f"Processing reply to message: {reply_data.get('text', '')[:50]}...")
        
        # Get context around the reply
        reply_context = await get_conversation_context(reply_message, client, context_limit)
        logger.info(f"Got {len(reply_context)} messages for reply context")
        
        # If no command text was provided, note that we're using reply as main input
        if not command_text:
            logger.info("No command text provided, using reply content as main instruction")
    
    # Get conversation history
    conversation_history = await get_conversation_context(event, client, context_limit)
    logger.info(f"Got {len(conversation_history)} messages for context")
    
    # Build prompt and prepare content for AI
    prompt_text = await build_prompt(
        command_text, 
        reply_data, 
        conversation_history,
        reply_context,
        my_info,
        mode
    )
    
    logger.info(f"Final prompt length: {len(prompt_text)} characters")
    
    # Prepare content for AI (text and images)
    contents = [prompt_text]
    images_to_close = []
    temp_files_to_remove = []
    
    # Process images and voice messages if any
    await process_command_media(event, reply_message, contents, images_to_close, temp_files_to_remove)
    
    try:
        # Send thinking indicator and get AI response
        if command_text or reply_data or conversation_history:
            has_valid_input = command_text or (reply_data and reply_data.get('text')) or conversation_history
    
            if has_valid_input:
                thinking_message = await send_thinking_message(event, reply_message, command_text or "Reply", mode)
    
            # Get response based on mode - ensure correct function mapping
            mode_function_map = {
                "default": get_default_response,
                "helpful": get_helpful_response,
                "transcription": get_transcription_response,
                "code": get_code_response,
                "summary": get_summary_response,
                "history": get_history_summary,
                "grounding": get_grounded_response
            }
            
            # Get the appropriate function for the mode
            response_function = mode_function_map.get(mode, get_default_response)
            
            # Call the function
            ai_response = await response_function(contents, my_info)
            
            # Split and send large responses in chunks
            await send_chunked_response(ai_response, thinking_message, client, event)
        else:
            await event.delete()
            return
            
    finally:
        # Clean up resources
        await cleanup_resources(images_to_close, temp_files_to_remove)

async def handle_image_mode(event, client, prompt_text, enhance_prompt=False):
    """Handle AI image generation/editing mode"""
    try:
        # Get user info
        me = await client.get_me()
        my_info = await get_user_info(me)
        
        # Get the actual prompt text from command or reply
        final_prompt = prompt_text
        
        # If prompt is empty and there's a reply, use the reply text as the prompt
        if not final_prompt and getattr(event, 'reply_to_msg_id', None):
            reply_message = await event.get_reply_message()
            if reply_message:
                reply_text = getattr(reply_message, 'text', '') or getattr(reply_message, 'caption', '')
                if reply_text:
                    final_prompt = reply_text
                    logger.info(f"Using reply text as image prompt: {reply_text[:50]}...")
        
        # If still no prompt, use a default
        if not final_prompt:
            await event.reply("❌ Будь ласка, надайте текст промпту для генерації зображення.")
            return
            
        # Store the original prompt before refinement
        original_prompt = final_prompt
        logger.info(f"Original image generation prompt: {original_prompt[:100]}...")
        
        # Send thinking indicator
        thinking_message = await event.reply("🎨 Генерую зображення...")
        
        # Prepare contents for AI - using ONLY the final prompt text, not full context
        contents = [final_prompt]
        
        # Process reply if available to get source image for editing
        reply_message = None
        images_to_close = []
        temp_files_to_remove = []
        
        if getattr(event, 'reply_to_msg_id', None):
            reply_message = await event.get_reply_message()
            
            # Check if reply has an image for editing
            if getattr(reply_message, 'photo', None) or (hasattr(reply_message, 'sticker') and reply_message.sticker):
                file_path = await reply_message.download_media()
                if file_path:
                    img = await process_image(file_path)
                    if img:
                        contents.append(img)
                        images_to_close.append(img)
                        temp_files_to_remove.append(file_path)
                        logger.info(f"Source image for editing: {file_path}")
        
        try:
            # Get AI response with image generation
            result = await get_image_response(contents, my_info, enhance_prompt)
            
            # The refined prompt is the first element of contents after refinement
            refined_prompt = contents[0] if (enhance_prompt and contents) else original_prompt
            
            # Send the generated images and text response
            if result["images"]:
                for i, image_path in enumerate(result["images"]):
                    # Create a caption with both original and refined prompts
                    caption = ""
                    if i == 0:  # Only add this to the first image if multiple are generated
                        caption = f"🖼 <b>Згенероване зображення</b>\n\n"
                        
                        if enhance_prompt:
                            caption += f"📝 <b>Оригінальний запит:</b>\n<i>{original_prompt}</i>\n\n"
                            caption += f"✨ <b>Покращений запит:</b>\n<i>{refined_prompt}</i>\n\n"
                        else:
                            caption += f"📝 <b>Запит:</b>\n<i>{original_prompt}</i>\n\n"
                            
                        if result["text"]:
                            caption += f"<b>💬 Коментар AI:</b>\n{result['text']}"
                    
                    await client.send_file(
                        event.chat_id,
                        image_path,
                        caption=caption,
                        reply_to=event.reply_to_msg_id if i == 0 else None,
                        parse_mode="html"
                    )
                # Edit the thinking message to indicate completion
                await thinking_message.edit("✅ Генерація зображення завершена!")
            else:
                # No images were generated, send error message
                await thinking_message.edit(f"❌ {result['text'] or 'Не вдалося згенерувати зображення'}")
                
        finally:
            # Clean up resources
            await cleanup_resources(images_to_close, temp_files_to_remove)
            
            # Also clean up generated images after sending
            for image_path in result.get("images", []):
                try:
                    if os.path.exists(image_path):
                        os.remove(image_path)
                except Exception as e:
                    logger.warning(f"Could not remove generated image {image_path}: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error in image generation handler: {str(e)}")
        logger.exception(e)
        await event.reply("❌ Помилка при генерації зображення")

async def handle_history_mode(event, client, context_limit):
    try:
        # Get user info
        me = await client.get_me()
        my_info = await get_user_info(me)
        
        # Send thinking indicator
        thinking_message = await event.reply("📜 Створюю детальний підсумок історії чату...")
        
        # Get extended conversation history
        conversation_history = await get_conversation_context(event, client, context_limit)
        
        # DEBUG: Print the actual messages to log
        logger.info(f"Got {len(conversation_history)} messages for history summary")
        for i, msg in enumerate(conversation_history[:5]):  # Log the first 5 messages
            logger.info(f"Message {i+1}: {msg[:100]}...")
        
        if not conversation_history:
            await thinking_message.edit("❌ Історію чату не знайдено.")
            return
        
        # Create more explicit Ukrainian prompt
        prompt = f"""
### SYSTEM INSTRUCTION
Створи ДЕТАЛЬНИЙ хронологічний підсумок цієї історії чату.
НІКОЛИ не використовуй символ @ перед іменами людей.
Включи значущі повідомлення з мітками часу.
Відмічай основні теми розмови та ключові моменти.
Зверни увагу на важливі події, рішення та дії.
Напиши підсумок як неупереджений спостерігач.
Використовуй чітку структуру з хронологічним порядком.
Якщо повідомлення присутні, НЕ пиши "Немає історії чату для підсумовування".

### CHAT HISTORY TO SUMMARIZE ({len(conversation_history)} messages)
"""
        
        # Add the conversation history with clear formatting
        for i, msg in enumerate(conversation_history):
            prompt += f"{i+1}. {msg}\n"
            
        logger.info(f"Created history prompt with {len(conversation_history)} messages")
        
        # Call the AI directly
        contents = [prompt]
        ai_response = await get_history_summary(contents, my_info)
        
        # Double-check response isn't empty
        if not ai_response or ai_response.strip() == "Немає історії чату для підсумовування.":
            await thinking_message.edit("❌ Не вдалося створити підсумок. Спробуйте знову або використайте менший ліміт повідомлень.")
            return
            
        # Format response
        if not ai_response.strip().startswith("📜"):
            ai_response = "📜 Підсумок історії чату:\n\n" + ai_response
            
        await send_chunked_response(ai_response, thinking_message, client, event)
        
    except Exception as e:
        logger.error(f"Error in history mode handler: {str(e)}")
        logger.exception(e)
        await event.reply("❌ Помилка при створенні підсумку історії чату")

async def handle_grounding_mode(event, client, command_text):
    """Handle search-grounded responses with factual information and citations"""
    try:
        # Get user info
        me = await client.get_me()
        my_info = await get_user_info(me)
        
        # Get the actual search query from command or reply
        final_query = command_text
        
        # If query is empty and there's a reply, use the reply text as the query
        if not final_query and getattr(event, 'reply_to_msg_id', None):
            reply_message = await event.get_reply_message()
            if reply_message:
                reply_text = getattr(reply_message, 'text', '') or getattr(reply_message, 'caption', '')
                if reply_text:
                    final_query = reply_text
                    logger.info(f"Using reply text as search query: {reply_text[:50]}...")
        
        # If still no query, return an error
        if not final_query:
            await event.reply("❌ Будь ласка, надайте запит для пошуку інформації.")
            return
            
        logger.info(f"Final search query: {final_query[:100]}...")
        
        # Send thinking indicator
        thinking_message = await event.reply("🔍 Шукаю інформацію...")
        
        # Prepare prompt for search
        prompt = f"""
### SEARCH QUERY
{final_query}

### INSTRUCTIONS
- Find the most accurate and recent information for this query
- Format your answer in a clear, well-structured way
- Include relevant facts, figures, and dates if available
- Mention all sources used at the end of your response
- Keep your answer concise but comprehensive
- Use Ukrainian language in your response
"""
        
        # Get grounded response
        contents = [prompt]
        result = await get_grounded_response(contents, my_info)
        
        # Send the response with sources
        await send_chunked_response(result, thinking_message, client, event)
        
    except Exception as e:
        logger.error(f"Error in grounding mode handler: {str(e)}")
        logger.exception(e)
        await event.reply("❌ Помилка при пошуку інформації")

async def handle_help_mode(event):
    """Display help information about available commands"""
    try:
        help_message = """📋 **Доступні команди:**

🔹 **`.` + текст** - Стандартний режим відповіді
🔹 **`.h` + текст** - Детальна освітня відповідь
🔹 **`.t` + текст** - Транскрибування або виправлення тексту
🔹 **`.c` + текст** - Допомога з кодом та програмуванням
🔹 **`.i` + текст** - Генерація зображень за описом
🔹 **`.s` + текст** - Підсумовування вмісту
🔹 **`.g` + текст** - Пошук інформації з посиланнями на джерела
🔹 **`.m` + [число]** - Підсумок історії чату з часовими мітками
🔹 **`.?`** - Показати цю довідку

📝 **Додаткові функції:**
- Можна відповідати на повідомлення для контексту
- Додавайте число після команди для збільшення контексту (напр. `.h 10 текст`)
- Додавайте зображення до запитів для аналізу
- Відповідайте на голосові повідомлення для транскрибування

🔄 **Модель:** {model}
"""
        help_message = help_message.format(model=Config.GEMINI_MODEL)
        await event.reply(help_message)
        
    except Exception as e:
        logger.error(f"Error in help mode handler: {str(e)}")
        logger.exception(e)
        await event.reply("❌ Помилка при відображенні довідки")

async def send_thinking_message(event, reply_message, command_text, mode="default"):
    """Send a thinking indicator message with mode information"""
    # Mode-specific thinking indicators
    indicators = {
        "default": "⏳  Думаю...",
        "helpful": "🧠 Готую детальну відповідь...",
        "transcription": "🎤 Дістаю текст...",
        "code": "💻 Пишу код...",
        "summary": "📋 Підсумовую...",
        "grounding": "🔍 Шукаю інформацію..."
    }
    
    indicator = indicators.get(mode, "⏳ Processing...")
    
    if not command_text:
        await event.delete()
        
    if reply_message:
        return await reply_message.reply(indicator)
    else:
        return await event.reply(indicator)


async def process_reply_message(reply_message):
    """Process a reply message and extract relevant data with enhanced priority"""
    reply_data = {}
    
    if reply_message:
        text = getattr(reply_message, 'text', '')
        caption = getattr(reply_message, 'caption', '')
        
        if text:
            reply_data["text"] = text
        elif caption:
            reply_data["text"] = f"[Media з підписом]: {caption}"
        else:
            # Check for specific media types to provide better context
            if hasattr(reply_message, 'voice') and reply_message.voice:
                reply_data["text"] = "[Голосове повідомлення]"
                reply_data["media_type"] = "voice"
            elif hasattr(reply_message, 'photo') and reply_message.photo:
                reply_data["text"] = "[Фотографія]"
                reply_data["media_type"] = "photo"
            elif hasattr(reply_message, 'sticker') and reply_message.sticker:
                emoji = getattr(reply_message.sticker, 'emoji', '')
                reply_data["text"] = f"[Стікер{f' з емодзі {emoji}' if emoji else ''}]"
                reply_data["media_type"] = "sticker"
            else:
                reply_data["text"] = "[Media без підпису]"
        
        # Get more detailed information about the message
        sender = await reply_message.get_sender()
        reply_data["user_info"] = await get_user_info(sender)
        reply_data["chat_info"] = await get_chat_info(reply_message)
        reply_data["message_id"] = reply_message.id
        reply_data["date"] = reply_message.date.strftime("%Y-%m-%d %H:%M:%S") if hasattr(reply_message, 'date') else "Unknown"
    
    return reply_data

async def process_command_media(event, reply_message, contents, images_to_close, temp_files_to_remove):
    """Process and add media (images, stickers, and voice messages) from command and reply to contents"""
    # Add images from command message if any
    if getattr(event.message, 'photo', None):
        file_path = await event.download_media()
        if file_path:
            img = await process_image(file_path)
            if img:
                contents.append(img)
                images_to_close.append(img)
                temp_files_to_remove.append(file_path)
    
    # Add stickers from command message
    if hasattr(event.message, 'sticker') and event.message.sticker:
        file_path = await event.download_media()
        if file_path:
            img = await process_image(file_path)
            if img:
                contents.append(img)
                images_to_close.append(img)
                temp_files_to_remove.append(file_path)
                logger.info(f"Sticker processed from command: {file_path}")
    
    # Add voice message from command message if any
    if hasattr(event.message, 'voice') and event.message.voice:
        file_path = await event.download_media()
        if file_path:
            # Upload voice file to Gemini using client.files.upload
            try:
                voice_file = client.files.upload(file=file_path)
                contents.append(voice_file)
                # No need to close file objects like images, but we still need to clean up the temp file
                temp_files_to_remove.append(file_path)
                # Add instruction for voice processing
                contents.insert(0, "Transcribe and respond to this voice message")
                logger.info(f"Voice message uploaded from command: {file_path}")
            except Exception as e:
                logger.error(f"Error uploading voice file: {str(e)}")

    # Add media from reply message if any
    if reply_message:
        # Handle images in reply
        if getattr(reply_message, 'photo', None):
            file_path = await reply_message.download_media()
            if file_path:
                img = await process_image(file_path)
                if img:
                    contents.append(img)
                    images_to_close.append(img)
                    temp_files_to_remove.append(file_path)
        
        # Handle stickers in reply
        if hasattr(reply_message, 'sticker') and reply_message.sticker:
            file_path = await reply_message.download_media()
            if file_path:
                img = await process_image(file_path)
                if img:
                    contents.append(img)
                    images_to_close.append(img)
                    temp_files_to_remove.append(file_path)
                    logger.info(f"Sticker processed from reply: {file_path}")
        
        # Handle voice messages in reply
        if hasattr(reply_message, 'voice') and reply_message.voice:
            file_path = await reply_message.download_media()
            if file_path:
                try:
                    voice_file = client.files.upload(file=file_path)
                    contents.append(voice_file)
                    temp_files_to_remove.append(file_path)
                    # Add instruction for voice processing if it's not already there
                    if not any(isinstance(c, str) and "voice message" in c.lower() for c in contents):
                        contents.insert(0, "Transcribe and respond to this voice message")
                    logger.info(f"Voice message uploaded from reply: {file_path}")
                except Exception as e:
                    logger.error(f"Error uploading reply voice file: {str(e)}")

async def send_chunked_response(ai_response, thinking_message, client, original_event):
    """Split and send large responses in multiple messages if needed"""
    # Maximum message length (Telegram limit is around 4096, using less to be safe)
    max_length = 4000
    header = f"**🤖 {Config.GEMINI_MODEL}**\n"
    
    if len(ai_response) <= max_length:
        # Response fits in one message
        await thinking_message.edit(f"{header}{ai_response}")
        return
        
    # Response is too large, split into chunks
    chunks = []
    
    # Improved chunking algorithm that preserves content better
    remaining_text = ai_response
    while remaining_text:
        # If remaining text fits in a chunk, add it and break
        if len(remaining_text) <= max_length:
            chunks.append(remaining_text)
            break
            
        # Find a good split point (paragraph break, sentence break, or word break)
        # Look for paragraph break within limits
        split_pos = remaining_text[:max_length].rfind("\n\n")
        
        # If no paragraph break, try sentence break
        if split_pos == -1 or split_pos < max_length // 2:
            # Look for sentence break (handling multiple punctuation marks)
            for punct in [". ", "! ", "? ", ".\n", "!\n", "?\n"]:
                pos = remaining_text[:max_length].rfind(punct)
                if pos > max_length // 2:  # Only use if at least halfway through the chunk
                    split_pos = pos + len(punct) - 1  # Include the punctuation but not the space
                    break
                    
        # If no good sentence break, split at a word boundary
        if split_pos == -1 or split_pos < max_length // 2:
            split_pos = remaining_text[:max_length].rfind(" ")
            if split_pos == -1:  # No spaces found, force split
                split_pos = max_length - 1
        
        # Add chunk and continue with remaining text
        chunks.append(remaining_text[:split_pos + 1])
        remaining_text = remaining_text[split_pos + 1:].strip()
    
    # Log the chunking results
    logger.info(f"Split response into {len(chunks)} chunks (total length: {len(ai_response)} chars)")
    
    # First chunk replaces thinking message
    first_chunk = f"{header}{chunks[0]}"
    if len(chunks) > 1:
        first_chunk += f"\n\n(1/{len(chunks)})"
    await thinking_message.edit(first_chunk)
    
    # Send remaining chunks as new messages
    for i, chunk in enumerate(chunks[1:], 2):
        chunk_text = f"{chunk}\n\n({i}/{len(chunks)})"
        try:
            await original_event.respond(chunk_text)
            # Add a small delay between messages to avoid rate limiting
            import asyncio
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Error sending chunk {i}/{len(chunks)}: {str(e)}")
            # Try to send error message
            try:
                await original_event.respond(f"❌ Помилка при відправці частини відповіді ({i}/{len(chunks)})")
            except:
                pass

async def handle_error(event):
    """Handle errors in command processing"""
    if hasattr(event, 'reply_to_msg_id'):
        await event.reply("❌ Виникла помилка під час обробки запиту.")
    else:
        await event.delete()