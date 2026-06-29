"""Collapsible section with arrow header — no QGroupBox checkbox."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget


class CollapsibleSection(QWidget):
    """Title row with ▶/▼ toggle; body shows or hides vertically."""

    toggled = pyqtSignal(bool)

    def __init__(self, title: str, *, expanded: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._expanded = expanded
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)
        self._arrow = QLabel(self._arrow_text())
        self._arrow.setFixedWidth(14)
        self._arrow.setStyleSheet("color: #7aa2f7; font-size: 10px; font-weight: bold;")
        self._arrow.setCursor(Qt.CursorShape.PointingHandCursor)
        self._arrow.mousePressEvent = lambda _e: self.toggle()  # type: ignore[method-assign]
        self._title = QLabel(title)
        self._title.setStyleSheet("font-weight: bold; color: #a9b1d6;")
        self._title.mousePressEvent = lambda _e: self.toggle()  # type: ignore[method-assign]
        self._title.setCursor(Qt.CursorShape.PointingHandCursor)
        header.addWidget(self._arrow)
        header.addWidget(self._title, stretch=1)
        root.addLayout(header)

        self._body = QWidget()
        self._body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(4, 0, 0, 4)
        self._body_layout.setSpacing(4)
        self._body.setVisible(expanded)
        root.addWidget(self._body)

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool) -> None:
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self._body.setVisible(expanded)
        self._arrow.setText(self._arrow_text())
        self.toggled.emit(expanded)

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def set_title(self, title: str) -> None:
        self._title.setText(title)

    def _arrow_text(self) -> str:
        return "▼" if self._expanded else "▶"
