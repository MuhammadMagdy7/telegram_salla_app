from datetime import datetime, timedelta
from app.db import db
from app.config import get_settings
from aiogram.types import ChatInviteLink
import logging

settings = get_settings()
logger = logging.getLogger(__name__)

class SubscriptionManager:
    @staticmethod
    async def create_subscription(user_id: int, salla_order_id: str, days: int = 30):
        # Calculate dates
        start_date = datetime.now()
        end_date = start_date + timedelta(days=days)
        
        # Insert subscription
        query = """
        INSERT INTO subscriptions (telegram_user_id, salla_order_id, status, start_date, end_date, remaining_days)
        VALUES ($1, $2, 'active', $3, $4, $5)
        RETURNING id
        """
        try:
            sub_id = await db.fetchrow(query, user_id, salla_order_id, start_date, end_date, days)
            return sub_id
        except Exception as e:
            logger.error(f"Error creating subscription: {e}")
            return None

    @staticmethod
    async def get_subscription(user_id: int):
        query = "SELECT * FROM subscriptions WHERE telegram_user_id = $1 AND status = 'active' AND end_date > NOW() ORDER BY end_date DESC LIMIT 1"
        return await db.fetchrow(query, user_id)

    @staticmethod
    async def extend_subscription(user_id: int, salla_order_id: str, days: int = 30):
        # Logic to extend existing subscription if active, or create new
        existing = await SubscriptionManager.get_subscription(user_id)
        if existing:
            new_end_date = existing['end_date'] + timedelta(days=days)
            new_remaining = existing['remaining_days'] + days
            query = """
            UPDATE subscriptions SET end_date = $1, remaining_days = $2, salla_order_id = $3 
            WHERE id = $4
            """
            await db.execute(query, new_end_date, new_remaining, salla_order_id, existing['id'])
            return existing['id']
        else:
            return await SubscriptionManager.create_subscription(user_id, salla_order_id, days)

    @staticmethod
    async def generate_invite_link(bot, channel_id: str, user_id: int = None):
        try:
            # Create a single-use invite link (can only be used once)
            link: ChatInviteLink = await bot.create_chat_invite_link(
                chat_id=channel_id,
                name=f"Subscription for {user_id}" if user_id else "Subscription Link",
                member_limit=1  # Single use only!
            )
            return link.invite_link
        except Exception as e:
            logger.error(f"Failed to generate invite link: {e}")
            return None
