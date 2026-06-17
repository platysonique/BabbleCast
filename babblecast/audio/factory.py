"""Pick desktop (sounddevice) or mobile (Android AudioRecord) audio backends."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from babblecast.audio.processing import NoiseGate, NoiseSuppressor


def platform_name() -> str:
    try:
        from kivy.utils import platform as kivy_platform

        return kivy_platform
    except ImportError:
        return sys.platform


def create_mic(
    device_key: str | None,
    gate: "NoiseGate",
    suppressor: "NoiseSuppressor",
    on_frame,
    on_level=None,
):
    if platform_name() == "android":
        from babblecast.audio.android_engine import AndroidMicCapture

        return AndroidMicCapture(device_key, gate, suppressor, on_frame, on_level)
    from babblecast.audio.engine import MicCapture

    return MicCapture(device_key, gate, suppressor, on_frame, on_level)


def create_speaker(device_key: str | None, master_volume: float = 1.0):
    if platform_name() == "android":
        from babblecast.audio.android_engine import AndroidSpeakerOutput

        return AndroidSpeakerOutput(device_key, master_volume)
    from babblecast.audio.engine import SpeakerOutput

    return SpeakerOutput(device_key, master_volume)
