"""Q&A chat page."""
from __future__ import annotations

import json

from nicegui import ui

from app.database import AsyncSessionLocal
from app.models import ChatSession, Document
from app.schemas import Citation, DocumentStatus, MessageRead, QueryRequest
from app.services import chat_history, rag
from sqlalchemy import select


async def _get_ready_documents() -> list[Document]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document)
            .where(Document.status == DocumentStatus.READY.value)
            .order_by(Document.name)
        )
        return list(result.scalars().all())


async def _get_sessions() -> list[ChatSession]:
    async with AsyncSessionLocal() as db:
        return await chat_history.list_sessions(db)


async def render() -> None:
    """Render the chat page body."""
    # Per-connection state (local variables are scoped to each browser tab)
    current_session_id: str | None = None
    selected_doc_ids: list[str] = []

    # ── Layout ────────────────────────────────────────────────────────────────
    with ui.row().classes("w-full h-full gap-0"):

        # ── Session sidebar ───────────────────────────────────────────────────
        with ui.column().classes("w-64 shrink-0 border-r border-gray-200 bg-gray-50 h-full p-3 gap-2"):
            ui.button(
                "New Chat",
                icon="add",
                on_click=lambda: _new_session(),
            ).props("outline").classes("w-full")

            ui.separator()
            ui.label("Recent Sessions").classes("text-xs text-gray-400 font-semibold uppercase tracking-wide px-1")

            session_list_area = ui.column().classes("w-full gap-1")

        # ── Chat area ─────────────────────────────────────────────────────────
        with ui.column().classes("flex-1 h-full"):

            # Document scope selector
            with ui.row().classes("w-full items-center gap-3 px-4 py-2 border-b border-gray-100 bg-white"):
                ui.icon("filter_list").classes("text-gray-400")
                ui.label("Scope:").classes("text-sm text-gray-500")
                doc_select = ui.select(
                    options={"__all__": "All Documents"},
                    multiple=True,
                    label="",
                ).props("dense outlined").classes("flex-1 max-w-md")
                doc_select.value = []

            # Messages
            messages_scroll = ui.scroll_area().classes("flex-1 w-full")
            with messages_scroll:
                messages_area = ui.column().classes("w-full p-4 gap-4")

            # Input
            with ui.row().classes("w-full items-end gap-3 px-4 py-3 border-t border-gray-100 bg-white"):
                input_field = (
                    ui.textarea(placeholder="Ask a question about your documents…")
                    .props("outlined autogrow rows=1")
                    .classes("flex-1")
                )
                send_btn = ui.button(icon="send", on_click=lambda: _send()).props("color=primary round")

    # ── Populate document selector ────────────────────────────────────────────
    async def refresh_doc_options() -> None:
        docs = await _get_ready_documents()
        options: dict[str, str] = {"__all__": "All Documents"}
        for d in docs:
            options[d.id] = d.name
        doc_select.options = options

    await refresh_doc_options()

    # ── Populate session list ─────────────────────────────────────────────────
    @ui.refreshable
    async def render_sessions() -> None:
        session_list_area.clear()
        sessions = await _get_sessions()
        with session_list_area:
            if not sessions:
                ui.label("No sessions yet").classes("text-xs text-gray-400 px-2 py-1")
                return
            for s in sessions:
                with ui.row().classes("w-full items-center group"):
                    is_active = s.id == current_session_id
                    btn_cls = (
                        "flex-1 text-left text-sm truncate rounded-lg px-2 py-1 "
                        + ("bg-blue-100 text-blue-700" if is_active else "hover:bg-gray-100 text-gray-700")
                    )
                    ui.button(
                        s.title[:35] + ("…" if len(s.title) > 35 else ""),
                        on_click=lambda sid=s.id: _load_session(sid),
                    ).props("flat no-caps align=left").classes(btn_cls)
                    (
                        ui.button(icon="delete_outline", on_click=lambda sid=s.id: _delete_session(sid))
                        .props("flat round dense color=negative")
                        .classes("opacity-0 group-hover:opacity-100")
                        .tooltip("Delete session")
                    )

    await render_sessions()

    # ── Message rendering ─────────────────────────────────────────────────────
    def _render_message(role: str, content: str, citations: list[Citation] | None = None) -> None:
        is_user = role == "user"
        align = "items-end" if is_user else "items-start"

        with messages_area:
            with ui.column().classes(f"w-full {align} gap-1"):
                ui.label("You" if is_user else "Lumen").classes("text-xs text-gray-400 px-1")
                bubble_cls = (
                    "max-w-2xl shadow-sm "
                    + ("bg-blue-600 text-white" if is_user else "bg-white border border-gray-200")
                )
                with ui.card().classes(bubble_cls):
                    if is_user:
                        ui.label(content).classes("text-sm whitespace-pre-wrap")
                    else:
                        ui.markdown(content).classes("text-sm prose prose-sm max-w-none")
                        if citations:
                            with ui.row().classes("flex-wrap gap-2 mt-2 pt-2 border-t border-gray-100"):
                                ui.label("Sources:").classes("text-xs text-gray-500 self-center")
                                for c in citations:
                                    _citation_chip(c)

    def _citation_chip(citation: Citation) -> None:
        chip = (
            ui.chip(f"{citation.document_name}  p.{citation.page_number}", icon="description")
            .props("outline color=primary")
            .classes("text-xs cursor-pointer")
        )

        async def show_source() -> None:
            with ui.dialog() as dlg, ui.card().classes("max-w-lg w-full"):
                with ui.row().classes("w-full items-center justify-between mb-2"):
                    ui.label(f"{citation.document_name} — Page {citation.page_number}").classes(
                        "font-semibold text-sm"
                    )
                    ui.button(icon="close", on_click=dlg.close).props("flat round dense")
                ui.separator()
                ui.label(citation.chunk_text).classes("text-sm text-gray-700 whitespace-pre-wrap mt-2")
            dlg.open()

        chip.on("click", show_source)

    # ── Actions ───────────────────────────────────────────────────────────────
    async def _new_session() -> None:
        nonlocal current_session_id
        current_session_id = None
        messages_area.clear()
        input_field.value = ""

    async def _load_session(session_id: str) -> None:
        nonlocal current_session_id
        current_session_id = session_id
        messages_area.clear()

        async with AsyncSessionLocal() as db:
            msgs = await chat_history.get_messages(db, session_id)

        for m in msgs:
            citations: list[Citation] = []
            if m.citations_json:
                try:
                    citations = [Citation(**c) for c in json.loads(m.citations_json)]
                except Exception:
                    pass
            _render_message(m.role, m.content, citations)

        messages_scroll.scroll_to(percent=1.0)
        await render_sessions.refresh()

    async def _delete_session(session_id: str) -> None:
        nonlocal current_session_id
        async with AsyncSessionLocal() as db:
            await chat_history.delete_session(db, session_id)
            await db.commit()
        if current_session_id == session_id:
            await _new_session()
        await render_sessions.refresh()

    async def _send() -> None:
        nonlocal current_session_id
        question = (input_field.value or "").strip()
        if not question:
            return

        input_field.value = ""
        input_field.disable()
        send_btn.disable()

        _render_message("user", question)

        # Resolve document scope
        scope = doc_select.value or []
        doc_ids = [v for v in scope if v != "__all__"] or None

        # Thinking indicator
        with messages_area:
            with ui.column().classes("w-full items-start gap-1"):
                ui.label("Lumen").classes("text-xs text-gray-400 px-1")
                with ui.card().classes("bg-white border border-gray-200 shadow-sm"):
                    with ui.row().classes("items-center gap-2 px-2 py-1"):
                        spinner = ui.spinner("dots", size="sm")
                        thinking_label = ui.label("Thinking…").classes("text-sm text-gray-400")
        thinking_card = messages_area.default_slot.children[-1]

        messages_scroll.scroll_to(percent=1.0)

        try:
            request = QueryRequest(
                session_id=current_session_id,
                question=question,
                document_ids=doc_ids,
            )

            async with AsyncSessionLocal() as db:
                # Auto-create session on first message
                if not current_session_id:
                    title = question[:60] + ("…" if len(question) > 60 else "")
                    session = await chat_history.create_session(db, title)
                    await db.commit()
                    current_session_id = session.id
                    request = request.model_copy(update={"session_id": current_session_id})

                await chat_history.add_message(db, current_session_id, "user", question)
                await db.commit()

                response = await rag.query(request, db)

                await chat_history.add_message(
                    db, current_session_id, "assistant", response.answer, response.citations
                )
                await db.commit()

            # Remove thinking indicator and show answer
            thinking_card.delete()
            _render_message("assistant", response.answer, response.citations)
            messages_scroll.scroll_to(percent=1.0)
            await render_sessions.refresh()

        except Exception as exc:
            thinking_card.delete()
            _render_message("assistant", f"⚠ An error occurred: {exc}")

        finally:
            input_field.enable()
            send_btn.enable()
            input_field.run_method("focus")

    # Ctrl+Enter to send
    input_field.on(
        "keydown.ctrl.enter",
        lambda: _send(),
    )
