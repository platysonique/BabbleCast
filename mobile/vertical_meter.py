"""DAW-style vertical level meter for Kivy — green bottom, red top, bar rises up."""

from __future__ import annotations

from kivy.clock import Clock
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

METER_WIDTH = dp(24)
METER_HEIGHT = dp(88)

_BG = (13 / 255, 15 / 255, 23 / 255, 1)
_BORDER = (59 / 255, 66 / 255, 97 / 255, 1)
_ZONE_GREEN = (61 / 255, 153 / 255, 112 / 255, 0.22)
_ZONE_YELLOW = (224 / 255, 175 / 255, 104 / 255, 0.22)
_ZONE_RED = (247 / 255, 118 / 255, 142 / 255, 0.28)
_LIT = {
    "green": (115 / 255, 218 / 255, 202 / 255, 1),
    "yellow": (224 / 255, 175 / 255, 104 / 255, 1),
    "red": (247 / 255, 118 / 255, 142 / 255, 1),
    "clip": (1, 0, 0.2, 1),
}
_PEAK = (192 / 255, 202 / 255, 245 / 255, 1)


class VerticalMeter(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (METER_WIDTH, METER_HEIGHT)
        self._level = 0.0
        self._peak = 0.0
        self._clip = False
        self._decay_ev = Clock.schedule_interval(self._decay_peak, 0.05)
        self.bind(pos=self._redraw, size=self._redraw)

    def stop(self) -> None:
        if getattr(self, "_decay_ev", None) is not None:
            Clock.unschedule(self._decay_ev)
            self._decay_ev = None

    def set_level(self, level: float) -> None:
        level = max(0.0, min(1.0, float(level)))
        self._level = level
        if level >= self._peak:
            self._peak = level
        self._clip = level >= 0.97
        self._redraw()

    def _decay_peak(self, _dt: float) -> bool:
        if self._peak <= self._level:
            return True
        self._peak = max(self._level, self._peak - 0.018)
        self._redraw()
        return True

    def _lit_color(self, t: float) -> tuple[float, float, float, float]:
        if t < 0.68:
            return _LIT["green"]
        if t < 0.88:
            return _LIT["yellow"]
        if self._clip and t > 0.88:
            return _LIT["clip"]
        return _LIT["red"]

    def _redraw(self, *_args) -> None:
        self.canvas.clear()
        x, y = self.pos
        w, h = self.size
        inset = dp(2)
        ix, iy = x + inset, y + inset
        tw, th = w - inset * 2, h - inset * 2

        with self.canvas:
            Color(*_BG)
            Rectangle(pos=(ix, iy), size=(tw, th))

            gh = th * 0.68
            yh = th * 0.20
            Color(*_ZONE_GREEN)
            Rectangle(pos=(ix + 1, iy + 1), size=(tw - 2, gh))
            Color(*_ZONE_YELLOW)
            Rectangle(pos=(ix + 1, iy + 1 + gh), size=(tw - 2, yh))
            Color(*_ZONE_RED)
            Rectangle(pos=(ix + 1, iy + 1 + gh + yh), size=(tw - 2, th - gh - yh - 2))

            fill_h = max(0, int(th * self._level))
            if fill_h > 0:
                band = max(dp(2), fill_h // 20)
                pos_y = iy + 1
                remaining = fill_h
                while remaining > 0:
                    seg_h = min(band, remaining)
                    t = ((pos_y + seg_h / 2) - iy) / max(1, th)
                    Color(*self._lit_color(t))
                    Rectangle(pos=(ix + 2, pos_y), size=(tw - 4, seg_h))
                    pos_y += seg_h
                    remaining -= seg_h

            Color(*_BORDER)
            Line(rectangle=(ix, iy, tw, th), width=1)

            if self._peak > 0.02:
                peak_y = iy + int(th * self._peak)
                Color(*(_LIT["clip"] if self._clip else _PEAK))
                Line(points=[ix + 2, peak_y, ix + tw - 2, peak_y], width=dp(1.5))
