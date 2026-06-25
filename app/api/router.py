from fastapi import APIRouter

from app.api import chat, documents
from app.api import settings as settings_api

api_router = APIRouter(prefix="/api")

api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(settings_api.router, prefix="/settings", tags=["settings"])
