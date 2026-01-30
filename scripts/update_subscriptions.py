import asyncio
import logging
from app.db import db
from app.bot import bot, send_notification
from app.config import get_settings
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("updater")

async def update_subscriptions():
    await db.connect()
    try:
        logger.info("Starting subscription update job...")
        
        # 1. Update remaining days
        # This simple query decrements days. A better approach is calculating diff from end_date.
        # But let's check for expired subscriptions based on end_date
        
        now = datetime.now()
        
        # Get active subscriptions that have expired
        expired_subs = await db.fetch("""
            SELECT id, telegram_user_id 
            FROM subscriptions 
            WHERE status = 'active' AND end_date < NOW()
        """)
        
        for sub in expired_subs:
            logger.info(f"Expiring subscription {sub['id']}")
            # Update status
            await db.execute("UPDATE subscriptions SET status = 'expired' WHERE id = $1", sub['id'])
            
            # Notify user
            msg = "⚠️ لقد انتهت فترة اشتراكك.\nلتجديد الاشتراك، يرجى زيارة المتجر."
            await send_notification(sub['telegram_user_id'], msg)
            
            # Kick user logic here if needed (kickChatMember)
            
        logger.info(f"Processed {len(expired_subs)} expired subscriptions.")
        
        # Optional: Notify users with 1 day remaining
        near_expiry = await db.fetch("""
            SELECT telegram_user_id 
            FROM subscriptions 
            WHERE status = 'active' 
            AND end_date BETWEEN NOW() AND NOW() + INTERVAL '1 day'
            AND remaining_days > 0
        """) # Simplistic check, usually allow a flag 'notified'
        
        for sub in near_expiry:
             await send_notification(sub['telegram_user_id'], "⏳ باقي يوم واحد على انتهاء اشتراكك.")

    except Exception as e:
        logger.error(f"Error in update job: {e}")
    finally:
        await db.disconnect()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(update_subscriptions())
