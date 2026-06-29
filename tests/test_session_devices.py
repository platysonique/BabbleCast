"""Session-aware PortAudio device resolution."""

from __future__ import annotations

from babblecast.audio.devices import list_output_devices, resolve_output_device
from babblecast.audio.session_devices import (
    SYSTEM_DEFAULT_KEY,
    migrate_settings_devices,
    normalize_device_key,
    resolve_session_device_index,
)
from babblecast.audio.devices import list_raw_output_candidates


def test_normalize_legacy_default_key() -> None:
    assert normalize_device_key("20:default") == SYSTEM_DEFAULT_KEY
    assert normalize_device_key("15:pulse") == SYSTEM_DEFAULT_KEY


def test_normalize_legacy_hw_key() -> None:
    key = normalize_device_key("0:HDA Intel PCH: ALC298 Analog (hw:0,0)")
    assert key == "name:HDA Intel PCH: ALC298 Analog (hw:0,0)"


def test_migrate_settings_devices() -> None:
    inp, out = migrate_settings_devices(
        "4:JOUNIVO MICROPHONE: USB Audio (hw:1,0)",
        "20:default",
    )
    assert inp.startswith("name:")
    assert out == SYSTEM_DEFAULT_KEY


def test_list_output_devices_curated() -> None:
    devices = list_output_devices()
    assert devices[0].is_system_default
    assert devices[0].storage_key == SYSTEM_DEFAULT_KEY
    names = {d.name for d in devices}
    assert "lavrate" not in names
    assert "pipewire" not in names
    assert any("hw:" in n for n in names)


def test_resolve_output_system_default_to_analog() -> None:
    idx = resolve_output_device(SYSTEM_DEFAULT_KEY)
    assert idx is not None
    candidates = list_raw_output_candidates()
    names = dict(candidates)
    assert idx in names


def test_resolve_session_device_index_prefers_analog() -> None:
    candidates = list_raw_output_candidates()
    idx = resolve_session_device_index(candidates, output=True)
    assert idx is not None
    name = dict(candidates)[idx]
    assert "analog" in name.lower() or "hdmi" in name.lower()
