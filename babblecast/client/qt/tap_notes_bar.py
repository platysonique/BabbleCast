"""Tap notes list widget — used inside tap chat."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from babblecast.client.qt.tap_note_dialog import TapNoteRowLabel
from babblecast.constants import UI_MUTED_RED, UI_SUNFLOWER
from babblecast.taps import SavedTap, get_tap_store


class TapNotesBar(QWidget):
    def __init__(
        self,
        *,
        on_add: Callable[[], None] | None = None,
        on_delete: Callable[[str], None],
        on_view: Callable[[str], None],
        peer_id: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._on_add = on_add
        self._on_delete = on_delete
        self._on_view = on_view
        self._peer_id = peer_id

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        title = QLabel("Tap Notes")
        title.setStyleSheet("font-weight: 700; color: #c0caf5;")
        header.addWidget(title)
        header.addStretch()
        if on_add is not None:
            add_btn = QPushButton("+")
            add_btn.setFixedSize(28, 28)
            add_btn.setToolTip("Add tap note")
            add_btn.setStyleSheet(
                f"QPushButton {{ background-color: {UI_SUNFLOWER}; color: #1a1b26; font-weight: 700; border: none; border-radius: 6px; }}"
            )
            add_btn.clicked.connect(on_add)
            header.addWidget(add_btn)
        root.addLayout(header)

        hint = QLabel("Double-click a note to open")
        hint.setStyleSheet("color: #565f89; font-size: 10px;")
        root.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(120)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._body = QWidget()
        self._list_layout = QVBoxLayout(self._body)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()
        scroll.setWidget(self._body)
        root.addWidget(scroll)

    def refresh(self, *, peer_id: str | None = None) -> None:
        if peer_id is not None:
            self._peer_id = peer_id
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        notes = sorted(get_tap_store().items, key=lambda t: t.created_at, reverse=True)
        if self._peer_id:
            notes = [t for t in notes if t.peer_id == self._peer_id]
        if not notes:
            empty = QLabel("(no tap notes yet)")
            empty.setStyleSheet("color: #565f89; font-size: 11px;")
            self._list_layout.insertWidget(0, empty)
            return
        for tap in notes:
            self._list_layout.insertWidget(self._list_layout.count() - 1, self._row_for(tap))

    def _row_for(self, tap: SavedTap) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(2, 2, 2, 2)
        mark = "✓ " if tap.done else "○ "
        label = TapNoteRowLabel(tap.save_id, f"{mark}{tap.display_subject[:72]}")
        label.setStyleSheet("color: #a9b1d6; font-size: 11px;")
        label.double_clicked.connect(self._on_view)
        delete_btn = QPushButton("✕")
        delete_btn.setFixedSize(24, 24)
        delete_btn.setToolTip("Delete tap note")
        delete_btn.setStyleSheet(
            f"QPushButton {{ color: {UI_MUTED_RED}; font-weight: 700; border: none; }}"
            "QPushButton:hover { color: #ff9eaa; }"
        )
        delete_btn.clicked.connect(lambda _c=False, sid=tap.save_id: self._on_delete(sid))
        layout.addWidget(label, stretch=1)
        layout.addWidget(delete_btn)
        return row
