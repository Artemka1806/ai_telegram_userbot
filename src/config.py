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
    
       # Command prefixes for different modes
    DEFAULT_PREFIX = "."
    HELPFUL_PREFIX = ".h"
    TRANSCRIPTION_PREFIX = ".t"
    IMAGE_PREFIX = ".i"
    HISTORY_PREFIX = ".m"
    CODE_PREFIX = ".c"
    SUMMARY_PREFIX = ".s"
    HELP_PREFIX = ".?"
    GROUNDING_PREFIX = ".g"
    FILE_PREFIX = ".f"
    
    # All command prefixes
    COMMAND_PREFIXES = [
        DEFAULT_PREFIX, 
        HELPFUL_PREFIX, 
        TRANSCRIPTION_PREFIX, 
        IMAGE_PREFIX, 
        HISTORY_PREFIX,
        CODE_PREFIX,
        SUMMARY_PREFIX,
        GROUNDING_PREFIX,
        HELP_PREFIX,
        FILE_PREFIX,
        # Legacy prefixes for compatibility
        ".ші", ".аі", ".ai", ".ии", ".gpt", ".гпт", ".gem"
    ]
    
    # AI configuration
    MAX_OUTPUT_TOKENS = 10000000
    TEMPERATURE = 0.7
    TOP_P = 0.95
    TOP_K = 40
    
    # Temp directories
    TEMP_DIR = "temp"
    TEMP_IMAGES_DIR = os.path.join(TEMP_DIR, "images")