"""Radial master-output volume control (DAW-style knob)."""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPen, QWheelEvent
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

_KNOB_SIZE = 64
_DOT_RADIUS = 5.0
_ARC_START_DEG = 225.0
_ARC_SPAN_DEG = 270.0


class _RadialDial(QWidget):
    """Painted dial — QSS cannot style QDial handles reliably on Linux."""

    valueChanged = pyqtSignal(int)

    def __init__(self, *, parent=None) -> None:
        super().__init__(parent)
        self._minimum = 0
        self._maximum = 200
        self._value = 100
        self.setFixedSize(_KNOB_SIZE, _KNOB_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Master output volume")

    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:
        clamped = max(self._minimum, min(self._maximum, int(value)))
        if clamped == self._value:
            return
        self._value = clamped
        self.update()
        self.valueChanged.emit(clamped)

    def _dot_center(self) -> QPointF:
        t = (self._value - self._minimum) / (self._maximum - self._minimum)
        deg = _ARC_START_DEG - t * _ARC_SPAN_DEG
        rad = math.radians(deg)
        radius = self.width() / 2 - 10
        cx = self.width() / 2
        cy = self.height() / 2
        return QPointF(cx + radius * math.cos(rad), cy - radius * math.sin(rad))

    def _value_from_pos(self, pos: QPointF) -> int:
        cx = self.width() / 2
        cy = self.height() / 2
        dx = pos.x() - cx
        dy = cy - pos.y()
        angle = math.degrees(math.atan2(dy, dx))
        if angle < 0:
            angle += 360.0
        rel = (_ARC_START_DEG - angle) % 360.0
        if rel > _ARC_SPAN_DEG:
            rel = 0.0 if angle >= 180.0 else _ARC_SPAN_DEG
        t = rel / _ARC_SPAN_DEG
        return int(round(self._minimum + t * (self._maximum - self._minimum)))

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        inset = 6.0
        face = QPointF(inset, inset)
        size = self.width() - inset * 2
        painter.setPen(QPen(QColor("#414868"), 2))
        painter.setBrush(QColor("#1a1b26"))
        painter.drawEllipse(face.x(), face.y(), size, size)

        dot = self._dot_center()
        painter.setPen(QPen(QColor("#cccccc"), 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(dot, _DOT_RADIUS, _DOT_RADIUS)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setValue(self._value_from_pos(event.position()))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.setValue(self._value_from_pos(event.position()))

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        step = 2 if delta > 0 else -2
        self.setValue(self._value + step)


class VolumeKnob(QWidget):
    """0–200% master output; emits integer percent like the old horizontal slider."""

    valueChanged = pyqtSignal(int)

    def __init__(self, *, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        self._dial = _RadialDial()
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
