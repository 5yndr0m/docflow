from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter

from app.config import settings
from app.schemas import AppSettings, ModelInfo
from app.services.ollama_client import ollama_client

router = APIRouter()
logger = logging.getLogger(__name__)

# Runtime overrides are persisted here so they survive container restarts.
_SETTINGS_FILE = Path("/data/settings.json")


def _load_overrides() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            return json.loads(_SETTINGS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_overrides(data: dict) -> None:
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(json.dumps(data, indent=2))


@router.get("/", response_model=AppSettings)
async def get_settings() -> AppSettings:
    overrides = _load_overrides()
    return AppSettings(
        chat_model=overrides.get("chat_model", settings.OLLAMA_CHAT_MODEL),
        embed_model=overrides.get("embed_model", settings.OLLAMA_EMBED_MODEL),
        chunk_size=overrides.get("chunk_size", settings.CHUNK_SIZE),
        chunk_overlap=overrides.get("chunk_overlap", settings.CHUNK_OVERLAP),
        top_k=overrides.get("top_k", settings.TOP_K),
    )


@router.put("/")
async def update_settings(data: AppSettings) -> dict:
    overrides = data.model_dump()
    _save_overrides(overrides)

    # Apply live — affects all subsequent requests in this process
    settings.OLLAMA_CHAT_MODEL = data.chat_model
    settings.OLLAMA_EMBED_MODEL = data.embed_model
    settings.CHUNK_SIZE = data.chunk_size
    settings.CHUNK_OVERLAP = data.chunk_overlap
    settings.TOP_K = data.top_k

    logger.info("Settings updated: %s", overrides)
    return {"status": "saved"}


@router.get("/models", response_model=list[ModelInfo])
async def list_models() -> list[ModelInfo]:
    models = await ollama_client.list_models()
    return [
        ModelInfo(
            name=m.get("name", ""),
            size=m.get("size"),
            modified_at=m.get("modified_at"),
        )
        for m in models
    ]
