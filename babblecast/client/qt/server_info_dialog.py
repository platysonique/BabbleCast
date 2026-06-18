"""Read-only server connection stats dialog."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from babblecast.client.link_stats import build_link_info_rows, format_link_info_text, link_display_name
from babblecast.client.bridge import BridgeManager


class ServerInfoDialog(QDialog):
    def __init__(
        self,
        bridge: BridgeManager,
        link_id: str,
        *,
        presence_count: int = 0,
        current_room_name: str = "",
        is_active: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        link = bridge.get_link(link_id)
        if not link:
            self.setWindowTitle("Server info")
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("This server is no longer connected."))
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)
            return

        session = bridge.get_session(link_id)
        rows = build_link_info_rows(
            link,
            session,
            presence_count=presence_count,
            current_room_name=current_room_name,
            is_active=is_active,
        )
        self.setWindowTitle(f"Server — {link_display_name(link)}")
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        text = QLabel(format_link_info_text(rows))
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.setStyleSheet("color: #a9b1d6; font-family: monospace; font-size: 12px;")
        body_layout.addWidget(text)
        scroll.setWidget(body)
        root.addWidget(scroll)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)
