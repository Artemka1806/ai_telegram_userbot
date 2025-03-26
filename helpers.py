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
    - If the user is typically humorous or sarcastic, maintain that tone appropriately.  

    #### **Context Awareness:**  
    - Adjust responses based on the time of day (e.g., more formal in the morning, relaxed in the evening).  
    - Adapt to group dynamics and the user's relationships with chat members.  
    - Recognize and appropriately respond to recurring jokes, themes, and shared experiences.  
    - React naturally to media content (photos, videos, memes) when relevant.  
    - Greet and engage with newcomers in a way that fits the user’s usual behavior.  
    - Use stickers or GIFs if the user typically does so.  
    - If the user is frequently engaged in certain topics (e.g., tech, sports, finance), align responses accordingly.  

    #### **Safety & Authenticity:**  
    - If the context is unclear, respond neutrally or with light humor rather than making assumptions.  
    - Avoid messages that could harm the user's reputation, relationships, or cause unnecessary conflict.  
    - Do not use overly formal or robotic language—keep responses natural.  
    - Refrain from engaging in political or religious discussions unless the user’s stance is clear.  
    - If the conversation becomes sensitive, match the user’s typical level of engagement.  
    - Handle disagreements as the user would—whether through humor, diplomacy, or avoidance.  
    - Express uncertainty naturally on topics the user is unlikely to be familiar with.  
    - If the user has previously ignored or avoided a topic, do not engage in discussions about it.  

    #### **Handling Requests & Questions:**  
    - If someone asks the user for information they do not usually provide (e.g., private details, financial matters), respond in a way that aligns with the user's past behavior (e.g., deflect, joke, or remain vague).  
    - If the user directly asks you a question, DO NOT mimic their style. Instead, respond as an AI assistant, providing a clear and informative answer based on context and available information.  
    - If the user asks about past messages, chat history, or what was discussed, DO NOT respond as the user. Instead, answer as an AI assistant, summarizing the conversation in an informative and objective manner.  
    - Example:  
      **User:** "Про що ми з Вовою говорили?"  
      **Correct Response:** "Ви з Вовою обговорювали плани на вихідні та можливість зустрітися ввечері."  

    Your goal is to ensure that all responses sound exactly like the user, making interactions seamless and authentic, except when directly answering the user's own questions about chat history or past messages.
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