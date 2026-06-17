"""
BabbleCast mobile client — Tokyo Night UI with bottom navigation.
"""

from __future__ import annotations

import threading
from typing import Any

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.screen import MDScreen
from kivymd.uix.screenmanager import MDScreenManager

from babblecast.client.bridge import BridgeManager
from babblecast.config import get_settings, save_settings
from babblecast.constants import MAX_NAME_LEN, composite_participant_key
from babblecast.discovery import ServerDiscovery
from babblecast.server.embedded import EmbeddedServer
from babblecast.taps import SavedTap, get_tap_store
from mobile.permissions import request_android_permissions
from mobile.theme import ACCENT, BG, MUTED, SURFACE, TEXT, apply_theme

KV = """
MDNavigationLayout:
    id: nav_layout

    MDScreenManager:
        id: screen_manager

        ConnectScreen:
            name: "connect"

        LiveScreen:
            name: "live"

        SettingsScreen:
            name: "settings"

    MDBottomNavigation:
        id: bottom_nav
        md_bg_color: app.theme_cls.bg_dark
        panel_color: [0.14, 0.15, 0.24, 1]
        text_color_active: [0.48, 0.64, 0.97, 1]
        MDBottomNavigationItem:
            icon: "lan-connect"
            text: "Connect"
            on_tab_press: app.switch_tab("connect")
        MDBottomNavigationItem:
            icon: "account-voice"
            text: "Live"
            on_tab_press: app.switch_tab("live")
        MDBottomNavigationItem:
            icon: "tune"
            text: "Settings"
            on_tab_press: app.switch_tab("settings")
"""


class BabbleController:
    """Shared bridge / discovery / tap logic for all mobile screens."""

    def __init__(self, app: BabbleCastMobileApp) -> None:
        self.app = app
        self._settings = get_settings()
        self._bridge = BridgeManager(
            on_link_connected=lambda lid: Clock.schedule_once(lambda _dt, i=lid: self._on_link_connected(i)),
            on_link_disconnected=lambda lid, r: Clock.schedule_once(
                lambda _dt, i=lid, reason=r: self._on_link_disconnected(i, reason)
            ),
            on_presence=lambda lid, rid, p: Clock.schedule_once(
                lambda _dt, i=lid, parts=p: self._on_presence(i, parts)
            ),
            on_chat=lambda lid, d: Clock.schedule_once(lambda _dt, i=lid, msg=d: self._on_chat(i, msg)),
            on_error=lambda lid, m: Clock.schedule_once(lambda _dt, msg=m: self.set_status(msg)),
            on_tap_received=lambda lid, d: Clock.schedule_once(
                lambda _dt, i=lid, data=d: self._on_tap_received(i, data)
            ),
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
        self._pending_host: str | None = None
        self._pending_port: int | None = None
        self.status_text = "Offline — connect to one or more servers"
        self.chat_text = ""
        self.is_muted = False
        self.ptt_active = False

    @property
    def settings(self):
        return self._settings

    def set_status(self, text: str) -> None:
        self.status_text = text
        live = self.app.root.ids.screen_manager.get_screen("live")
        if hasattr(live, "status_text"):
            live.status_text = text

    def start_discovery(self) -> None:
        request_android_permissions()
        self._discovery.start()

    def stop_all(self) -> None:
        self._discovery.stop()
        self._bridge.disconnect_all()
        if self._embedded and self._embedded.running:
            self._embedded.stop()

    def _apply_servers(self, servers) -> None:
        screen = self.app.root.ids.screen_manager.get_screen("connect")
        screen.update_servers(servers)

    def select_server(self, host: str, port: int) -> None:
        self._pending_host = host
        self._pending_port = port
        self.set_status(f"Selected {host}:{port} — tap Connect")

    def connect_selected(self, display_name: str) -> None:
        host = self._pending_host or self._settings.last_server_host or "127.0.0.1"
        port = self._pending_port or self._settings.last_server_port or 8765
        for link in self._bridge.links:
            if link.host == host and link.port == port and link.connected:
                self.set_status(f"Already on {host}:{port}")
                return
        self._settings.display_name = display_name.strip()
        self._settings.last_server_host = host
        self._settings.last_server_port = port
        save_settings(self._settings)
        self._bridge.update_settings(self._settings)
        self.set_status(f"Connecting {host}:{port}…")
        self._bridge.connect(host, port)
        self.app.switch_tab("live")

    def host_server(self) -> None:
        if self._embedded and self._embedded.running:
            self.set_status("Server already running — use Connect to join it")
            return
        self._prompt_host_server_name()

    def _prompt_host_server_name(self) -> None:
        from kivymd.uix.button import MDFlatButton, MDRaisedButton
        from kivymd.uix.textfield import MDTextField

        default = self._settings.hosted_server_name or self._settings.display_name or "My Server"
        field = MDTextField(hint_text="Server name", text=default, size_hint_y=None, height=dp(48))

        dialog_holder: list[MDDialog] = []

        def cancel(_dlg: MDDialog, *_args) -> None:
            dialog_holder[0].dismiss()

        def start(_dlg: MDDialog, *_args) -> None:
            name = field.text.strip()
            if not name:
                self.set_status("Enter a server name to host")
                return
            dialog_holder[0].dismiss()
            self._start_host(name)

        dialog = MDDialog(
            title="Name your server",
            text="This is how others will see you in Discover.",
            type="custom",
            content_cls=field,
            buttons=[
                MDFlatButton(text="Cancel", on_release=cancel),
                MDRaisedButton(text="Start", on_release=start),
            ],
        )
        dialog_holder.append(dialog)
        field.bind(on_text_validate=lambda *_: start(dialog))
        dialog.open()

    def _start_host(self, name: str) -> None:
        clean = name.strip()[:MAX_NAME_LEN]
        self._settings.hosted_server_name = clean
        save_settings(self._settings)
        self._embedded = EmbeddedServer(server_name=clean)
        self._embedded.start()
        self.set_status(f"Hosting as “{clean}”…")
        threading.Timer(0.8, lambda: Clock.schedule_once(lambda _dt: self._join_local_host())).start()

    def _join_local_host(self) -> None:
        self.select_server("127.0.0.1", 8765)
        screen = self.app.root.ids.screen_manager.get_screen("connect")
        self.connect_selected(screen.display_name)

    def _on_link_connected(self, link_id: str) -> None:
        link = self._bridge.get_link(link_id)
        if not link:
            return
        if not self._active_link_id:
            self._active_link_id = link_id
        live = self.app.root.ids.screen_manager.get_screen("live")
        live.add_connected_link(link_id, link)
        n = sum(1 for l in self._bridge.links if l.connected)
        self.set_status(f"{n} server(s) connected")

    def _on_link_disconnected(self, link_id: str, reason: str) -> None:
        live = self.app.root.ids.screen_manager.get_screen("live")
        live.remove_connected_link(link_id)
        self._presence.pop(link_id, None)
        if self._active_link_id == link_id:
            remaining = live.connected_link_ids()
            self._active_link_id = remaining[0] if remaining else None
        live.refresh_people(self._presence, self._bridge, self._tap_ids, self._active_link_id)
        if not self._bridge.links:
            self.set_status(f"Offline — {reason}")

    def set_active_link(self, link_id: str) -> None:
        self._active_link_id = link_id
        link = self._bridge.get_link(link_id)
        if link:
            self.set_status(f"Active: {link.label}")
        self.chat_text = ""
        live = self.app.root.ids.screen_manager.get_screen("live")
        live.chat_text = ""

    def toggle_listen(self, link_id: str) -> None:
        link = self._bridge.get_link(link_id)
        if link:
            self._bridge.set_listen_muted(link_id, not link.listen_muted)

    def toggle_mic(self, link_id: str) -> None:
        link = self._bridge.get_link(link_id)
        if link:
            self._bridge.set_mic_muted(link_id, not link.mic_muted)

    def disconnect_link(self, link_id: str) -> None:
        link = self._bridge.get_link(link_id)
        label = link.label if link else link_id
        self._bridge.disconnect(link_id)
        self.set_status(f"Disconnected from {label}")

    def toggle_mute(self) -> None:
        self.is_muted = not self.is_muted
        self._bridge.set_global_muted(self.is_muted)
        live = self.app.root.ids.screen_manager.get_screen("live")
        live.is_muted = self.is_muted

    def toggle_ptt(self) -> None:
        self.ptt_active = not self.ptt_active
        self._bridge.set_global_ptt(self.ptt_active)
        live = self.app.root.ids.screen_manager.get_screen("live")
        live.ptt_active = self.ptt_active

    def send_chat(self, text: str) -> None:
        if not self._active_link_id or not text.strip():
            return
        self._bridge.send_chat(self._active_link_id, text.strip())

    def _on_presence(self, link_id: str, participants) -> None:
        self._presence[link_id] = participants
        live = self.app.root.ids.screen_manager.get_screen("live")
        live.refresh_people(self._presence, self._bridge, self._tap_ids, self._active_link_id)

    def _on_chat(self, link_id: str, data: dict) -> None:
        if link_id != self._active_link_id:
            return
        line = f"{data.get('name', '?')}: {data.get('text', '')}\n"
        live = self.app.root.ids.screen_manager.get_screen("live")
        live.chat_text += line

    def set_gate_db(self, value: float) -> None:
        self._bridge.set_gate_db(value)
        self._settings.gate_threshold_db = value
        save_settings(self._settings)

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
            live = self.app.root.ids.screen_manager.get_screen("live")
            live.refresh_people(self._presence, self._bridge, self._tap_ids, self._active_link_id)
            self.set_status(f"Tap from {from_name} — tap message icon to open")
        elif target_name:
            self.set_status(f"Tap sent to {target_name}")

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

        tap_input = MDTextField(hint_text="Tap message…")
        tap_log = MDLabel(text="", size_hint_y=None)

        def send_msg(*_args) -> None:
            text = tap_input.text.strip()
            if text:
                self._bridge.send_tap_chat(link_id, tap_id, text)
                tap_input.text = ""

        def save_tap(*_args) -> None:
            reminder = f"Follow up with {peer_name}"
            link = self._bridge.get_link(link_id)
            get_tap_store().add(
                SavedTap.create(
                    peer_id=peer_id,
                    peer_name=peer_name,
                    server_label=link.label if link else link_id,
                    reminder=reminder,
                    messages=list(self._tap_messages),
                )
            )
            self.set_status("Tap saved")

        def close_tap(*_args) -> None:
            if self._tap_dialog:
                self._tap_dialog.dismiss()
            self._bridge.end_tap(link_id, tap_id)
            self._tap_messages.clear()

        self._tap_dialog = MDDialog(
            title=f"Tap — {peer_name}",
            type="custom",
            content_cls=tap_log,
            buttons=[
                MDRaisedButton(text="Save Tap", on_release=save_tap),
                MDRaisedButton(text="Send", on_release=send_msg),
                MDFlatButton(text="Close", on_release=close_tap),
            ],
        )
        self._tap_input = tap_input
        self._tap_log = tap_log
        box = self._tap_dialog.content_cls.parent
        if box and tap_input not in box.children:
            box.add_widget(tap_input)
        self._tap_dialog.open()
        live = self.app.root.ids.screen_manager.get_screen("live")
        live.refresh_people(self._presence, self._bridge, self._tap_ids, self._active_link_id)

    def _on_tap_chat(self, data: dict) -> None:
        if self._tap_dialog and hasattr(self, "_tap_log"):
            line = f"{data.get('name', '?')}: {data.get('text', '')}\n"
            self._tap_messages.append({"name": data.get("name"), "text": data.get("text")})
            self._tap_log.text += line


class ConnectScreen(MDScreen):
    display_name = StringProperty("")

    def on_enter(self, *_args) -> None:
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        self.display_name = app.controller.settings.display_name or "Mobile"
        app.controller.start_discovery()

    def on_leave(self, *_args) -> None:
        pass

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = MDBoxLayout(orientation="vertical", md_bg_color=BG, padding=dp(16), spacing=dp(12))
        from kivymd.uix.label import MDLabel
        from kivymd.uix.textfield import MDTextField
        from kivymd.uix.button import MDRaisedButton, MDFlatButton
        from kivy.uix.scrollview import ScrollView

        header = MDLabel(text="BabbleCast", font_style="H4", theme_text_color="Custom", text_color=ACCENT)
        sub = MDLabel(
            text="Connect to a server or host your own",
            theme_text_color="Custom",
            text_color=MUTED,
            font_style="Body2",
        )
        self._name_field = MDTextField(hint_text="Your name", text=self.display_name)
        self._name_field.bind(text=lambda _w, v: setattr(self, "display_name", v))

        discover_label = MDLabel(text="Discover nearby", font_style="H6", theme_text_color="Custom", text_color=TEXT)
        self._server_box = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        self._server_box.bind(minimum_height=self._server_box.setter("height"))
        server_scroll = ScrollView(size_hint_y=None, height=dp(200))
        server_scroll.add_widget(self._server_box)

        btn_row = MDBoxLayout(spacing=dp(12), size_hint_y=None, height=dp(48))
        host_btn = MDRaisedButton(text="Host server", md_bg_color=ACCENT, on_release=lambda *_: self._host())
        connect_btn = MDFlatButton(text="Connect", on_release=lambda *_: self._connect())
        btn_row.add_widget(host_btn)
        btn_row.add_widget(connect_btn)

        for w in (header, sub, self._name_field, discover_label, server_scroll, btn_row):
            root.add_widget(w)
        self.add_widget(root)

    def _host(self) -> None:
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        app.controller.host_server()

    def _connect(self) -> None:
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        app.controller.connect_selected(self._name_field.text)

    def update_servers(self, servers) -> None:
        from kivymd.uix.button import MDFlatButton

        self._server_box.clear_widgets()
        if not servers:
            from kivymd.uix.label import MDLabel

            self._server_box.add_widget(
                MDLabel(
                    text="No servers found — host one or join manually from Live tab",
                    theme_text_color="Custom",
                    text_color=MUTED,
                    size_hint_y=None,
                    height=dp(48),
                )
            )
            return
        for s in servers:
            card = MDCard(
                orientation="vertical",
                padding=dp(12),
                size_hint_y=None,
                height=dp(72),
                md_bg_color=SURFACE,
                ripple_behavior=True,
            )
            from kivymd.uix.label import MDLabel

            card.add_widget(MDLabel(text=s.label, theme_text_color="Custom", text_color=TEXT, font_style="Subtitle1"))
            card.add_widget(
                MDLabel(
                    text=f"{s.host}:{s.ws_port}",
                    theme_text_color="Custom",
                    text_color=MUTED,
                    font_style="Caption",
                )
            )
            card.bind(on_release=lambda _c, h=s.host, p=s.ws_port: self._pick(h, p))
            self._server_box.add_widget(card)

    def _pick(self, host: str, port: int) -> None:
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        app.controller.select_server(host, port)


class LiveScreen(MDScreen):
    status_text = StringProperty("Offline")
    chat_text = StringProperty("")
    is_muted = BooleanProperty(False)
    ptt_active = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._link_items: dict[str, Any] = {}
        root = MDBoxLayout(orientation="vertical", md_bg_color=BG, padding=dp(12), spacing=dp(8))
        from kivymd.uix.label import MDLabel
        from kivymd.uix.textfield import MDTextField
        from kivymd.uix.button import MDRaisedButton, MDFlatButton
        from kivy.uix.scrollview import ScrollView

        self._status = MDLabel(text=self.status_text, theme_text_color="Custom", text_color=MUTED)
        self.bind(status_text=lambda _s, v: setattr(self._status, "text", v))

        conn_label = MDLabel(text="Connected servers", font_style="H6", theme_text_color="Custom", text_color=TEXT)
        self._connected_box = MDBoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        self._connected_box.bind(minimum_height=self._connected_box.setter("height"))
        conn_scroll = ScrollView(size_hint_y=None, height=dp(120))
        conn_scroll.add_widget(self._connected_box)

        people_label = MDLabel(text="People in room", font_style="H6", theme_text_color="Custom", text_color=TEXT)
        self._people_box = MDBoxLayout(orientation="vertical", spacing=dp(4), size_hint_y=None)
        self._people_box.bind(minimum_height=self._people_box.setter("height"))
        people_scroll = ScrollView(size_hint_y=None, height=dp(160))
        people_scroll.add_widget(self._people_box)

        ctrl = MDBoxLayout(spacing=dp(8), size_hint_y=None, height=dp(44))
        self._mute_btn = MDRaisedButton(text="Mute all", on_release=lambda *_: self._toggle_mute())
        self._ptt_btn = MDFlatButton(text="PTT", on_release=lambda *_: self._toggle_ptt())
        ctrl.add_widget(self._mute_btn)
        ctrl.add_widget(self._ptt_btn)

        self._chat_input = MDTextField(hint_text="Room chat (active server)", on_text_validate=lambda *_: self._send_chat())
        send_btn = MDRaisedButton(text="Send", size_hint_y=None, height=dp(44), on_release=lambda *_: self._send_chat())
        self._chat_log = MDLabel(
            text="",
            theme_text_color="Custom",
            text_color=TEXT,
            size_hint_y=None,
        )
        self._chat_log.bind(texture_size=lambda _l, s: setattr(self._chat_log, "height", s[1]))
        self.bind(chat_text=lambda _s, v: setattr(self._chat_log, "text", v))

        chat_scroll = ScrollView(size_hint_y=1)
        chat_scroll.add_widget(self._chat_log)

        for w in (
            self._status,
            conn_label,
            conn_scroll,
            people_label,
            people_scroll,
            ctrl,
            self._chat_input,
            send_btn,
            chat_scroll,
        ):
            root.add_widget(w)
        self.add_widget(root)

    def _toggle_mute(self) -> None:
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        app.controller.toggle_mute()
        self._mute_btn.text = "Unmute all" if self.is_muted else "Mute all"

    def _toggle_ptt(self) -> None:
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        app.controller.toggle_ptt()

    def _send_chat(self) -> None:
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        app.controller.send_chat(self._chat_input.text)
        self._chat_input.text = ""

    def connected_link_ids(self) -> list[str]:
        return list(self._link_items.keys())

    def add_connected_link(self, link_id: str, link) -> None:
        from kivymd.uix.button import MDIconButton

        row = MDBoxLayout(size_hint_y=None, height=dp(48), spacing=dp(4))
        card = MDCard(
            orientation="horizontal",
            padding=dp(8),
            size_hint_x=0.55,
            md_bg_color=SURFACE,
            ripple_behavior=True,
        )
        from kivymd.uix.label import MDLabel

        card.add_widget(MDLabel(text=link.label, theme_text_color="Custom", text_color=TEXT))
        card.bind(on_release=lambda *_: self._set_active(link_id))

        listen = MDIconButton(
            icon="volume-off" if link.listen_muted else "volume-high",
            on_release=lambda *_: self._listen(link_id),
        )
        mic = MDIconButton(
            icon="microphone-off" if link.mic_muted else "microphone",
            on_release=lambda *_: self._mic(link_id),
        )
        disc = MDIconButton(icon="link-off", on_release=lambda *_: self._disconnect(link_id))
        row.add_widget(card)
        row.add_widget(listen)
        row.add_widget(mic)
        row.add_widget(disc)
        self._link_items[link_id] = row
        self._connected_box.add_widget(row)

    def remove_connected_link(self, link_id: str) -> None:
        row = self._link_items.pop(link_id, None)
        if row:
            self._connected_box.remove_widget(row)

    def _set_active(self, link_id: str) -> None:
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        app.controller.set_active_link(link_id)

    def _listen(self, link_id: str) -> None:
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        app.controller.toggle_listen(link_id)

    def _mic(self, link_id: str) -> None:
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        app.controller.toggle_mic(link_id)

    def _disconnect(self, link_id: str) -> None:
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        app.controller.disconnect_link(link_id)

    def refresh_people(
        self,
        presence: dict,
        bridge: BridgeManager,
        tap_ids: dict,
        active_link_id: str | None,
    ) -> None:
        from kivymd.uix.button import MDIconButton
        from kivymd.uix.label import MDLabel

        self._people_box.clear_widgets()
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        for lid, participants in presence.items():
            link = bridge.get_link(lid)
            label = link.label if link else lid
            pending = link.pending_taps if link else set()
            my_id = link.client_id if link else ""
            for p in participants:
                cid = str(p.get("client_id", ""))
                name = str(p.get("name", "?"))
                tap_mark = " 👆" if cid in pending else ""
                speak = " 🔊" if p.get("speaking") else ""
                row = MDBoxLayout(size_hint_y=None, height=dp(40))
                text = f"{name}{tap_mark}{speak} · {label}"
                if cid == my_id:
                    text = f"{name} (you) · {label}{speak}"
                row.add_widget(MDLabel(text=text, theme_text_color="Custom", text_color=TEXT))
                if cid != my_id:
                    tap_btn = MDIconButton(
                        icon="gesture-tap",
                        on_release=lambda *_a, ll=lid, pid=cid: app.controller._send_tap(ll, pid),
                    )
                    row.add_widget(tap_btn)
                    if cid in pending or tap_ids.get((lid, cid)):
                        chat_btn = MDIconButton(
                            icon="message-text",
                            on_release=lambda *_a, ll=lid, pid=cid, n=name: app.controller._open_tap_chat(
                                ll, pid, n
                            ),
                        )
                        row.add_widget(chat_btn)
                self._people_box.add_widget(row)


class SettingsScreen(MDScreen):
    gate_db = NumericProperty(-40)

    def on_enter(self, *_args) -> None:
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        self.gate_db = int(app.controller.settings.gate_threshold_db)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = MDBoxLayout(orientation="vertical", md_bg_color=BG, padding=dp(16), spacing=dp(16))
        from kivymd.uix.label import MDLabel
        from kivymd.uix.slider import MDSlider

        root.add_widget(
            MDLabel(text="Audio", font_style="H5", theme_text_color="Custom", text_color=ACCENT)
        )
        self._gate_label = MDLabel(
            text="Noise gate: -40 dB",
            theme_text_color="Custom",
            text_color=TEXT,
        )
        slider = MDSlider(min=-80, max=0, value=-40, step=1)
        slider.bind(value=lambda _s, v: self._gate_changed(v))
        root.add_widget(self._gate_label)
        root.add_widget(slider)
        hint = MDLabel(
            text="Lower = more sensitive mic. Same gate as desktop BabbleCast.",
            theme_text_color="Custom",
            text_color=MUTED,
            font_style="Caption",
        )
        root.add_widget(hint)
        self.add_widget(root)

    def _gate_changed(self, value: float) -> None:
        self._gate_label.text = f"Noise gate: {int(value)} dB"
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        app.controller.set_gate_db(float(value))


class BabbleCastMobileApp(MDApp):
    controller: BabbleController

    def build(self):
        apply_theme(self)
        Builder.load_string(KV)
        self.controller = BabbleController(self)
        from kivymd.uix.navigationdrawer import MDNavigationLayout

        root = MDNavigationLayout()
        sm = MDScreenManager(id="screen_manager")
        sm.add_widget(ConnectScreen(name="connect"))
        sm.add_widget(LiveScreen(name="live"))
        sm.add_widget(SettingsScreen(name="settings"))
        root.add_widget(sm)
        from kivymd.uix.bottomnavigation import MDBottomNavigation, MDBottomNavigationItem

        nav = MDBottomNavigation(id="bottom_nav")
        for icon, text, name in (
            ("lan-connect", "Connect", "connect"),
            ("account-voice", "Live", "live"),
            ("tune", "Settings", "settings"),
        ):
            item = MDBottomNavigationItem(icon=icon, text=text)
            item.bind(on_tab_press=lambda _i, n=name: self.switch_tab(n))
            nav.add_widget(item)
        root.add_widget(nav)
        root.ids = {"screen_manager": sm, "bottom_nav": nav}
        return root

    def switch_tab(self, name: str) -> None:
        self.root.ids.screen_manager.current = name

    def on_stop(self) -> None:
        self.controller.stop_all()

    def on_pause(self) -> bool:
        return True


if __name__ == "__main__":
    BabbleCastMobileApp().run()
