from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.deps import get_db
from app.models import Document
from app.schemas import DocumentRead, DocumentStatus
from app.services.ingestor import delete_document_data, ingest_document
from app.services.vector_store import vector_store

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".txt"}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


@router.post("/", response_model=DocumentRead, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> DocumentRead:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{suffix}' is not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds the 100 MB limit.")
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    doc_id = str(uuid.uuid4())
    file_type = suffix.lstrip(".")
    safe_filename = f"{doc_id}.{file_type}"
    file_path = Path(settings.UPLOAD_DIR) / safe_filename
    file_path.write_bytes(content)

    doc = Document(
        id=doc_id,
        name=file.filename or safe_filename,
        file_type=file_type,
        file_path=str(file_path),
        status=DocumentStatus.PENDING.value,
        size_bytes=len(content),
    )
    db.add(doc)
    await db.flush()

    # Commit before launching the background task so the row is visible to it.
    await db.commit()
    asyncio.create_task(
        ingest_document(doc_id, str(file_path), file_type, file.filename or safe_filename)
    )

    await db.refresh(doc)
    return DocumentRead.model_validate(doc)


@router.get("/", response_model=list[DocumentRead])
async def list_documents(db: AsyncSession = Depends(get_db)) -> list[DocumentRead]:
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    return [DocumentRead.model_validate(d) for d in result.scalars().all()]


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(document_id: str, db: AsyncSession = Depends(get_db)) -> DocumentRead:
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentRead.model_validate(doc)


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: str, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    await delete_document_data(doc.id, doc.file_path, db)
    await db.commit()


@router.post("/{document_id}/reindex", status_code=202)
async def reindex_document(
    document_id: str, db: AsyncSession = Depends(get_db)
) -> dict:
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    if doc.status == DocumentStatus.INGESTING.value:
        raise HTTPException(status_code=409, detail="Document is already being ingested.")

    # Clear existing vectors
    await asyncio.to_thread(vector_store.delete_document, doc.id)

    doc.status = DocumentStatus.PENDING.value
    doc.chunk_count = None
    doc.error_message = None
    await db.commit()

    asyncio.create_task(ingest_document(doc.id, doc.file_path, doc.file_type, doc.name))

    return {"status": "reindex started", "document_id": document_id}
