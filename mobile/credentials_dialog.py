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
from babblecast.constants import MAX_NAME_LEN, MAX_ROOM_NAME_LEN

_ERROR_COLOR = (0.97, 0.46, 0.56, 1)


def _clean_name(text: str) -> str:
    return text.strip()[:MAX_NAME_LEN] or "Anonymous"


def _error_label() -> MDLabel:
    return MDLabel(
        text="",
        theme_text_color="Custom",
        text_color=_ERROR_COLOR,
        font_style="Caption",
        size_hint_y=None,
        height=0,
    )


def _set_error(label: MDLabel, message: str) -> None:
    if message:
        label.text = message
        label.height = dp(20)
    else:
        label.text = ""
        label.height = 0


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
        hint_text="Server password (optional)" if not password_required else "Server password",
        password=True,
        size_hint_y=None,
        height=dp(48),
    )
    error_label = _error_label()
    body = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, adaptive_height=True)
    body.add_widget(
        MDTextField(text=f"{server_label}", readonly=True, size_hint_y=None, height=dp(44))
    )
    body.add_widget(name_field)
    if password_required:
        body.add_widget(password_field)
    body.add_widget(error_label)
    holder: list[MDDialog] = []

    def dismiss() -> None:
        holder[0].dismiss()

    def accept(*_args) -> None:
        name = _clean_name(name_field.text)
        pwd = password_field.text if password_required and password_field.text.strip() else ""
        if password_required and not pwd:
            _set_error(error_label, "Enter the server password.")
            return
        _set_error(error_label, "")
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
    protect_row.add_widget(MDLabel(text="Host password", size_hint_x=1))
    password_field = MDTextField(
        hint_text="Your password — guests need it to join; you need it for admin",
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

    error_label = _error_label()
    body = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, adaptive_height=True)
    body.add_widget(server_field)
    body.add_widget(name_field)
    body.add_widget(
        MDLabel(
            text="Your phone's LAN address is advertised automatically on this Wi‑Fi.",
            theme_text_color="Custom",
            text_color=(0.6, 0.65, 0.75, 1),
            font_style="Caption",
            size_hint_y=None,
        )
    )
    body.add_widget(protect_row)
    body.add_widget(password_field)
    body.add_widget(error_label)
    holder: list[MDDialog] = []

    def dismiss() -> None:
        holder[0].dismiss()

    def accept(*_args) -> None:
        server = server_field.text.strip()[:MAX_NAME_LEN]
        if not server:
            _set_error(error_label, "Enter a server name.")
            return
        name = _clean_name(name_field.text)
        pwd = password_field.text if protect_cb.active else ""
        if protect_cb.active and not pwd.strip():
            _set_error(error_label, "Enter a host password or turn off protection.")
            return
        _set_error(error_label, "")
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


def prompt_create_room(default_name: str, on_ok: Callable[[str, str], None]) -> None:
    """Returns (room_name, password) — password empty when not protected."""
    name_field = MDTextField(
        hint_text="Room name",
        text=default_name,
        size_hint_y=None,
        height=dp(48),
    )
    protect_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(4))
    protect_cb = MDCheckbox(size_hint=(None, None), size=(dp(32), dp(32)))
    protect_row.add_widget(protect_cb)
    protect_row.add_widget(MDLabel(text="Password protect", size_hint_x=1))
    password_field = MDTextField(
        hint_text="Room password",
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

    error_label = _error_label()
    body = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, adaptive_height=True)
    body.add_widget(name_field)
    body.add_widget(
        MDLabel(
            text="Only you can delete a room you create. Others need the password to enter.",
            theme_text_color="Custom",
            text_color=(0.6, 0.65, 0.75, 1),
            font_style="Caption",
            size_hint_y=None,
        )
    )
    body.add_widget(protect_row)
    body.add_widget(password_field)
    body.add_widget(error_label)
    holder: list[MDDialog] = []

    def dismiss() -> None:
        holder[0].dismiss()

    def accept(*_args) -> None:
        name = name_field.text.strip()[:MAX_ROOM_NAME_LEN]
        if not name:
            _set_error(error_label, "Enter a room name.")
            return
        pwd = password_field.text if protect_cb.active else ""
        if protect_cb.active and not pwd.strip():
            _set_error(error_label, "Enter a password or turn off protection.")
            return
        _set_error(error_label, "")
        dismiss()
        on_ok(name, pwd if protect_cb.active else "")

    dialog = MDDialog(
        title="Create room",
        type="custom",
        content_cls=body,
        buttons=[
            MDFlatButton(text="Cancel", on_release=lambda *_: dismiss()),
            MDRaisedButton(text="Create", on_release=accept),
        ],
    )
    holder.append(dialog)
    dialog.open()


def prompt_room_password(
    room_name: str,
    on_ok: Callable[[str], None],
    *,
    title: str = "Room password",
    hint: str = "Room password",
) -> None:
    password_field = MDTextField(
        hint_text=hint,
        password=True,
        size_hint_y=None,
        height=dp(48),
    )
    error_label = _error_label()
    body = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, adaptive_height=True)
    body.add_widget(
        MDTextField(text=room_name, readonly=True, size_hint_y=None, height=dp(44))
    )
    body.add_widget(password_field)
    body.add_widget(error_label)
    holder: list[MDDialog] = []

    def dismiss() -> None:
        holder[0].dismiss()

    def accept(*_args) -> None:
        pwd = password_field.text.strip()
        if not pwd:
            _set_error(error_label, "Enter the room password.")
            return
        _set_error(error_label, "")
        dismiss()
        on_ok(pwd)

    dialog = MDDialog(
        title=title,
        type="custom",
        content_cls=body,
        buttons=[
            MDFlatButton(text="Cancel", on_release=lambda *_: dismiss()),
            MDRaisedButton(text="Join", on_release=accept),
        ],
    )
    holder.append(dialog)
    password_field.bind(on_text_validate=accept)
    dialog.open()


def prompt_host_password(
    on_ok: Callable[[str], None],
    *,
    title: str = "Host password",
    hint: str = "Your host password",
) -> None:
    password_field = MDTextField(
        hint_text=hint,
        password=True,
        size_hint_y=None,
        height=dp(48),
    )
    error_label = _error_label()
    body = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, adaptive_height=True)
    body.add_widget(
        MDLabel(
            text="Enter the password you set when hosting this server.",
            theme_text_color="Custom",
            text_color=(0.6, 0.65, 0.75, 1),
            font_style="Caption",
            size_hint_y=None,
        )
    )
    body.add_widget(password_field)
    body.add_widget(error_label)
    holder: list[MDDialog] = []

    def dismiss() -> None:
        holder[0].dismiss()

    def accept(*_args) -> None:
        pwd = password_field.text.strip()
        if not pwd:
            _set_error(error_label, "Enter your host password.")
            return
        _set_error(error_label, "")
        dismiss()
        on_ok(pwd)

    dialog = MDDialog(
        title=title,
        type="custom",
        content_cls=body,
        buttons=[
            MDFlatButton(text="Cancel", on_release=lambda *_: dismiss()),
            MDRaisedButton(text="Confirm", on_release=accept),
        ],
    )
    holder.append(dialog)
    password_field.bind(on_text_validate=accept)
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
                md_bg_color=_ERROR_COLOR,
                on_release=confirm,
            ),
        ],
    )
    holder.append(dialog)
    dialog.open()
