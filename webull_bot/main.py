import asyncio
import logging
from aiogram import Bot, Dispatcher
from src.config import Config
from src.bot_handlers import router
from src.monitor import MonitorEngine

logging.basicConfig(level=logging.INFO)

async def main():
    Config.validate()
    
    bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    monitor = MonitorEngine(bot)
    asyncio.create_task(monitor.start())
    
    try:
        await dp.start_polling(bot)
    finally:
        await monitor.stop()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
