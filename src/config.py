import os
import json
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
    
    # Auto-response configuration
    AUTO_RESPONSE_ENABLED = os.getenv("AUTO_RESPONSE_ENABLED", "true").lower() == "true"
    AUTO_RESPONSE_CONTEXT_LIMIT = int(os.getenv("AUTO_RESPONSE_CONTEXT_LIMIT", 100))
    AUTO_RESPONSE_CHATS_FILE = os.path.join("temp", "auto_response_chats.json")
    
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
    
    @staticmethod
    def get_auto_response_chats():
        """Get the list of chat IDs where auto-response is enabled"""
        try:
            if os.path.exists(Config.AUTO_RESPONSE_CHATS_FILE):
                with open(Config.AUTO_RESPONSE_CHATS_FILE, 'r') as f:
                    return json.load(f)
            else:
                return []
        except Exception:
            return []
    
    @staticmethod
    def save_auto_response_chats(chat_ids):
        """Save the list of chat IDs where auto-response is enabled"""
        os.makedirs(os.path.dirname(Config.AUTO_RESPONSE_CHATS_FILE), exist_ok=True)
        with open(Config.AUTO_RESPONSE_CHATS_FILE, 'w') as f:
            json.dump(chat_ids, f)