"""CRUD operations for chat sessions and messages."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatMessage, ChatSession
from app.schemas import Citation


async def create_session(db: AsyncSession, title: str) -> ChatSession:
    session = ChatSession(
        id=str(uuid.uuid4()),
        title=title[:200],
        created_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.flush()
    return session


async def get_session(db: AsyncSession, session_id: str) -> ChatSession | None:
    return await db.get(ChatSession, session_id)


async def list_sessions(db: AsyncSession, limit: int = 50) -> list[ChatSession]:
    result = await db.execute(
        select(ChatSession).order_by(ChatSession.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def delete_session(db: AsyncSession, session_id: str) -> bool:
    session = await db.get(ChatSession, session_id)
    if not session:
        return False
    await db.delete(session)
    return True


async def count_messages(db: AsyncSession, session_id: str) -> int:
    result = await db.execute(
        select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == session_id)
    )
    return result.scalar() or 0


async def add_message(
    db: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    citations: list[Citation] | None = None,
) -> ChatMessage:
    msg = ChatMessage(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role=role,
        content=content,
        citations_json=json.dumps([c.model_dump() for c in citations]) if citations else None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    await db.flush()
    return msg


async def get_messages(db: AsyncSession, session_id: str) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    return list(result.scalars().all())


async def get_recent_messages_for_llm(
    db: AsyncSession, session_id: str, limit: int = 10
) -> list[dict]:
    """Return the most recent messages in the {role, content} format the LLM expects."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = list(reversed(result.scalars().all()))
    return [{"role": m.role, "content": m.content} for m in messages]
