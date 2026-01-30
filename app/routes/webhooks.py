from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from app.services.salla import SallaWebhookHandler
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/salla")
async def salla_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Verify Logic (Simplified)
    # in real world, check headers vs SALLA_SECRET
    
    # Process in background to respond quickly to Salla
    background_tasks.add_task(SallaWebhookHandler.handle_webhook, payload)
    
    return {"status": "received"}
