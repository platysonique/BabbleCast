"""Connected server row with per-link mute controls."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QContextMenuEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QWidget

from babblecast.constants import UI_ACTIVE_GREEN, UI_MUTED_RED


def _mute_button_style(muted: bool) -> str:
    bg = UI_MUTED_RED if muted else UI_ACTIVE_GREEN
    return (
        f"QPushButton {{ background-color: {bg}; color: #1a1b26; border: none;"
        f" border-radius: 6px; font-size: 14px; font-weight: 600; }}"
    )


class ServerLinkWidget(QWidget):
    selected = pyqtSignal(str)
    listen_mute_toggled = pyqtSignal(str, bool)
    mic_mute_toggled = pyqtSignal(str, bool)
    disconnect_requested = pyqtSignal(str)
    info_requested = pyqtSignal(str)

    def __init__(self, link_id: str, label: str, parent=None) -> None:
        super().__init__(parent)
        self.link_id = link_id
        self._label = QLabel(label)
        self._label.setToolTip("Right-click for server info")
        self._listen_btn = QPushButton("🔊")
        self._listen_btn.setCheckable(True)
        self._listen_btn.setToolTip("Mute listening to this server (red = muted, green = hearing)")
        self._listen_btn.setFixedWidth(40)
        self._mic_btn = QPushButton("🎤")
        self._mic_btn.setCheckable(True)
        self._mic_btn.setToolTip("Mute your mic to this server only (red = muted, green = live)")
        self._mic_btn.setFixedWidth(40)
        self._close_btn = QPushButton("✕")
        self._close_btn.setToolTip("Disconnect from this server")
        self._close_btn.setFixedWidth(28)
        self._close_btn.setStyleSheet(
            "QPushButton { color: #f7768e; font-weight: 700; font-size: 14px; border: none; }"
            "QPushButton:hover { color: #ff9eaa; }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self._label, stretch=1)
        layout.addWidget(self._listen_btn)
        layout.addWidget(self._mic_btn)
        layout.addWidget(self._close_btn)

        self._listen_btn.toggled.connect(self._listen_toggled)
        self._mic_btn.toggled.connect(self._mic_toggled)
        self._close_btn.clicked.connect(lambda: self.disconnect_requested.emit(self.link_id))
        self.set_listen_muted(False)
        self.set_mic_muted(False)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.link_id)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = QMenu(self)
        menu.addAction("Server info…", lambda: self.info_requested.emit(self.link_id))
        menu.exec(event.globalPos())

    def _listen_toggled(self, muted: bool) -> None:
        self.set_listen_muted(muted)
        self.listen_mute_toggled.emit(self.link_id, muted)

    def _mic_toggled(self, muted: bool) -> None:
        self.set_mic_muted(muted)
        self.mic_mute_toggled.emit(self.link_id, muted)

    def update_label(self, label: str) -> None:
        self._label.setText(label)

    def set_listen_muted(self, muted: bool) -> None:
        self._listen_btn.blockSignals(True)
        self._listen_btn.setChecked(muted)
        self._listen_btn.setText("🔇" if muted else "🔊")
        self._listen_btn.setStyleSheet(_mute_button_style(muted))
        self._listen_btn.blockSignals(False)

    def set_mic_muted(self, muted: bool) -> None:
        self._mic_btn.blockSignals(True)
        self._mic_btn.setChecked(muted)
        self._mic_btn.setText("🎤✕" if muted else "🎤")
        self._mic_btn.setStyleSheet(_mute_button_style(muted))
        self._mic_btn.blockSignals(False)

    def attach_midi_menus(self, midi, link_id: str, label: str) -> None:
        from babblecast.client.qt.midi.context_menus import attach_toggle_menu
        from babblecast.client.qt.midi.targets import MidiTarget, link_target

        attach_toggle_menu(
            self._listen_btn,
            midi,
            MidiTarget(
                link_target(link_id, "listen_mute"),
                f"{label} listen",
                "toggle",
                "link",
                link_id=link_id,
                link_label=label,
            ),
        )
        attach_toggle_menu(
            self._mic_btn,
            midi,
            MidiTarget(
                link_target(link_id, "mic_mute"),
                f"{label} mic",
                "toggle",
                "link",
                link_id=link_id,
                link_label=label,
            ),
        )

    def set_active(self, active: bool) -> None:
        self.setStyleSheet("background: #24283b;" if active else "")
