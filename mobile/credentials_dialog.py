"""Connect / host credential prompts — username not on main Connect screen."""

from __future__ import annotations

import socket
from typing import Callable

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField

from babblecast.config import get_settings, save_settings
from babblecast.constants import MAX_NAME_LEN


def _clean_name(text: str) -> str:
    return text.strip()[:MAX_NAME_LEN] or "Anonymous"


def prompt_connect(
    host: str,
    port: int,
    server_label: str,
    on_ok: Callable[[str, str], None],
    *,
    password_required: bool = False,
) -> None:
    settings = get_settings()
    default = settings.display_name or socket.gethostname()

    name_field = MDTextField(
        hint_text="Your display name",
        text=default,
        size_hint_y=None,
        height=dp(48),
    )
    password_field = MDTextField(
        hint_text="Server password",
        password=True,
        size_hint_y=None,
        height=dp(48),
    )
    body = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, adaptive_height=True)
    body.add_widget(
        MDTextField(text=f"{server_label}", readonly=True, size_hint_y=None, height=dp(44))
    )
    body.add_widget(name_field)
    if password_required:
        body.add_widget(password_field)
    holder: list[MDDialog] = []

    def dismiss() -> None:
        holder[0].dismiss()

    def accept(*_args) -> None:
        name = _clean_name(name_field.text)
        pwd = password_field.text if password_required else ""
        if password_required and not pwd:
            return
        settings.display_name = name
        save_settings(settings)
        dismiss()
        on_ok(name, pwd)

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


def prompt_host(on_ok: Callable[[str, str, str], None]) -> None:
    """Returns (server_name, display_name, password) via callback."""
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
    protect_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(4))
    protect_cb = MDCheckbox(size_hint=(None, None), size=(dp(32), dp(32)))
    protect_row.add_widget(protect_cb)
    protect_row.add_widget(MDLabel(text="Password protect", size_hint_x=1))
    password_field = MDTextField(
        hint_text="Password for clients",
        password=True,
        disabled=True,
        size_hint_y=None,
        height=dp(48),
    )

    def on_protect(_instance, value: bool) -> None:
        password_field.disabled = not value
        if not value:
            password_field.text = ""

    protect_cb.bind(active=on_protect)

    body = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, adaptive_height=True)
    body.add_widget(server_field)
    body.add_widget(name_field)
    body.add_widget(protect_row)
    body.add_widget(password_field)
    holder: list[MDDialog] = []

    def dismiss() -> None:
        holder[0].dismiss()

    def accept(*_args) -> None:
        server = server_field.text.strip()[:MAX_NAME_LEN]
        if not server:
            return
        name = _clean_name(name_field.text)
        pwd = password_field.text if protect_cb.active else ""
        if protect_cb.active and not pwd:
            return
        settings.hosted_server_name = server
        settings.display_name = name
        save_settings(settings)
        dismiss()
        on_ok(server, name, pwd)

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


def prompt_disconnect(server_label: str, on_confirm: Callable[[bool], None]) -> None:
    """Ask to disconnect; callback receives skip_future_confirms."""
    skip_cb = MDCheckbox(size_hint=(None, None), size=(dp(32), dp(32)))
    row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(4))
    row.add_widget(skip_cb)
    row.add_widget(MDLabel(text="Don't ask again", size_hint_x=1))
    body = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, adaptive_height=True)
    body.add_widget(MDLabel(text=f"Disconnect from “{server_label}”?", size_hint_y=None))
    body.add_widget(row)
    holder: list[MDDialog] = []

    def dismiss() -> None:
        holder[0].dismiss()

    def confirm(*_args) -> None:
        skip = bool(skip_cb.active)
        dismiss()
        on_confirm(skip)

    dialog = MDDialog(
        title="Disconnect",
        type="custom",
        content_cls=body,
        buttons=[
            MDFlatButton(text="Cancel", on_release=lambda *_: dismiss()),
            MDRaisedButton(
                text="Disconnect",
                md_bg_color=(0.97, 0.46, 0.56, 1),
                on_release=confirm,
            ),
        ],
    )
    holder.append(dialog)
    dialog.open()
