import asyncpg
from app.config import get_settings

settings = get_settings()

class Database:
    pool: asyncpg.Pool = None

    async def connect(self):
        if not self.pool:
            if not settings.DATABASE_URL:
                 print("CRITICAL ERROR: DATABASE_URL is empty or missing!")
            print(f"Connecting to DB with URL length: {len(settings.DATABASE_URL) if settings.DATABASE_URL else 0}")
            self.pool = await asyncpg.create_pool(
                dsn=settings.DATABASE_URL,
                min_size=1,
                max_size=5
            )
            print("DB Pool created")

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            print("DB Pool closed")

    async def fetchrow(self, query, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetch(self, query, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def execute(self, query, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

db = Database()

