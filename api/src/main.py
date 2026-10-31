from fastapi import FastAPI

from src.core.config import get_settings
from src.health.router import router as health_router

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.include_router(health_router, prefix="/api")
