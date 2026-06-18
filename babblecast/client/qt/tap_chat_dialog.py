"""Private Tap chat — clear, messages, tap notes, save-on-close."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from babblecast.active_tap_chats import get_active_tap_chat_store
from babblecast.client.bridge import BridgeManager
from babblecast.client.qt.confirm_dialog import ConfirmCheckboxDialog
from babblecast.client.qt.tap_note_dialog import TapNoteComposeDialog, TapNoteViewDialog
from babblecast.client.qt.tap_notes_bar import TapNotesBar
from babblecast.config import get_settings, save_settings
from babblecast.constants import UI_MUTED_RED, UI_SUNFLOWER
from babblecast.taps import SavedTap, get_tap_store


class TapChatDialog(QDialog):
    def __init__(
        self,
        bridge: BridgeManager,
        link_id: str,
        tap_id: str,
        peer_id: str,
        peer_name: str,
        server_label: str,
        *,
        on_delete_tap_note: Callable[[str], None],
        on_notes_changed: Callable[[], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._link_id = link_id
        self._tap_id = tap_id
        self._peer_id = peer_id
        self._peer_name = peer_name
        self._server_label = server_label
        self._messages: list[dict] = []
        self._suppress_close_prompt = False
        self._note_added = False
        self._on_delete_tap_note = on_delete_tap_note
        self._on_notes_changed = on_notes_changed

        self.setWindowTitle(f"Tap — {peer_name}")
        self.setMinimumSize(440, 520)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Private tap with <b>{peer_name}</b> on {server_label}"))

        toolbar = QHBoxLayout()
        toolbar.addStretch()
        clear_btn = QPushButton("Clear Chat")
        clear_btn.setStyleSheet(
            f"QPushButton {{ background-color: {UI_MUTED_RED}; color: #1a1b26; font-weight: 700; padding: 4px 10px; border: none; border-radius: 6px; }}"
        )
        clear_btn.clicked.connect(self._clear_chat)
        add_btn = QPushButton("+ Tap Note")
        add_btn.setStyleSheet(
            f"QPushButton {{ background-color: {UI_SUNFLOWER}; color: #1a1b26; font-weight: 700; padding: 4px 10px; border: none; border-radius: 6px; }}"
        )
        add_btn.clicked.connect(self._compose_tap_note)
        toolbar.addWidget(clear_btn)
        toolbar.addWidget(add_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        layout.addWidget(self._log, stretch=1)

        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Tap message…")
        self._input.returnPressed.connect(self._send)
        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self._send)
        row.addWidget(self._input)
        row.addWidget(send_btn)
        layout.addLayout(row)

        self._notes_bar = TapNotesBar(
            on_add=self._compose_tap_note,
            on_delete=self._delete_tap_note,
            on_view=self._view_tap_note,
            peer_id=peer_id,
        )
        layout.addWidget(self._notes_bar)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        buttons.accepted.connect(self.close)
        layout.addWidget(buttons)

        self._bridge.open_tap(link_id, tap_id)
        self._bridge.clear_pending_tap(link_id, peer_id)
        self._load_persisted_messages()
        self._notes_bar.refresh()

    def _load_persisted_messages(self) -> None:
        chat = get_active_tap_chat_store().get(self._tap_id)
        if not chat:
            return
        self._messages = list(chat.messages)
        for msg in self._messages:
            name = msg.get("name", "?")
            text = msg.get("text", "")
            ts = msg.get("ts", "")
            self._log.append(f"<b>[{ts}] {name}</b>: {text}")

    def append_message(self, data: dict) -> None:
        name = data.get("name", "?")
        text = data.get("text", "")
        ts = datetime.now().strftime("%H:%M")
        entry = {"name": name, "text": text, "ts": ts}
        if not self._messages or self._messages[-1] != entry:
            self._messages.append(entry)
        self._log.append(f"<b>[{ts}] {name}</b>: {text}")

    def _send(self) -> None:
        text = self._input.text().strip()
        if text:
            self._bridge.send_tap_chat(self._link_id, self._tap_id, text)
            self._input.clear()

    def _clear_chat(self) -> None:
        settings = get_settings()
        if not settings.skip_clear_chat_confirm:
            dlg = ConfirmCheckboxDialog(
                "Clear Chat",
                "Clear all messages in this tap chat?",
                confirm_label="Clear",
                confirm_style="color: #f7768e; font-weight: 600;",
                parent=self,
            )
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            if dlg.skip_future:
                settings.skip_clear_chat_confirm = True
                save_settings(settings)
        get_active_tap_chat_store().clear_messages(self._tap_id)
        self._messages.clear()
        self._log.clear()

    def _compose_tap_note(self) -> None:
        dlg = TapNoteComposeDialog(
            default_subject=f"Follow up with {self._peer_name}",
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        get_tap_store().add(
            SavedTap.create(
                peer_id=self._peer_id,
                peer_name=self._peer_name,
                server_label=self._server_label,
                subject=dlg.subject,
                detail=dlg.detail,
            )
        )
        self._note_added = True
        self._notify_notes_changed()

    def _view_tap_note(self, save_id: str) -> None:
        tap = get_tap_store().get(save_id)
        if not tap:
            return
        dlg = TapNoteViewDialog(tap, on_saved=self._notify_notes_changed, parent=self)
        dlg.exec()

    def _delete_tap_note(self, save_id: str) -> None:
        self._on_delete_tap_note(save_id)

    def refresh_notes(self) -> None:
        self._notes_bar.refresh()

    def _notify_notes_changed(self) -> None:
        self.refresh_notes()
        if self._on_notes_changed:
            self._on_notes_changed()

    def closeEvent(self, event) -> None:
        show_prompt = (
            not self._suppress_close_prompt
            and not self._bridge.shutting_down
            and not self._note_added
            and bool(self._messages)
        )
        if show_prompt:
            settings = get_settings()
            if not settings.skip_tap_note_save_confirm:
                dlg = ConfirmCheckboxDialog(
                    "+ Tap Note",
                    "Add a tap note from this conversation before closing?",
                    confirm_label="Add tap note",
                    cancel_label="Close without note",
                    parent=self,
                )
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    if dlg.skip_future:
                        settings.skip_tap_note_save_confirm = True
                        save_settings(settings)
                    self._compose_tap_note()
        self._log.clear()
        self._messages.clear()
        super().closeEvent(event)
