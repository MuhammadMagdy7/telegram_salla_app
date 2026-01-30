import asyncio
from app.db import db

async def migrate():
    await db.connect()
    print("Creating pending_subscriptions table...")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pending_subscriptions (
            id SERIAL PRIMARY KEY,
            phone_number TEXT NOT NULL,
            salla_order_id TEXT UNIQUE, 
            days INTEGER DEFAULT 30,
            status TEXT DEFAULT 'pending', -- pending, claimed
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_pending_phone ON pending_subscriptions(phone_number);
    """)
    print("Migration complete.")
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(migrate())
