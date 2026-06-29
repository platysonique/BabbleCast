"""Peer controls on Android — modal instead of a side drawer."""

from __future__ import annotations

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.slider import MDSlider

from babblecast.constants import composite_participant_key
from mobile.theme import ACCENT, MUTED, TEXT
from mobile.vertical_meter import METER_HEIGHT, VerticalMeter


def open_peer_dialog(
    controller,
    link_id: str,
    participant: dict,
    *,
    tap_active: bool = False,
    tapped: bool = False,
) -> None:
    cid = str(participant.get("client_id", ""))
    composite = composite_participant_key(link_id, cid)
    link = controller._bridge.get_link(link_id)
    my_id = link.client_id if link else ""
    is_self = cid == my_id
    name = str(participant.get("name", "?"))
    title = f"{name} (you)" if is_self else name

    local_muted = controller.settings.per_user_muted.get(composite, False)
    local_vol = controller.settings.per_user_volumes.get(
        composite, float(participant.get("volume", 1.0))
    )

    body = MDBoxLayout(
        orientation="vertical",
        spacing=dp(10),
        size_hint_y=None,
        adaptive_height=True,
        padding=(0, dp(4), 0, 0),
    )
    body.add_widget(
        MDLabel(
            text="Double-tap a name in the room list to open this panel.",
            theme_text_color="Custom",
            text_color=MUTED,
            font_style="Caption",
            size_hint_y=None,
        )
    )

    meter_row = MDBoxLayout(size_hint_y=None, height=METER_HEIGHT + dp(8), spacing=dp(8))
    meter = VerticalMeter()
    meter.set_level(float(participant.get("voice_level", 0)))
    meter_row.add_widget(meter)

    vol_col = MDBoxLayout(orientation="vertical", spacing=dp(4), size_hint_x=0.65)
    hear_btn = MDRaisedButton(
        text="Hear them (off)" if local_muted else "Hear them",
        md_bg_color=(0.97, 0.46, 0.56, 1) if local_muted else (0.62, 0.81, 0.42, 1),
        size_hint_y=None,
        height=dp(40),
    )
    vol_slider = MDSlider(min=0, max=200, value=int(local_vol * 100), step=1)
    vol_caption = MDLabel(
        text=f"Their volume: {int(local_vol * 100)}%",
        theme_text_color="Custom",
        text_color=MUTED,
        font_style="Caption",
        size_hint_y=None,
        height=dp(16),
    )
    vol_col.add_widget(hear_btn)
    vol_col.add_widget(vol_caption)
    vol_col.add_widget(vol_slider)
    meter_row.add_widget(vol_col)
    body.add_widget(meter_row)

    tap_row = MDBoxLayout(spacing=dp(8), size_hint_y=None, height=dp(44))
    tap_btn = MDRaisedButton(text="Tap", size_hint_x=0.5, md_bg_color=ACCENT)
    tap_chat_btn = MDFlatButton(text="Tap chat", size_hint_x=0.5)
    tap_btn.disabled = is_self
    tap_chat_btn.disabled = is_self
    tap_row.add_widget(tap_btn)
    tap_row.add_widget(tap_chat_btn)
    body.add_widget(tap_row)

    holder: list[MDDialog] = []

    def dismiss() -> None:
        if holder:
            holder[0].dismiss()

    def toggle_hear(*_args) -> None:
        muted = hear_btn.text.startswith("Hear them (")
        new_muted = not muted
        controller.set_peer_muted(composite, new_muted)
        hear_btn.text = "Hear them (off)" if new_muted else "Hear them"
        hear_btn.md_bg_color = (0.97, 0.46, 0.56, 1) if new_muted else (0.62, 0.81, 0.42, 1)

    def on_vol(_slider, value: float) -> None:
        vol_caption.text = f"Their volume: {int(value)}%"
        controller.set_peer_volume(composite, value / 100.0)

    def on_tap(*_args) -> None:
        controller.send_peer_tap(link_id, cid)
        dismiss()

    def on_tap_chat(*_args) -> None:
        dismiss()
        controller.open_tap_chat_for_peer(link_id, cid)

    hear_btn.bind(on_release=toggle_hear)
    vol_slider.bind(value=on_vol)
    tap_btn.bind(on_release=on_tap)
    tap_chat_btn.bind(on_release=on_tap_chat)

    dialog = MDDialog(
        title=title,
        type="custom",
        content_cls=body,
        buttons=[MDFlatButton(text="Close", on_release=lambda *_: dismiss())],
    )
    holder.append(dialog)
    dialog.open()
