"""BabbleCast mobile — KivyMD screens."""

from __future__ import annotations

import time
from typing import Any

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.card import MDCard
from kivymd.uix.screen import MDScreen

from babblecast.client.bridge import BridgeManager
from babblecast.config import get_settings
from babblecast.constants import DEFAULT_WS_PORT
from mobile.branding import banner_widget
from mobile.platform_ui import is_android
from mobile.theme import ACCENT, BG, DANGER, MUTED, MUTE_ORANGE, SUCCESS, SURFACE, TEXT

class ConnectScreen(MDScreen):
    display_name = StringProperty("")

    def on_enter(self, *_args) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        if not getattr(app, "controller", None):
            return
        from mobile.display_name import default_display_name

        self.display_name = default_display_name(app.controller.settings)
        app.controller.refresh_host_ui()
        app.controller.refresh_discovery_ui(force=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = MDBoxLayout(orientation="vertical", md_bg_color=BG, padding=dp(16), spacing=dp(12))
        from kivymd.uix.label import MDLabel
        from kivymd.uix.textfield import MDTextField
        from kivy.uix.scrollview import ScrollView

        header = banner_widget(height_dp=72)
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
            text=f"Or enter LAN IP (e.g. 192.168.1.141) or name.babblecast.local + port {DEFAULT_WS_PORT}",
            font_style="H6",
            theme_text_color="Custom",
            text_color=TEXT,
        )
        manual_row = MDBoxLayout(spacing=dp(8), size_hint_y=None, height=dp(48))
        settings = get_settings()
        self._host_field = MDTextField(
            hint_text="LAN IP (192.168.x.x)",
            text=settings.last_server_host or "",
            size_hint_x=0.65,
        )
        self._port_field = MDTextField(
            hint_text="Port",
            text=str(settings.last_server_port or DEFAULT_WS_PORT),
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
            port = int(self._port_field.text.strip() or str(DEFAULT_WS_PORT))
        except ValueError:
            port = DEFAULT_WS_PORT
        app.controller.connect_to(self._host_field.text, port)

    def set_hosting(self, active: bool) -> None:
        self._host_btn.text = "Stop hosting" if active else "Host on this phone"

    def set_discovery_status(self, text: str) -> None:
        self._discovery_status.text = text

    def update_servers(self, servers) -> None:
        signature = tuple((s.service_name, s.host, s.ws_port) for s in servers)
        if signature == getattr(self, "_server_signature", None):
            return
        self._server_signature = signature

        self._server_box.clear_widgets()
        if not servers:
            from kivymd.uix.label import MDLabel

            self._server_box.add_widget(
                MDLabel(
                    text="Nothing found — enter a LAN IP (192.168.x.x) or name.babblecast.local below",
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
            text="*",
            theme_text_color="Custom",
            text_color=MUTED,
            size_hint_x=None,
            width=dp(14),
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
        self._led.text_color = SUCCESS if speaking else MUTED
        self._led.text = ">" if speaking else "*"

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
        from kivymd.uix.label import MDLabel
        from kivymd.uix.textfield import MDTextField
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

        self._server_hint = MDLabel(
            text="Hear = listen to server · Talk = send mic · Leave = disconnect",
            theme_text_color="Custom",
            text_color=MUTED,
            font_style="Caption",
            size_hint_y=None,
            height=dp(28),
        )
        self._connected_box = MDBoxLayout(orientation="horizontal", spacing=dp(4), size_hint_y=None, height=dp(48))
        self._current_room = MDLabel(
            text=self.current_room_text,
            theme_text_color="Custom",
            text_color=ACCENT,
            font_style="Caption",
            size_hint_y=None,
            height=dp(20),
        )
        self.bind(current_room_text=lambda _s, v: setattr(self._current_room, "text", v))

        self._room_pwd_label = None
        self._self_meter = None
        if is_android():
            self._room_pwd_label = MDLabel(
                text="",
                theme_text_color="Custom",
                text_color=MUTED,
                font_style="Caption",
                size_hint_y=None,
                height=0,
                opacity=0,
            )

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
        self._people_hint = MDLabel(
            text="Double-tap a name for person controls (Tap, volume, etc.)",
            theme_text_color="Custom",
            text_color=MUTED,
            font_style="Caption",
            size_hint_y=None,
            height=dp(22),
        )
        people_scroll = ScrollView(size_hint_y=None, height=dp(72))
        people_scroll.add_widget(self._people_box)

        self._chat_log = MDLabel(text="", theme_text_color="Custom", text_color=TEXT, font_style="Body2", size_hint_y=None)
        self._chat_log.bind(texture_size=lambda _l, s: setattr(self._chat_log, "height", max(dp(24), s[1])))
        self.bind(chat_text=lambda _s, v: setattr(self._chat_log, "text", v))
        chat_scroll = ScrollView(size_hint_y=1)
        chat_scroll.add_widget(self._chat_log)

        chat_row = MDBoxLayout(spacing=dp(4), size_hint_y=None, height=dp(44))
        self._mute_btn = MDRaisedButton(
            text="Mic",
            size_hint_x=None,
            width=dp(72),
            md_bg_color=SUCCESS,
            on_release=lambda *_: None,
        )
        self._mute_btn.bind(on_touch_down=self._on_mute_touch_down, on_touch_up=self._on_mute_touch_up)
        self._mute_hold_clock = None
        self._ptt_from_hold = False
        self._mute_touch_active = False
        self.bind(is_muted=lambda _s, v: self._sync_mute_button())
        self.bind(ptt_active=lambda _s, v: self._sync_mute_button())
        self._chat_input = MDTextField(
            hint_text="Type a message, then hit ↵",
            on_text_validate=lambda *_: self._send_chat(),
            font_size=dp(13),
        )
        chat_row.add_widget(self._mute_btn)
        chat_row.add_widget(self._chat_input)

        for w in (
            self._status,
            self._server_hint,
            self._connected_box,
            self._current_room,
            *([self._room_pwd_label] if self._room_pwd_label is not None else []),
            room_create,
            self._rooms_box,
            self._people_hint,
            people_scroll,
            chat_scroll,
            chat_row,
        ):
            main.add_widget(w)

        app_stub = MDApp.get_running_app()
        controller = getattr(app_stub, "controller", None)
        self.detail_panel = None
        if controller and not is_android():
            self.detail_panel = SideDetailPanel(controller)
        outer.add_widget(main)
        if self.detail_panel:
            outer.add_widget(self.detail_panel)
        self.add_widget(outer)

    def on_enter(self, *_args) -> None:
        app = MDApp.get_running_app()
        if not hasattr(app, "controller"):
            return
        if not is_android() and self.detail_panel is None:
            from kivy.uix.boxlayout import BoxLayout
            from mobile.detail_panel import SideDetailPanel

            outer = self.children[0] if self.children else None
            if isinstance(outer, BoxLayout):
                self.detail_panel = SideDetailPanel(app.controller)
                outer.add_widget(self.detail_panel)
        elif self.detail_panel is not None and hasattr(self.detail_panel, "_controller"):
            self.detail_panel._controller = app.controller
        app.controller.on_live_enter()

    def set_room_password_display(self, visible: bool, text: str) -> None:
        label = getattr(self, "_room_pwd_label", None)
        if label is None:
            return
        label.text = text if visible else ""
        label.opacity = 1 if visible else 0
        label.height = dp(18) if visible else 0

    def _sync_mute_button(self, *_args) -> None:
        if not hasattr(self, "_mute_btn"):
            return
        if self.ptt_active and self.is_muted:
            self._mute_btn.text = "Talk"
            self._mute_btn.md_bg_color = SUCCESS
        elif self.is_muted:
            self._mute_btn.text = "Muted"
            self._mute_btn.md_bg_color = MUTE_ORANGE
        else:
            self._mute_btn.text = "Mic"
            self._mute_btn.md_bg_color = SUCCESS

    def _on_mute_touch_down(self, widget, touch):
        if not widget.collide_point(*touch.pos):
            return False
        self._mute_touch_active = True
        if self.is_muted:
            self._mute_hold_clock = Clock.schedule_once(lambda _dt: self._begin_hold_ptt(), 0.25)
        return True

    def _on_mute_touch_up(self, widget, touch):
        if not self._mute_touch_active:
            return False
        self._mute_touch_active = False
        if self._mute_hold_clock is not None:
            Clock.unschedule(self._mute_hold_clock)
            self._mute_hold_clock = None
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        if self._ptt_from_hold:
            app.controller.set_ptt(False)
            self._ptt_from_hold = False
        else:
            app.controller.toggle_mute()
        self._sync_mute_button()
        return True

    def _begin_hold_ptt(self) -> None:
        self._mute_hold_clock = None
        if not self.is_muted:
            return
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        self._ptt_from_hold = True
        app.controller.set_ptt(True)
        self._sync_mute_button()

    def _toggle_mute(self) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        app.controller.toggle_mute()
        self._sync_mute_button()

    def _send_chat(self) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        app.controller.send_chat(self._chat_input.text)
        self._chat_input.text = ""

    def _create_room(self) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        app.controller.create_room(self._new_room_field.text)
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
            lock = "[locked] " if r.get("password_protected") else ""
            label_text = f"> {lock}{name} ({count})" if is_current else f"{lock}{name} ({count})"
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

            def bind_long_press(card, room_id=rid, room_name=name, room_meta=r) -> None:
                card._long_pressed = False  # type: ignore[attr-defined]
                state: dict[str, object | None] = {"ev": None}

                def fire_long(_dt) -> None:
                    state["ev"] = None
                    card._long_pressed = True  # type: ignore[attr-defined]
                    if not app.controller._bridge.can_delete_room(
                        app.controller._active_link_id or "", room_meta
                    ):
                        app.controller.set_status("You cannot delete this room")
                        return
                    if can_delete:
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
                bind_long_press(row, rid, name, r)
            self._rooms_box.add_widget(row)

    def connected_link_ids(self) -> list[str]:
        return list(self._link_items.keys())

    def add_connected_link(self, link_id: str, link) -> None:
        if link_id in self._link_items:
            self.refresh_link_row(link_id, link)
            return
        from babblecast.client.link_stats import link_display_name

        def _hear_text(muted: bool) -> str:
            return "Hear (off)" if muted else "Hear"

        def _talk_text(muted: bool) -> str:
            return "Talk (off)" if muted else "Talk"

        row = MDBoxLayout(size_hint_y=None, height=dp(48), spacing=dp(4))
        card = MDCard(
            orientation="horizontal",
            padding=dp(8),
            size_hint_x=0.55,
            md_bg_color=SURFACE,
            ripple_behavior=True,
        )
        from kivymd.uix.label import MDLabel

        name_lbl = MDLabel(
            text=link_display_name(link),
            theme_text_color="Custom",
            text_color=TEXT,
            size_hint_x=1,
        )
        card.add_widget(name_lbl)
        card.bind(on_release=lambda *_: self._set_active(link_id))

        def show_info(*_args) -> None:
            app = MDApp.get_running_app()
            if hasattr(app, "controller"):
                app.controller.show_server_info(link_id)

        info = MDFlatButton(
            text="Info",
            theme_text_color="Custom",
            text_color=MUTED,
            size_hint_x=None,
            width=dp(44),
            on_release=show_info,
        )
        listen = MDRaisedButton(
            text=_hear_text(link.listen_muted),
            md_bg_color=DANGER if link.listen_muted else SUCCESS,
            size_hint_x=None,
            width=dp(58),
            font_size=dp(11),
            on_release=lambda *_: self._listen(link_id),
        )
        mic = MDRaisedButton(
            text=_talk_text(link.mic_muted),
            md_bg_color=DANGER if link.mic_muted else SUCCESS,
            size_hint_x=None,
            width=dp(58),
            font_size=dp(11),
            on_release=lambda *_: self._mic(link_id),
        )
        disc = MDFlatButton(
            text="Leave",
            theme_text_color="Custom",
            text_color=DANGER,
            size_hint_x=None,
            width=dp(52),
            on_release=lambda *_: self._disconnect(link_id),
        )
        row.add_widget(card)
        row.add_widget(info)
        row.add_widget(listen)
        row.add_widget(mic)
        row.add_widget(disc)
        self._link_items[link_id] = {"row": row, "card": card, "listen": listen, "mic": mic, "name": name_lbl}
        self._connected_box.add_widget(row)

    def refresh_link_row(self, link_id: str, link) -> None:
        from babblecast.client.link_stats import link_display_name

        item = self._link_items.get(link_id)
        if not item or not link:
            return
        name_lbl = item.get("name")
        if name_lbl is not None:
            name_lbl.text = link_display_name(link)
        item["listen"].text = "Hear (off)" if link.listen_muted else "Hear"
        item["listen"].md_bg_color = DANGER if link.listen_muted else SUCCESS
        item["mic"].text = "Talk (off)" if link.mic_muted else "Talk"
        item["mic"].md_bg_color = DANGER if link.mic_muted else SUCCESS

    def set_active_link(self, link_id: str) -> None:
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
    master_pct = NumericProperty(100)
    mic_pct = NumericProperty(100)

    def on_enter(self, *_args) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        s = app.controller.settings
        self.gate_db = int(s.gate_threshold_db)
        self.noise_pct = int(s.noise_suppression * 100)
        self.master_pct = int(s.output_volume * 100)
        self.mic_pct = int(s.input_volume * 100)
        if hasattr(self, "_gate_slider"):
            self._gate_slider.value = self.gate_db
            self._noise_slider.value = self.noise_pct
            self._master_slider.value = self.master_pct
            self._mic_slider.value = self.mic_pct
        if hasattr(self, "_route_buttons"):
            app = MDApp.get_running_app()
            if is_android() and hasattr(app, "controller") and not self._route_buttons:
                self._build_route_buttons(app.controller)
            elif hasattr(app, "controller"):
                self._refresh_route_ui(app.controller)
        app = MDApp.get_running_app()
        if is_android() and hasattr(app, "controller"):
            app.controller.ensure_self_audio_meter()

    def set_self_mic_level(self, level: float) -> None:
        meter = getattr(self, "_self_meter", None)
        if meter is not None:
            meter.set_level(level)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from kivy.uix.scrollview import ScrollView
        from kivymd.uix.label import MDLabel
        from kivymd.uix.slider import MDSlider
        from kivymd.uix.textfield import MDTextField

        outer = MDBoxLayout(orientation="vertical", md_bg_color=BG, padding=dp(16), spacing=dp(8))
        scroll = ScrollView(size_hint=(1, 1))
        root = MDBoxLayout(orientation="vertical", spacing=dp(14), size_hint_y=None, padding=(0, dp(4)))
        root.bind(minimum_height=root.setter("height"))

        root.add_widget(
            MDLabel(text="Settings", font_style="H4", theme_text_color="Custom", text_color=ACCENT, size_hint_y=None)
        )
        root.add_widget(
            MDLabel(
                text="Audio and host options live here on mobile — not on the Live side strip.",
                theme_text_color="Custom",
                text_color=MUTED,
                font_style="Caption",
                size_hint_y=None,
            )
        )

        root.add_widget(
            MDLabel(text="Audio output", font_style="H6", theme_text_color="Custom", text_color=TEXT, size_hint_y=None)
        )

        self._route_row = MDBoxLayout(orientation="vertical", spacing=dp(4), size_hint_y=None)
        self._route_label = None
        self._route_buttons: dict[str, MDFlatButton] = {}
        if is_android():
            self._route_label = MDLabel(
                text="Output route: Speaker",
                theme_text_color="Custom",
                text_color=MUTED,
                font_style="Caption",
                size_hint_y=None,
                height=dp(20),
            )
            btn_row = MDBoxLayout(spacing=dp(4), size_hint_y=None, height=dp(36))
            self._route_row.add_widget(self._route_label)
            self._route_row.add_widget(btn_row)
            self._route_btn_row = btn_row
            root.add_widget(self._route_row)
        else:
            root.add_widget(
                MDLabel(
                    text="Output route selection is available on Android only.",
                    theme_text_color="Custom",
                    text_color=MUTED,
                    font_style="Caption",
                    size_hint_y=None,
                )
            )

        self._master_label = MDLabel(
            text="Master volume: 100%",
            theme_text_color="Custom",
            text_color=TEXT,
            size_hint_y=None,
        )
        self._master_slider = MDSlider(min=0, max=200, value=100, step=1)
        self._master_slider.bind(value=lambda _s, v: self._master_changed(v))
        root.add_widget(self._master_label)
        root.add_widget(self._master_slider)

        root.add_widget(
            MDLabel(text="Microphone input", font_style="H6", theme_text_color="Custom", text_color=TEXT, size_hint_y=None)
        )
        from mobile.vertical_meter import METER_HEIGHT, VerticalMeter

        mic_meter_row = MDBoxLayout(size_hint_y=None, height=METER_HEIGHT + dp(8), spacing=dp(8))
        self._self_meter = VerticalMeter()
        mic_col = MDBoxLayout(orientation="vertical", spacing=dp(4), size_hint_x=0.72)
        self._mic_label = MDLabel(
            text="Mic volume: 100%",
            theme_text_color="Custom",
            text_color=TEXT,
            size_hint_y=None,
        )
        self._mic_slider = MDSlider(min=0, max=200, value=100, step=1)
        self._mic_slider.bind(value=lambda _s, v: self._mic_changed(v))
        mic_col.add_widget(self._mic_label)
        mic_col.add_widget(self._mic_slider)
        mic_meter_row.add_widget(self._self_meter)
        mic_meter_row.add_widget(mic_col)
        root.add_widget(mic_meter_row)

        root.add_widget(
            MDLabel(text="Processing", font_style="H6", theme_text_color="Custom", text_color=TEXT, size_hint_y=None)
        )
        self._gate_label = MDLabel(
            text="Noise gate: -40 dB",
            theme_text_color="Custom",
            text_color=TEXT,
            size_hint_y=None,
        )
        self._gate_slider = MDSlider(min=-80, max=0, value=-40, step=1)
        self._gate_slider.bind(value=lambda _s, v: self._gate_changed(v))
        root.add_widget(self._gate_label)
        root.add_widget(self._gate_slider)
        self._noise_label = MDLabel(
            text="Noise suppression: 50%",
            theme_text_color="Custom",
            text_color=TEXT,
            size_hint_y=None,
        )
        self._noise_slider = MDSlider(min=0, max=100, value=50, step=1)
        self._noise_slider.bind(value=lambda _s, v: self._noise_changed(v))
        root.add_widget(self._noise_label)
        root.add_widget(self._noise_slider)
        root.add_widget(
            MDLabel(
                text="Suppression uses a built-in expander on Android (noisereduce optional on desktop).",
                theme_text_color="Custom",
                text_color=MUTED,
                font_style="Caption",
                size_hint_y=None,
            )
        )

        root.add_widget(
            MDLabel(text="Host admin", font_style="H6", theme_text_color="Custom", text_color=TEXT, size_hint_y=None)
        )
        root.add_widget(
            MDLabel(
                text="Personal host password — required to delete rooms created by others.",
                theme_text_color="Custom",
                text_color=MUTED,
                font_style="Caption",
                size_hint_y=None,
            )
        )
        self._host_pwd_field = MDTextField(
            hint_text="Host password",
            password=True,
            size_hint_y=None,
            height=dp(48),
        )
        save_host = MDRaisedButton(text="Save host password", size_hint_y=None, height=dp(44), on_release=lambda *_: self._save_host_password())
        root.add_widget(self._host_pwd_field)
        root.add_widget(save_host)

        scroll.add_widget(root)
        outer.add_widget(scroll)
        self.add_widget(outer)

        if is_android():
            app = MDApp.get_running_app()
            if hasattr(app, "controller"):
                self._build_route_buttons(app.controller)

    def _build_route_buttons(self, controller) -> None:
        if not hasattr(self, "_route_btn_row"):
            return
        self._route_btn_row.clear_widgets()
        self._route_buttons.clear()
        for route_id, label, _enabled in controller.list_audio_routes():
            btn = MDFlatButton(
                text=label,
                size_hint_x=0.25,
                on_release=lambda _b, rid=route_id: self._route_pressed(rid),
            )
            self._route_buttons[route_id] = btn
            self._route_btn_row.add_widget(btn)
        self._refresh_route_ui(controller)

    def _refresh_route_ui(self, controller) -> None:
        if not self._route_buttons:
            return
        s = controller.settings
        selected = getattr(s, "android_audio_route", "speaker")
        labels = {rid: label for rid, label, _ in controller.list_audio_routes()}
        if self._route_label:
            self._route_label.text = f"Output route: {labels.get(selected, selected.title())}"
        available = {rid: ok for rid, _lbl, ok in controller.list_audio_routes()}
        for route_id, btn in self._route_buttons.items():
            enabled = available.get(route_id, route_id != "bluetooth")
            btn.disabled = not enabled
            btn.text_color = ACCENT if route_id == selected else MUTED

    def _route_pressed(self, route_id: str) -> None:
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        app.controller.set_audio_route(route_id)
        self._refresh_route_ui(app.controller)

    def _master_changed(self, value: float) -> None:
        self._master_label.text = f"Master volume: {int(value)}%"
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        app.controller.set_master_volume(value / 100.0)

    def _mic_changed(self, value: float) -> None:
        self._mic_label.text = f"Mic volume: {int(value)}%"
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        app.controller.set_input_volume(value / 100.0)

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

    def _save_host_password(self) -> None:
        pwd = self._host_pwd_field.text.strip()
        if not pwd:
            return
        app = MDApp.get_running_app()
        assert hasattr(app, "controller")
        app.controller.set_host_password(pwd)
        self._host_pwd_field.text = ""

