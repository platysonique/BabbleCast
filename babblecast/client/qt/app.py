"""PyQt6 application entry."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from babblecast.client.qt.main_window import MainWindow
from babblecast.client.qt.single_instance import SingleInstanceServer, another_instance_running
from babblecast.client.qt.splash import SplashScreen
from babblecast.killswitch import KillSwitchRevoked, check_killswitch_or_raise

_ASSETS = Path(__file__).resolve().parents[3] / "assets"
_ICON = _ASSETS / "icon.png"


def run_gui() -> int:
    # Must run before QApplication — cheap socket ping, no GUI yet.
    if another_instance_running():
        return 0

    try:
        check_killswitch_or_raise("babblecast")
    except KillSwitchRevoked:
        return 1

    app = QApplication(sys.argv)
    app.setApplicationName("BabbleCast")
    app.setApplicationDisplayName("BabbleCast")
    app.setOrganizationName("BabbleCast")
    app.setDesktopFileName("babblecast")
    app.setQuitOnLastWindowClosed(True)
    if _ICON.is_file():
        app.setWindowIcon(QIcon(str(_ICON)))

    instance_server = SingleInstanceServer()
    window: MainWindow | None = None

    def _present_window() -> None:
        nonlocal window
        if window is None:
            return
        window.show()
        window.raise_()
        window.activateWindow()

    instance_server.raise_requested.connect(_present_window)

    kill_timer = QTimer()
    kill_timer.setInterval(15 * 60 * 1000)

    def _killswitch_tick() -> None:
        try:
            check_killswitch_or_raise("babblecast")
        except KillSwitchRevoked:
            app.quit()

    kill_timer.timeout.connect(_killswitch_tick)
    kill_timer.start()

    splash = SplashScreen()
    splash.show_on_primary_screen()
    app.processEvents()

    # Heavy imports + MainWindow build happen while splash is visible.
    window = MainWindow()
    if _ICON.is_file():
        window.setWindowIcon(QIcon(str(_ICON)))

    SplashScreen.show_then(_present_window, splash=splash)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_gui())
