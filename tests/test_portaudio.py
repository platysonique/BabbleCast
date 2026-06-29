"""PortAudio device fallback ordering tests."""

from __future__ import annotations

from babblecast.audio.session_devices import NAME_KEY_PREFIX, SYSTEM_DEFAULT_KEY
from babblecast.audio.portaudio import iter_output_device_indices


def test_iter_output_prefers_session_resolution(monkeypatch) -> None:
    monkeypatch.setattr(
        "babblecast.audio.portaudio.resolve_output_device",
        lambda key: 7 if key == SYSTEM_DEFAULT_KEY else 3,
    )
    monkeypatch.setattr(
        "babblecast.audio.portaudio.list_raw_output_candidates",
        lambda: [(3, "hdmi"), (7, "analog hw:0,0")],
    )
    order = list(iter_output_device_indices(SYSTEM_DEFAULT_KEY))
    assert order[0] == 7


def test_iter_output_name_key_before_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "babblecast.audio.portaudio.resolve_output_device",
        lambda key: 3 if key == SYSTEM_DEFAULT_KEY else 5,
    )
    monkeypatch.setattr(
        "babblecast.audio.portaudio.list_raw_output_candidates",
        lambda: [(3, "hdmi"), (5, "analog hw:0,0"), (7, "other")],
    )
    key = f"{NAME_KEY_PREFIX}analog hw:0,0"
    order = list(iter_output_device_indices(key))
    assert order[0] == 5
