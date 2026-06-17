"""Collapsible section — arrow header, compact body (no checkbox)."""

from __future__ import annotations

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel

from mobile.theme import ACCENT, MUTED


class CollapsibleSection(MDBoxLayout):
    def __init__(self, title: str, *, expanded: bool = False, on_toggle=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.size_hint_y = None
        self.spacing = dp(2)
        self._expanded = expanded
        self._on_toggle = on_toggle

        header = MDBoxLayout(size_hint_y=None, height=dp(28), spacing=dp(4))
        self._arrow = MDLabel(
            text="▼" if expanded else "▶",
            theme_text_color="Custom",
            text_color=ACCENT,
            font_style="Caption",
            size_hint_x=None,
            width=dp(14),
        )
        self._title = MDLabel(
            text=title,
            theme_text_color="Custom",
            text_color=MUTED,
            font_style="Subtitle2",
            bold=True,
        )
        header.add_widget(self._arrow)
        header.add_widget(self._title)
        header.bind(on_touch_down=self._on_header_touch)
        self.add_widget(header)

        self._body = MDBoxLayout(
            orientation="vertical",
            spacing=dp(4),
            padding=(dp(4), 0, 0, dp(4)),
            size_hint_y=None,
        )
        self._body.bind(minimum_height=self._on_body_resize)
        self._body.opacity = 1 if expanded else 0
        self._body.disabled = not expanded
        if not expanded:
            self._body.height = 0
        self.add_widget(self._body)
        self._on_body_resize()

    def _on_body_resize(self, *_args) -> None:
        header_h = dp(28)
        body_h = self._body.minimum_height if self._expanded else 0
        self.height = header_h + body_h

    @property
    def body(self) -> MDBoxLayout:
        return self._body

    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool) -> None:
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self._arrow.text = "▼" if expanded else "▶"
        self._body.opacity = 1 if expanded else 0
        self._body.disabled = not expanded
        if expanded:
            self._body.height = self._body.minimum_height
        else:
            self._body.height = 0
        self._on_body_resize()
        if self._on_toggle:
            self._on_toggle(expanded)

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def _on_header_touch(self, instance, touch):
        if not instance.collide_point(*touch.pos):
            return False
        self.toggle()
        return True

    def set_title(self, title: str) -> None:
        self._title.text = title
