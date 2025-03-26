from src.telegram.client import create_client
from src.utils.logger import logger

def main():
    """Entry point for the application"""
    client = create_client()
    
    client.start()
    logger.info("Userbot is running and listening to your messages...")
    client.run_until_disconnected()

if __name__ == "__main__":
    main()