"""Startup splash — full BabbleCast logo, centered, auto-dismiss."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

_ASSETS = Path(__file__).resolve().parents[3] / "assets"
_SPLASH = _ASSETS / "splash.png"
_DURATION_MS = 3000


class SplashScreen(QWidget):
    """Fullscreen black backdrop with logo scaled and centered on the active screen."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.SplashScreen | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet("background-color: #000000;")
        self._label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()
        layout.addWidget(self._label, stretch=0)
        layout.addStretch()
        self._set_logo()

    def _set_logo(self) -> None:
        if not _SPLASH.is_file():
            self._label.setText("BabbleCast")
            self._label.setStyleSheet("color: white; font-size: 48px; font-weight: bold;")
            return
        pixmap = QPixmap(str(_SPLASH))
        if pixmap.isNull():
            return
        screen = QApplication.primaryScreen()
        if screen is None:
            self._label.setPixmap(pixmap)
            return
        bounds = screen.availableGeometry()
        max_w = int(bounds.width() * 0.88)
        max_h = int(bounds.height() * 0.88)
        scaled = pixmap.scaled(
            max_w,
            max_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)

    def show_on_primary_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.setGeometry(geo)
        self.show()
        QApplication.processEvents()

    @staticmethod
    def show_then(run_after, duration_ms: int = _DURATION_MS) -> SplashScreen:
        splash = SplashScreen()
        splash.show_on_primary_screen()
        QTimer.singleShot(duration_ms, lambda: _finish(splash, run_after))
        return splash


def _finish(splash: SplashScreen, run_after) -> None:
    splash.close()
    run_after()
