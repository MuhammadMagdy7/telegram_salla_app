import sys
import os
import asyncio
import logging

# Setup Logger
logger = logging.getLogger(__name__)

# --- Path Magic to support legacy imports ---
# The webull_bot uses 'from src...' which implies webull_bot directory is in sys.path
# We add it here so imports work without refactoring the whole folder.
current_dir = os.getcwd()
webull_bot_path = os.path.join(current_dir, "webull_bot")
if webull_bot_path not in sys.path:
    sys.path.insert(0, webull_bot_path)

try:
    from src.config import Config
    from src.bot_handlers import router
    from src.monitor import MonitorEngine
    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
except ImportError as e:
    logger.error(f"Failed to import Webull Bot modules: {e}")
    # Handle case where dependencies aren't installed yet or path is wrong
    Config = None

async def start_webull_bot():
    if not Config:
        logger.error("Webull Bot config not loaded. Skipping startup.")
        return

    logger.info("Initializing Webull Bot...")
    
    # Ensure DB path points to webull_bot directory if not absolute
    # This prevents creating a new empty 'bot.db' in the root folder
    if not os.path.isabs(Config.DB_PATH):
        Config.DB_PATH = os.path.join(webull_bot_path, os.path.basename(Config.DB_PATH))
    
    # Also fix FAVORITES_FILE and TEMPLATES_FILE in bot_handlers if they rely on __file__
    # bot_handlers.py uses: os.path.join(os.path.dirname(os.path.dirname(__file__)), "favorites.json")
    # This resolves relative to bot_handlers.py, so it SHOULD be fine (inside src, parent is webull_bot).
    
    try:
        # Validate Config (will raise if tokens missing)
        try:
            Config.validate()
        except ValueError as e:
            logger.warning(f"Webull Bot Validation Failed (Secrets missing in .env?): {e}")
            return

        # Initialize Bot
        # Remove default parse_mode=HTML as the original bot expected plain text defaults
        # and some messages (like help text with <>) break in HTML mode.
        bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
        dp = Dispatcher()
        dp.include_router(router)
        
        # Start Monitor
        monitor = MonitorEngine(bot)
        # We start monitor as a task. 
        # Note: We should probably keep a reference or clean it up, but for this integration:
        asyncio.create_task(monitor.start())
        
        logger.info("Webull Bot Polling Starting...")
        # handle_signals=False is crucial as Uvicorn handles them
        await dp.start_polling(bot, handle_signals=False)
        
    except Exception as e:
        logger.error(f"Webull Bot Startup Error: {e}")
