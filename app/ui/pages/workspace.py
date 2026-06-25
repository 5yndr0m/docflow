"""Document workspace page — upload, view, manage documents."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from nicegui import ui, events

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Document
from app.schemas import DocumentStatus
from app.services.ingestor import delete_document_data, ingest_document
from app.services.vector_store import vector_store
from sqlalchemy import select

# Map file types to Material Icons
_FILE_ICONS = {
    "pdf": "picture_as_pdf",
    "docx": "description",
    "pptx": "slideshow",
    "xlsx": "table_chart",
    "txt": "article",
}

_STATUS_COLORS = {
    DocumentStatus.PENDING.value: "grey",
    DocumentStatus.INGESTING.value: "blue",
    DocumentStatus.READY.value: "positive",
    DocumentStatus.ERROR.value: "negative",
}

_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".txt"}


async def _get_documents() -> list[Document]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Document).order_by(Document.created_at.desc()))
        return list(result.scalars().all())


async def render() -> None:
    """Render the workspace page body."""

    # ── Upload zone ───────────────────────────────────────────────────────────
    with ui.card().classes("w-full p-6 bg-white shadow-sm"):
        ui.label("Upload Documents").classes("text-lg font-semibold mb-3")
        upload = ui.upload(
            multiple=True,
            auto_upload=True,
            label="Drop files here or click to browse  ·  PDF  DOCX  PPTX  XLSX  TXT  ·  max 100 MB",
        ).props('accept=".pdf,.docx,.pptx,.xlsx,.txt" flat bordered').classes("w-full")

    # ── Document list (refreshable) ───────────────────────────────────────────
    ui.separator().classes("my-4")
    ui.label("Your Documents").classes("text-lg font-semibold mb-2")

    doc_area = ui.column().classes("w-full gap-3")
    refresh_timer = ui.timer(3.0, lambda: None, active=False)  # configured below

    @ui.refreshable
    async def document_list() -> None:
        doc_area.clear()
        docs = await _get_documents()

        has_ingesting = any(d.status == DocumentStatus.INGESTING.value for d in docs)
        refresh_timer.active = has_ingesting

        if not docs:
            with doc_area:
                with ui.card().classes("w-full p-10 text-center bg-gray-50"):
                    ui.icon("upload_file").classes("text-5xl text-gray-300 block mx-auto")
                    ui.label("No documents yet").classes("text-gray-500 mt-2")
                    ui.label("Upload a file above to get started").classes("text-sm text-gray-400")
            return

        with doc_area:
            for doc in docs:
                _document_row(doc, on_change=document_list.refresh)

    # Wire the timer to refresh
    refresh_timer.callback = document_list.refresh  # type: ignore[assignment]

    await document_list()

    # ── Upload handler ────────────────────────────────────────────────────────
    async def handle_upload(e: events.UploadEventArguments) -> None:
        suffix = Path(e.name).suffix.lower()
        if suffix not in _ALLOWED_EXTENSIONS:
            ui.notify(f"'{suffix}' is not supported.", type="negative")
            return

        content = e.content.read()
        if not content:
            ui.notify("Uploaded file is empty.", type="negative")
            return

        doc_id = str(uuid.uuid4())
        file_type = suffix.lstrip(".")
        file_path = Path(settings.UPLOAD_DIR) / f"{doc_id}.{file_type}"
        file_path.write_bytes(content)

        async with AsyncSessionLocal() as db:
            doc = Document(
                id=doc_id,
                name=e.name,
                file_type=file_type,
                file_path=str(file_path),
                status=DocumentStatus.PENDING.value,
                size_bytes=len(content),
            )
            db.add(doc)
            await db.commit()

        asyncio.create_task(ingest_document(doc_id, str(file_path), file_type, e.name))
        ui.notify(f"'{e.name}' queued for ingestion.", type="positive")
        await document_list.refresh()

    upload.on_upload(handle_upload)


def _document_row(doc: Document, on_change) -> None:
    """Render a single document card."""
    icon = _FILE_ICONS.get(doc.file_type, "insert_drive_file")
    status_color = _STATUS_COLORS.get(doc.status, "grey")
    size_kb = doc.size_bytes / 1024

    with ui.card().classes("w-full shadow-sm hover:shadow-md transition-shadow"):
        with ui.row().classes("w-full items-center gap-4 px-4 py-3"):
            # Icon
            ui.icon(icon).classes("text-3xl text-gray-400 shrink-0")

            # Name + metadata
            with ui.column().classes("flex-1 gap-0 min-w-0"):
                ui.label(doc.name).classes("font-medium text-sm truncate")
                meta = f"{size_kb:.0f} KB"
                if doc.chunk_count:
                    meta += f"  ·  {doc.chunk_count} chunks"
                meta += f"  ·  {doc.created_at.strftime('%b %d, %Y')}"
                ui.label(meta).classes("text-xs text-gray-400")

            # Status badge
            with ui.element("div"):
                badge = ui.badge(doc.status, color=status_color)
                if doc.status == DocumentStatus.INGESTING.value:
                    badge.props("rounded")
                if doc.error_message:
                    badge.tooltip(doc.error_message)

            # Actions
            with ui.row().classes("gap-1 shrink-0"):
                (
                    ui.button(icon="refresh", on_click=lambda d=doc: _reindex(d, on_change))
                    .props("flat round dense")
                    .tooltip("Re-index")
                )
                (
                    ui.button(icon="delete_outline", on_click=lambda d=doc: _confirm_delete(d, on_change))
                    .props("flat round dense color=negative")
                    .tooltip("Delete")
                )


async def _reindex(doc: Document, on_change) -> None:
    if doc.status == DocumentStatus.INGESTING.value:
        ui.notify("Document is currently being ingested.", type="warning")
        return

    await asyncio.to_thread(vector_store.delete_document, doc.id)

    async with AsyncSessionLocal() as db:
        d = await db.get(Document, doc.id)
        if d:
            d.status = DocumentStatus.PENDING.value
            d.chunk_count = None
            d.error_message = None
            await db.commit()

    asyncio.create_task(ingest_document(doc.id, doc.file_path, doc.file_type, doc.name))
    ui.notify(f"Re-indexing '{doc.name}'…", type="info")
    await on_change()


def _confirm_delete(doc: Document, on_change) -> None:
    with ui.dialog() as dialog, ui.card().classes("p-6 max-w-sm"):
        ui.label("Delete document?").classes("text-lg font-semibold")
        ui.label(
            f"'{doc.name}' and all its indexed data will be permanently removed."
        ).classes("text-sm text-gray-600 mt-1")

        async def do_delete() -> None:
            dialog.close()
            async with AsyncSessionLocal() as db:
                await delete_document_data(doc.id, doc.file_path, db)
                await db.commit()
            ui.notify(f"'{doc.name}' deleted.", type="positive")
            await on_change()

        with ui.row().classes("gap-3 mt-6 justify-end w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Delete", on_click=do_delete).props("color=negative")

    dialog.open()
