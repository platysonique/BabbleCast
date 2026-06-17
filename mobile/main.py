"""
BabbleCast mobile client (Android / iOS) — KivyMD UI sharing the same protocol core.

Build Android:
  cd mobile && buildozer android debug

Build iOS (macOS with kivy-ios):
  cd mobile && ./build_ios.sh
"""

from __future__ import annotations

import threading

from kivy.lang import Builder
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.list import MDList, OneLineListItem, TwoLineListItem
from kivymd.uix.screen import MDScreen
from kivymd.uix.label import MDLabel
from kivymd.uix.slider import MDSlider
from kivymd.uix.textfield import MDTextField

from babblecast.client.session import ClientSession
from babblecast.config import get_settings, save_settings
from babblecast.discovery import ServerDiscovery

KV = """
<BabbleMobileScreen>:
    MDBoxLayout:
        orientation: "vertical"
        padding: "12dp"
        spacing: "8dp"
        MDLabel:
            text: "BabbleCast"
            font_style: "H5"
            theme_text_color: "Primary"
            size_hint_y: None
            height: self.texture_size[1]
        MDLabel:
            id: status_label
            text: root.status_text
            theme_text_color: "Secondary"
            size_hint_y: None
            height: self.texture_size[1]
        MDTextField:
            id: name_field
            hint_text: "Your name"
            text: root.display_name
            size_hint_y: None
            height: "48dp"
        ScrollView:
            MDList:
                id: server_list
        MDBoxLayout:
            size_hint_y: None
            height: "48dp"
            spacing: "8dp"
            MDRaisedButton:
                text: "Host"
                on_release: root.host_server()
            MDRaisedButton:
                text: "Connect"
                on_release: root.connect_selected()
        MDLabel:
            text: "Noise gate / suppression"
            size_hint_y: None
            height: self.texture_size[1]
        MDSlider:
            id: gate_slider
            min: -80
            max: 0
            value: root.gate_db
            on_value: root.set_gate(self.value)
        MDSlider:
            id: noise_slider
            min: 0
            max: 100
            value: root.noise_pct
            on_value: root.set_noise(self.value)
        MDBoxLayout:
            size_hint_y: None
            height: "48dp"
            spacing: "8dp"
            MDRaisedButton:
                text: "Mute" if not root.is_muted else "Unmute"
                on_release: root.toggle_mute()
            MDRaisedButton:
                text: "PTT"
                on_release: root.toggle_ptt()
        MDTextField:
            id: chat_input
            hint_text: "Chat message"
            size_hint_y: None
            height: "48dp"
            on_text_validate: root.send_chat()
        ScrollView:
            MDLabel:
                id: chat_log
                text: root.chat_text
                size_hint_y: None
                height: self.texture_size[1]
                padding: "8dp"
"""


class BabbleMobileScreen(MDScreen):
    status_text = StringProperty("Offline")
    display_name = StringProperty("")
    chat_text = StringProperty("")
    gate_db = NumericProperty(-40)
    noise_pct = NumericProperty(50)
    is_muted = BooleanProperty(False)
    ptt_active = BooleanProperty(False)
    servers = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._settings = get_settings()
        self.display_name = self._settings.display_name or "Mobile"
        self.gate_db = self._settings.gate_threshold_db
        self.noise_pct = int(self._settings.noise_suppression * 100)
        self._session = ClientSession(
            on_presence=self._on_presence,
            on_chat=self._on_chat,
            on_connected=lambda: setattr(self, "status_text", "Connected"),
            on_disconnected=lambda r: setattr(self, "status_text", f"Offline — {r}"),
        )
        self._discovery = ServerDiscovery(on_update=self._on_servers)
        self._embedded = None
        self._selected_host = ("127.0.0.1", 8765)

    def on_enter(self, *args):
        self._discovery.start()

    def on_leave(self, *args):
        self._discovery.stop()
        self._session.disconnect()

    def _on_servers(self, servers):
        self.servers = [(s.host, s.ws_port, s.label) for s in servers]
        lst = self.ids.server_list
        lst.clear_widgets()
        for host, port, label in self.servers:
            item = TwoLineListItem(text=label, secondary_text=f"{host}:{port}")
            item.bind(on_release=lambda _i, h=host, p=port: self._select(h, p))
            lst.add_widget(item)

    def _select(self, host, port):
        self._selected_host = (host, port)

    def connect_selected(self):
        self._settings.display_name = self.ids.name_field.text
        save_settings(self._settings)
        self._session.update_settings(self._settings)
        host, port = self._selected_host
        self.status_text = f"Connecting {host}:{port}…"
        self._session.connect(host, port)

    def host_server(self):
        from babblecast.client.qt.server_runner import EmbeddedServer

        if self._embedded and self._embedded.running:
            self._embedded.stop()
            self.status_text = "Server stopped"
            return
        self._embedded = EmbeddedServer()
        self._embedded.start()
        self.status_text = "Hosting…"
        threading.Timer(0.5, lambda: self._session.connect("127.0.0.1", 8765)).start()

    def toggle_mute(self):
        self.is_muted = not self.is_muted
        self._session.set_muted(self.is_muted)

    def toggle_ptt(self):
        self.ptt_active = not self.ptt_active
        self._session.set_ptt(self.ptt_active)

    def set_gate(self, value):
        self.gate_db = value
        self._session.set_gate_db(float(value))

    def set_noise(self, value):
        self.noise_pct = value
        self._session.set_noise_suppression(value / 100.0)

    def send_chat(self):
        text = self.ids.chat_input.text.strip()
        if text:
            self._session.send_chat(text)
            self.ids.chat_input.text = ""

    def _on_presence(self, _room_id, participants):
        lines = [f"{p.get('name')} {'🔊' if p.get('speaking') else ''}" for p in participants]
        self.status_text = "Connected — " + ", ".join(lines)

    def _on_chat(self, data):
        self.chat_text += f"{data.get('name')}: {data.get('text')}\n"


class BabbleCastMobileApp(MDApp):
    def build(self):
        Builder.load_string(KV)
        return BabbleMobileScreen()


if __name__ == "__main__":
    BabbleCastMobileApp().run()
