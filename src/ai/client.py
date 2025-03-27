from google import genai
from google.genai import types
from src.config import Config
from src.utils.logger import logger
from src.ai.prompts import get_system_instruction
from PIL import Image
from io import BytesIO
import os
import uuid

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

async def get_ai_image_response(contents, user_info):
    """Get image generation/editing response from Google Gemini API."""
    try:
        # Log request info
        logger.info(f"Sending image generation request to Gemini model: {Config.GEMINI_IMAGE_MODEL}")
        if isinstance(contents, list) and len(contents) > 0:
            if isinstance(contents[0], str):
                text_preview = contents[0][:100] + "..." if len(contents[0]) > 100 else contents[0]
                logger.info(f"Text prompt preview: {text_preview}")
                logger.info(f"Total content parts: {len(contents)}")
        
        # Generate content with image modality using the dedicated image model
        response = client.models.generate_content(
            model=Config.GEMINI_IMAGE_MODEL,  # Use the image-specific model
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=['Text', 'Image'],
                max_output_tokens=Config.MAX_OUTPUT_TOKENS,
                temperature=Config.TEMPERATURE,
                top_p=Config.TOP_P,
                top_k=Config.TOP_K
            )
        )
        
        # Process response to extract text and images
        result = {
            "text": "",
            "images": []
        }
        
        # Extract text and images from response
        for part in response.candidates[0].content.parts:
            if part.text is not None:
                result["text"] += part.text
            elif part.inline_data is not None:
                # Save image to temporary file
                temp_dir = "temp_images"
                os.makedirs(temp_dir, exist_ok=True)
                
                # Generate unique filename
                image_path = os.path.join(temp_dir, f"generated_{uuid.uuid4().hex}.png")
                
                # Save the image
                image = Image.open(BytesIO(part.inline_data.data))
                image.save(image_path)
                result["images"].append(image_path)
                
                logger.info(f"Image generated and saved to {image_path}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error in get_ai_image_response: {str(e)}")
        logger.exception(e)
        return {"text": f"Error generating image: {str(e)}", "images": []}
