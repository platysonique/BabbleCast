"""Private Tap chat dialog with save-on-close flow."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from babblecast.client.bridge import BridgeManager
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
        self._saved_on_close = False

        self.setWindowTitle(f"Tap — {peer_name}")
        self.setMinimumSize(420, 360)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Private tap with <b>{peer_name}</b> on {server_label}"))

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        layout.addWidget(self._log)

        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Tap message…")
        self._input.returnPressed.connect(self._send)
        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self._send)
        row.addWidget(self._input)
        row.addWidget(send_btn)
        layout.addLayout(row)

        save_btn = QPushButton("Save Tap (reminder)")
        save_btn.clicked.connect(self._save_tap_now)
        layout.addWidget(save_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        buttons.accepted.connect(self.close)
        layout.addWidget(buttons)

        self._bridge.open_tap(link_id, tap_id)
        self._bridge.clear_pending_tap(link_id, peer_id)

    def append_message(self, data: dict) -> None:
        name = data.get("name", "?")
        text = data.get("text", "")
        ts = datetime.now().strftime("%H:%M")
        self._messages.append({"name": name, "text": text, "ts": ts})
        self._log.append(f"<b>[{ts}] {name}</b>: {text}")

    def _send(self) -> None:
        text = self._input.text().strip()
        if text:
            self._bridge.send_tap_chat(self._link_id, self._tap_id, text)
            self._input.clear()

    def _save_tap_now(self) -> None:
        reminder, ok = QInputDialog.getText(
            self,
            "Save Tap",
            "Reminder note for this tap:",
            text=f"Follow up with {self._peer_name}",
        )
        if ok and reminder.strip():
            get_tap_store().add(
                SavedTap.create(
                    peer_id=self._peer_id,
                    peer_name=self._peer_name,
                    server_label=self._server_label,
                    reminder=reminder.strip(),
                    messages=list(self._messages),
                )
            )
            QMessageBox.information(self, "Tap saved", "Reminder saved to your tap list.")
            self._saved_on_close = True

    def closeEvent(self, event) -> None:
        if not self._saved_on_close and self._messages:
            reply = QMessageBox.question(
                self,
                "Save tap?",
                "Save this tap as a reminder before closing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                reminder, ok = QInputDialog.getText(
                    self,
                    "Save Tap",
                    "Describe this tap reminder:",
                    text=f"Follow up with {self._peer_name}",
                )
                if ok and reminder.strip():
                    get_tap_store().add(
                        SavedTap.create(
                            peer_id=self._peer_id,
                            peer_name=self._peer_name,
                            server_label=self._server_label,
                            reminder=reminder.strip(),
                            messages=list(self._messages),
                        )
                    )
                    self._saved_on_close = True
        self._bridge.end_tap(self._link_id, self._tap_id)
        self._log.clear()
        self._messages.clear()
        super().closeEvent(event)
