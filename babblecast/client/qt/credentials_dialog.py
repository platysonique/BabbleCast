"""Username / server-name prompts — not shown on the main UI."""

from __future__ import annotations

import socket

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from babblecast.config import get_settings, save_settings
from babblecast.constants import MAX_NAME_LEN, MAX_ROOM_NAME_LEN


def _clean_name(text: str) -> str:
    return text.strip()[:MAX_NAME_LEN] or "Anonymous"


class ConnectCredentialsDialog(QDialog):
    """Ask display name (and password when needed) when joining a server."""

    def __init__(
        self,
        default_name: str,
        server_label: str,
        parent=None,
        *,
        password_required: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connect to server")
        layout = QFormLayout(self)
        layout.addRow("Server", QLineEdit(server_label, readOnly=True))
        self._name = QLineEdit(default_name or socket.gethostname())
        self._name.setPlaceholderText("Display name on this server")
        layout.addRow("Your name", self._name)
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText("Server password")
        self._password.setVisible(password_required)
        if password_required:
            layout.addRow("Password", self._password)
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
        if self._password.isVisible() and not self._password.text():
            QMessageBox.warning(self, "BabbleCast", "Enter the server password.")
            return
        self.accept()

    @property
    def display_name(self) -> str:
        return _clean_name(self._name.text())

    @property
    def password(self) -> str:
        return self._password.text() if self._password.isVisible() else ""


class HostCredentialsDialog(QDialog):
    """Ask server name, display name, and optional password when hosting."""

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
        layout.addRow(
            QLabel(
                "Your PC's LAN address is advertised automatically — "
                "others find you via Discover or name.babblecast.local."
            )
        )
        self._protect = QCheckBox("Password protect")
        self._protect.setChecked(False)
        self._protect.toggled.connect(self._on_protect_toggled)
        layout.addRow(self._protect)
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText("Password for clients")
        self._password.setEnabled(False)
        layout.addRow("Password", self._password)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_protect_toggled(self, checked: bool) -> None:
        self._password.setEnabled(checked)
        if not checked:
            self._password.clear()

    def _accept(self) -> None:
        if not self._server.text().strip():
            QMessageBox.warning(self, "BabbleCast", "Enter a server name.")
            return
        if not self._name.text().strip():
            QMessageBox.warning(self, "BabbleCast", "Enter your display name.")
            return
        if self._protect.isChecked() and not self._password.text():
            QMessageBox.warning(self, "BabbleCast", "Enter a password or uncheck Password protect.")
            return
        settings = get_settings()
        settings.hosted_server_name = self._server.text().strip()[:MAX_NAME_LEN]
        settings.display_name = _clean_name(self._name.text())
        save_settings(settings)
        self.accept()

    @property
    def server_name(self) -> str:
        return self._server.text().strip()[:MAX_NAME_LEN]

    @property
    def display_name(self) -> str:
        return _clean_name(self._name.text())

    @property
    def server_password(self) -> str:
        if self._protect.isChecked():
            return self._password.text()
        return ""


class DisconnectConfirmDialog(QDialog):
    """Confirm disconnect from a connected server."""

    def __init__(self, server_label: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Disconnect")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Disconnect from “{server_label}”?"))
        self._dont_ask = QCheckBox("Don't ask again")
        layout.addWidget(self._dont_ask)
        buttons = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        disconnect = QPushButton("Disconnect")
        disconnect.setStyleSheet("color: #f7768e; font-weight: 600;")
        disconnect.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(disconnect)
        layout.addLayout(buttons)

    @property
    def skip_future_confirms(self) -> bool:
        return self._dont_ask.isChecked()


class RoomCreateDialog(QDialog):
    """Create a room with optional password protection."""

    def __init__(self, default_name: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create room")
        layout = QFormLayout(self)
        self._name = QLineEdit(default_name)
        self._name.setPlaceholderText("Room name")
        layout.addRow("Name", self._name)
        self._protect = QCheckBox("Password protect this room")
        self._protect.toggled.connect(self._on_protect_toggled)
        layout.addRow(self._protect)
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText("Room password")
        self._password.setEnabled(False)
        layout.addRow("Password", self._password)
        layout.addRow(
            QLabel("Only you can delete a room you create. Others need the password to enter.")
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_protect_toggled(self, checked: bool) -> None:
        self._password.setEnabled(checked)
        if not checked:
            self._password.clear()

    def _accept(self) -> None:
        if not self._name.text().strip():
            QMessageBox.warning(self, "BabbleCast", "Enter a room name.")
            return
        if self._protect.isChecked() and not self._password.text():
            QMessageBox.warning(self, "BabbleCast", "Enter a room password or uncheck protection.")
            return
        self.accept()

    @property
    def room_name(self) -> str:
        return self._name.text().strip()[:MAX_ROOM_NAME_LEN] or "Room"

    @property
    def room_password(self) -> str:
        if self._protect.isChecked():
            return self._password.text()
        return ""


class RoomPasswordDialog(QDialog):
    """Ask for a protected room's password before joining."""

    def __init__(self, room_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Room password")
        layout = QFormLayout(self)
        layout.addRow("Room", QLineEdit(room_name, readOnly=True))
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText("Room password")
        layout.addRow("Password", self._password)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _accept(self) -> None:
        if not self._password.text():
            QMessageBox.warning(self, "BabbleCast", "Enter the room password.")
            return
        self.accept()

    @property
    def password(self) -> str:
        return self._password.text()
