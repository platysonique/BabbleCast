"""Participant row — speaking LED + double-click opens detail drawer."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

_SPEAKING_LED_ON = "#9ece6a"
_SPEAKING_LED_OFF = "#565f89"


class ParticipantWidget(QWidget):
    double_clicked = pyqtSignal(str)

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

        self._led = QLabel()
        self._led.setFixedSize(12, 12)
        self._set_speaking_led(False)
        layout.addWidget(self._led)

        self._name_label = QLabel(self._label_text())
        self._name_label.setMinimumWidth(100)
        layout.addWidget(self._name_label, stretch=1)

        if self._tapped:
            self._name_label.setStyleSheet("color: #e0af68;")

    def _set_speaking_led(self, speaking: bool) -> None:
        color = _SPEAKING_LED_ON if speaking else _SPEAKING_LED_OFF
        self._led.setStyleSheet(f"border-radius: 6px; background-color: {color};")

    def _label_text(self) -> str:
        suffix = " (you)" if self._is_self else ""
        tap = " · tapped" if self._tapped else ""
        return f"{self._display_name}{suffix}{tap}"

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.double_clicked.emit(self.composite_key)
        super().mouseDoubleClickEvent(event)

    def set_tapped(self, tapped: bool) -> None:
        self._tapped = tapped
        self._name_label.setText(self._label_text())
        if tapped:
            self._name_label.setStyleSheet("color: #e0af68;")
        else:
            self._name_label.setStyleSheet("")

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
        self._set_speaking_led(speaking)
        self._name_label.setText(self._label_text())

    @property
    def client_id(self) -> str:
        return self._client_id

    @property
    def is_self(self) -> bool:
        return self._is_self

    @property
    def server_label(self) -> str:
        return self._server_label

    def participant_snapshot(self) -> dict:
        return {
            "voice_level": self._voice_level,
            "speaking": self._speaking,
            "muted": self._muted,
            "volume": self._volume,
            "name": self._display_name,
            "tapped": self._tapped,
        }
