"""BabbleCast mobile — KivyMD screens."""

from __future__ import annotations

import time

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.screen import MDScreen

from babblecast.client.bridge import BridgeManager
from babblecast.config import get_settings
from mobile.theme import ACCENT, BG, MUTED, SUCCESS, SURFACE, TEXT

class ConnectScreen(MDScreen):
    display_name = StringProperty("")

    def on_enter(self, *_args) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        if not getattr(app, "controller", None):
            return
        self.display_name = app.controller.settings.display_name or "Mobile"
        app.controller.refresh_host_ui()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = MDBoxLayout(orientation="vertical", md_bg_color=BG, padding=dp(16), spacing=dp(12))
        from kivymd.uix.label import MDLabel
        from kivymd.uix.textfield import MDTextField
        from kivymd.uix.button import MDRaisedButton, MDFlatButton
        from kivy.uix.scrollview import ScrollView

        header = MDLabel(text="BabbleCast", font_style="H4", theme_text_color="Custom", text_color=ACCENT)
        sub = MDLabel(
            text="Tap a server or enter IP — you'll set your name when you connect",
            theme_text_color="Custom",
            text_color=MUTED,
            font_style="Body2",
        )

        discover_label = MDLabel(text="Discover", font_style="H6", theme_text_color="Custom", text_color=TEXT)
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
        assert hasattr(app, "controller")
        app.controller.host_server()

    def _connect(self) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        try:
            port = int(self._port_field.text.strip() or "8765")
        except ValueError:
            port = 8765
        app.controller.connect_to(self._host_field.text, port)

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
                    text=f"{s.hostname or s.host}:{s.ws_port}",
                    theme_text_color="Custom",
                    text_color=MUTED,
                    font_style="Caption",
                )
            )
            card.bind(
                on_release=lambda _c, srv=s: self._connect_server(srv),
            )
            self._server_box.add_widget(card)

    def _connect_server(self, server) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        app.controller.connect_discovered(
            server.connect_host,
            server.ws_port,
            server.label,
            password_required=server.password_required,
        )


class PersonNameRow(MDBoxLayout):
    """Speaking LED + double-tap opens side detail panel."""

    def __init__(self, name: str, on_double_tap, *, speaking: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._on_double_tap = on_double_tap
        self._last_tap = 0.0
        self.size_hint_y = None
        self.height = dp(36)
        self.spacing = dp(6)
        from kivymd.uix.label import MDLabel

        self._led = MDLabel(
            text="●",
            theme_text_color="Custom",
            text_color=MUTED,
            size_hint_x=None,
            width=dp(16),
            halign="center",
        )
        self.set_speaking(speaking)
        self.add_widget(self._led)
        self.add_widget(
            MDLabel(
                text=name,
                theme_text_color="Custom",
                text_color=TEXT,
                size_hint_x=1,
                font_style="Body2",
            )
        )

    def set_speaking(self, speaking: bool) -> None:
        from mobile.theme import SUCCESS

        self._led.text_color = SUCCESS if speaking else MUTED

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos):
            now = time.time()
            if now - self._last_tap < 0.35:
                self._on_double_tap()
                self._last_tap = 0.0
                return True
            self._last_tap = now
            return True
        return super().on_touch_up(touch)


class LiveScreen(MDScreen):
    status_text = StringProperty("Offline")
    chat_text = StringProperty("")
    current_room_text = StringProperty("In room: —")
    is_muted = BooleanProperty(False)
    ptt_active = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._link_items: dict[str, Any] = {}
        from kivy.uix.boxlayout import BoxLayout
        from kivymd.uix.button import MDIconButton
        from kivymd.uix.label import MDLabel
        from kivymd.uix.textfield import MDTextField
        from kivymd.uix.button import MDRaisedButton
        from kivy.uix.scrollview import ScrollView
        from mobile.detail_panel import SideDetailPanel

        outer = BoxLayout(orientation="horizontal")
        main = MDBoxLayout(orientation="vertical", md_bg_color=BG, padding=dp(6), spacing=dp(4))

        self._status = MDLabel(
            text=self.status_text,
            theme_text_color="Custom",
            text_color=MUTED,
            font_style="Caption",
            size_hint_y=None,
            height=dp(22),
        )
        self.bind(status_text=lambda _s, v: setattr(self._status, "text", v))

        self._connected_box = MDBoxLayout(orientation="horizontal", spacing=dp(4), size_hint_y=None, height=dp(44))
        self._current_room = MDLabel(
            text=self.current_room_text,
            theme_text_color="Custom",
            text_color=ACCENT,
            font_style="Caption",
            size_hint_y=None,
            height=dp(20),
        )
        self.bind(current_room_text=lambda _s, v: setattr(self._current_room, "text", v))
        room_create = MDBoxLayout(spacing=dp(4), size_hint_y=None, height=dp(40))
        self._new_room_field = MDTextField(
            hint_text="New room",
            size_hint_x=0.65,
            font_size=dp(13),
            on_text_validate=lambda *_: self._create_room(),
        )
        create_room_btn = MDRaisedButton(text="+", size_hint_x=0.35, on_release=lambda *_: self._create_room())
        room_create.add_widget(self._new_room_field)
        room_create.add_widget(create_room_btn)
        self._rooms_box = MDBoxLayout(orientation="horizontal", spacing=dp(4), size_hint_y=None, height=dp(36))

        self._people_box = MDBoxLayout(orientation="vertical", spacing=dp(2), size_hint_y=None)
        self._people_box.bind(minimum_height=self._people_box.setter("height"))
        people_scroll = ScrollView(size_hint_y=None, height=dp(72))
        people_scroll.add_widget(self._people_box)

        self._chat_log = MDLabel(text="", theme_text_color="Custom", text_color=TEXT, font_style="Body2", size_hint_y=None)
        self._chat_log.bind(texture_size=lambda _l, s: setattr(self._chat_log, "height", max(dp(24), s[1])))
        self.bind(chat_text=lambda _s, v: setattr(self._chat_log, "text", v))
        chat_scroll = ScrollView(size_hint_y=1)
        chat_scroll.add_widget(self._chat_log)

        chat_row = MDBoxLayout(spacing=dp(4), size_hint_y=None, height=dp(44))
        self._mute_btn = MDIconButton(icon="microphone", on_release=lambda *_: self._toggle_mute())
        self._ptt_btn = MDIconButton(icon="record-circle-outline", on_release=lambda *_: self._toggle_ptt())
        self.bind(ptt_active=self._sync_ptt_icon)
        self._chat_input = MDTextField(
            hint_text="Type a message, then hit ↵",
            on_text_validate=lambda *_: self._send_chat(),
            font_size=dp(13),
        )
        chat_row.add_widget(self._mute_btn)
        chat_row.add_widget(self._ptt_btn)
        chat_row.add_widget(self._chat_input)

        for w in (
            self._status,
            self._connected_box,
            self._current_room,
            room_create,
            self._rooms_box,
            people_scroll,
            chat_scroll,
            chat_row,
        ):
            main.add_widget(w)

        app_stub = MDApp.get_running_app()
        controller = getattr(app_stub, "controller", None)
        self.detail_panel = SideDetailPanel(controller) if controller else None
        outer.add_widget(main)
        if self.detail_panel:
            outer.add_widget(self.detail_panel)
        self.add_widget(outer)

    def on_enter(self, *_args) -> None:
        app = MDApp.get_running_app()
        if not hasattr(app, "controller"):
            return
        if self.detail_panel is None:
            from kivy.uix.boxlayout import BoxLayout
            from mobile.detail_panel import SideDetailPanel

            outer = self.children[0] if self.children else None
            if isinstance(outer, BoxLayout):
                self.detail_panel = SideDetailPanel(app.controller)
                outer.add_widget(self.detail_panel)
        elif hasattr(self.detail_panel, "_controller"):
            self.detail_panel._controller = app.controller
        app.controller.on_live_enter()

    def _toggle_mute(self) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        app.controller.toggle_mute()
        self._mute_btn.icon = "microphone-off" if self.is_muted else "microphone"

    def _sync_ptt_icon(self, _instance, value: bool) -> None:
        if hasattr(self, "_ptt_btn"):
            self._ptt_btn.icon = "record-circle" if value else "record-circle-outline"

    def _toggle_ptt(self) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        app.controller.toggle_ptt()
        self._sync_ptt_icon(self, self.ptt_active)

    def _send_chat(self) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        app.controller.send_chat(self._chat_input.text)
        self._chat_input.text = ""

    def _create_room(self) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        name = self._new_room_field.text.strip()
        if name:
            app.controller.create_room(name)
            self._new_room_field.text = ""

    def update_rooms(self, rooms: list, is_active: bool, current_room_id: str = "") -> None:
        from kivy.clock import Clock
        from kivymd.uix.label import MDLabel

        self._rooms_box.clear_widgets()
        if not is_active:
            return
        if not rooms:
            self._rooms_box.add_widget(
                MDLabel(
                    text="General",
                    theme_text_color="Custom",
                    text_color=MUTED,
                    font_style="Caption",
                    size_hint_x=None,
                    width=dp(72),
                )
            )
            return
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        can_delete = len(rooms) > 1
        for r in rooms:
            rid = str(r.get("room_id", ""))
            name = str(r.get("name", "Room"))
            count = int(r.get("member_count", 0))
            is_current = rid == current_room_id
            label_text = f"▸ {name} ({count})" if is_current else f"{name} ({count})"
            row = MDCard(
                padding=dp(6),
                size_hint_x=None,
                width=dp(96),
                size_hint_y=None,
                height=dp(32),
                md_bg_color=ACCENT if is_current else SURFACE,
                ripple_behavior=True,
            )
            row.add_widget(
                MDLabel(
                    text=label_text,
                    theme_text_color="Custom",
                    text_color=BG if is_current else TEXT,
                    font_style="Caption",
                )
            )

            def on_tap(_w, room_id=rid) -> None:
                if row._long_pressed:  # type: ignore[attr-defined]
                    row._long_pressed = False  # type: ignore[attr-defined]
                    return
                if room_id != current_room_id:
                    app.controller.join_room(room_id)

            def bind_long_press(card, room_id=rid, room_name=name) -> None:
                card._long_pressed = False  # type: ignore[attr-defined]
                state: dict[str, object | None] = {"ev": None}

                def fire_long(_dt) -> None:
                    state["ev"] = None
                    card._long_pressed = True  # type: ignore[attr-defined]
                    app.controller.delete_room(room_id, room_name)

                def touch_down(_card, touch) -> bool:
                    if card.collide_point(*touch.pos):
                        state["ev"] = Clock.schedule_once(fire_long, 0.6)
                    return False

                def touch_up(_card, touch) -> bool:
                    ev = state.get("ev")
                    if ev is not None:
                        Clock.unschedule(ev)  # type: ignore[arg-type]
                        state["ev"] = None
                    return False

                card.bind(on_touch_down=touch_down, on_touch_up=touch_up)

            row.bind(on_release=on_tap)
            if can_delete:
                bind_long_press(row, rid, name)
            self._rooms_box.add_widget(row)

    def connected_link_ids(self) -> list[str]:
        return list(self._link_items.keys())

    def add_connected_link(self, link_id: str, link) -> None:
        if link_id in self._link_items:
            self.refresh_link_row(link_id, link)
            return
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
        from mobile.theme import ACCENT, SURFACE, TEXT

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
        disc = MDIconButton(
            icon="close",
            theme_text_color="Custom",
            text_color=(0.97, 0.46, 0.56, 1),
            on_release=lambda *_: self._disconnect(link_id),
        )
        row.add_widget(card)
        row.add_widget(listen)
        row.add_widget(mic)
        row.add_widget(disc)
        self._link_items[link_id] = {"row": row, "card": card, "listen": listen, "mic": mic}
        self._connected_box.add_widget(row)

    def refresh_link_row(self, link_id: str, link) -> None:
        item = self._link_items.get(link_id)
        if not item or not link:
            return
        item["listen"].icon = "volume-off" if link.listen_muted else "volume-high"
        item["mic"].icon = "microphone-off" if link.mic_muted else "microphone"

    def set_active_link(self, link_id: str) -> None:
        from mobile.theme import ACCENT, SURFACE

        for lid, item in self._link_items.items():
            item["card"].md_bg_color = ACCENT if lid == link_id else SURFACE

    def remove_connected_link(self, link_id: str) -> None:
        item = self._link_items.pop(link_id, None)
        if item:
            self._connected_box.remove_widget(item["row"])

    def _set_active(self, link_id: str) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        app.controller.set_active_link(link_id)

    def _listen(self, link_id: str) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        app.controller.toggle_listen(link_id)

    def _mic(self, link_id: str) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        app.controller.toggle_mic(link_id)

    def _disconnect(self, link_id: str) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
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
        assert hasattr(app, "controller")
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
                on_double_tap=lambda ll=active_link_id, part=dict(p): app.controller.open_user_panel(ll, part),
                speaking=bool(p.get("speaking", False)),
            )
            self._people_box.add_widget(row)


class SettingsScreen(MDScreen):
    gate_db = NumericProperty(-40)
    noise_pct = NumericProperty(50)

    def on_enter(self, *_args) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        s = app.controller.settings
        self.gate_db = int(s.gate_threshold_db)
        self.noise_pct = int(s.noise_suppression * 100)

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
        gate_slider = MDSlider(min=-80, max=0, value=-40, step=1)
        gate_slider.bind(value=lambda _s, v: self._gate_changed(v))
        root.add_widget(self._gate_label)
        root.add_widget(gate_slider)
        self._noise_label = MDLabel(
            text="Noise suppression: 50%",
            theme_text_color="Custom",
            text_color=TEXT,
        )
        noise_slider = MDSlider(min=0, max=100, value=50, step=1)
        noise_slider.bind(value=lambda _s, v: self._noise_changed(v))
        root.add_widget(self._noise_label)
        root.add_widget(noise_slider)
        hint = MDLabel(
            text="Gate and suppression match desktop. Suppression uses a built-in expander on Android.",
            theme_text_color="Custom",
            text_color=MUTED,
            font_style="Caption",
        )
        root.add_widget(hint)
        self.add_widget(root)

    def _gate_changed(self, value: float) -> None:
        self._gate_label.text = f"Noise gate: {int(value)} dB"
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        app.controller.set_gate_db(float(value))

    def _noise_changed(self, value: float) -> None:
        self._noise_label.text = f"Noise suppression: {int(value)}%"
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        app.controller.set_noise_suppression(value / 100.0)

