"""Ensure one BabbleCast GUI instance; raise existing window on relaunch."""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

_SERVER_KEY = "BabbleCast-gui"


def another_instance_running(timeout_ms: int = 500) -> bool:
    """If a GUI is already running, ask it to come forward and return True."""
    socket = QLocalSocket()
    socket.connectToServer(_SERVER_KEY)
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(b"raise")
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return True


class SingleInstanceServer(QObject):
    """Listen for relaunch pings and emit raise_requested."""

    raise_requested = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        QLocalServer.removeServer(_SERVER_KEY)
        if not self._server.listen(_SERVER_KEY):
            raise RuntimeError(f"Could not bind single-instance socket: {_SERVER_KEY}")

    def _on_new_connection(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        conn.waitForReadyRead(200)
        conn.readAll()
        conn.disconnectFromServer()
        self.raise_requested.emit()
