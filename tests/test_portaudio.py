"""PortAudio device fallback ordering tests."""

from __future__ import annotations

from babblecast.audio.devices import AudioDevice
from babblecast.audio.portaudio import _host_rank, _ordered_indices


def _dev(index: int, name: str, host: str, *, default_in=False, default_out=False) -> AudioDevice:
    return AudioDevice(
        index=index,
        name=name,
        host_api=host,
        max_input_channels=2,
        max_output_channels=2,
        default_sample_rate=48000.0,
        is_default_input=default_in,
        is_default_output=default_out,
    )


def test_host_rank_prefers_pipewire_over_alsa() -> None:
    assert _host_rank("PipeWire") < _host_rank("ALSA")
    assert _host_rank("PulseAudio") < _host_rank("ALSA")


def test_output_order_prefers_pipewire_default() -> None:
    devices = [
        _dev(0, "alsa-out", "ALSA", default_out=True),
        _dev(1, "pw-out", "PipeWire", default_out=True),
    ]
    order = list(_ordered_indices(devices, None, default_attr="is_default_output"))
    assert order[0] == 1


def test_preferred_device_tried_first() -> None:
    devices = [
        _dev(0, "alsa-out", "ALSA"),
        _dev(1, "pw-out", "PipeWire", default_out=True),
    ]
    order = list(_ordered_indices(devices, "0:alsa-out", default_attr="is_default_output"))
    assert order[0] == 0
