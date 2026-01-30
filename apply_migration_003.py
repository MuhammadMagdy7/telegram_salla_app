import asyncio
import asyncpg
from app.config import get_settings
import os

async def run_migration():
    settings = get_settings()
    print(f"Connecting to DB...")
    conn = await asyncpg.connect(settings.DATABASE_URL)
    
    with open('d:/mostaql/telegram_salla_app/migrations/003_entry_exit_details.sql', 'r') as f:
        sql = f.read()
        
    print("Applying migration...")
    try:
        await conn.execute(sql)
        print("Migration applied successfully!")
    except Exception as e:
        print(f"Error applying migration: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(run_migration())
