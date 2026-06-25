from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas import (
    Citation,
    MessageRead,
    QueryRequest,
    QueryResponse,
    SessionCreate,
    SessionRead,
)
from app.services import chat_history, rag

router = APIRouter()


@router.post("/sessions", response_model=SessionRead, status_code=201)
async def create_session(
    data: SessionCreate, db: AsyncSession = Depends(get_db)
) -> SessionRead:
    session = await chat_history.create_session(db, data.title)
    await db.commit()
    return SessionRead(id=session.id, title=session.title, created_at=session.created_at, message_count=0)


@router.get("/sessions", response_model=list[SessionRead])
async def list_sessions(db: AsyncSession = Depends(get_db)) -> list[SessionRead]:
    sessions = await chat_history.list_sessions(db)
    result = []
    for s in sessions:
        count = await chat_history.count_messages(db, s.id)
        result.append(SessionRead(id=s.id, title=s.title, created_at=s.created_at, message_count=count))
    return result


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)) -> None:
    deleted = await chat_history.delete_session(db, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found.")
    await db.commit()


@router.get("/sessions/{session_id}/messages", response_model=list[MessageRead])
async def get_messages(session_id: str, db: AsyncSession = Depends(get_db)) -> list[MessageRead]:
    session = await chat_history.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = await chat_history.get_messages(db, session_id)
    result = []
    for m in messages:
        citations: list[Citation] = []
        if m.citations_json:
            try:
                citations = [Citation(**c) for c in json.loads(m.citations_json)]
            except Exception:
                pass
        result.append(
            MessageRead(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                citations=citations,
            )
        )
    return result


@router.post("/query", response_model=QueryResponse)
async def query_documents(
    request: QueryRequest, db: AsyncSession = Depends(get_db)
) -> QueryResponse:
    # Auto-create session if none provided
    if not request.session_id:
        title = request.question[:60] + ("…" if len(request.question) > 60 else "")
        session = await chat_history.create_session(db, title)
        await db.commit()
        request = request.model_copy(update={"session_id": session.id})
    else:
        session = await chat_history.get_session(db, request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")

    # Persist user message
    await chat_history.add_message(db, request.session_id, "user", request.question)
    await db.commit()

    # Run RAG pipeline
    response = await rag.query(request, db)

    # Persist assistant message with citations
    await chat_history.add_message(
        db, request.session_id, "assistant", response.answer, response.citations
    )
    await db.commit()

    return response
