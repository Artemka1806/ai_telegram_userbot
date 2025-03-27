import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram configuration
    TG_API_ID = int(os.getenv("TG_API_ID"))
    TG_API_HASH = os.getenv("TG_API_HASH")
    TG_SESSION_NAME = os.getenv("TG_SESSION_NAME")
    
    # Gemini configuration
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.0-flash-exp-image-generation")
    
    # App configuration
    CONTEXT_MESSAGE_LIMIT = int(os.getenv("CONTEXT_MESSAGE_LIMIT", 5))
    COMMAND_PREFIXES = [".", ".ші", ".аі", ".ai", ".ии", ".gpt", ".гпт", ".gem"]
    IMAGE_COMMAND_PREFIXES = ["img", "image"]
    
    # AI configuration
    MAX_OUTPUT_TOKENS = 10000000
    TEMPERATURE = 0.7
    TOP_P = 0.95
    TOP_K = 40
    
    # Temp directories
    TEMP_DIR = "temp"
    TEMP_IMAGES_DIR = os.path.join(TEMP_DIR, "images")