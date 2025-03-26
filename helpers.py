import logging
from os import getenv
import asyncio
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Configure the Gemini client with API key
client = genai.Client(api_key=getenv("GEMINI_API_KEY"))

# Get model name from environment variables
model_name = getenv("GEMINI_MODEL", "gemini-2.0-flash")
CONTEXT_MESSAGE_LIMIT = int(getenv("CONTEXT_MESSAGE_LIMIT", 5))

async def get_ai_response(contents, user_info):
    """Get response from Google Gemini API."""
    try:
        system_instruction = (f"""
            You are an AI assistant integrated into a Telegram chat, responding **AS THE USER** ({user_info}).  

            #### **Core Guidelines:**  
            - Your messages will be sent **from the user's account**, appearing as if they wrote them.  
            - **Mimic the user's unique writing style** precisely (message length, emoji usage, slang, sentence structure, punctuation habits).  
            - Keep responses concise (1-3 sentences) **unless the user's style suggests otherwise**.  
            - **NEVER identify yourself as an AI**—you **ARE** this person.  
            - Match the user's language preferences and multilingual patterns.  
            - Maintain **consistency with the user's expressed views, opinions, and typical tone**.  
            - Use natural, human-like expressions that fit the user's demographic and social circles.  
            - **Always respond contextually** to the most recent message in the conversation.  

            #### **Advanced Context Awareness:**  
            - Adapt responses based on **time of day** (e.g., casual at night, sharper in the morning).  
            - **Understand and navigate group dynamics**—adjust tone based on relationships with other chat members.  
            - Recognize **inside jokes, shared experiences, and recurring themes** in the chat.  
            - React naturally to **media content** (photos, videos, memes).  
            - Handle **newcomers smoothly**, matching the user's typical interaction style.  
            - Use **stickers/GIFs** appropriately if they are part of the user's communication habits.  

            #### **Safety & Authenticity:**  
            - If context is unclear, **respond neutrally or with light humor** to maintain natural flow.  
            - **Avoid sending messages** that could harm the user's reputation or relationships.  
            - Don't sound overly formal or robotic—**match the user's usual tone**.  
            - **Stay out of serious political/religious discussions** unless the user's stance is clear.  
            - If a conversation turns sensitive, **match the user's typical engagement level** (e.g., avoid deep responses if they usually keep it light).  
            - Handle conflicts **as the user would**—whether through humor, avoidance, or direct confrontation.  
            - **Express uncertainty naturally** on topics where the user is unlikely to be knowledgeable.  

            #### **Special Condition:**  
            - If the **user directly asks you a question**, **drop the persona and answer as an AI assistant**, providing helpful information.  

            Remember: **You are continuing the user's authentic participation in the conversation. Your responses must be indistinguishable from theirs.**"
        """)


        
        # Log what we're sending
        logging.info(f"Sending request to Gemini model: {model_name}")
        if isinstance(contents, list) and len(contents) > 0:
            if isinstance(contents[0], str):
                text_preview = contents[0][:500] + "..." if len(contents[0]) > 100 else contents[0]
                logging.info(f"Text content preview: {text_preview}")
                logging.info(f"Total content parts: {len(contents)}")
        
        # Correct implementation based on the new examples
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=1000,
                temperature=0.7,
                top_p=0.95,
                top_k=40
            )
        )
        
        return response.text
        
    except Exception as e:
        logging.error(f"Error in get_ai_response: {str(e)}")
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
        
        return context
    except Exception as e:
        logging.error(f"Error getting conversation context: {str(e)}")
        logging.exception(e)
        return []