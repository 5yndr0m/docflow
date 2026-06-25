"""
Document ingestion pipeline — runs as an asyncio background task.

Flow: parse → chunk → embed → store in ChromaDB → update DB status.

Opens its own DB sessions (not request-scoped) because it runs outside
any FastAPI request context.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.database import AsyncSessionLocal
from app.models import Document
from app.schemas import DocumentStatus
from app.services.chunker import chunk_segments
from app.services.document_parser import parse_document
from app.services.ollama_client import ollama_client
from app.services.vector_store import vector_store

logger = logging.getLogger(__name__)


async def ingest_document(
    document_id: str,
    file_path: str,
    file_type: str,
    document_name: str,
) -> None:
    """Full ingestion pipeline for a single document.

    Called via asyncio.create_task() after the Document row has been
    committed to the database.
    """
    logger.info("Ingesting document %s (%s)", document_name, document_id)

    # ── Mark as ingesting ─────────────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        doc = await db.get(Document, document_id)
        if not doc:
            logger.error("Document %s not found in DB — aborting ingestion", document_id)
            return
        doc.status = DocumentStatus.INGESTING.value
        await db.commit()

    try:
        # ── Parse ─────────────────────────────────────────────────────────────
        segments = await asyncio.to_thread(parse_document, file_path, file_type)
        if not segments:
            raise ValueError("No text content could be extracted from the document.")

        # ── Chunk ─────────────────────────────────────────────────────────────
        from app.config import settings

        chunks = chunk_segments(
            segments,
            document_id=document_id,
            document_name=document_name,
            chunk_size=settings.CHUNK_SIZE,
            overlap=settings.CHUNK_OVERLAP,
        )
        if not chunks:
            raise ValueError("Document produced no usable chunks after splitting.")

        logger.info("  %d chunks created for %s", len(chunks), document_name)

        # ── Embed ─────────────────────────────────────────────────────────────
        texts = [c.text for c in chunks]
        embeddings = await ollama_client.embed(texts)
        logger.info("  Embeddings generated")

        # ── Store ─────────────────────────────────────────────────────────────
        await asyncio.to_thread(vector_store.add_chunks, chunks, embeddings)
        logger.info("  Stored in ChromaDB")

        # ── Update status: ready ──────────────────────────────────────────────
        async with AsyncSessionLocal() as db:
            doc = await db.get(Document, document_id)
            if doc:
                doc.status = DocumentStatus.READY.value
                doc.chunk_count = len(chunks)
                await db.commit()

        logger.info("Document %s ingested successfully (%d chunks)", document_name, len(chunks))

    except Exception as exc:
        logger.exception("Ingestion failed for document %s: %s", document_id, exc)

        async with AsyncSessionLocal() as db:
            doc = await db.get(Document, document_id)
            if doc:
                doc.status = DocumentStatus.ERROR.value
                doc.error_message = str(exc)[:500]
                await db.commit()


async def delete_document_data(document_id: str, file_path: str, db) -> None:
    """Delete a document's vectors, file on disk, and DB row.

    The caller is responsible for committing the DB session.
    """
    # Remove from vector store
    await asyncio.to_thread(vector_store.delete_document, document_id)

    # Remove file from disk
    try:
        Path(file_path).unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Could not delete file %s: %s", file_path, exc)

    # Delete DB row
    doc = await db.get(Document, document_id)
    if doc:
        await db.delete(doc)
