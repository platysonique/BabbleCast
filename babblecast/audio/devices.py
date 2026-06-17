"""Audio device enumeration with human-readable labels."""

from __future__ import annotations

from dataclasses import dataclass

import sounddevice as sd


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

    @property
    def label(self) -> str:
        role = []
        if self.is_default_input:
            role.append("default mic")
        if self.is_default_output:
            role.append("default speaker")
        suffix = f" — {', '.join(role)}" if role else ""
        direction = []
        if self.max_input_channels > 0:
            direction.append("in")
        if self.max_output_channels > 0:
            direction.append("out")
        dir_tag = "/".join(direction)
        return f"{self.name} [{self.host_api}, {dir_tag}]{suffix}"

    @property
    def storage_key(self) -> str:
        return f"{self.index}:{self.name}"


def _host_api_name(idx: int) -> str:
    try:
        apis = sd.query_hostapis()
        return str(apis[idx]["name"])
    except Exception:
        return "Unknown"


def list_input_devices() -> list[AudioDevice]:
    default_in, _ = sd.default.device
    devices: list[AudioDevice] = []
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] < 1:
            continue
        devices.append(
            AudioDevice(
                index=i,
                name=str(dev["name"]),
                host_api=_host_api_name(int(dev["hostapi"])),
                max_input_channels=int(dev["max_input_channels"]),
                max_output_channels=int(dev["max_output_channels"]),
                default_sample_rate=float(dev["default_samplerate"]),
                is_default_input=i == default_in,
            )
        )
    return devices


def list_output_devices() -> list[AudioDevice]:
    _, default_out = sd.default.device
    devices: list[AudioDevice] = []
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_output_channels"] < 1:
            continue
        devices.append(
            AudioDevice(
                index=i,
                name=str(dev["name"]),
                host_api=_host_api_name(int(dev["hostapi"])),
                max_input_channels=int(dev["max_input_channels"]),
                max_output_channels=int(dev["max_output_channels"]),
                default_sample_rate=float(dev["default_samplerate"]),
                is_default_output=i == default_out,
            )
        )
    return devices


def resolve_input_device(storage_key: str | None) -> int | None:
    devices = list_input_devices()
    if not devices:
        return None
    if storage_key:
        for d in devices:
            if d.storage_key == storage_key:
                return d.index
        for d in devices:
            if storage_key.endswith(d.name):
                return d.index
    for d in devices:
        if d.is_default_input:
            return d.index
    return devices[0].index


def resolve_output_device(storage_key: str | None) -> int | None:
    devices = list_output_devices()
    if not devices:
        return None
    if storage_key:
        for d in devices:
            if d.storage_key == storage_key:
                return d.index
        for d in devices:
            if storage_key.endswith(d.name):
                return d.index
    for d in devices:
        if d.is_default_output:
            return d.index
    return devices[0].index
