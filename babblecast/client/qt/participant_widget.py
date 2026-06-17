"""Participant row — name only; details via context menu."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMenu, QWidget

from babblecast.client.qt.participant_details_dialog import ParticipantDetailsDialog


class ParticipantWidget(QWidget):
    volume_changed = pyqtSignal(str, float)
    mute_toggled = pyqtSignal(str, bool)
    tap_requested = pyqtSignal(str)
    reopen_tap_chat = pyqtSignal(str, str)

    def __init__(
        self,
        composite_key: str,
        name: str,
        server_label: str,
        is_self: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.composite_key = composite_key
        self._client_id = composite_key.split(":", 1)[-1]
        self._display_name = name
        self._server_label = server_label
        self._is_self = is_self
        self._tapped = False
        self._voice_level = 0.0
        self._muted = False
        self._speaking = False
        self._volume = 1.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        self._name_label = QLabel(self._label_text())
        self._name_label.setMinimumWidth(100)
        layout.addWidget(self._name_label, stretch=1)

    def _label_text(self) -> str:
        suffix = " (you)" if self._is_self else ""
        return f"{self._display_name}{suffix}"

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.addAction("More details", self._show_details)
        menu.exec(event.globalPos())

    def _show_details(self) -> None:
        dlg = ParticipantDetailsDialog(
            self.composite_key,
            self._display_name,
            self._server_label,
            is_self=self._is_self,
            voice_level=self._voice_level,
            muted=self._muted,
            speaking=self._speaking,
            volume=self._volume,
            tapped=self._tapped,
            on_volume=lambda k, v: self.volume_changed.emit(k, v),
            on_mute=lambda k, m: self.mute_toggled.emit(k, m),
            on_tap=lambda cid: self.tap_requested.emit(cid),
            on_reopen_tap=lambda sid, cid: self.reopen_tap_chat.emit(sid, cid),
            parent=self.window(),
        )
        dlg.exec()

    def set_tapped(self, tapped: bool) -> None:
        self._tapped = tapped

    def update_state(
        self,
        name: str,
        voice_level: float,
        muted: bool,
        speaking: bool,
        volume: float,
        *,
        server_label: str | None = None,
    ) -> None:
        self._display_name = name
        if server_label is not None:
            self._server_label = server_label
        self._voice_level = voice_level
        self._muted = muted
        self._speaking = speaking
        self._volume = volume
        self._name_label.setText(self._label_text())
