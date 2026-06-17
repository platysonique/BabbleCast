"""Compact meter + vertical volume slider row (DAW channel-strip style)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from babblecast.client.qt.vertical_meter import METER_HEIGHT, METER_WIDTH, VerticalMeter

_SLIDER_WIDTH = 28


class MeterVolumeStrip(QWidget):
    """Fixed-height row: level meter + optional vertical volume slider."""

    def __init__(
        self,
        *,
        volume_label: str = "Mic",
        show_volume: bool = True,
        on_volume=None,
        parent=None,
    ) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.meter = VerticalMeter()
        row.addWidget(self.meter, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._vol_slider: QSlider | None = None
        if show_volume:
            self._vol_slider = QSlider(Qt.Orientation.Vertical)
            self._vol_slider.setRange(0, 200)
            self._vol_slider.setFixedSize(_SLIDER_WIDTH, METER_HEIGHT)
            if on_volume:
                self._vol_slider.valueChanged.connect(on_volume)
            row.addWidget(self._vol_slider, alignment=Qt.AlignmentFlag.AlignVCenter)

        row.addStretch()
        root.addLayout(row)

        self._caption = QLabel(f"{volume_label} · 100%")
        self._caption.setStyleSheet("color: #a9b1d6; font-size: 11px;")
        root.addWidget(self._caption)

        self.setFixedHeight(METER_HEIGHT + 22)

    def set_meter_level(self, level: float) -> None:
        self.meter.set_level(level)

    def set_volume_percent(self, pct: int) -> None:
        if self._vol_slider is None:
            return
        self._vol_slider.blockSignals(True)
        self._vol_slider.setValue(int(pct))
        self._vol_slider.blockSignals(False)
        parts = self._caption.text().split("·", 1)
        name = parts[0].strip() if parts else "Mic"
        self._caption.setText(f"{name} · {int(pct)}%")

    def set_volume_label(self, text: str) -> None:
        parts = self._caption.text().split("·", 1)
        name = parts[0].strip() if parts else "Mic"
        self._caption.setText(f"{name} · {text}")
