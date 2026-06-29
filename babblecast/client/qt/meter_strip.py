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
        compact: bool = False,
        on_volume=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._compact = compact
        self._volume_name = volume_label

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4 if not compact else 0)

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
            self._vol_slider.setToolTip(f"{volume_label} input volume")
            if on_volume:
                self._vol_slider.valueChanged.connect(on_volume)
            row.addWidget(self._vol_slider, alignment=Qt.AlignmentFlag.AlignVCenter)

        if not compact:
            row.addStretch()
        root.addLayout(row)

        self._caption: QLabel | None = None
        if not compact:
            self._caption = QLabel(f"{volume_label} · 100%")
            self._caption.setStyleSheet("color: #a9b1d6; font-size: 11px;")
            root.addWidget(self._caption)
            self.setFixedHeight(METER_HEIGHT + 22)
        else:
            self.setFixedHeight(METER_HEIGHT + 4)

    def set_meter_level(self, level: float) -> None:
        self.meter.set_level(level)

    def set_volume_percent(self, pct: int) -> None:
        if self._vol_slider is None:
            return
        self._vol_slider.blockSignals(True)
        self._vol_slider.setValue(int(pct))
        self._vol_slider.blockSignals(False)
        if self._caption is None:
            return
        parts = self._caption.text().split("·", 1)
        name = parts[0].strip() if parts else self._volume_name
        self._caption.setText(f"{name} · {int(pct)}%")

    def volume_slider(self):
        return self._vol_slider

    def set_volume_label(self, text: str) -> None:
        if self._caption is None:
            return
        parts = self._caption.text().split("·", 1)
        name = parts[0].strip() if parts else self._volume_name
        self._caption.setText(f"{name} · {text}")
