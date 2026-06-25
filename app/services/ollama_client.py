"""
Async HTTP client wrapping the Ollama REST API.

All service modules import the module-level singleton:
    from app.services.ollama_client import ollama_client
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Ollama can take a long time to respond when generating — use a generous timeout.
_TIMEOUT = httpx.Timeout(300.0, connect=10.0)


class OllamaClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=settings.OLLAMA_BASE_URL, timeout=_TIMEOUT)

    # ── Health ────────────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        try:
            r = await self._client.get("/")
            return r.status_code == 200
        except Exception:
            return False

    # ── Embeddings ────────────────────────────────────────────────────────────

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """Return one embedding vector per input text.

        Sends texts in batches of 32 to avoid request-size issues.
        Uses Ollama's /api/embed endpoint (supports batch input).
        """
        model = model or settings.OLLAMA_EMBED_MODEL
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), 32):
            batch = texts[i : i + 32]
            r = await self._client.post("/api/embed", json={"model": model, "input": batch})
            r.raise_for_status()
            all_embeddings.extend(r.json()["embeddings"])

        return all_embeddings

    # ── Chat ──────────────────────────────────────────────────────────────────

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        stream: bool = False,
    ) -> str:
        """Send a chat request and return the full response content.

        When stream=False (default) waits for the complete response.
        For streaming, use chat_stream() instead.
        """
        model = model or settings.OLLAMA_CHAT_MODEL
        r = await self._client.post(
            "/api/chat",
            json={"model": model, "messages": messages, "stream": False},
        )
        r.raise_for_status()
        return r.json()["message"]["content"]

    async def chat_stream(
        self,
        messages: list[dict],
        model: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat response tokens as they arrive."""
        model = model or settings.OLLAMA_CHAT_MODEL

        async with self._client.stream(
            "POST",
            "/api/chat",
            json={"model": model, "messages": messages, "stream": True},
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if not data.get("done") and "message" in data:
                        yield data["message"]["content"]
                except json.JSONDecodeError:
                    continue

    # ── Model management ──────────────────────────────────────────────────────

    async def list_models(self) -> list[dict]:
        """Return all models currently available in Ollama."""
        r = await self._client.get("/api/tags")
        r.raise_for_status()
        return r.json().get("models", [])

    async def pull_model(self, model_name: str) -> AsyncGenerator[str, None]:
        """Pull a model from Ollama registry, yielding raw NDJSON status lines."""
        async with self._client.stream(
            "POST", "/api/pull", json={"name": model_name}
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    yield line


# Module-level singleton — import this, not the class.
ollama_client = OllamaClient()
