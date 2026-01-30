import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from app.config import get_settings
from app.db import db
from app.routes import webhooks, admin
from app.bot import start_bot, bot
from app.webull_wrapper import start_webull_bot
from app.services.subscription_tasks import subscription_checker_loop

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await db.connect()
    
    # Start bot polling in background task
    # Note: In production with multiple workers this is bad. But requirements said 1 worker.
    # Ideally, run bot as separate service or use webhooks. For simplicity/resource constraints:
    asyncio.create_task(start_bot())
    asyncio.create_task(start_webull_bot())
    
    # Start subscription expiration checker (runs every hour)
    asyncio.create_task(subscription_checker_loop(bot))
    
    yield
    
    # Shutdown
    if db.pool:
        await db.disconnect()
    # Bot session close
    await bot.session.close()

app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Include Routers
app.include_router(webhooks.router) # Expose /salla directly
app.include_router(admin.router, prefix="/admin")

@app.get("/")
async def root():
    return {"message": "Telegram Salla App is Running"}
