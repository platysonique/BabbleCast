"""PyQt6 application entry."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from babblecast.client.qt.main_window import MainWindow
from babblecast.client.qt.splash import SplashScreen

_ASSETS = Path(__file__).resolve().parents[3] / "assets"
_ICON = _ASSETS / "icon.png"


def run_gui() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("BabbleCast")
    app.setOrganizationName("BabbleCast")
    if _ICON.is_file():
        app.setWindowIcon(QIcon(str(_ICON)))

    window = MainWindow()
    if _ICON.is_file():
        window.setWindowIcon(QIcon(str(_ICON)))

    def _open_main() -> None:
        window.show()
        window.raise_()
        window.activateWindow()

    SplashScreen.show_then(_open_main)
    return app.exec()
