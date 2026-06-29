"""Audio device enumeration with human-readable labels."""

from __future__ import annotations

from dataclasses import dataclass

import sounddevice as sd

from babblecast.audio.session_devices import (
    NAME_KEY_PREFIX,
    SESSION_ROUTE_NAMES,
    SYSTEM_DEFAULT_KEY,
    friendly_name_for_portaudio_device,
    is_alsa_plugin_junk,
    is_physical_portaudio_name,
    normalize_device_key,
    query_linux_session_input,
    query_linux_session_output,
)
from babblecast.constants import CHANNELS, SAMPLE_RATE


def device_supports_output_rate(device_index: int, sample_rate: int) -> bool:
    try:
        sd.check_output_settings(
            device=device_index,
            channels=CHANNELS,
            samplerate=sample_rate,
            dtype="float32",
        )
        return True
    except Exception:
        return False


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    host_api: str
    max_input_channels: int
    max_output_channels: int
    default_sample_rate: float
    is_default_input: bool = False
    is_default_output: bool = False
    is_system_default: bool = False
    friendly_name: str = ""

    @property
    def label(self) -> str:
        if self.is_system_default:
            return self.friendly_name or "System default"
        role = []
        if self.is_default_input:
            role.append("default mic")
        if self.is_default_output:
            role.append("default speaker")
        suffix = f" — {', '.join(role)}" if role else ""
        display = self.friendly_name or self.name
        direction = []
        if self.max_input_channels > 0:
            direction.append("in")
        if self.max_output_channels > 0:
            direction.append("out")
        dir_tag = "/".join(direction)
        return f"{display} [{self.host_api}, {dir_tag}]{suffix}"

    @property
    def storage_key(self) -> str:
        if self.is_system_default:
            return SYSTEM_DEFAULT_KEY
        return f"{NAME_KEY_PREFIX}{self.name}"


def _host_api_name(idx: int) -> str:
    try:
        apis = sd.query_hostapis()
        return str(apis[idx]["name"])
    except Exception:
        return "Unknown"


def _raw_input_devices() -> list[AudioDevice]:
    default_in, _ = sd.default.device
    devices: list[AudioDevice] = []
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] < 1:
            continue
        name = str(dev["name"])
        devices.append(
            AudioDevice(
                index=i,
                name=name,
                host_api=_host_api_name(int(dev["hostapi"])),
                max_input_channels=int(dev["max_input_channels"]),
                max_output_channels=int(dev["max_output_channels"]),
                default_sample_rate=float(dev["default_samplerate"]),
                is_default_input=i == default_in,
                friendly_name=friendly_name_for_portaudio_device(name),
            )
        )
    return devices


def _raw_output_devices() -> list[AudioDevice]:
    _, default_out = sd.default.device
    devices: list[AudioDevice] = []
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_output_channels"] < 1:
            continue
        name = str(dev["name"])
        devices.append(
            AudioDevice(
                index=i,
                name=name,
                host_api=_host_api_name(int(dev["hostapi"])),
                max_input_channels=int(dev["max_input_channels"]),
                max_output_channels=int(dev["max_output_channels"]),
                default_sample_rate=float(dev["default_samplerate"]),
                is_default_output=i == default_out,
                friendly_name=friendly_name_for_portaudio_device(name),
            )
        )
    return devices


def _curate_inputs(devices: list[AudioDevice]) -> list[AudioDevice]:
    curated: list[AudioDevice] = []
    seen_names: set[str] = set()
    for dev in devices:
        if is_alsa_plugin_junk(dev.name):
            continue
        if not is_physical_portaudio_name(dev.name):
            continue
        if dev.name in seen_names:
            continue
        seen_names.add(dev.name)
        curated.append(dev)
    curated.sort(
        key=lambda d: (
            0 if "usb" in d.name.lower() else 1,
            0 if "analog" in d.name.lower() else 1,
            d.name.lower(),
        )
    )
    return curated


def _curate_outputs(devices: list[AudioDevice]) -> list[AudioDevice]:
    curated: list[AudioDevice] = []
    seen_names: set[str] = set()
    for dev in devices:
        if is_alsa_plugin_junk(dev.name):
            continue
        if not is_physical_portaudio_name(dev.name):
            continue
        if dev.name in seen_names:
            continue
        seen_names.add(dev.name)
        curated.append(dev)
    curated.sort(key=lambda d: (0 if "analog" in d.name.lower() else 1, d.name.lower()))
    return curated


def _system_default_input_label() -> str:
    session = query_linux_session_input()
    if session and session.description:
        return f"System default ({session.description})"
    return "System default (follow OS input)"


def _system_default_output_label() -> str:
    session = query_linux_session_output()
    if session and session.description:
        return f"System default ({session.description})"
    return "System default (follow OS output)"


def list_input_devices() -> list[AudioDevice]:
    curated = _curate_inputs(_raw_input_devices())
    system = AudioDevice(
        index=-1,
        name=SYSTEM_DEFAULT_KEY,
        host_api="Session",
        max_input_channels=1,
        max_output_channels=0,
        default_sample_rate=48000.0,
        is_default_input=True,
        is_system_default=True,
        friendly_name=_system_default_input_label(),
    )
    return [system] + curated


def list_output_devices() -> list[AudioDevice]:
    curated = _curate_outputs(_raw_output_devices())
    system = AudioDevice(
        index=-1,
        name=SYSTEM_DEFAULT_KEY,
        host_api="Session",
        max_input_channels=0,
        max_output_channels=2,
        default_sample_rate=48000.0,
        is_default_output=True,
        is_system_default=True,
        friendly_name=_system_default_output_label(),
    )
    return [system] + curated


def list_raw_output_candidates() -> list[tuple[int, str]]:
    return [(d.index, d.name) for d in _raw_output_devices() if not is_alsa_plugin_junk(d.name)]


def list_raw_input_candidates() -> list[tuple[int, str]]:
    return [(d.index, d.name) for d in _raw_input_devices() if not is_alsa_plugin_junk(d.name)]


def list_session_input_routes() -> list[tuple[int, str]]:
    """PipeWire/Pulse virtual capture endpoints (not raw hardware)."""
    routes: list[tuple[int, str]] = []
    for d in _raw_input_devices():
        if d.name.lower() in SESSION_ROUTE_NAMES:
            routes.append((d.index, d.name))
    return routes


def list_session_output_routes() -> list[tuple[int, str]]:
    """PipeWire/Pulse virtual playback endpoints (follow OS default sink)."""
    routes: list[tuple[int, str]] = []
    for d in _raw_output_devices():
        if d.name.lower() in SESSION_ROUTE_NAMES:
            routes.append((d.index, d.name))
    return routes


def _match_device_index_by_key(
    devices: list[AudioDevice],
    storage_key: str | None,
) -> int | None:
    key = normalize_device_key(storage_key)
    if key == SYSTEM_DEFAULT_KEY:
        return None
    name = key[len(NAME_KEY_PREFIX) :] if key and key.startswith(NAME_KEY_PREFIX) else key
    if not name:
        return None
    for d in devices:
        if d.name == name:
            return d.index
    for d in devices:
        if name.endswith(d.name) or d.name.endswith(name):
            return d.index
    return None


def resolve_input_device(storage_key: str | None) -> int | None:
    from babblecast.audio.session_devices import resolve_session_device_index

    key = normalize_device_key(storage_key, output=False)
    if key == SYSTEM_DEFAULT_KEY:
        return resolve_session_device_index(
            list_raw_input_candidates(),
            output=False,
        )
    raw = _raw_input_devices()
    matched = _match_device_index_by_key(raw, key)
    if matched is not None:
        return matched
    return resolve_session_device_index(list_raw_input_candidates(), output=False)


def resolve_output_device(storage_key: str | None) -> int | None:
    from babblecast.audio.session_devices import resolve_session_device_index

    key = normalize_device_key(storage_key, output=True)
    if key == SYSTEM_DEFAULT_KEY:
        for idx, _name in list_session_output_routes():
            if device_supports_output_rate(idx, SAMPLE_RATE):
                return idx
        return resolve_session_device_index(
            list_raw_output_candidates(),
            output=True,
        )
    raw = _raw_output_devices()
    matched = _match_device_index_by_key(raw, key)
    if matched is not None:
        return matched
    return resolve_session_device_index(list_raw_output_candidates(), output=True)
