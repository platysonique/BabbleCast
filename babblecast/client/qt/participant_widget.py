"""Participant row with voice meter and per-user controls."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSlider,
    QWidget,
)


class ParticipantWidget(QWidget):
    volume_changed = pyqtSignal(str, float)
    mute_toggled = pyqtSignal(str, bool)

    def __init__(self, client_id: str, name: str, is_self: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.client_id = client_id
        self._name = name
        self._is_self = is_self

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        self._name_label = QLabel(name)
        self._name_label.setMinimumWidth(100)
        layout.addWidget(self._name_label)

        self._meter = QProgressBar()
        self._meter.setRange(0, 100)
        self._meter.setValue(0)
        self._meter.setTextVisible(False)
        self._meter.setFixedHeight(12)
        layout.addWidget(self._meter, stretch=1)

        self._mute_btn = QPushButton("Mute")
        self._mute_btn.setCheckable(True)
        self._mute_btn.setFixedWidth(64)
        self._mute_btn.toggled.connect(self._on_mute)
        layout.addWidget(self._mute_btn)

        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 200)
        self._vol.setValue(100)
        self._vol.setFixedWidth(80)
        self._vol.valueChanged.connect(self._on_volume)
        layout.addWidget(self._vol)

        if is_self:
            self._mute_btn.setToolTip("Self mute — use PTT to talk while muted")

    def _on_mute(self, checked: bool) -> None:
        self.mute_toggled.emit(self.client_id, checked)

    def _on_volume(self, value: int) -> None:
        self.volume_changed.emit(self.client_id, value / 100.0)

    def update_state(
        self,
        name: str,
        voice_level: float,
        muted: bool,
        speaking: bool,
        volume: float,
    ) -> None:
        self._name = name
        suffix = " (you)" if self._is_self else ""
        tag = " 🔊" if speaking else ""
        mute_tag = " 🔇" if muted else ""
        self._name_label.setText(f"{name}{suffix}{tag}{mute_tag}")
        self._meter.setValue(int(min(100, voice_level * 100)))
        self._mute_btn.blockSignals(True)
        self._mute_btn.setChecked(muted)
        self._mute_btn.blockSignals(False)
        self._vol.blockSignals(True)
        self._vol.setValue(int(volume * 100))
        self._vol.blockSignals(False)
