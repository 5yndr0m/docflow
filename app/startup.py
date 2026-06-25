"""
Application startup sequence.

Called once during the FastAPI lifespan before the server accepts requests.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from tenacity import before_sleep_log, retry, stop_after_attempt, wait_fixed

from app.config import settings
from app.database import init_db
from app.services.ollama_client import ollama_client

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(18),       # ~60 seconds total
    wait=wait_fixed(4),
    before_sleep=before_sleep_log(logger, logging.INFO),
    reraise=True,
)
async def _wait_for_ollama() -> None:
    if not await ollama_client.health_check():
        raise ConnectionError("Ollama not responding yet")
    logger.info("Ollama is up")


async def _ensure_model(model_name: str) -> None:
    """Pull model if it is not already present in Ollama."""
    try:
        models = await ollama_client.list_models()
        present = {m["name"] for m in models}
        base = model_name.split(":")[0]

        if any(n == model_name or n.startswith(base + ":") for n in present):
            logger.info("Model '%s' already available", model_name)
            return

        logger.info("Pulling model '%s' — this may take several minutes…", model_name)
        async for line in ollama_client.pull_model(model_name):
            try:
                data = json.loads(line)
                status = data.get("status", "")
                if "completed" in data and "total" in data and data["total"]:
                    pct = int(data["completed"] / data["total"] * 100)
                    logger.info("  %s %d%%", status, pct)
                elif status and status != "success":
                    logger.info("  %s", status)
            except Exception:
                pass
        logger.info("Model '%s' ready", model_name)

    except Exception as exc:
        logger.error("Could not ensure model '%s': %s", model_name, exc)
        raise


async def run_startup() -> None:
    logger.info("═══ Lumen startup ═══")

    # Ensure data directories exist (important when running outside Docker)
    for path_str in [settings.UPLOAD_DIR, settings.CHROMA_PERSIST_DIR]:
        Path(path_str).mkdir(parents=True, exist_ok=True)

    # Initialise SQLite tables
    await init_db()
    logger.info("Database ready")

    # Wait for Ollama to become available
    try:
        await _wait_for_ollama()
    except Exception as exc:
        logger.error("Ollama did not become available: %s", exc)
        logger.warning("Lumen will start without Ollama — ingestion and Q&A will fail until Ollama is reachable.")
        return

    # Pull required models if missing
    await _ensure_model(settings.OLLAMA_EMBED_MODEL)
    await _ensure_model(settings.OLLAMA_CHAT_MODEL)

    logger.info("═══ Lumen is ready — http://%s:%s ═══", settings.APP_HOST, settings.APP_PORT)
