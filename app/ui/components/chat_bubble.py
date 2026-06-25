"""Chat message bubble with inline citation chips."""
from __future__ import annotations

from nicegui import ui

from app.schemas import Citation, MessageRead


def chat_bubble(message: MessageRead) -> None:
    """Render a single chat message with optional source citations."""
    is_user = message.role == "user"

    align = "items-end" if is_user else "items-start"
    with ui.column().classes(f"w-full {align} gap-1"):
        # Role label
        role_label = "You" if is_user else "Lumen"
        ui.label(role_label).classes("text-xs text-gray-400 px-1")

        # Bubble
        bubble_color = "bg-blue-600 text-white" if is_user else "bg-white border border-gray-200"
        max_w = "max-w-2xl"
        with ui.card().classes(f"{max_w} {bubble_color} shadow-sm"):
            if is_user:
                ui.label(message.content).classes("text-sm whitespace-pre-wrap")
            else:
                # Render markdown for assistant messages
                ui.markdown(message.content).classes("text-sm prose prose-sm max-w-none")

                # Citation chips
                if message.citations:
                    with ui.row().classes("flex-wrap gap-2 mt-2 pt-2 border-t border-gray-100"):
                        ui.label("Sources:").classes("text-xs text-gray-500 self-center")
                        for citation in message.citations:
                            _citation_chip(citation)


def _citation_chip(citation: Citation) -> None:
    label = f"{citation.document_name}  p.{citation.page_number}"

    with ui.element("div"):
        chip = (
            ui.chip(label, icon="description")
            .classes("text-xs cursor-pointer")
            .props("outline color=primary")
        )

        async def show_source(c: Citation = citation) -> None:
            with ui.dialog() as dialog, ui.card().classes("max-w-lg w-full"):
                with ui.row().classes("w-full items-center justify-between mb-2"):
                    ui.label(f"{c.document_name} — Page {c.page_number}").classes(
                        "font-semibold text-sm"
                    )
                    ui.button(icon="close", on_click=dialog.close).props("flat round dense")
                ui.separator()
                ui.label(c.chunk_text).classes("text-sm text-gray-700 whitespace-pre-wrap mt-2")
            dialog.open()

        chip.on("click", show_source)
