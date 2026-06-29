"""Microphone routing and resampling tests."""

from __future__ import annotations

from babblecast.audio.input_routing import (
    iter_mic_open_candidates,
    native_input_sample_rate,
)
from babblecast.audio.resample import native_frame_samples, resample_mono_to_48k
from babblecast.audio.session_devices import SYSTEM_DEFAULT_KEY, session_matches_device_name
from babblecast.constants import FRAME_SAMPLES, SAMPLE_RATE
import numpy as np


def test_native_frame_samples_44100() -> None:
    assert native_frame_samples(44100) == 882
    assert native_frame_samples(SAMPLE_RATE) == FRAME_SAMPLES


def test_resample_mono_to_48k_from_44100() -> None:
    src = np.random.randint(-1000, 1000, 882, dtype=np.int16)
    out = resample_mono_to_48k(src, 44100)
    assert out.shape == (FRAME_SAMPLES,)
    assert out.dtype == np.int16


def test_usb_mic_candidate_includes_resample_or_session() -> None:
    usb_key = "name:JOUNIVO MICROPHONE: USB Audio (hw:1,0)"
    kinds = [c.route_kind for c in iter_mic_open_candidates(usb_key)]
    assert kinds
    assert any(k.startswith("session:") or k == "hardware-resampled" or k == "hardware" for k in kinds)


def test_system_default_candidates_include_session_route() -> None:
    kinds = [c.route_kind for c in iter_mic_open_candidates(SYSTEM_DEFAULT_KEY)]
    assert any(k.startswith("session:") for k in kinds)


def test_session_matches_usb_name() -> None:
    from babblecast.audio.session_devices import SessionEndpoint

    session = SessionEndpoint(
        "alsa_input.usb-0c76_JOUNIVO_MICROPHONE-00.mono-fallback",
        "JOUNIVO MICROPHONE Mono",
    )
    assert session_matches_device_name(
        "JOUNIVO MICROPHONE: USB Audio (hw:1,0)",
        session,
    )


def test_native_input_sample_rate_usb() -> None:
    from babblecast.audio.devices import list_raw_input_candidates

    usb = [
        idx
        for idx, name in list_raw_input_candidates()
        if "JOUNIVO" in name or "USB" in name.upper()
    ]
    if not usb:
        return
    assert native_input_sample_rate(usb[0]) in (44100, 48000)
