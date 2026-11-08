from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from src.chat.router import router as chat_router
from src.core.config import get_settings
from src.health.router import router as health_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with httpx.AsyncClient(headers={"User-Agent": settings.app_name}) as http_client:
        app.state.http_client = http_client
        yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
app.include_router(health_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
