"""Radial master-output volume control (DAW-style knob)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QDial, QLabel, QVBoxLayout, QWidget


class VolumeKnob(QWidget):
    """0–200% master output; emits integer percent like the old horizontal slider."""

    valueChanged = pyqtSignal(int)

    def __init__(self, *, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        self._dial = QDial()
        self._dial.setObjectName("volumeKnob")
        self._dial.setRange(0, 200)
        self._dial.setValue(100)
        self._dial.setNotchesVisible(True)
        self._dial.setWrapping(False)
        self._dial.setFixedSize(64, 64)
        self._dial.setToolTip("Master output volume")
        self._dial.valueChanged.connect(self._emit_value)

        self._label = QLabel("100%")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("color: #a9b1d6; font-size: 10px;")

        root.addWidget(self._dial, alignment=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        root.addWidget(self._label, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.setFixedWidth(72)

    def value(self) -> int:
        return int(self._dial.value())

    def setValue(self, value: int) -> None:
        self._dial.blockSignals(True)
        self._dial.setValue(int(value))
        self._dial.blockSignals(False)
        self._label.setText(f"{int(value)}%")

    def blockSignals(self, block: bool) -> bool:
        return self._dial.blockSignals(block)

    def _emit_value(self, value: int) -> None:
        self._label.setText(f"{int(value)}%")
        self.valueChanged.emit(int(value))
