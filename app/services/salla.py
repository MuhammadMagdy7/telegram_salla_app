import hmac
import hashlib
import json
import logging
from datetime import datetime
from fastapi import Request, HTTPException
from app.config import get_settings
from app.db import db
from app.services.subscription_manager import SubscriptionManager
from app.bot import bot, send_notification

settings = get_settings()
logger = logging.getLogger(__name__)

class SallaWebhookHandler:
    @staticmethod
    async def verify_signature(request: Request) -> bool:
        # Implement actual matching logic if shared secret provided
        return True

    @staticmethod
    async def handle_webhook(payload: dict):
        event = payload.get('event') 
        data = payload.get('data', {})
        
        # Log the webhook
        await db.execute(
            "INSERT INTO webhook_logs (payload, event_type, status) VALUES ($1, $2, 'pending')",
            json.dumps(payload), event
        )

        try:
            if event == 'order.paid':
                await SallaWebhookHandler.process_paid_order(data)
            elif event == 'subscription.created':
                await SallaWebhookHandler.process_subscription_created(data)
            elif event == 'subscription.updated':
                await SallaWebhookHandler.process_subscription_updated(data)
            elif event == 'subscription.charge.succeeded':
                await SallaWebhookHandler.process_subscription_charge_succeeded(data)
            elif event == 'subscription.charge.failed':
                await SallaWebhookHandler.process_subscription_charge_failed(data)
            elif event == 'subscription.cancelled':
                await SallaWebhookHandler.process_subscription_cancelled(data)
            else:
                logger.info(f"Unhandled event type: {event}")
        except Exception as e:
            logger.error(f"Error processing webhook {event}: {e}")
            # Try to update log if possible, though 'data' might be structure dependent
            pass

    @staticmethod
    async def get_user_from_payload(data: dict):
        # 1. Try customer object
        customer = data.get('customer')
        phone = None
        if customer and isinstance(customer, dict):
            phone = customer.get('mobile')
        
        # 2. Try top level mobile
        if not phone:
            phone = data.get('mobile')
        
        if not phone:
             return None
             
        # Normalize
        if phone.startswith('+'):
            phone = phone[1:]
        
        return await db.fetchrow("SELECT telegram_user_id FROM users WHERE phone_number = $1", phone)

    @staticmethod
    async def process_paid_order(order_data: dict):
        salla_order_id = str(order_data.get('id'))
        
        existing = await db.fetchrow("SELECT id FROM subscriptions WHERE salla_order_id = $1", salla_order_id)
        if existing:
            return

        user = await SallaWebhookHandler.get_user_from_payload(order_data)
        
        if user:
            user_id = user['telegram_user_id']
            await SubscriptionManager.create_subscription(user_id, salla_order_id)
            
            # Create Invite Link
            try:
                invite_link = await SubscriptionManager.generate_invite_link(bot, settings.CHANNEL_ID)
            except Exception as e:
                logger.error(f"Invite link generation failed: {e}")
                invite_link = None
            
            msg = f"✅ تم تفعيل اشتراكك بنجاح!\nرقم الطلب: {salla_order_id}\n\n"
            if invite_link:
                msg += f"رابط الانضمام للقناة:\n{invite_link}\n\n(اضغط على الرابط للدخول مباشرة)"
            else:
                 msg += "يرجى التواصل مع الدعم الفني للحصول على رابط القناة."
                
            await send_notification(user_id, msg)
            await SallaWebhookHandler.update_log_status(salla_order_id, 'success')
        else:
            logger.warning(f"No user found for order {salla_order_id}. Saving to pending.")
            # Store in pending_subscriptions
            phone = None
            customer = order_data.get('customer')
            if customer: phone = customer.get('mobile')
            if not phone: phone = order_data.get('mobile')
            
            if phone:
                if phone.startswith('+'): phone = phone[1:]
                
                # Default 30 days or handle products logic
                await db.execute("""
                    INSERT INTO pending_subscriptions (phone_number, salla_order_id, days, status)
                    VALUES ($1, $2, 30, 'pending')
                    ON CONFLICT (salla_order_id) DO NOTHING
                """, phone, salla_order_id)
                await SallaWebhookHandler.update_log_status(salla_order_id, 'pending_user_registration')
            else:
                await SallaWebhookHandler.update_log_status(salla_order_id, 'failed_no_phone')

    @staticmethod
    async def process_subscription_created(data: dict):
        sub_id = str(data.get('id'))
        existing = await db.fetchrow("SELECT id FROM subscriptions WHERE salla_order_id = $1", sub_id)
        if existing: return

        user = await SallaWebhookHandler.get_user_from_payload(data)
        if not user:
            logger.warning(f"No user found for subscription {sub_id}")
            return

        user_id = user['telegram_user_id']
        created_at_str = data.get('created_at')
        valid_till_str = data.get('valid_till') # e.g. "2025-11-11T09:00:00+03:00"
        
        start_date = datetime.now()
        end_date = start_date 
        
        if created_at_str:
            try: start_date = datetime.fromisoformat(created_at_str)
            except: pass
        if valid_till_str:
            try: end_date = datetime.fromisoformat(valid_till_str)
            except: pass

        query = """
        INSERT INTO subscriptions (telegram_user_id, salla_order_id, status, start_date, end_date)
        VALUES ($1, $2, 'active', $3, $4)
        """
        await db.execute(query, user_id, sub_id, start_date, end_date)
        
        await send_notification(user_id, f"✅ تم تفعيل اشتراكك رقم {sub_id}")
        await SallaWebhookHandler.update_log_status(sub_id, 'success')

    @staticmethod
    async def process_subscription_updated(data: dict):
        sub_id = str(data.get('id'))
        valid_till = data.get('valid_till')
        if valid_till:
            try:
                end_date = datetime.fromisoformat(valid_till)
                await db.execute("UPDATE subscriptions SET end_date = $1 WHERE salla_order_id = $2", end_date, sub_id)
            except: pass

    @staticmethod
    async def process_subscription_charge_succeeded(data: dict):
        await SallaWebhookHandler.process_subscription_updated(data)
        sub_id = str(data.get('id'))
        sub = await db.fetchrow("SELECT telegram_user_id FROM subscriptions WHERE salla_order_id = $1", sub_id)
        if sub: await send_notification(sub['telegram_user_id'], "✅ تم تجديد اشتراكك بنجاح!")

    @staticmethod
    async def process_subscription_charge_failed(data: dict):
        sub_id = str(data.get('id'))
        await db.execute("UPDATE subscriptions SET status = 'payment_failed' WHERE salla_order_id = $1", sub_id)
        sub = await db.fetchrow("SELECT telegram_user_id FROM subscriptions WHERE salla_order_id = $1", sub_id)
        if sub: await send_notification(sub['telegram_user_id'], "⚠️ فشل تجديد الاشتراك.")

    @staticmethod
    async def process_subscription_cancelled(data: dict):
        sub_id = str(data.get('id'))
        await db.execute("UPDATE subscriptions SET status = 'cancelled' WHERE salla_order_id = $1", sub_id)
        sub = await db.fetchrow("SELECT telegram_user_id FROM subscriptions WHERE salla_order_id = $1", sub_id)
        if sub: await send_notification(sub['telegram_user_id'], "❌ تم إلغاء اشتراكك.")

    @staticmethod
    async def update_log_status(ref_id: str, status: str):
        # Approximate matching for logs
        await db.execute("UPDATE webhook_logs SET status = $1 WHERE payload::jsonb->'data'->>'id' = $2", status, ref_id)

