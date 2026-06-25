"""Settings page — model selection, RAG parameters, Ollama status."""
from __future__ import annotations

import json

from nicegui import ui

from app.config import settings
from app.services.ollama_client import ollama_client


async def render() -> None:
    """Render the settings page body."""
    with ui.row().classes("w-full gap-6 items-start flex-wrap"):

        # ── LLM Models ────────────────────────────────────────────────────────
        with ui.card().classes("flex-1 min-w-80 p-5"):
            ui.label("Language Models").classes("text-base font-semibold mb-4")

            available_models: list[str] = []

            async def load_models() -> None:
                try:
                    models = await ollama_client.list_models()
                    available_models.clear()
                    available_models.extend(m["name"] for m in models)
                    chat_select.options = available_models
                    embed_select.options = available_models
                except Exception:
                    ui.notify("Could not reach Ollama.", type="negative")

            with ui.column().classes("w-full gap-4"):
                chat_select = ui.select(
                    options=available_models,
                    label="Chat / Reasoning model",
                    value=settings.OLLAMA_CHAT_MODEL,
                ).props("outlined dense").classes("w-full")

                embed_select = ui.select(
                    options=available_models,
                    label="Embedding model",
                    value=settings.OLLAMA_EMBED_MODEL,
                ).props("outlined dense").classes("w-full")

                with ui.row().classes("items-center gap-2 w-full"):
                    ui.button("Refresh model list", icon="refresh", on_click=load_models).props(
                        "flat dense"
                    ).classes("text-sm")

            ui.separator().classes("my-4")

            # Pull a new model
            ui.label("Pull a new model from Ollama").classes("text-sm font-medium text-gray-600")
            with ui.row().classes("w-full gap-2 items-center"):
                pull_input = ui.input(placeholder="e.g. llama3.1:8b").props("outlined dense").classes("flex-1")
                pull_btn = ui.button("Pull", icon="download", on_click=lambda: _pull_model()).props("dense")

            pull_log = ui.log(max_lines=8).classes("w-full text-xs h-24 hidden")

            async def _pull_model() -> None:
                model_name = (pull_input.value or "").strip()
                if not model_name:
                    ui.notify("Enter a model name.", type="warning")
                    return
                pull_log.classes(remove="hidden")
                pull_btn.disable()
                pull_log.push(f"Pulling {model_name}…")
                try:
                    async for line in ollama_client.pull_model(model_name):
                        try:
                            data = json.loads(line)
                            status = data.get("status", "")
                            if "completed" in data and "total" in data:
                                pct = int(data["completed"] / data["total"] * 100)
                                pull_log.push(f"  {status} {pct}%")
                            elif status:
                                pull_log.push(f"  {status}")
                        except Exception:
                            pull_log.push(line)
                    pull_log.push("Done!")
                    await load_models()
                except Exception as exc:
                    pull_log.push(f"Error: {exc}")
                finally:
                    pull_btn.enable()

        # ── RAG Parameters ────────────────────────────────────────────────────
        with ui.card().classes("flex-1 min-w-80 p-5"):
            ui.label("RAG Parameters").classes("text-base font-semibold mb-1")
            ui.label(
                "Changing chunk size requires re-indexing all documents."
            ).classes("text-xs text-amber-600 mb-4")

            chunk_size = ui.number(
                label="Chunk size (characters)",
                value=settings.CHUNK_SIZE,
                min=128, max=2048, step=64,
            ).props("outlined dense").classes("w-full")

            chunk_overlap = ui.number(
                label="Chunk overlap (characters)",
                value=settings.CHUNK_OVERLAP,
                min=0, max=256, step=16,
            ).props("outlined dense").classes("w-full mt-3")

            top_k = ui.number(
                label="Top-K results per query",
                value=settings.TOP_K,
                min=1, max=20, step=1,
            ).props("outlined dense").classes("w-full mt-3")

        # ── Right column: status + storage ────────────────────────────────────
        with ui.column().classes("flex-1 min-w-64 gap-4"):

            # Ollama status
            with ui.card().classes("w-full p-5"):
                with ui.row().classes("items-center gap-2 mb-3"):
                    ui.label("Ollama Status").classes("text-base font-semibold")
                    status_dot = ui.icon("circle").classes("text-sm text-gray-400")

                ui.label(settings.OLLAMA_BASE_URL).classes("text-xs text-gray-500 font-mono mb-3")

                models_list = ui.column().classes("w-full gap-1")

                async def refresh_status() -> None:
                    ok = await ollama_client.health_check()
                    status_dot.classes(
                        remove="text-gray-400 text-green-500 text-red-500",
                        add="text-green-500" if ok else "text-red-500",
                    )
                    models_list.clear()
                    if ok:
                        models = await ollama_client.list_models()
                        with models_list:
                            for m in models:
                                size_gb = m.get("size", 0) / 1e9
                                ui.label(
                                    f"{m['name']}  ·  {size_gb:.1f} GB"
                                ).classes("text-xs text-gray-600 font-mono")
                    else:
                        with models_list:
                            ui.label("Cannot connect to Ollama").classes("text-xs text-red-500")

                ui.button("Refresh status", icon="refresh", on_click=refresh_status).props(
                    "flat dense"
                ).classes("text-sm w-full")

            # Storage info
            with ui.card().classes("w-full p-5"):
                ui.label("Storage").classes("text-base font-semibold mb-3")
                for label, path in [
                    ("Uploads", settings.UPLOAD_DIR),
                    ("Vector index", settings.CHROMA_PERSIST_DIR),
                    ("Database", settings.SQLITE_URL.split("///")[-1]),
                ]:
                    with ui.row().classes("w-full items-start gap-2"):
                        ui.label(label + ":").classes("text-xs text-gray-500 w-20 shrink-0")
                        ui.label(path).classes("text-xs font-mono text-gray-700 break-all")

    # ── Save button ───────────────────────────────────────────────────────────
    ui.separator().classes("my-6")
    with ui.row().classes("gap-3"):
        async def save() -> None:
            import httpx
            from app.schemas import AppSettings
            data = AppSettings(
                chat_model=chat_select.value or settings.OLLAMA_CHAT_MODEL,
                embed_model=embed_select.value or settings.OLLAMA_EMBED_MODEL,
                chunk_size=int(chunk_size.value or settings.CHUNK_SIZE),
                chunk_overlap=int(chunk_overlap.value or settings.CHUNK_OVERLAP),
                top_k=int(top_k.value or settings.TOP_K),
            )
            # Call the API endpoint to persist + apply changes
            async with httpx.AsyncClient() as client:
                r = await client.put(
                    f"http://localhost:{settings.APP_PORT}/api/settings/",
                    json=data.model_dump(),
                    timeout=10,
                )
            if r.status_code == 200:
                ui.notify("Settings saved.", type="positive")
            else:
                ui.notify("Failed to save settings.", type="negative")

        ui.button("Save Settings", icon="save", on_click=save).props("color=primary")

    # Load data on page open
    await refresh_status()
    await load_models()
