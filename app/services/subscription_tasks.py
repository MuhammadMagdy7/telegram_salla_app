"""
Subscription Background Tasks - runs periodically to manage expired subscriptions
"""
import asyncio
import logging
from datetime import datetime
from app.db import db
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


async def check_expired_subscriptions(bot):
    """
    Check for expired subscriptions and handle them:
    1. Find subscriptions where end_date < NOW() AND status = 'active'
    2. Update status to 'expired'
    3. Kick user from channel/group
    4. Send notification to user
    """
    try:
        # Find expired subscriptions
        query = """
            SELECT s.*, u.telegram_user_id 
            FROM subscriptions s
            LEFT JOIN users u ON s.telegram_user_id = u.telegram_user_id
            WHERE s.status = 'active' AND s.end_date < NOW()
        """
        expired_subs = await db.fetch(query)
        
        if not expired_subs:
            return 0
        
        count = 0
        for sub in expired_subs:
            user_id = sub['telegram_user_id']
            sub_id = sub['id']
            
            try:
                # 1. Update subscription status to 'expired'
                await db.execute(
                    "UPDATE subscriptions SET status = 'expired' WHERE id = $1",
                    sub_id
                )
                
                # 2. Try to kick user from channel AND groups
                target_chats = []
                if settings.CHANNEL_ID:
                    target_chats.append(settings.CHANNEL_ID)
                
                # Add extra groups
                extra_groups = settings.get_group_ids()
                target_chats.extend(extra_groups)
                
                for chat_id in target_chats:
                    if not chat_id: continue
                    try:
                        await bot.ban_chat_member(
                            chat_id=chat_id,
                            user_id=user_id
                        )
                        # Unban immediately so they can rejoin if they subscribe again
                        await bot.unban_chat_member(
                            chat_id=chat_id,
                            user_id=user_id,
                            only_if_banned=True
                        )
                        logger.info(f"Kicked user {user_id} from chat {chat_id} due to expired subscription")
                    except Exception as kick_err:
                        logger.warning(f"Could not kick user {user_id} from {chat_id}: {kick_err}")
                
                # 3. Send notification to user
                try:
                    await bot.send_message(
                        user_id,
                        "⚠️ *انتهى اشتراكك*\n\n"
                        "لقد انتهت مدة اشتراكك في خدماتنا.\n"
                        "لتجديد الاشتراك والعودة للقناة، يرجى زيارة المتجر:\n"
                        "https://salla.sa/investly11",
                        parse_mode="Markdown"
                    )
                except Exception as msg_err:
                    logger.warning(f"Could not notify user {user_id}: {msg_err}")
                
                count += 1
                
            except Exception as e:
                logger.error(f"Error processing expired subscription {sub_id}: {e}")
        
        if count > 0:
            logger.info(f"Processed {count} expired subscriptions")
        
        return count
        
    except Exception as e:
        logger.error(f"Error in check_expired_subscriptions: {e}")
        return 0


async def send_expiration_reminders(bot):
    """
    Send reminder notifications to users when their subscription is about to expire.
    - 3 days before expiration
    - 1 day before expiration
    - On expiration day
    """
    try:
        # Find subscriptions expiring in 3 days
        three_days = await db.fetch("""
            SELECT s.*, u.telegram_user_id 
            FROM subscriptions s
            LEFT JOIN users u ON s.telegram_user_id = u.telegram_user_id
            WHERE s.status = 'active' 
            AND DATE(s.end_date) = CURRENT_DATE + INTERVAL '3 days'
            AND (s.reminder_3_days IS NULL OR s.reminder_3_days = FALSE)
        """)
        
        for sub in three_days:
            try:
                await bot.send_message(
                    sub['telegram_user_id'],
                    "⏰ *تذكير: اشتراكك سينتهي خلال 3 أيام*\n\n"
                    "لتجديد اشتراكك والاستمتاع بخدماتنا، يرجى زيارة المتجر:\n"
                    "https://salla.sa/investly11",
                    parse_mode="Markdown"
                )
                await db.execute("UPDATE subscriptions SET reminder_3_days = TRUE WHERE id = $1", sub['id'])
            except Exception as e:
                logger.warning(f"Could not send 3-day reminder to {sub['telegram_user_id']}: {e}")
        
        # Find subscriptions expiring tomorrow
        one_day = await db.fetch("""
            SELECT s.*, u.telegram_user_id 
            FROM subscriptions s
            LEFT JOIN users u ON s.telegram_user_id = u.telegram_user_id
            WHERE s.status = 'active' 
            AND DATE(s.end_date) = CURRENT_DATE + INTERVAL '1 day'
            AND (s.reminder_1_day IS NULL OR s.reminder_1_day = FALSE)
        """)
        
        for sub in one_day:
            try:
                await bot.send_message(
                    sub['telegram_user_id'],
                    "⚠️ *تنبيه: اشتراكك سينتهي غداً!*\n\n"
                    "لا تفوت الفرصة! جدد الآن:\n"
                    "https://salla.sa/investly11",
                    parse_mode="Markdown"
                )
                await db.execute("UPDATE subscriptions SET reminder_1_day = TRUE WHERE id = $1", sub['id'])
            except Exception as e:
                logger.warning(f"Could not send 1-day reminder to {sub['telegram_user_id']}: {e}")
        
        # Find subscriptions expiring today
        today_expiring = await db.fetch("""
            SELECT s.*, u.telegram_user_id 
            FROM subscriptions s
            LEFT JOIN users u ON s.telegram_user_id = u.telegram_user_id
            WHERE s.status = 'active' 
            AND DATE(s.end_date) = CURRENT_DATE
            AND (s.reminder_today IS NULL OR s.reminder_today = FALSE)
        """)
        
        for sub in today_expiring:
            try:
                await bot.send_message(
                    sub['telegram_user_id'],
                    "🚨 *اشتراكك ينتهي اليوم!*\n\n"
                    "جدد الآن لتجنب فقدان الوصول للقناة:\n"
                    "https://salla.sa/investly11",
                    parse_mode="Markdown"
                )
                await db.execute("UPDATE subscriptions SET reminder_today = TRUE WHERE id = $1", sub['id'])
            except Exception as e:
                logger.warning(f"Could not send today reminder to {sub['telegram_user_id']}: {e}")
        
        total = len(three_days) + len(one_day) + len(today_expiring)
        if total > 0:
            logger.info(f"Sent {total} expiration reminders")
        
    except Exception as e:
        logger.error(f"Error in send_expiration_reminders: {e}")


async def subscription_checker_loop(bot):
    """
    Background loop that runs every hour to check expired subscriptions.
    """
    logger.info("Starting subscription checker background task")
    
    while True:
        try:
            await send_expiration_reminders(bot)
            await check_expired_subscriptions(bot)
            await check_unauthorized_members(bot)
        except Exception as e:
            logger.error(f"Error in subscription checker loop: {e}")
        
        # Wait 1 hour before next check
        await asyncio.sleep(3600)  # 3600 seconds = 1 hour



async def check_unauthorized_members(bot):
    """
    Check for channel members without active subscription and kick them.
    Excludes admins.
    """
    if not settings.CHANNEL_ID:
        return 0
    
    try:
        # Get channel admins (to exclude from kicking)
        admins = []
        try:
            admin_list = await bot.get_chat_administrators(settings.CHANNEL_ID)
            admins = [admin.user.id for admin in admin_list]
            logger.info(f"Found {len(admins)} admins to exclude from check")
        except Exception as e:
            logger.warning(f"Could not get admin list: {e}")
            return 0
        
        # Get all users who have been in our system (registered with bot)
        all_users = await db.fetch("SELECT telegram_user_id FROM users WHERE telegram_user_id IS NOT NULL")
        
        kicked_count = 0
        
        for user_row in all_users:
            user_id = user_row['telegram_user_id']
            
            # Skip admins
            if user_id in admins:
                continue
            
            # Check if user has active subscription
            has_subscription = await db.fetchrow(
                "SELECT id FROM subscriptions WHERE telegram_user_id = $1 AND status = 'active' AND end_date > NOW()",
                user_id
            )
            
            if has_subscription:
                continue
            
            # Check if user is member of any target chat (Channel + Groups)
            target_chats = []
            if settings.CHANNEL_ID:
                target_chats.append(settings.CHANNEL_ID)
            target_chats.extend(settings.get_group_ids())

            for chat_id in target_chats:
                if not chat_id: continue
                try:
                    member = await bot.get_chat_member(chat_id, user_id)
                    
                    # If member is still in chat (not left, kicked, or restricted)
                    if member.status in ['member', 'restricted']:
                        # Kick user
                        try:
                            await bot.ban_chat_member(
                                chat_id=chat_id,
                                user_id=user_id
                            )
                            # Unban immediately
                            await bot.unban_chat_member(
                                chat_id=chat_id,
                                user_id=user_id,
                                only_if_banned=True
                            )
                            logger.info(f"Kicked unauthorized user {user_id} from chat {chat_id}")
                            
                            # Notify user (once per run is enough, but maybe acceptable here)
                            if chat_id == settings.CHANNEL_ID: # Notify mostly for channel
                                try:
                                    await bot.send_message(
                                        user_id,
                                        "⚠️ تم إزالتك من القناة/المجموعة لأنه لا يوجد لديك اشتراك فعال.\n\n"
                                        "للاشتراك والعودة:\n"
                                        "https://salla.sa/investly11"
                                    )
                                except:
                                    pass
                            
                            kicked_count += 1
                            
                        except Exception as kick_err:
                            logger.warning(f"Could not kick user {user_id} from {chat_id}: {kick_err}")
                            
                except Exception as check_err:
                    # User might not be/never was in chat - that's fine
                    pass
        
        if kicked_count > 0:
            logger.info(f"Kicked {kicked_count} unauthorized members from channel")
        
        return kicked_count
        
    except Exception as e:
        logger.error(f"Error in check_unauthorized_members: {e}")
        return 0
