"""
BabbleCast mobile client — Tokyo Night UI with bottom navigation.
"""

from __future__ import annotations

import threading
from typing import Any

from kivy.clock import Clock
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
from mobile.android_network import acquire_multicast_lock, release_multicast_lock
from mobile.permissions import location_granted, request_android_permissions
from mobile.theme import ACCENT, BG, MUTED, SURFACE, TEXT, apply_theme


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
            on_rooms=lambda lid, r: Clock.schedule_once(lambda _dt, i=lid, rooms=r: self._on_rooms(i, rooms)),
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
        self._rooms: dict[str, list] = {}
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
        live = self.app.screen("live")
        if hasattr(live, "status_text"):
            live.status_text = text

    def start_discovery(self) -> None:
        request_android_permissions()
        acquire_multicast_lock()
        self._discovery.start()
        self._apply_servers(self._discovery.servers)
        screen = self.app.screen("connect")
        if location_granted():
            screen.set_discovery_status("Searching LAN for BabbleCast servers…")
        else:
            screen.set_discovery_status(
                "Grant Location permission for auto-discover, or enter PC IP below"
            )

    def stop_all(self) -> None:
        self._discovery.stop()
        release_multicast_lock()
        self._bridge.disconnect_all()
        if self._embedded and self._embedded.running:
            self._embedded.stop()

    def _apply_servers(self, servers) -> None:
        screen = self.app.screen("connect")
        screen.update_servers(servers)
        if servers:
            screen.set_discovery_status(f"{len(servers)} server(s) on your network — tap one to connect")
        elif location_granted():
            screen.set_discovery_status("No servers found yet — same Wi‑Fi as PC, or enter IP below")

    def connect_to(self, host: str, port: int, display_name: str) -> None:
        host = host.strip()
        if not host:
            self.set_status("Enter a server IP or hostname")
            return
        try:
            port = int(port)
        except (TypeError, ValueError):
            self.set_status("Port must be a number (usually 8765)")
            return
        self._pending_host = host
        self._pending_port = port
        self.connect_selected(display_name, host=host, port=port)

    def connect_selected(
        self,
        display_name: str,
        *,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        host = (host or self._pending_host or self._settings.last_server_host or "").strip()
        port = port or self._pending_port or self._settings.last_server_port or 8765
        if not host:
            self.set_status("Pick a discovered server or enter IP:port below")
            return
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
            self.stop_hosting()
            return
        self._prompt_host_server_name()

    def stop_hosting(self) -> None:
        if self._embedded and self._embedded.running:
            self._embedded.stop()
            self._embedded = None
            self.set_status("Server stopped")
        self.refresh_host_ui()

    def refresh_host_ui(self) -> None:
        screen = self.app.screen("connect")
        if hasattr(screen, "set_hosting"):
            screen.set_hosting(bool(self._embedded and self._embedded.running))

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
        self.refresh_host_ui()
        threading.Timer(0.8, lambda: Clock.schedule_once(lambda _dt: self._join_local_host())).start()

    def _join_local_host(self) -> None:
        screen = self.app.screen("connect")
        self.connect_to("127.0.0.1", 8765, screen.display_name)

    def _on_link_connected(self, link_id: str) -> None:
        link = self._bridge.get_link(link_id)
        if not link:
            return
        if not self._active_link_id:
            self._active_link_id = link_id
        self._bridge.request_rooms(link_id)
        live = self.app.screen("live")
        live.add_connected_link(link_id, link)
        n = sum(1 for l in self._bridge.links if l.connected)
        self.set_status(f"{n} server(s) connected")
        rooms = self._rooms.get(link_id, [])
        live.update_rooms(rooms, self._active_link_id == link_id)

    def _on_link_disconnected(self, link_id: str, reason: str) -> None:
        live = self.app.screen("live")
        live.remove_connected_link(link_id)
        self._presence.pop(link_id, None)
        self._rooms.pop(link_id, None)
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
        live = self.app.screen("live")
        live.chat_text = ""
        rooms = self._rooms.get(link_id, [])
        live.update_rooms(rooms, True)

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
        live = self.app.screen("live")
        live.is_muted = self.is_muted

    def toggle_ptt(self) -> None:
        self.ptt_active = not self.ptt_active
        self._bridge.set_global_ptt(self.ptt_active)
        live = self.app.screen("live")
        live.ptt_active = self.ptt_active

    def send_chat(self, text: str) -> None:
        if not self._active_link_id or not text.strip():
            return
        self._bridge.send_chat(self._active_link_id, text.strip())

    def _on_presence(self, link_id: str, participants) -> None:
        self._presence[link_id] = participants
        live = self.app.screen("live")
        live.refresh_people(self._presence, self._bridge, self._tap_ids, self._active_link_id)

    def _on_rooms(self, link_id: str, rooms: list) -> None:
        self._rooms[link_id] = rooms
        live = self.app.screen("live")
        live.update_rooms(rooms, self._active_link_id == link_id)

    def join_room(self, room_id: str) -> None:
        if not self._active_link_id:
            return
        self._bridge.join_room(self._active_link_id, room_id)
        self.set_status("Switching room…")

    def create_room(self, name: str) -> None:
        if not self._active_link_id or not name.strip():
            return
        self._bridge.create_room(self._active_link_id, name.strip())
        self.set_status(f"Creating room “{name.strip()}”…")

    def show_person_details(self, link_id: str, participant: dict) -> None:
        from kivymd.uix.button import MDFlatButton, MDRaisedButton
        from kivymd.uix.dialog import MDDialog
        from kivymd.uix.label import MDLabel
        from kivymd.uix.slider import MDSlider

        cid = str(participant.get("client_id", ""))
        name = str(participant.get("name", "?"))
        link = self._bridge.get_link(link_id)
        server = link.label if link else link_id
        my_id = link.client_id if link else ""
        is_self = cid == my_id
        pending = link.pending_taps if link else set()
        has_tap = cid in pending or bool(self._tap_ids.get((link_id, cid)))
        composite = composite_participant_key(link_id, cid)
        muted = bool(participant.get("muted", False))
        speaking = bool(participant.get("speaking", False))
        voice_level = float(participant.get("voice_level", 0))
        volume = float(participant.get("volume", 1.0))

        info = MDLabel(
            text=(
                f"Server: {server}\n"
                f"Speaking: {'Yes' if speaking else 'No'}\n"
                f"Voice level: {voice_level:.0%}\n"
                f"Tap pending: {'Yes' if has_tap else 'No'}"
            ),
            theme_text_color="Custom",
            text_color=TEXT,
            size_hint_y=None,
        )
        info.bind(texture_size=lambda _l, s: setattr(info, "height", s[1]))
        body = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, adaptive_height=True)
        body.add_widget(info)

        vol_label = MDLabel(
            text=f"Your volume: {int(volume * 100)}%",
            theme_text_color="Custom",
            text_color=TEXT,
            size_hint_y=None,
            height=dp(24),
        )
        vol_slider = MDSlider(min=0, max=200, value=int(volume * 100), step=1)

        def on_vol_change(_slider, value: float) -> None:
            vol_label.text = f"Your volume: {int(value)}%"
            self._bridge.set_participant_volume(composite, value / 100.0)

        vol_slider.bind(value=on_vol_change)
        body.add_widget(vol_label)
        body.add_widget(vol_slider)

        mute_state = {"muted": muted}

        def toggle_mute(_btn: MDRaisedButton) -> None:
            mute_state["muted"] = not mute_state["muted"]
            self._bridge.set_participant_muted(composite, mute_state["muted"])
            _btn.text = "Unmute" if mute_state["muted"] else "Mute"

        mute_btn = MDRaisedButton(text="Unmute" if muted else "Mute", on_release=toggle_mute)
        body.add_widget(mute_btn)

        dialog_holder: list[MDDialog] = []

        def close(_dlg: MDDialog, *_args) -> None:
            dialog_holder[0].dismiss()

        buttons = [MDFlatButton(text="Close", on_release=close)]
        if not is_self:
            buttons.insert(
                0,
                MDRaisedButton(
                    text="Tap",
                    on_release=lambda *_: (dialog_holder[0].dismiss(), self._send_tap(link_id, cid)),
                ),
            )
            if has_tap:
                buttons.insert(
                    0,
                    MDRaisedButton(
                        text="Tap chat",
                        on_release=lambda *_: (
                            dialog_holder[0].dismiss(),
                            self._open_tap_chat(link_id, cid, name),
                        ),
                    ),
                )

        dialog = MDDialog(
            title=f"{name}{' (you)' if is_self else ''}",
            type="custom",
            content_cls=body,
            buttons=buttons,
        )
        dialog_holder.append(dialog)
        dialog.open()

    def _on_chat(self, link_id: str, data: dict) -> None:
        if link_id != self._active_link_id:
            return
        line = f"{data.get('name', '?')}: {data.get('text', '')}\n"
        live = self.app.screen("live")
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
            live = self.app.screen("live")
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
        live = self.app.screen("live")
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
        if not getattr(app, "controller", None):
            return
        self.display_name = app.controller.settings.display_name or "Mobile"
        app.controller.refresh_host_ui()

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

        discover_label = MDLabel(text="Discover (same Wi‑Fi)", font_style="H6", theme_text_color="Custom", text_color=TEXT)
        self._discovery_status = MDLabel(
            text="Searching…",
            theme_text_color="Custom",
            text_color=MUTED,
            font_style="Caption",
            size_hint_y=None,
            height=dp(36),
        )
        self._server_box = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        self._server_box.bind(minimum_height=self._server_box.setter("height"))
        server_scroll = ScrollView(size_hint_y=None, height=dp(160))
        server_scroll.add_widget(self._server_box)

        manual_label = MDLabel(
            text="Or connect manually (PC LAN IP, not 127.0.0.1)",
            font_style="H6",
            theme_text_color="Custom",
            text_color=TEXT,
        )
        manual_row = MDBoxLayout(spacing=dp(8), size_hint_y=None, height=dp(48))
        settings = get_settings()
        self._host_field = MDTextField(
            hint_text="Server IP",
            text=settings.last_server_host or "",
            size_hint_x=0.65,
        )
        self._port_field = MDTextField(
            hint_text="Port",
            text=str(settings.last_server_port or 8765),
            size_hint_x=0.35,
        )
        manual_row.add_widget(self._host_field)
        manual_row.add_widget(self._port_field)

        btn_row = MDBoxLayout(spacing=dp(12), size_hint_y=None, height=dp(48))
        self._host_btn = MDRaisedButton(text="Host on this phone", md_bg_color=ACCENT, on_release=lambda *_: self._host())
        connect_btn = MDRaisedButton(text="Connect", on_release=lambda *_: self._connect())
        btn_row.add_widget(self._host_btn)
        btn_row.add_widget(connect_btn)

        for w in (
            header,
            sub,
            self._name_field,
            discover_label,
            self._discovery_status,
            server_scroll,
            manual_label,
            manual_row,
            btn_row,
        ):
            root.add_widget(w)
        self.add_widget(root)

    def _host(self) -> None:
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        app.controller.host_server()

    def _connect(self) -> None:
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        try:
            port = int(self._port_field.text.strip() or "8765")
        except ValueError:
            port = 8765
        app.controller.connect_to(self._host_field.text, port, self._name_field.text)

    def set_hosting(self, active: bool) -> None:
        self._host_btn.text = "Stop hosting" if active else "Host on this phone"

    def set_discovery_status(self, text: str) -> None:
        self._discovery_status.text = text

    def update_servers(self, servers) -> None:
        from kivymd.uix.button import MDFlatButton

        self._server_box.clear_widgets()
        if not servers:
            from kivymd.uix.label import MDLabel

            self._server_box.add_widget(
                MDLabel(
                    text="Nothing on LAN yet — enter your PC’s IP below (Settings → Wi‑Fi on PC for address)",
                    theme_text_color="Custom",
                    text_color=MUTED,
                    size_hint_y=None,
                    height=dp(56),
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
            card.bind(on_release=lambda _c, h=s.host, p=s.ws_port, n=s.name: self._connect_server(h, p, n))
            self._server_box.add_widget(card)

    def _connect_server(self, host: str, port: int, _name: str) -> None:
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        app.controller.connect_to(host, port, self._name_field.text)


class PersonNameRow(MDBoxLayout):
    """Name-only row; long-press opens context menu with More details."""

    def __init__(self, name: str, on_more_details, **kwargs):
        super().__init__(**kwargs)
        self._on_more_details = on_more_details
        self._hold_event = None
        self._menu = None
        self.size_hint_y = None
        self.height = dp(44)
        from kivymd.uix.label import MDLabel

        self.add_widget(
            MDLabel(
                text=name,
                theme_text_color="Custom",
                text_color=TEXT,
                size_hint_x=1,
            )
        )

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._hold_event = Clock.schedule_once(lambda _dt: self._open_context_menu(), 0.45)
            return True
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if self._hold_event is not None:
            Clock.unschedule(self._hold_event)
            self._hold_event = None
        return super().on_touch_up(touch)

    def _open_context_menu(self) -> None:
        self._hold_event = None
        from kivymd.uix.menu import MDDropdownMenu

        def open_details(*_args) -> None:
            if self._menu:
                self._menu.dismiss()
            self._on_more_details()

        self._menu = MDDropdownMenu(
            caller=self,
            items=[{"text": "More details", "on_release": open_details}],
            width_mult=3,
        )
        self._menu.open()


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
        conn_scroll = ScrollView(size_hint_y=None, height=dp(100))
        conn_scroll.add_widget(self._connected_box)

        rooms_label = MDLabel(text="Rooms (active server)", font_style="H6", theme_text_color="Custom", text_color=TEXT)
        room_create = MDBoxLayout(spacing=dp(8), size_hint_y=None, height=dp(48))
        self._new_room_field = MDTextField(
            hint_text="New room name",
            size_hint_x=0.7,
            on_text_validate=lambda *_: self._create_room(),
        )
        create_room_btn = MDRaisedButton(text="Create room", size_hint_x=0.3, on_release=lambda *_: self._create_room())
        room_create.add_widget(self._new_room_field)
        room_create.add_widget(create_room_btn)
        self._rooms_box = MDBoxLayout(orientation="vertical", spacing=dp(4), size_hint_y=None)
        self._rooms_box.bind(minimum_height=self._rooms_box.setter("height"))
        rooms_scroll = ScrollView(size_hint_y=None, height=dp(80))
        rooms_scroll.add_widget(self._rooms_box)

        people_label = MDLabel(text="People in room", font_style="H6", theme_text_color="Custom", text_color=TEXT)
        self._people_box = MDBoxLayout(orientation="vertical", spacing=dp(4), size_hint_y=None)
        self._people_box.bind(minimum_height=self._people_box.setter("height"))
        people_scroll = ScrollView(size_hint_y=None, height=dp(120))
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
            rooms_label,
            room_create,
            rooms_scroll,
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

    def _create_room(self) -> None:
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        name = self._new_room_field.text.strip()
        if name:
            app.controller.create_room(name)
            self._new_room_field.text = ""

    def update_rooms(self, rooms: list, is_active: bool) -> None:
        from kivymd.uix.label import MDLabel

        self._rooms_box.clear_widgets()
        if not is_active:
            return
        if not rooms:
            self._rooms_box.add_widget(
                MDLabel(
                    text="Default room",
                    theme_text_color="Custom",
                    text_color=MUTED,
                    size_hint_y=None,
                    height=dp(32),
                )
            )
            return
        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        for r in rooms:
            rid = str(r.get("room_id", ""))
            name = str(r.get("name", "Room"))
            count = int(r.get("member_count", 0))
            row = MDCard(
                padding=dp(8),
                size_hint_y=None,
                height=dp(40),
                md_bg_color=SURFACE,
                ripple_behavior=True,
            )
            row.add_widget(
                MDLabel(
                    text=f"{name} ({count})",
                    theme_text_color="Custom",
                    text_color=TEXT,
                )
            )
            row.bind(on_release=lambda _w, r=rid: app.controller.join_room(r))
            self._rooms_box.add_widget(row)

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
        from kivymd.uix.label import MDLabel

        self._people_box.clear_widgets()
        if not active_link_id:
            self._people_box.add_widget(
                MDLabel(
                    text="Connect to a server to see people in your room",
                    theme_text_color="Custom",
                    text_color=MUTED,
                    size_hint_y=None,
                    height=dp(40),
                )
            )
            return

        app = MDApp.get_running_app()
        assert isinstance(app, BabbleCastMobileApp)
        link = bridge.get_link(active_link_id)
        my_id = link.client_id if link else ""
        participants = presence.get(active_link_id, [])

        if not participants:
            self._people_box.add_widget(
                MDLabel(
                    text="Nobody else in this room yet",
                    theme_text_color="Custom",
                    text_color=MUTED,
                    size_hint_y=None,
                    height=dp(40),
                )
            )
            return

        for p in participants:
            cid = str(p.get("client_id", ""))
            name = str(p.get("name", "?"))
            if cid == my_id:
                name = f"{name} (you)"
            row = PersonNameRow(
                name,
                on_more_details=lambda ll=active_link_id, part=dict(p): app.controller.show_person_details(ll, part),
            )
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
        return root

    def switch_tab(self, name: str) -> None:
        self._screen_manager.current = name

    def screen(self, name: str) -> MDScreen:
        return self._screen_manager.get_screen(name)

    def on_stop(self) -> None:
        self.controller.stop_all()

    def on_pause(self) -> bool:
        return True


if __name__ == "__main__":
    BabbleCastMobileApp().run()
