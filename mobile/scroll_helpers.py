"""ScrollView helpers — MDSlider drags must win over vertical scroll."""

from __future__ import annotations

from kivy.uix.scrollview import ScrollView
from kivymd.uix.slider import MDSlider


class SliderFriendlyScrollView(ScrollView):
    """Allow MDSlider thumb drags inside a ScrollView on Android."""

    def _touch_hits_slider(self, touch) -> bool:
        if not self.collide_point(*touch.pos):
            return False
        touch.push()
        touch.apply_transform_2d(self.to_local)
        try:
            for child in self.walk(restrict=True):
                if isinstance(child, MDSlider) and child.collide_point(*touch.pos):
                    return True
        finally:
            touch.pop()
        return False

    def on_scroll_start(self, touch, check_children=True):
        if self._touch_hits_slider(touch):
            return False
        return super().on_scroll_start(touch, check_children=check_children)
