"""Tokyo Night palette for KivyMD mobile client."""

from __future__ import annotations

from kivy.core.window import Window
from kivymd.app import MDApp

BG = "#1a1b26"
SURFACE = "#24283b"
BORDER = "#414868"
ACCENT = "#7aa2f7"
TEXT = "#c0caf5"
MUTED = "#565f89"
SUCCESS = "#9ece6a"
DANGER = "#f7768e"
MUTE_ORANGE = "#e0af68"
SUNFLOWER = "#ffda03"


def apply_theme(app: MDApp) -> None:
    app.theme_cls.theme_style = "Dark"
    app.theme_cls.primary_palette = "BlueGray"
    app.theme_cls.accent_palette = "LightBlue"
    Window.clearcolor = (26 / 255, 27 / 255, 38 / 255, 1)
