import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    WEBULL_ACCESS_TOKEN = os.getenv("WEBULL_ACCESS_TOKEN")
    # FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY") # Deprecated
    # MASSIVE_API_KEY = os.getenv("MASSIVE_API_KEY") # Deprecated
    
    DB_PATH = os.getenv("DB_PATH", "bot.db")
    # Optional: ID of the group to send all updates to
    # Can be a single ID or comma-separated list of IDs
    TELEGRAM_GROUP_ID_RAW = os.getenv("TELEGRAM_GROUP_ID", "")
    TELEGRAM_GROUP_IDS = [x.strip() for x in TELEGRAM_GROUP_ID_RAW.split(',') if x.strip()]
    # Backward compatibility
    TELEGRAM_GROUP_ID = TELEGRAM_GROUP_IDS[0] if TELEGRAM_GROUP_IDS else None
    
    # Optional: Only these users can control the bot
    ADMIN_USER_ID_RAW = os.getenv("ADMIN_USER_ID", "")
    ADMIN_USER_IDS = [x.strip() for x in ADMIN_USER_ID_RAW.split(',') if x.strip()]
    # Backward compatibility (first admin or None)
    ADMIN_USER_ID = ADMIN_USER_IDS[0] if ADMIN_USER_IDS else None
    
    # Postgres Database Config
    POSTGRES_DB = os.getenv("POSTGRES_DB", "telegram_auction")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "auction_user")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

    @classmethod
    def validate(cls):
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is not set")
        if not cls.WEBULL_ACCESS_TOKEN:
            raise ValueError("WEBULL_ACCESS_TOKEN is not set")
