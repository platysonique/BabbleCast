"""Global Tap Notes panel shown below room chat."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from babblecast.active_tap_chats import ActiveTapChat, get_active_tap_chat_store
from babblecast.constants import UI_MUTED_RED, UI_SUNFLOWER
from babblecast.taps import SavedTap, get_tap_store


class TapNotesBar(QGroupBox):
    def __init__(
        self,
        *,
        on_add: Callable[[], None],
        on_delete: Callable[[str], None],
        on_open: Callable[[str], None],
        on_open_active: Callable[[str], None],
        on_clear_active: Callable[[str], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._on_add = on_add
        self._on_delete = on_delete
        self._on_open = on_open
        self._on_open_active = on_open_active
        self._on_clear_active = on_clear_active

        root = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel("Tap Notes")
        title.setStyleSheet("font-weight: 700; color: #c0caf5;")
        add_btn = QPushButton("+")
        add_btn.setFixedSize(28, 28)
        add_btn.setToolTip("Add tap note manually")
        add_btn.setStyleSheet(
            f"QPushButton {{ background-color: {UI_SUNFLOWER}; color: #1a1b26; font-weight: 700; border: none; border-radius: 6px; }}"
        )
        add_btn.clicked.connect(self._on_add)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(add_btn)
        root.addLayout(header)

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

    def refresh(self) -> None:
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        active = get_active_tap_chat_store().all_chats()
        notes = sorted(get_tap_store().items, key=lambda t: t.created_at, reverse=True)
        if not active and not notes:
            empty = QLabel("(no tap notes yet)")
            empty.setStyleSheet("color: #565f89; font-size: 11px;")
            self._list_layout.insertWidget(0, empty)
            return
        for chat in active:
            self._list_layout.insertWidget(
                self._list_layout.count() - 1, self._row_for_active(chat)
            )
        for tap in notes:
            self._list_layout.insertWidget(self._list_layout.count() - 1, self._row_for(tap))

    def _row_for_active(self, chat: ActiveTapChat) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(2, 2, 2, 2)
        peer = chat.peer_name or "?"
        label = QLabel(f"💬 {chat.preview()[:56]}  ·  {peer}")
        label.setStyleSheet("color: #7aa2f7; font-size: 11px;")
        label.setCursor(Qt.CursorShape.PointingHandCursor)
        label.mousePressEvent = lambda _e, tid=chat.tap_id: self._on_open_active(tid)  # type: ignore[method-assign]
        delete_btn = QPushButton("✕")
        delete_btn.setFixedSize(24, 24)
        delete_btn.setToolTip("Clear tap chat")
        delete_btn.setStyleSheet(
            f"QPushButton {{ color: {UI_MUTED_RED}; font-weight: 700; border: none; }}"
            "QPushButton:hover { color: #ff9eaa; }"
        )
        delete_btn.clicked.connect(lambda _c=False, tid=chat.tap_id: self._on_clear_active(tid))
        layout.addWidget(label, stretch=1)
        layout.addWidget(delete_btn)
        return row

    def _row_for(self, tap: SavedTap) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(2, 2, 2, 2)
        mark = "✓ " if tap.done else "○ "
        peer = tap.peer_name or "Note"
        label = QLabel(f"{mark}{tap.reminder[:64]}  ·  {peer}")
        label.setStyleSheet("color: #a9b1d6; font-size: 11px;")
        label.setCursor(Qt.CursorShape.PointingHandCursor)
        label.mousePressEvent = lambda _e, sid=tap.save_id: self._on_open(sid)  # type: ignore[method-assign]
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
