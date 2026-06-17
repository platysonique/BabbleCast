"""Right-side panel — collapsible strip + Your audio drawer + peer details."""

from __future__ import annotations

from kivy.animation import Animation
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDIconButton, MDRaisedButton
from kivymd.uix.label import MDLabel
from kivymd.uix.slider import MDSlider

from mobile.collapsible import CollapsibleSection
from mobile.theme import ACCENT, MUTED, TEXT
from mobile.vertical_meter import METER_HEIGHT, VerticalMeter


class SideDetailPanel(MDBoxLayout):
    """Chevron strip + sliding body; self-audio pinned to top."""

    _STRIP_W = dp(22)
    _BODY_W = dp(256)

    def __init__(self, controller, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.md_bg_color = (36 / 255, 40 / 255, 59 / 255, 1)
        self.size_hint_x = None
        self.spacing = 0
        self._controller = controller
        self._peer_key: str | None = None
        self._peer_link_id = ""
        self._peer_client_id = ""
        self._peer_open = False

        s = controller.settings
        self._panel_expanded = bool(s.ui_panel_expanded)
        self._self_expanded = bool(s.ui_self_audio_expanded)

        self._toggle = MDIconButton(
            icon="chevron-left" if self._panel_expanded else "chevron-right",
            size_hint=(None, None),
            size=(self._STRIP_W, dp(32)),
            on_release=lambda *_: self.toggle_panel(),
        )
        self.add_widget(self._toggle)

        self._body = MDBoxLayout(
            orientation="vertical",
            size_hint_x=None,
            width=self._BODY_W if self._panel_expanded else 0,
            padding=(dp(4), dp(6), dp(6), dp(6)),
            spacing=dp(4),
        )
        self._body.opacity = 1 if self._panel_expanded else 0
        self._body.disabled = not self._panel_expanded

        self._self_section = CollapsibleSection(
            "Your audio",
            expanded=self._self_expanded,
            on_toggle=self._on_self_toggled,
        )
        self_layout = self._self_section.body

        meter_row = MDBoxLayout(size_hint_y=None, height=METER_HEIGHT + dp(20), spacing=dp(8))
        self._self_meter = VerticalMeter()
        mic_col = MDBoxLayout(orientation="vertical", spacing=dp(2), size_hint_x=0.65)
        self._mic_caption = MDLabel(
            text="Mic · 100%",
            theme_text_color="Custom",
            text_color=MUTED,
            font_style="Caption",
            size_hint_y=None,
            height=dp(16),
        )
        self._mic_vol_slider = MDSlider(min=0, max=200, value=100, step=1)
        self._mic_vol_slider.bind(value=lambda _s, v: self._mic_vol_changed(v))
        mic_col.add_widget(self._mic_caption)
        mic_col.add_widget(self._mic_vol_slider)
        meter_row.add_widget(self._self_meter)
        meter_row.add_widget(mic_col)
        self_layout.add_widget(meter_row)

        self._gate_label = MDLabel(
            text="Noise gate: -40 dB",
            theme_text_color="Custom",
            text_color=MUTED,
            font_style="Caption",
            size_hint_y=None,
            height=dp(16),
        )
        self._gate_slider = MDSlider(min=-80, max=0, value=-40, step=1)
        self._gate_slider.bind(value=lambda _s, v: self._gate_changed(v))
        self_layout.add_widget(self._gate_label)
        self_layout.add_widget(self._gate_slider)

        self._noise_label = MDLabel(
            text="Noise suppression: 50%",
            theme_text_color="Custom",
            text_color=MUTED,
            font_style="Caption",
            size_hint_y=None,
            height=dp(16),
        )
        self._noise_slider = MDSlider(min=0, max=100, value=50, step=1)
        self._noise_slider.bind(value=lambda _s, v: self._noise_changed(v))
        self_layout.add_widget(self._noise_label)
        self_layout.add_widget(self._noise_slider)

        self._master_label = MDLabel(
            text="Master output: 100%",
            theme_text_color="Custom",
            text_color=MUTED,
            font_style="Caption",
            size_hint_y=None,
            height=dp(16),
        )
        self._master_slider = MDSlider(min=0, max=200, value=100, step=1)
        self._master_slider.bind(value=lambda _s, v: self._master_changed(v))
        self_layout.add_widget(self._master_label)
        self_layout.add_widget(self._master_slider)

        self._body.add_widget(self._self_section)

        self._peer_box = MDBoxLayout(orientation="vertical", spacing=dp(4), size_hint_y=1)
        self._peer_box.opacity = 0
        self._peer_box.disabled = True
        self._peer_box.size_hint_y = None
        self._peer_box.height = 0

        header = MDBoxLayout(size_hint_y=None, height=dp(32), spacing=dp(4))
        self._close_btn = MDIconButton(icon="close", on_release=lambda *_: self.close_peer())
        self._title = MDLabel(text="", theme_text_color="Custom", text_color=TEXT, font_style="Subtitle1")
        header.add_widget(self._close_btn)
        header.add_widget(self._title)
        self._peer_box.add_widget(header)

        self._controls_section = CollapsibleSection("Controls", expanded=True)
        controls = self._controls_section.body
        peer_meter_row = MDBoxLayout(size_hint_y=None, height=METER_HEIGHT + dp(8), spacing=dp(8))
        self._peer_meter = VerticalMeter()
        vol_col = MDBoxLayout(orientation="vertical", spacing=dp(2), size_hint_x=0.55)
        self._listen_btn = MDIconButton(icon="volume-high", on_release=lambda *_: self._toggle_listen())
        self._vol_slider = MDSlider(min=0, max=200, value=100, step=1)
        self._vol_slider.bind(value=lambda _s, v: self._vol_changed(v))
        vol_col.add_widget(self._listen_btn)
        vol_col.add_widget(self._vol_slider)
        peer_meter_row.add_widget(self._peer_meter)
        peer_meter_row.add_widget(vol_col)
        controls.add_widget(peer_meter_row)

        tap_row = MDBoxLayout(spacing=dp(8), size_hint_y=None, height=dp(40))
        self._tap_btn = MDRaisedButton(text="Tap", size_hint_x=0.5, on_release=lambda *_: self._tap())
        self._tap_chat_btn = MDFlatButton(text="Tap chat", size_hint_x=0.5, on_release=lambda *_: self._tap_chat())
        tap_row.add_widget(self._tap_btn)
        tap_row.add_widget(self._tap_chat_btn)
        controls.add_widget(tap_row)
        self._peer_box.add_widget(self._controls_section)

        self._tech_section = CollapsibleSection("Technical details", expanded=False)
        self._tech_label = MDLabel(
            text="",
            theme_text_color="Custom",
            text_color=MUTED,
            font_style="Caption",
            size_hint_y=None,
        )
        self._tech_label.bind(texture_size=lambda _l, sz: setattr(self._tech_label, "height", max(dp(40), sz[1])))
        self._tech_section.body.add_widget(self._tech_label)
        self._peer_box.add_widget(self._tech_section)

        self._taps_section = CollapsibleSection("Taps", expanded=True)
        self._taps_box = MDBoxLayout(orientation="vertical", spacing=dp(2), size_hint_y=None)
        self._taps_box.bind(minimum_height=self._taps_box.setter("height"))
        self._taps_section.body.add_widget(self._taps_box)
        self._peer_box.add_widget(self._taps_section)

        peer_scroll = ScrollView(size_hint_y=None, height=0, do_scroll_x=False)
        peer_scroll.add_widget(self._peer_box)
        self._peer_scroll = peer_scroll
        self._body.add_widget(peer_scroll)

        self.add_widget(self._body)
        self._apply_width(animated=False)
        self._load_settings(s)

    def _load_settings(self, s) -> None:
        self._gate_slider.value = int(s.gate_threshold_db)
        self._noise_slider.value = int(s.noise_suppression * 100)
        self._master_slider.value = int(s.output_volume * 100)
        self._mic_vol_slider.value = int(s.input_volume * 100)
        self._gate_label.text = f"Noise gate: {int(s.gate_threshold_db)} dB"
        self._noise_label.text = f"Noise suppression: {int(s.noise_suppression * 100)}%"
        self._master_label.text = f"Master output: {int(s.output_volume * 100)}%"
        self._mic_caption.text = f"Mic · {int(s.input_volume * 100)}%"

    def sync_from_settings(self) -> None:
        if not self._controller:
            return
        s = self._controller.settings
        self._load_settings(s)
        self._panel_expanded = bool(s.ui_panel_expanded)
        self._self_section.set_expanded(bool(s.ui_self_audio_expanded))
        self._toggle.icon = "chevron-left" if self._panel_expanded else "chevron-right"
        self._apply_width(animated=False)

    def toggle_panel(self) -> None:
        self.set_panel_expanded(not self._panel_expanded)

    def set_panel_expanded(self, expanded: bool, *, animated: bool = True) -> None:
        if self._panel_expanded == expanded:
            return
        self._panel_expanded = expanded
        self._toggle.icon = "chevron-left" if expanded else "chevron-right"
        self._body.opacity = 1 if expanded else 0
        self._body.disabled = not expanded
        self._apply_width(animated=animated)
        if self._controller:
            self._controller.set_audio_panel_expanded(expanded)

    def _apply_width(self, *, animated: bool) -> None:
        target_body = self._BODY_W if self._panel_expanded else 0
        target_total = self._STRIP_W + target_body
        if animated:
            Animation(width=target_body, duration=0.22, t="out_cubic").start(self._body)
            Animation(width=target_total, duration=0.22, t="out_cubic").start(self)
        else:
            self._body.width = target_body
            self.width = target_total

    def _on_self_toggled(self, expanded: bool) -> None:
        if self._controller:
            self._controller.set_self_audio_expanded(expanded)

    def set_self_mic_level(self, level: float) -> None:
        self._self_meter.set_level(level)

    def is_open_for(self, composite: str) -> bool:
        return self._peer_key == composite and self._peer_open

    def toggle_peer(self, composite: str, participant: dict, *, link_id: str, server: str, is_self: bool) -> None:
        if self.is_open_for(composite):
            self.close_peer()
            return
        if not self._panel_expanded:
            self.set_panel_expanded(True)
        self._peer_key = composite
        self._peer_link_id = link_id
        self._peer_client_id = str(participant.get("client_id", ""))
        name = str(participant.get("name", "?"))
        self._title.text = f"{name}{' (you)' if is_self else ''}"
        self._controls_section.set_title(f"{name} controls")
        local_muted = self._controller.settings.per_user_muted.get(composite, False)
        local_vol = self._controller.settings.per_user_volumes.get(
            composite, float(participant.get("volume", 1.0))
        )
        self._listen_btn.icon = "volume-off" if local_muted else "volume-high"
        self._vol_slider.value = int(local_vol * 100)
        self._peer_meter.set_level(float(participant.get("voice_level", 0)))
        self._tap_btn.disabled = is_self
        self._tap_btn.opacity = 0.35 if is_self else 1
        self._tap_chat_btn.disabled = is_self
        self._tech_label.text = (
            f"client_id: {self._peer_client_id}\nlink: {link_id}\nserver: {server}\n"
            f"composite: {composite}\nvoice: {float(participant.get('voice_level', 0)):.3f}\n"
            f"speaking: {participant.get('speaking')}\nptt: {participant.get('ptt_active')}"
        )
        self._refresh_taps()
        self._peer_box.opacity = 1
        self._peer_box.disabled = False
        self._peer_scroll.size_hint_y = 1
        self._peer_scroll.height = max(dp(120), self._body.height - self._self_section.height - dp(8))
        self._peer_open = True

    def update_peer(self, participant: dict) -> None:
        if not self._peer_key or not self._peer_open:
            return
        composite = self._peer_key
        local_muted = self._controller.settings.per_user_muted.get(composite, False)
        local_vol = self._controller.settings.per_user_volumes.get(
            composite, float(participant.get("volume", 1.0))
        )
        self._peer_meter.set_level(float(participant.get("voice_level", 0)))
        self._vol_slider.value = int(local_vol * 100)
        self._listen_btn.icon = "volume-off" if local_muted else "volume-high"

    def close_peer(self) -> None:
        self._peer_key = None
        self._peer_open = False
        self._peer_box.opacity = 0
        self._peer_box.disabled = True
        self._peer_scroll.size_hint_y = None
        self._peer_scroll.height = 0

    def _gate_changed(self, value: float) -> None:
        self._gate_label.text = f"Noise gate: {int(value)} dB"
        self._controller.set_gate_db(float(value))

    def _noise_changed(self, value: float) -> None:
        self._noise_label.text = f"Noise suppression: {int(value)}%"
        self._controller.set_noise_suppression(value / 100.0)

    def _master_changed(self, value: float) -> None:
        self._master_label.text = f"Master output: {int(value)}%"
        self._controller.set_master_volume(value / 100.0)

    def _mic_vol_changed(self, value: float) -> None:
        self._mic_caption.text = f"Mic · {int(value)}%"
        self._controller.set_input_volume(value / 100.0)

    def _toggle_listen(self) -> None:
        if not self._peer_key:
            return
        muted = self._listen_btn.icon == "volume-high"
        self._listen_btn.icon = "volume-off" if muted else "volume-high"
        self._controller.set_peer_muted(self._peer_key, muted)

    def _vol_changed(self, value: float) -> None:
        if self._peer_key:
            self._controller.set_peer_volume(self._peer_key, value / 100.0)

    def _tap(self) -> None:
        if self._peer_link_id and self._peer_client_id:
            self._controller.send_peer_tap(self._peer_link_id, self._peer_client_id)

    def _tap_chat(self) -> None:
        if self._peer_link_id and self._peer_client_id:
            self._controller.open_tap_for_peer(self._peer_link_id, self._peer_client_id)

    def _refresh_taps(self) -> None:
        from babblecast.taps import get_tap_store

        self._taps_box.clear_widgets()
        saved = get_tap_store().all_for_peer(self._peer_client_id)
        if not saved:
            self._taps_box.add_widget(
                MDLabel(text="(none)", theme_text_color="Custom", text_color=MUTED, font_style="Caption")
            )
            return
        for tap in saved:
            mark = "✓" if tap.done else "○"
            btn = MDFlatButton(
                text=f"{mark} {tap.reminder[:32]}",
                on_release=lambda *_t, sid=tap.save_id: self._controller.reinsert_saved_tap(
                    self._peer_link_id, sid
                ),
            )
            self._taps_box.add_widget(btn)
