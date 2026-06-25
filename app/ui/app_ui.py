"""
NiceGUI page registration and shared layout.

Call init_ui() once from main.py before ui.run_with().
All @ui.page decorators must be registered before the server starts.
"""
from __future__ import annotations

from nicegui import ui

from app.ui.pages import chat, settings as settings_page, workspace


def init_ui() -> None:
    """Register all application pages."""

    @ui.page("/")
    async def root() -> None:
        ui.navigate.to("/workspace")

    @ui.page("/workspace")
    async def workspace_route() -> None:
        _render_shell("workspace")
        with ui.column().classes("w-full p-6 gap-4"):
            await workspace.render()

    @ui.page("/chat")
    async def chat_route() -> None:
        _render_shell("chat")
        # Chat page manages its own full-height layout
        with ui.element("div").classes("w-full flex-1 flex overflow-hidden"):
            await chat.render()

    @ui.page("/settings")
    async def settings_route() -> None:
        _render_shell("settings")
        with ui.column().classes("w-full p-6 gap-4"):
            await settings_page.render()


def _render_shell(active: str) -> None:
    """Render the persistent header and left navigation drawer."""
    ui.query("body").classes(add="bg-gray-50")

    with ui.header(elevated=True).classes("bg-blue-700 text-white px-4 h-14 items-center"):
        with ui.row().classes("w-full h-full items-center gap-3"):
            ui.icon("wb_incandescent").classes("text-2xl text-yellow-300")
            ui.label("Lumen").classes("text-xl font-bold tracking-tight")
            ui.label("·").classes("opacity-40 text-lg")
            ui.label("Document Intelligence").classes("text-sm opacity-70 hidden sm:block")
            ui.space()
            # Quick nav links in header (visible on larger screens)
            for label, href, page in [
                ("Workspace", "/workspace", "workspace"),
                ("Chat", "/chat", "chat"),
                ("Settings", "/settings", "settings"),
            ]:
                btn_cls = "text-white text-sm hidden md:flex"
                active_cls = "underline underline-offset-4" if page == active else "opacity-70 hover:opacity-100"
                ui.button(
                    label,
                    on_click=lambda h=href: ui.navigate.to(h),
                ).props("flat no-caps").classes(f"{btn_cls} {active_cls}")

    with ui.left_drawer(fixed=True, value=True).classes(
        "bg-white border-r border-gray-200 pt-6 px-2 flex flex-col gap-1"
    ):
        _nav_item("Workspace", "/workspace", "folder_open", active == "workspace")
        _nav_item("Chat", "/chat", "chat_bubble_outline", active == "chat")
        ui.separator().classes("my-3")
        _nav_item("Settings", "/settings", "settings", active == "settings")


def _nav_item(label: str, href: str, icon: str, is_active: bool) -> None:
    active_cls = "bg-blue-50 text-blue-700 font-semibold"
    idle_cls = "text-gray-600 hover:bg-gray-100"
    cls = f"w-full rounded-lg {active_cls if is_active else idle_cls}"

    ui.button(
        label,
        icon=icon,
        on_click=(lambda h=href: ui.navigate.to(h)) if not is_active else None,
    ).props("flat no-caps align=left").classes(cls)
