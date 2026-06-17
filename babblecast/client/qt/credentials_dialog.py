"""Username / server-name prompts — not shown on the main UI."""

from __future__ import annotations

import socket

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
)

from babblecast.constants import MAX_NAME_LEN


def _clean_name(text: str) -> str:
    return text.strip()[:MAX_NAME_LEN] or "Anonymous"


class ConnectCredentialsDialog(QDialog):
    """Ask display name when joining a server."""

    def __init__(self, default_name: str, server_label: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connect to server")
        layout = QFormLayout(self)
        layout.addRow("Server", QLineEdit(server_label, readOnly=True))
        self._name = QLineEdit(default_name or socket.gethostname())
        self._name.setPlaceholderText("Display name on this server")
        layout.addRow("Your name", self._name)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _accept(self) -> None:
        if not self._name.text().strip():
            QMessageBox.warning(self, "BabbleCast", "Enter a display name.")
            return
        self.accept()

    @property
    def display_name(self) -> str:
        return _clean_name(self._name.text())


class HostCredentialsDialog(QDialog):
    """Ask server name + display name when hosting."""

    def __init__(self, default_server: str, default_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Host server")
        layout = QFormLayout(self)
        self._server = QLineEdit(default_server or default_name or socket.gethostname())
        self._server.setPlaceholderText("Name others see in Discover")
        layout.addRow("Server name", self._server)
        self._name = QLineEdit(default_name or socket.gethostname())
        self._name.setPlaceholderText("Your display name on this server")
        layout.addRow("Your name", self._name)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _accept(self) -> None:
        if not self._server.text().strip():
            QMessageBox.warning(self, "BabbleCast", "Enter a server name.")
            return
        if not self._name.text().strip():
            QMessageBox.warning(self, "BabbleCast", "Enter your display name.")
            return
        self.accept()

    @property
    def server_name(self) -> str:
        return self._server.text().strip()[:MAX_NAME_LEN]

    @property
    def display_name(self) -> str:
        return _clean_name(self._name.text())
