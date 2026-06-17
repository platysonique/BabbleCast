"""BabbleCast mobile — KivyMD screens."""

from __future__ import annotations

from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.screen import MDScreen

from babblecast.client.bridge import BridgeManager
from babblecast.config import get_settings
from mobile.theme import ACCENT, BG, MUTED, SURFACE, TEXT

class ConnectScreen(MDScreen):
    display_name = StringProperty("")

    def on_enter(self, *_args) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
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
        assert hasattr(app, "controller")
        app.controller.host_server()

    def _connect(self) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
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
        assert hasattr(app, "controller")
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
    current_room_text = StringProperty("In room: —")
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
        self._current_room = MDLabel(
            text=self.current_room_text,
            theme_text_color="Custom",
            text_color=ACCENT,
            font_style="Subtitle2",
            size_hint_y=None,
            height=dp(28),
        )
        self.bind(current_room_text=lambda _s, v: setattr(self._current_room, "text", v))
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
            self._current_room,
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
        assert hasattr(app, "controller")
        app.controller.toggle_mute()
        self._mute_btn.text = "Unmute all" if self.is_muted else "Mute all"

    def _toggle_ptt(self) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        app.controller.toggle_ptt()

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
                    text="Default room",
                    theme_text_color="Custom",
                    text_color=MUTED,
                    size_hint_y=None,
                    height=dp(32),
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
                padding=dp(8),
                size_hint_y=None,
                height=dp(40),
                md_bg_color=ACCENT if is_current else SURFACE,
                ripple_behavior=True,
            )
            row.add_widget(
                MDLabel(
                    text=label_text,
                    theme_text_color="Custom",
                    text_color=BG if is_current else TEXT,
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
                on_more_details=lambda ll=active_link_id, part=dict(p): app.controller.show_person_details(ll, part),
            )
            self._people_box.add_widget(row)


class SettingsScreen(MDScreen):
    gate_db = NumericProperty(-40)

    def on_enter(self, *_args) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
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
        assert hasattr(app, "controller")
        app.controller.set_gate_db(float(value))

