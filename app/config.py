# import os
# from pydantic_settings import BaseSettings
# from functools import lru_cache

# class Settings(BaseSettings):
#     APP_NAME: str = "Telegram Salla Subs"
#     DATABASE_URL: str
#     TELEGRAM_TOKEN: str
#     SALLA_SECRET: str
#     APP_BASE_URL: str
#     ADMIN_USERNAME: str = "admin"
#     ADMIN_PASSWORD_HASH: str  # Use a tool to generate this, e.g. bcrypt or simple sha256 for this demo if needed, ideally bcrypt
#     SECRET_KEY: str = "supersecretkeychangeinproduction" # For session signing

#     class Config:
#         env_file = "/opt/telegram_salla_app/.env"

# @lru_cache()
# def get_settings():
#     return Settings()


from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    APP_NAME: str = "Telegram Salla Subs"
    DATABASE_URL: str
    TELEGRAM_TOKEN: str
    SALLA_SECRET: str
    APP_BASE_URL: str
    CHANNEL_ID: str = "-1001234567890" # Default placeholder, should be in env
    TELEGRAM_GROUP_ID: str = ""  # Comma-separated group IDs
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD_HASH: str
    SECRET_KEY: str = "supersecretkeychangeinproduction"
    SUBSCRIPTION_LINK: str = "https://salla.sa/investly11"
    
    def get_group_ids(self) -> list:
        """Parse comma-separated group IDs into a list."""
        if not self.TELEGRAM_GROUP_ID:
            return []
        return [gid.strip() for gid in self.TELEGRAM_GROUP_ID.split(',') if gid.strip()]

    class Config:
        env_file = BASE_DIR / ".env"
        extra = 'ignore'  # Allow extra environment variables

@lru_cache()
def get_settings():
    return Settings()
