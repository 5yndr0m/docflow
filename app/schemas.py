from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


# ── Document ──────────────────────────────────────────────────────────────────

class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    INGESTING = "ingesting"
    READY = "ready"
    ERROR = "error"


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    file_type: str
    file_path: str
    status: str
    chunk_count: int | None
    size_bytes: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime


# ── Internal chunk representation (not serialized to API) ─────────────────────

class ChunkData(BaseModel):
    document_id: str
    chunk_index: int
    text: str
    page_number: int
    metadata: dict[str, Any] = {}


# ── Chat ──────────────────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    title: str


class SessionRead(BaseModel):
    id: str
    title: str
    created_at: datetime
    message_count: int


class Citation(BaseModel):
    document_name: str
    page_number: int
    chunk_text: str


class MessageRead(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: datetime
    citations: list[Citation] = []


# ── RAG ───────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    session_id: str | None = None
    question: str
    document_ids: list[str] | None = None


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    model_used: str
    session_id: str | None = None


# ── Settings ──────────────────────────────────────────────────────────────────

class AppSettings(BaseModel):
    chat_model: str
    embed_model: str
    chunk_size: int
    chunk_overlap: int
    top_k: int


class ModelInfo(BaseModel):
    name: str
    size: int | None = None
    modified_at: str | None = None
