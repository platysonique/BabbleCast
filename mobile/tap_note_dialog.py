"""Tap note compose and view/edit dialogs (KivyMD mobile)."""

from __future__ import annotations

import time
from collections.abc import Callable

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField

from babblecast.taps import SavedTap, get_tap_store


def _warn(title: str, message: str) -> None:
    holder: list[MDDialog] = []

    def dismiss() -> None:
        holder[0].dismiss()

    dialog = MDDialog(
        title=title,
        text=message,
        buttons=[MDFlatButton(text="OK", on_release=lambda *_: dismiss())],
    )
    holder.append(dialog)
    dialog.open()


def prompt_compose_tap_note(
    *,
    default_subject: str = "",
    on_save: Callable[[str, str], None],
) -> None:
    subject = MDTextField(
        hint_text="Subject (required)",
        text=default_subject,
        size_hint_y=None,
        height=dp(48),
    )
    detail = MDTextField(
        hint_text="Details (optional)",
        multiline=True,
        max_text_length=4096,
        size_hint_y=None,
        height=dp(120),
    )
    content = MDBoxLayout(
        orientation="vertical",
        spacing=dp(8),
        size_hint_y=None,
        adaptive_height=True,
    )
    content.add_widget(subject)
    content.add_widget(detail)
    holder: list[MDDialog] = []

    def dismiss() -> None:
        holder[0].dismiss()

    def save(*_args) -> None:
        subj = subject.text.strip()
        if not subj:
            _warn("+ Tap Note", "Subject is required.")
            return
        dismiss()
        on_save(subj, detail.text.strip())

    dialog = MDDialog(
        title="+ Tap Note",
        type="custom",
        content_cls=content,
        buttons=[
            MDFlatButton(text="Cancel", on_release=lambda *_: dismiss()),
            MDRaisedButton(text="Save", on_release=save),
        ],
    )
    holder.append(dialog)
    dialog.open()


def show_tap_note_viewer(
    tap: SavedTap,
    *,
    on_saved: Callable[[], None] | None = None,
) -> None:
    holder: list[MDDialog] = []
    state = {"subject": tap.display_subject, "detail": tap.detail}

    subject_field = MDTextField(
        text=state["subject"],
        size_hint_y=None,
        height=dp(48),
        readonly=True,
    )
    detail_field = MDTextField(
        text=state["detail"],
        multiline=True,
        size_hint_y=None,
        height=dp(140),
        readonly=True,
    )
    meta = MDLabel(
        text=f"{tap.peer_name} · {tap.server_label}",
        theme_text_color="Secondary",
        size_hint_y=None,
        height=dp(24),
    )
    content = MDBoxLayout(
        orientation="vertical",
        spacing=dp(8),
        size_hint_y=None,
        adaptive_height=True,
    )
    content.add_widget(meta)
    content.add_widget(MDLabel(text="Subject", size_hint_y=None, height=dp(20)))
    content.add_widget(subject_field)
    content.add_widget(MDLabel(text="Details", size_hint_y=None, height=dp(20)))
    content.add_widget(detail_field)

    def dismiss() -> None:
        holder[0].dismiss()

    def set_readonly(readonly: bool) -> None:
        subject_field.readonly = readonly
        detail_field.readonly = readonly

    def rebuild_buttons(view_mode: bool) -> None:
        holder[0].buttons.clear_widgets()
        if view_mode:
            holder[0].buttons.add_widget(
                MDRaisedButton(text="Edit", on_release=lambda *_: enter_edit())
            )
            holder[0].buttons.add_widget(
                MDFlatButton(text="Close", on_release=lambda *_: dismiss())
            )
        else:
            holder[0].buttons.add_widget(
                MDFlatButton(text="Cancel", on_release=lambda *_: cancel_edit())
            )
            holder[0].buttons.add_widget(
                MDRaisedButton(text="Save", on_release=lambda *_: commit(close_after=False))
            )
            holder[0].buttons.add_widget(
                MDRaisedButton(text="Save & Exit", on_release=lambda *_: commit(close_after=True))
            )

    def enter_edit() -> None:
        set_readonly(False)
        rebuild_buttons(view_mode=False)

    def cancel_edit() -> None:
        subject_field.text = state["subject"]
        detail_field.text = state["detail"]
        set_readonly(True)
        rebuild_buttons(view_mode=True)

    def commit(*, close_after: bool) -> None:
        subj = subject_field.text.strip()
        if not subj:
            _warn("Tap Note", "Subject is required.")
            return
        body = detail_field.text.strip()
        if not get_tap_store().update(tap.save_id, subject=subj, detail=body):
            _warn("Tap Note", "Could not save this note.")
            return
        state["subject"] = subj
        state["detail"] = body
        tap.subject = subj
        tap.detail = body
        if on_saved:
            on_saved()
        if close_after:
            dismiss()
            return
        cancel_edit()

    dialog = MDDialog(
        title="Tap Note",
        type="custom",
        content_cls=content,
        buttons=[],
    )
    holder.append(dialog)
    rebuild_buttons(view_mode=True)
    dialog.open()


class TapNoteListRow(MDBoxLayout):
    """Double-tap row for opening a tap note."""

    def __init__(self, save_id: str, label: str, on_open: Callable[[str], None], **kwargs):
        super().__init__(size_hint_y=None, height=dp(32), spacing=dp(4), **kwargs)
        self._save_id = save_id
        self._on_open = on_open
        self._last_tap = 0.0
        from kivymd.uix.button import MDFlatButton

        self.add_widget(
            MDFlatButton(
                text=label,
                on_release=self._on_press,
            )
        )

    def _on_press(self, *_args) -> None:
        now = time.time()
        if now - self._last_tap < 0.35:
            self._on_open(self._save_id)
            self._last_tap = 0.0
        else:
            self._last_tap = now
