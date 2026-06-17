"""PyQt6 application entry."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from babblecast.client.qt.main_window import MainWindow


def run_gui() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("BabbleCast")
    app.setOrganizationName("BabbleCast")
    window = MainWindow()
    window.show()
    return app.exec()
