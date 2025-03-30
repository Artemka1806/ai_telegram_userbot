from google import genai
from google.genai import types
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch
from src.config import Config
from src.utils.logger import logger
from src.ai.prompts import get_system_instruction
from PIL import Image
from io import BytesIO
import os
import uuid

# Initialize Gemini client
client = genai.Client(api_key=Config.GEMINI_API_KEY)

async def get_default_response(contents, user_info):
    """Get default response from Google Gemini API."""
    return await _get_gemini_response(contents, user_info, "default")

async def get_helpful_response(contents, user_info):
    """Get helpful, detailed response from Google Gemini API."""
    return await _get_gemini_response(contents, user_info, "helpful")

async def get_transcription_response(contents, user_info):
    """Get transcription and grammar improvement response."""
    return await _get_gemini_response(contents, user_info, "transcription")

async def get_code_response(contents, user_info):
    """Get code-focused response from Google Gemini API."""
    return await _get_gemini_response(contents, user_info, "code")

async def get_summary_response(contents, user_info):
    """Get summarization response from Google Gemini API."""
    return await _get_gemini_response(contents, user_info, "summary")

async def get_history_summary(contents, user_info):
    """Get chat history summary from Google Gemini API."""
    return await _get_gemini_response(contents, user_info, "history")


async def get_grounded_response(contents, user_info):
    """Get factual, search-grounded response from Google Gemini API."""
    try:
        system_instruction = get_system_instruction(user_info, "grounding")
        
        # Log request info
        logger.info(f"Sending grounded search request to Gemini model: {Config.GEMINI_MODEL}")
        if isinstance(contents, list) and len(contents) > 0:
            if isinstance(contents[0], str):
                text_preview = contents[0][:100] + "..." if len(contents[0]) > 100 else contents[0]
                logger.info(f"Text content preview: {text_preview}")
                logger.info(f"Total content parts: {len(contents)}")
        
        # Create search tool
        google_search_tool = Tool(
            google_search=GoogleSearch()
        )
        
        # Generate content with search grounding
        response = client.models.generate_content(
            model=Config.GEMINI_MODEL,
            contents=contents,
            config=GenerateContentConfig(
                system_instruction=system_instruction,
                tools=[google_search_tool],
                response_modalities=["TEXT"],
                max_output_tokens=Config.MAX_OUTPUT_TOKENS,
                temperature=Config.TEMPERATURE,
                top_p=Config.TOP_P,
                top_k=Config.TOP_K
            )
        )
        
        # Extract the response text
        import re
        response_text = response.text
        
        # PHASE 1: Minimal cleaning - only remove obvious citation markers
        # Remove citation markers like [1], [2]
        response_text = re.sub(r'\[\d+\]', '', response_text)
        
        # PHASE 2: Extract proper source information from grounding metadata
        sources = []
        seen_uris = set()
        
        if (hasattr(response, 'candidates') and 
            response.candidates and 
            hasattr(response.candidates[0], 'grounding_metadata') and 
            response.candidates[0].grounding_metadata):
            
            grounding_metadata = response.candidates[0].grounding_metadata
            
            if hasattr(grounding_metadata, 'grounding_chunks') and grounding_metadata.grounding_chunks:
                for chunk in grounding_metadata.grounding_chunks:
                    if hasattr(chunk, 'web') and chunk.web:
                        uri = getattr(chunk.web, 'uri', "")
                        title = getattr(chunk.web, 'title', "")
                        
                        # Skip if URI is missing or already seen
                        if not uri or uri in seen_uris:
                            continue
                            
                        seen_uris.add(uri)
                        
                        # Clean and improve title
                        if not title or title.strip().lower() in ['', 'untitled', 'none']:
                            # Extract domain name as title if missing
                            domain_match = re.search(r'https?://(?:www\.)?([^/]+)', uri)
                            if domain_match:
                                domain = domain_match.group(1)
                                title = domain.split('.')[0].capitalize()
                        else:
                            # Remove common suffixes from titles
                            title = re.sub(r'\s*[-–|]\s.*$', '', title)
                            title = re.sub(r'\s*\|.*$', '', title)
                            # Clean up whitespace
                            title = re.sub(r'\s+', ' ', title).strip()
                        
                        sources.append({"title": title, "uri": uri})
            
            # Track search queries used
            if hasattr(grounding_metadata, 'web_search_queries') and grounding_metadata.web_search_queries:
                search_query = grounding_metadata.web_search_queries[0]
                logger.info(f"Search query used: {search_query}")
        
        # PHASE 3: Add a clean, formatted sources section
        
        # Add the structured sources list if any were found
        if sources:
            response_text += "\n\n📚 **Джерела інформації:**\n"
            for i, source in enumerate(sources, 1):
                title = source['title']
                if len(title) > 60:
                    title = title[:57] + "..."
                response_text += f"{i}. [{title}]({source['uri']})\n"
            
            # Include search query if available
            if hasattr(grounding_metadata, 'web_search_queries') and grounding_metadata.web_search_queries:
                search_query = grounding_metadata.web_search_queries[0]
                response_text += f"\n\n🔍 **Пошуковий запит:**\n`{search_query}`"
        
        return response_text
        
    except Exception as e:
        logger.error(f"Error in get_grounded_response: {str(e)}")
        logger.exception(e)
        return f"❌ Помилка при отриманні відповіді: {str(e)}"
        
    except Exception as e:
        logger.error(f"Error in get_grounded_response: {str(e)}")
        logger.exception(e)
        return f"❌ Помилка при отриманні відповіді: {str(e)}"

async def _get_gemini_response(contents, user_info, mode="default"):
    """Base function to get response from Google Gemini API with specified mode."""
    try:
        system_instruction = get_system_instruction(user_info, mode)
        
        # Log request info
        logger.info(f"Sending {mode} mode request to Gemini model: {Config.GEMINI_MODEL}")
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
        logger.error(f"Error in get_gemini_response ({mode} mode): {str(e)}")
        return f"Error getting AI response in {mode} mode: {str(e)}"

async def refine_image_prompt(prompt, user_info):
    """Refine and enhance the image prompt to improve generation quality and translate to English."""
    try:
        refinement_instruction = f"""
Improve this prompt to generate the best possible image. Make it clear, detailed, and effective. 
Then, translate it into English. 
Provide only the final, optimized prompt without explanations.
Ensure all details are expressed exclusively in English.
Answer only with the optimized prompt in English.
Prompt:
"{prompt}"
"""
        # Log refinement request
        logger.info(f"Refining image prompt: {prompt[:50]}...")
        
        # Generate refined prompt using the text model
        response = client.models.generate_content(
            model=Config.GEMINI_MODEL,
            contents=[refinement_instruction],
            config=types.GenerateContentConfig(
                system_instruction=get_system_instruction(user_info, "default"),
                max_output_tokens=1000,
                temperature=0.4,  # Lower temperature for more focused refinement
            )
        )
        
        refined_prompt = response.text.strip()
        logger.info(f"Original prompt: {prompt[:50]}...")
        logger.info(f"Refined prompt: {refined_prompt[:50]}...")
        
        return refined_prompt
    except Exception as e:
        logger.error(f"Error refining image prompt: {str(e)}")
        logger.exception(e)
        # Return the original prompt if refinement fails
        return prompt

async def get_image_response(contents, user_info, enhance_prompt=False):
    """Get image generation/editing response from Google Gemini API."""
    try:
        # Extract the text prompt from contents
        text_prompt = ""
        if isinstance(contents, list) and len(contents) > 0 and isinstance(contents[0], str):
            text_prompt = contents[0]
        
        # Refine the prompt only when enhance_prompt is True
        if enhance_prompt:
            refined_prompt = await refine_image_prompt(text_prompt, user_info)
            
            # Replace the original prompt with the refined one
            if isinstance(contents, list) and len(contents) > 0 and isinstance(contents[0], str):
                contents[0] = refined_prompt
            
            logger.info(f"Enhanced prompt: {refined_prompt[:100]}...")
        
        # Log request info
        logger.info(f"Sending image generation request to Gemini model: {Config.GEMINI_IMAGE_MODEL}")
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
        
        # Check if response has valid structure before processing
        if (hasattr(response, 'candidates') and 
            response.candidates and 
            hasattr(response.candidates[0], 'content') and
            response.candidates[0].content and
            hasattr(response.candidates[0].content, 'parts')):
            
            # Extract text and images from response
            for part in response.candidates[0].content.parts:
                if part.text is not None:
                    result["text"] += part.text
                elif part.inline_data is not None:
                    # Save image to temporary file
                    temp_dir = Config.TEMP_IMAGES_DIR
                    os.makedirs(temp_dir, exist_ok=True)
                    
                    # Generate unique filename
                    image_path = os.path.join(temp_dir, f"generated_{uuid.uuid4().hex}.png")
                    
                    # Save the image
                    image = Image.open(BytesIO(part.inline_data.data))
                    image.save(image_path)
                    result["images"].append(image_path)
                    
                    logger.info(f"Image generated and saved to {image_path}")
        else:
            logger.warning("Received incomplete or invalid response structure from Gemini API")
            result["text"] = "Не вдалося згенерувати зображення: API повернув неповні дані."
        
        return result
        
    except Exception as e:
        logger.error(f"Error in get_ai_image_response: {str(e)}")
        logger.exception(e)
        return {"text": f"Error generating image: {str(e)}", "images": []}
    
async def get_file_analysis(contents, user_info, file_obj=None):
    """Analyze a file using Google Gemini API"""
    try:
        system_instruction = get_system_instruction(user_info, "helpful")
        
        # Log request info
        logger.info(f"Sending file analysis request to Gemini model: {Config.GEMINI_MODEL}")
        
        # Prepare final contents list
        final_contents = []
        
        # Add file to contents if provided
        if file_obj:
            final_contents.append(file_obj)
            logger.info(f"Added file to analysis request")
        
        # Add text prompt (should be the instruction on what to do with the file)
        if isinstance(contents, list) and contents and isinstance(contents[0], str):
            prompt = contents[0]
            # If prompt is empty or too generic, use a default one
            if not prompt or prompt.strip() in ["", "analyze", "analyze this"]:
                prompt = """Analyze this document thoroughly and provide a detailed summary including:
1. Main topics and key points
2. Important facts and figures
3. Structure and organization
4. Conclusions or recommendations (if any)
5. Any notable issues or inconsistencies 

Present your analysis in a well-structured format with clear sections."""

            final_contents.append(prompt)
            text_preview = prompt[:100] + "..." if len(prompt) > 100 else prompt
            logger.info(f"Analysis instruction: {text_preview}")

        # Generate content
        response = client.models.generate_content(
            model=Config.GEMINI_MODEL,
            contents=final_contents,
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
        logger.error(f"Error in get_file_analysis: {str(e)}")
        logger.exception(e)
        return f"❌ Помилка при аналізі файлу: {str(e)}"