from google import genai
from google.genai import types
from src.config import Config
from src.utils.logger import logger
from src.ai.prompts import get_system_instruction

# Initialize Gemini client
client = genai.Client(api_key=Config.GEMINI_API_KEY)

async def get_ai_response(contents, user_info):
    """Get response from Google Gemini API."""
    try:
        system_instruction = get_system_instruction(user_info)
        
        # Log request info
        logger.info(f"Sending request to Gemini model: {Config.GEMINI_MODEL}")
        if isinstance(contents, list) and len(contents) > 0:
            if isinstance(contents[0], str):
                text_preview = contents[0][:100] + "..." if len(contents[0]) > 100 else contents[0]
                logger.info(f"Text content preview: {text_preview}")
                logger.info(f"Total content parts: {len(contents)}")
        
        # Generate content
        response = client.models.generate_content(
            model=Config.GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=Config.MAX_OUTPUT_TOKENS,
                temperature=Config.TEMPERATURE,
                top_p=Config.TOP_P,
                top_k=Config.TOP_K
            )
        )
        
        return response.text
        
    except Exception as e:
        logger.error(f"Error in get_ai_response: {str(e)}")
        return f"Error getting AI response: {str(e)}"