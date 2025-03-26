import os
from PIL import Image
from src.utils.logger import logger

async def process_image(file_path):
    """Process an image for Gemini API using PIL"""
    try:
        return Image.open(file_path)
    except Exception as e:
        logger.error(f"Error processing image {file_path}: {str(e)}")
        return None

async def cleanup_resources(images=None, files=None):
    """Clean up resources after API calls"""
    # Close images
    if images:
        for img in images:
            try:
                if hasattr(img, 'close'):
                    img.close()
            except Exception as e:
                logger.warning(f"Error closing image: {str(e)}")
    
    # Remove temporary files
    if files:
        # Small delay to ensure resources aren't in use
        import time
        time.sleep(0.1)
        
        for file_path in files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.warning(f"Could not remove file {file_path}: {str(e)}")