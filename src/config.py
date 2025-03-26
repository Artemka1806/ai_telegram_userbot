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
    
    # App configuration
    CONTEXT_MESSAGE_LIMIT = int(os.getenv("CONTEXT_MESSAGE_LIMIT", 5))
    COMMAND_PREFIXES = [".", ".ші", ".аі", ".ai", ".ии", ".gpt", ".гпт", ".gem"]
    
    # AI configuration
    MAX_OUTPUT_TOKENS = 1000
    TEMPERATURE = 0.7
    TOP_P = 0.95
    TOP_K = 40