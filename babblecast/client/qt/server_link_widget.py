"""Connected server row with per-link mute controls."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class ServerLinkWidget(QWidget):
    selected = pyqtSignal(str)
    listen_mute_toggled = pyqtSignal(str, bool)
    mic_mute_toggled = pyqtSignal(str, bool)
    disconnect_requested = pyqtSignal(str)

    def __init__(self, link_id: str, label: str, parent=None) -> None:
        super().__init__(parent)
        self.link_id = link_id
        self._label = QLabel(label)
        self._listen_btn = QPushButton("🔊")
        self._listen_btn.setCheckable(True)
        self._listen_btn.setToolTip("Mute listening to this server")
        self._listen_btn.setFixedWidth(36)
        self._mic_btn = QPushButton("🎤")
        self._mic_btn.setCheckable(True)
        self._mic_btn.setToolTip("Mute your mic to this server only")
        self._mic_btn.setFixedWidth(36)
        self._close_btn = QPushButton("Disconnect")
        self._close_btn.setToolTip("Disconnect from this server")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self._label, stretch=1)
        layout.addWidget(self._listen_btn)
        layout.addWidget(self._mic_btn)
        layout.addWidget(self._close_btn)

        self._listen_btn.toggled.connect(lambda c: self.listen_mute_toggled.emit(self.link_id, c))
        self._mic_btn.toggled.connect(lambda c: self.mic_mute_toggled.emit(self.link_id, c))
        self._close_btn.clicked.connect(lambda: self.disconnect_requested.emit(self.link_id))
        self.mousePressEvent = lambda _e: self.selected.emit(self.link_id)  # type: ignore[method-assign]

    def update_label(self, label: str) -> None:
        self._label.setText(label)

    def set_active(self, active: bool) -> None:
        self.setStyleSheet("background: #24283b;" if active else "")
