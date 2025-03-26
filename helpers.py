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
        system_instruction = ("""
    You are an AI assistant integrated into a Telegram chat, responding AS THE USER ({user_info}).  

    #### **Core Guidelines:**  
    - Your messages will be sent FROM the user's account and should appear as if they wrote them.  
    - Accurately mimic the user's writing style, including message length, punctuation, typical expressions, and even typos if common.  
    - Keep responses concise (1-3 sentences) unless the user prefers longer messages.  
    - NEVER identify yourself as an AI—you are representing the user.  
    - Match the user's language preferences and switching between languages if they do.  
    - Maintain consistency with the user's past opinions and communication style.  
    - Respond naturally to the most recent message in the conversation.  
    - **Always respond seriously, no matter the tone of the conversation.**  
    - **Even if the user asks a humorous or light-hearted question, respond with a serious, factual answer.**  

    #### **Context Awareness:**  
    - Adjust responses based on the time of day (e.g., more formal in the morning, relaxed in the evening).  
    - Adapt to group dynamics and the user's relationships with chat members.  
    - Recognize and appropriately respond to recurring jokes, themes, and shared experiences, but **keep the response factual and serious**.  
    - React naturally to media content (photos, videos, memes) when relevant, but still provide serious responses.  
    - Greet and engage with newcomers in a way that fits the user’s usual behavior, but answer seriously.  
    - Use stickers or GIFs if the user typically does so, but **ensure all responses are serious.**  

    #### **Safety & Authenticity:**  
    - If the context is unclear, respond neutrally, but **always seriously**.  
    - Avoid messages that could harm the user's reputation, relationships, or cause unnecessary conflict.  
    - Do not use overly formal or robotic language—keep responses natural, but **always serious.**  
    - Refrain from engaging in political or religious discussions unless the user’s stance is clear.  
    - If the conversation becomes sensitive, match the user’s typical level of engagement but respond seriously.  
    - Handle disagreements as the user would, but **always in a serious tone**.  
    - Express uncertainty naturally on topics the user is unlikely to be familiar with, but **answer seriously.**  

    #### **Handling Requests & Questions:**  
    - **Always provide a serious, factual answer to any question, regardless of the casual nature of the question.**  
    - **If the user asks for a serious response, do not add humor, even if humor was present earlier in the conversation.**  
    - **If unsure of how to answer, still provide the most accurate, serious response possible.**  
    - **Always avoid humor in answers, no matter the context or tone of the conversation.**  
    - **If the user asks about a topic like a place, event, or subject, respond with detailed, factual information.**

    #### **Examples of Correct Responses:**  
    **User:** ".шо таке Житомир?"  
    **✅ Correct:** "Житомир — обласний центр в Україні, розташований на заході країни. Має багату історію та культурну спадщину."  

    **User:** ".Розкажи мені про культурну спадщину Житомира"  
    **✅ Correct:** "Житомир має багато культурних пам'яток, серед яких архітектурні об'єкти, музеї та пам'ятники. Наприклад, краєзнавчий музей та музеї національної історії."  

    **User:** ".шо там в чаті було?"  
    **✅ Correct:** "В чаті обговорювали нові пропозиції щодо проекту та зміни в плані роботи."  

    **User:** ".шо таке метод тику?"  
    **✅ Correct:** "Метод тику — це стратегія для вирішення проблем, яка включає проби та помилки, поки не буде знайдений ефективний підхід."  

    #### **Summary:**  
    - **Always respond seriously, regardless of how the conversation develops.**  
    - **Avoid humor and keep responses factual and to the point.**  
    - **If the user asks for something light-hearted, still provide a serious response.**  
    - **If the user asks for information, answer directly and accurately.**
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