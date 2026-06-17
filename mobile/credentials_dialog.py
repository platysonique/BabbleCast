"""Connect / host credential prompts — username not on main Connect screen."""

from __future__ import annotations

import socket
from typing import Callable

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.textfield import MDTextField

from babblecast.config import get_settings, save_settings
from babblecast.constants import MAX_NAME_LEN


def _clean_name(text: str) -> str:
    return text.strip()[:MAX_NAME_LEN] or "Anonymous"


def prompt_connect(host: str, port: int, server_label: str, on_ok: Callable[[str], None]) -> None:
    settings = get_settings()
    default = settings.display_name or socket.gethostname()

    name_field = MDTextField(
        hint_text="Your display name",
        text=default,
        size_hint_y=None,
        height=dp(48),
    )
    body = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, adaptive_height=True)
    body.add_widget(
        MDTextField(text=f"{server_label}", readonly=True, size_hint_y=None, height=dp(44))
    )
    body.add_widget(name_field)
    holder: list[MDDialog] = []

    def dismiss() -> None:
        holder[0].dismiss()

    def accept(*_args) -> None:
        name = _clean_name(name_field.text)
        settings.display_name = name
        save_settings(settings)
        dismiss()
        on_ok(name)

    dialog = MDDialog(
        title="Connect to server",
        type="custom",
        content_cls=body,
        buttons=[
            MDFlatButton(text="Cancel", on_release=lambda *_: dismiss()),
            MDRaisedButton(text="Connect", on_release=accept),
        ],
    )
    holder.append(dialog)
    name_field.bind(on_text_validate=accept)
    dialog.open()


def prompt_host(on_ok: Callable[[str, str], None]) -> None:
    """Returns (server_name, display_name) via callback."""
    settings = get_settings()
    server_field = MDTextField(
        hint_text="Server name (Discover)",
        text=settings.hosted_server_name or settings.display_name or socket.gethostname(),
        size_hint_y=None,
        height=dp(48),
    )
    name_field = MDTextField(
        hint_text="Your display name",
        text=settings.display_name or socket.gethostname(),
        size_hint_y=None,
        height=dp(48),
    )
    body = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, adaptive_height=True)
    body.add_widget(server_field)
    body.add_widget(name_field)
    holder: list[MDDialog] = []

    def dismiss() -> None:
        holder[0].dismiss()

    def accept(*_args) -> None:
        server = server_field.text.strip()[:MAX_NAME_LEN]
        if not server:
            return
        name = _clean_name(name_field.text)
        settings.hosted_server_name = server
        settings.display_name = name
        save_settings(settings)
        dismiss()
        on_ok(server, name)

    dialog = MDDialog(
        title="Host server",
        type="custom",
        content_cls=body,
        buttons=[
            MDFlatButton(text="Cancel", on_release=lambda *_: dismiss()),
            MDRaisedButton(text="Start", on_release=accept),
        ],
    )
    holder.append(dialog)
    dialog.open()
