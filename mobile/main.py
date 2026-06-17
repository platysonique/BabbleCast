"""
BabbleCast mobile client (Android / iOS) — multi-server bridge + Tap.
"""

from __future__ import annotations

import threading

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import BooleanProperty, StringProperty
from kivymd.app import MDApp
from kivymd.uix.dialog import MDDialog
from kivymd.uix.screen import MDScreen

from babblecast.client.bridge import BridgeManager
from babblecast.config import get_settings, save_settings
from babblecast.constants import composite_participant_key
from babblecast.discovery import ServerDiscovery
from babblecast.server.embedded import EmbeddedServer
from babblecast.taps import SavedTap, get_tap_store
from mobile.permissions import request_android_permissions

KV = """
<BabbleMobileScreen>:
    MDBoxLayout:
        orientation: "vertical"
        padding: "12dp"
        spacing: "8dp"
        ScrollView:
            MDBoxLayout:
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
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
                MDLabel:
                    text: "Discover"
                    font_style: "Subtitle1"
                    size_hint_y: None
                    height: self.texture_size[1]
                ScrollView:
                    size_hint_y: None
                    height: "120dp"
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
                    text: "Connected (mixed audio)"
                    font_style: "Subtitle1"
                    size_hint_y: None
                    height: self.texture_size[1]
                MDLabel:
                    text: "Tap row = active server · icons: hear / mic / disconnect"
                    theme_text_color: "Secondary"
                    font_style: "Caption"
                    size_hint_y: None
                    height: self.texture_size[1]
                MDList:
                    id: connected_list
                MDLabel:
                    text: "People in room"
                    font_style: "Subtitle1"
                    size_hint_y: None
                    height: self.texture_size[1]
                MDList:
                    id: people_list
                MDBoxLayout:
                    size_hint_y: None
                    height: "48dp"
                    spacing: "8dp"
                    MDRaisedButton:
                        text: "Mute all" if not root.is_muted else "Unmute all"
                        on_release: root.toggle_mute()
                    MDRaisedButton:
                        text: "PTT"
                        on_release: root.toggle_ptt()
                MDTextField:
                    id: chat_input
                    hint_text: "Room chat (active server)"
                    size_hint_y: None
                    height: "48dp"
                    on_text_validate: root.send_chat()
                MDRaisedButton:
                    text: "Send chat"
                    size_hint_y: None
                    height: "48dp"
                    on_release: root.send_chat()
                MDLabel:
                    id: chat_log
                    text: root.chat_text
                    size_hint_y: None
                    height: self.texture_size[1]
                    padding: "8dp"
"""


class BabbleMobileScreen(MDScreen):
    status_text = StringProperty("Offline — connect to one or more servers")
    display_name = StringProperty("")
    chat_text = StringProperty("")
    is_muted = BooleanProperty(False)
    ptt_active = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._settings = get_settings()
        self.display_name = self._settings.display_name or "Mobile"
        self._bridge = BridgeManager(
            on_link_connected=lambda lid: Clock.schedule_once(lambda _dt, i=lid: self._on_link_connected(i)),
            on_link_disconnected=lambda lid, r: Clock.schedule_once(
                lambda _dt, i=lid, reason=r: self._on_link_disconnected(i, reason)
            ),
            on_presence=lambda lid, rid, p: Clock.schedule_once(
                lambda _dt, i=lid, parts=p: self._on_presence(i, parts)
            ),
            on_chat=lambda lid, d: Clock.schedule_once(lambda _dt, i=lid, msg=d: self._on_chat(i, msg)),
            on_error=lambda lid, m: Clock.schedule_once(lambda _dt, msg=m: setattr(self, "status_text", msg)),
            on_tap_received=lambda lid, d: Clock.schedule_once(lambda _dt, i=lid, data=d: self._on_tap_received(i, data)),
            on_tap_chat=lambda lid, d: Clock.schedule_once(lambda _dt, data=d: self._on_tap_chat(data)),
        )
        self._discovery = ServerDiscovery(
            on_update=lambda s: Clock.schedule_once(lambda _dt, sv=s: self._apply_servers(sv))
        )
        self._embedded: EmbeddedServer | None = None
        self._active_link_id: str | None = None
        self._presence: dict[str, list] = {}
        self._tap_ids: dict[tuple[str, str], str] = {}
        self._tap_messages: list[dict] = []
        self._tap_dialog: MDDialog | None = None
        self._tap_link_id = ""
        self._tap_id = ""
        self._tap_peer_name = ""

    def on_enter(self, *args):
        request_android_permissions()
        self._discovery.start()

    def on_leave(self, *args):
        self._discovery.stop()
        self._bridge.disconnect_all()
        if self._embedded and self._embedded.running:
            self._embedded.stop()

    def _apply_servers(self, servers) -> None:
        from kivymd.uix.list import TwoLineListItem

        lst = self.ids.server_list
        lst.clear_widgets()
        for s in servers:
            item = TwoLineListItem(text=s.label, secondary_text=f"{s.host}:{s.ws_port}")
            item.bind(on_release=lambda _i, h=s.host, p=s.ws_port: self._select_server(h, p))
            lst.add_widget(item)

    def _select_server(self, host: str, port: int) -> None:
        self._pending_host = host
        self._pending_port = port
        self.status_text = f"Selected {host}:{port} — tap Connect"

    def connect_selected(self):
        host = getattr(self, "_pending_host", None) or self._settings.last_server_host or "127.0.0.1"
        port = getattr(self, "_pending_port", None) or self._settings.last_server_port or 8765
        for link in self._bridge.links:
            if link.host == host and link.port == port and link.connected:
                self.status_text = f"Already on {host}:{port}"
                return
        self._settings.display_name = self.ids.name_field.text.strip()
        self._settings.last_server_host = host
        self._settings.last_server_port = port
        save_settings(self._settings)
        self._bridge.update_settings(self._settings)
        self.status_text = f"Connecting {host}:{port}…"
        self._bridge.connect(host, port)

    def host_server(self):
        if self._embedded and self._embedded.running:
            self.status_text = "Server already running — use Connect to join it"
            return
        self._embedded = EmbeddedServer()
        self._embedded.start()
        self.status_text = "Hosting on this device…"
        threading.Timer(0.8, lambda: Clock.schedule_once(lambda _dt: self._join_local_host())).start()

    def _join_local_host(self):
        self._select_server("127.0.0.1", 8765)
        self.connect_selected()

    def _on_link_connected(self, link_id: str) -> None:
        from kivymd.uix.list import OneLineAvatarIconListItem, IconRightWidget

        link = self._bridge.get_link(link_id)
        if not link:
            return
        if not self._active_link_id:
            self._active_link_id = link_id
        lst = self.ids.connected_list
        item = OneLineAvatarIconListItem(text=link.label)
        listen_icon = IconRightWidget(icon="volume-off" if link.listen_muted else "volume-high")
        mic_icon = IconRightWidget(icon="microphone-off" if link.mic_muted else "microphone")
        disconnect_icon = IconRightWidget(icon="link-off")
        item.add_widget(listen_icon)
        item.add_widget(mic_icon)
        item.add_widget(disconnect_icon)
        item.bind(on_release=lambda _i, lid=link_id: self._set_active_link(lid))
        listen_icon.bind(on_release=lambda _w, lid=link_id: self._toggle_listen(lid))
        mic_icon.bind(on_release=lambda _w, lid=link_id: self._toggle_mic(lid))
        disconnect_icon.bind(on_release=lambda _w, lid=link_id: self._disconnect_link(lid))
        item.link_id = link_id
        lst.add_widget(item)
        n = sum(1 for l in self._bridge.links if l.connected)
        self.status_text = f"{n} server(s) connected"

    def _on_link_disconnected(self, link_id: str, reason: str) -> None:
        lst = self.ids.connected_list
        for child in list(lst.children):
            if getattr(child, "link_id", None) == link_id:
                lst.remove_widget(child)
        self._presence.pop(link_id, None)
        if self._active_link_id == link_id:
            remaining = [getattr(c, "link_id", None) for c in lst.children]
            remaining = [x for x in remaining if x]
            self._active_link_id = remaining[0] if remaining else None
        self._refresh_people()
        if not self._bridge.links:
            self.status_text = f"Offline — {reason}"

    def _set_active_link(self, link_id: str) -> None:
        self._active_link_id = link_id
        link = self._bridge.get_link(link_id)
        if link:
            self.status_text = f"Active: {link.label}"
        self.chat_text = ""

    def _toggle_listen(self, link_id: str) -> None:
        link = self._bridge.get_link(link_id)
        if link:
            self._bridge.set_listen_muted(link_id, not link.listen_muted)

    def _toggle_mic(self, link_id: str) -> None:
        link = self._bridge.get_link(link_id)
        if link:
            self._bridge.set_mic_muted(link_id, not link.mic_muted)

    def _disconnect_link(self, link_id: str) -> None:
        link = self._bridge.get_link(link_id)
        label = link.label if link else link_id
        self._bridge.disconnect(link_id)
        self.status_text = f"Disconnected from {label}"

    def toggle_mute(self):
        self.is_muted = not self.is_muted
        self._bridge.set_global_muted(self.is_muted)

    def toggle_ptt(self):
        self.ptt_active = not self.ptt_active
        self._bridge.set_global_ptt(self.ptt_active)

    def send_chat(self):
        if not self._active_link_id:
            return
        text = self.ids.chat_input.text.strip()
        if text:
            self._bridge.send_chat(self._active_link_id, text)
            self.ids.chat_input.text = ""

    def _on_presence(self, link_id: str, participants) -> None:
        self._presence[link_id] = participants
        self._refresh_people()

    def _refresh_people(self) -> None:
        from kivymd.uix.list import OneLineAvatarIconListItem, IconRightWidget

        lst = self.ids.people_list
        lst.clear_widgets()
        for lid, participants in self._presence.items():
            link = self._bridge.get_link(lid)
            label = link.label if link else lid
            pending = link.pending_taps if link else set()
            my_id = link.client_id if link else ""
            for p in participants:
                cid = str(p.get("client_id", ""))
                name = str(p.get("name", "?"))
                tap_mark = " 👆" if cid in pending else ""
                speak = " 🔊" if p.get("speaking") else ""
                item = OneLineAvatarIconListItem(text=f"{name}{tap_mark}{speak} · {label}")
                if cid != my_id:
                    tap_btn = IconRightWidget(icon="gesture-tap")
                    tap_btn.bind(on_release=lambda _w, ll=lid, pid=cid: self._send_tap(ll, pid))
                    item.add_widget(tap_btn)
                    if cid in pending or (ll := lid) and self._tap_ids.get((ll, cid)):
                        chat_btn = IconRightWidget(icon="message-text")
                        chat_btn.bind(
                            on_release=lambda _w, ll=lid, pid=cid, n=name: self._open_tap_chat(ll, pid, n)
                        )
                        item.add_widget(chat_btn)
                elif cid == my_id:
                    item.text = f"{name} (you) · {label}{speak}"
                lst.add_widget(item)

    def _send_tap(self, link_id: str, target_id: str) -> None:
        self._bridge.send_tap(link_id, target_id)

    def _open_tap_chat(self, link_id: str, peer_id: str, name: str) -> None:
        tap_id = self._tap_ids.get((link_id, peer_id))
        if tap_id:
            self._open_tap_dialog(link_id, tap_id, peer_id, name)

    def _on_tap_received(self, link_id: str, data: dict) -> None:
        tap_id = str(data.get("tap_id", ""))
        from_id = str(data.get("from_id", ""))
        from_name = str(data.get("from_name", "?"))
        target_id = str(data.get("target_id", ""))
        target_name = str(data.get("target_name", ""))
        peer_id = target_id if data.get("self_sent") else from_id
        if tap_id and peer_id:
            self._tap_ids[(link_id, peer_id)] = tap_id
        if not data.get("self_sent"):
            self._refresh_people()
            self.status_text = f"Tap from {from_name} — tap message icon to open"
        elif target_name:
            self.status_text = f"Tap sent to {target_name}"

    def _open_tap_dialog(self, link_id: str, tap_id: str, peer_id: str, peer_name: str) -> None:
        from kivymd.uix.button import MDFlatButton, MDRaisedButton
        from kivymd.uix.label import MDLabel
        from kivymd.uix.textfield import MDTextField

        self._tap_link_id = link_id
        self._tap_id = tap_id
        self._tap_peer_name = peer_name
        self._tap_messages = []
        self._bridge.open_tap(link_id, tap_id)
        self._bridge.clear_pending_tap(link_id, peer_id)

        self._tap_input = MDTextField(hint_text="Tap message…")
        self._tap_log = MDLabel(text="", size_hint_y=None)

        def send_msg(*_args):
            text = self._tap_input.text.strip()
            if text:
                self._bridge.send_tap_chat(link_id, tap_id, text)
                self._tap_input.text = ""

        def save_tap(*_args):
            reminder = f"Follow up with {peer_name}"
            get_tap_store().add(
                SavedTap.create(
                    peer_id=peer_id,
                    peer_name=peer_name,
                    server_label=link.label if (link := self._bridge.get_link(link_id)) else link_id,
                    reminder=reminder,
                    messages=list(self._tap_messages),
                )
            )
            self.status_text = "Tap saved"

        def close_tap(*_args):
            if self._tap_dialog:
                self._tap_dialog.dismiss()
            self._bridge.end_tap(link_id, tap_id)
            self._tap_messages.clear()

        self._tap_dialog = MDDialog(
            title=f"Tap — {peer_name}",
            type="custom",
            content_cls=self._tap_log,
            buttons=[
                MDRaisedButton(text="Save Tap", on_release=save_tap),
                MDRaisedButton(text="Send", on_release=send_msg),
                MDFlatButton(text="Close", on_release=close_tap),
            ],
        )
        box = self._tap_dialog.content_cls.parent
        if box and self._tap_input not in box.children:
            box.add_widget(self._tap_input)
        self._tap_dialog.open()
        self._refresh_people()

    def _on_tap_chat(self, data: dict) -> None:
        if self._tap_dialog and self._tap_log:
            line = f"{data.get('name', '?')}: {data.get('text', '')}\n"
            self._tap_messages.append({"name": data.get("name"), "text": data.get("text")})
            self._tap_log.text += line


class BabbleCastMobileApp(MDApp):
    def build(self):
        Builder.load_string(KV)
        return BabbleMobileScreen()

    def on_pause(self):
        return True


if __name__ == "__main__":
    BabbleCastMobileApp().run()
