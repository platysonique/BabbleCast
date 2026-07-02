"""BabbleCast mobile app shell — entry via mobile/main.py for buildozer."""

from __future__ import annotations

from kivy.clock import Clock
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.screen import MDScreen
from kivymd.uix.screenmanager import MDScreenManager

from kivy.metrics import dp

from mobile.android_lifecycle import android_activity_is_finishing, should_run_in_background
from mobile.controller import BabbleController
from mobile.screens import ConnectScreen, LiveScreen, SettingsScreen
from mobile.theme import SURFACE, apply_theme


class BabbleCastMobileApp(MDApp):
    controller: BabbleController

    def build(self):
        apply_theme(self)
        self.controller = BabbleController(self)

        root = MDBoxLayout(orientation="vertical")
        sm = MDScreenManager(size_hint_y=1)
        self._screen_manager = sm
        sm.add_widget(ConnectScreen(name="connect"))
        sm.add_widget(LiveScreen(name="live"))
        sm.add_widget(SettingsScreen(name="settings"))
        root.add_widget(sm)

        from kivymd.uix.button import MDFlatButton

        tab_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(52),
            md_bg_color=SURFACE,
            padding=(dp(4), dp(4)),
            spacing=dp(4),
        )
        for label, name in (
            ("Connect", "connect"),
            ("Live", "live"),
            ("Settings", "settings"),
        ):
            btn = MDFlatButton(
                text=label,
                on_release=lambda _w, n=name: self.switch_tab(n),
            )
            tab_row.add_widget(btn)
        root.add_widget(tab_row)

        Clock.schedule_once(lambda _dt: self.controller.start_discovery(), 0)
        Clock.schedule_once(lambda _dt: self._maybe_smoke_connect(), 2.0)
        return root

    def _maybe_smoke_connect(self) -> None:
        from mobile.display_name import default_display_name
        from mobile.smoke_intent import read_smoke_connect_target

        target = read_smoke_connect_target()
        if not target:
            return
        host, port = target
        name = self.controller.settings.display_name or default_display_name(self.controller.settings)
        self.controller.connect_to(host, port, name, skip_name_prompt=True)

    def switch_tab(self, name: str) -> None:
        self._screen_manager.current = name

    def screen(self, name: str) -> MDScreen:
        return self._screen_manager.get_screen(name)

    def on_stop(self) -> None:
        if android_activity_is_finishing():
            self.controller.stop_all()

    def on_pause(self) -> bool:
        if android_activity_is_finishing():
            self.controller.stop_all()
            return True
        if should_run_in_background(self.controller.voice_session_active):
            return False
        return True

    def on_resume(self) -> None:
        if hasattr(self, "controller"):
            self.controller.refresh_discovery_ui(force=True)
