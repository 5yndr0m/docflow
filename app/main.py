"""
Application entry point.

Wires FastAPI + NiceGUI together into a single server process.
Run with:  python -m app.main
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from nicegui import ui

from app.api.router import api_router
from app.config import settings
from app.startup import run_startup
from app.ui.app_ui import init_ui


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_startup()
    yield
    # Shutdown cleanup (if needed in the future) goes here


fastapi_app = FastAPI(
    title="Lumen",
    description="Local-first AI document analyzer",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

fastapi_app.include_router(api_router)

# Register NiceGUI pages — must happen before ui.run_with()
init_ui()

if __name__ == "__main__":
    ui.run_with(
        fastapi_app,
        title="Lumen",
        favicon="💡",
        storage_secret=settings.NICEGUI_STORAGE_SECRET,
    )
    uvicorn.run(
        fastapi_app,
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.DEBUG,
    )
