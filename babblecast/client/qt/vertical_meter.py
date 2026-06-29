"""DAW-style vertical level meter — zone housing + bar rising from bottom."""

from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

METER_WIDTH = 24
METER_HEIGHT = 88


class VerticalMeter(QWidget):
    """0–1 level: dim green→yellow→red housing; lit bar grows up from the bottom."""

    _BG = QColor("#0d0f17")
    _BORDER = QColor("#3b4261")
    _ZONE_GREEN = QColor(61, 153, 112, 55)
    _ZONE_YELLOW = QColor(224, 175, 104, 55)
    _ZONE_RED = QColor(247, 118, 142, 70)
    _LIT_GREEN = QColor("#73daca")
    _LIT_YELLOW = QColor("#e0af68")
    _LIT_RED = QColor("#f7768e")
    _PEAK = QColor("#c0caf5")
    _CLIP = QColor("#ff0033")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._level = 0.0
        self._peak = 0.0
        self._clip = False
        self.setFixedSize(METER_WIDTH, METER_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._decay = QTimer(self)
        self._decay.setInterval(50)
        self._decay.timeout.connect(self._decay_peak)
        self._decay.start()

    def set_level(self, level: float) -> None:
        level = max(0.0, min(1.0, float(level)))
        self._level = level
        if level >= self._peak:
            self._peak = level
        self._clip = level >= 0.97
        self.update()

    def _decay_peak(self) -> None:
        if self._peak <= self._level:
            return
        self._peak = max(self._level, self._peak - 0.018)
        self.update()

    def _lit_color(self, t: float) -> QColor:
        """t: 0 = bottom of housing (safe), 1 = top (hot)."""
        if t < 0.68:
            return self._LIT_GREEN
        if t < 0.88:
            return self._LIT_YELLOW
        return self._LIT_RED

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        inset = 2
        x0, y0 = inset, inset
        tw, th = w - inset * 2, h - inset * 2
        x1, y1 = x0 + tw - 1, y0 + th - 1

        p.fillRect(x0, y0, tw, th, self._BG)

        # Fixed zone housing: green at bottom, red at top (standard DAW orientation).
        zone = QLinearGradient(0, y1, 0, y0)
        zone.setColorAt(0.0, self._ZONE_GREEN)
        zone.setColorAt(0.68, self._ZONE_YELLOW)
        zone.setColorAt(1.0, self._ZONE_RED)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(zone))
        p.drawRect(x0 + 1, y0 + 1, tw - 2, th - 2)

        p.setPen(QPen(self._BORDER, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(x0, y0, tw - 1, th - 1)

        fill_h = max(0, int(th * self._level))
        if fill_h > 0:
            fy = y1 - fill_h + 1
            band = max(2, fill_h // 20)
            for i in range(0, fill_h, band):
                seg_h = min(band, fill_h - i)
                sy = fy + (fill_h - i - seg_h)
                t = (sy + seg_h / 2 - y0) / max(1, th)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(self._CLIP if (self._clip and t > 0.88) else self._lit_color(t)))
                p.drawRect(x0 + 2, int(sy), tw - 4, seg_h)

        if self._peak > 0.02:
            peak_y = y1 - int(th * self._peak)
            p.setPen(QPen(self._CLIP if self._clip else self._PEAK, 2))
            p.drawLine(x0 + 2, peak_y, x1 - 2, peak_y)

        p.end()
