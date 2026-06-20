"""Tests for MidiEngine port open compatibility."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from babblecast.client.qt.midi.engine import MidiEngine


def test_open_port_without_dont_ignore_sysex() -> None:
    """Regression: python-rtmidi 1.5 has ignore_types, not dont_ignore_sysex."""
    fake_in = MagicMock()
    fake_in.get_ports.return_value = ["Device A"]
    fake_in.ignore_types = MagicMock()
    del fake_in.dont_ignore_sysex  # ensure attribute missing

    with patch("babblecast.client.qt.midi.engine.HAS_RTMIDI", True), patch(
        "babblecast.client.qt.midi.engine.rtmidi"
    ) as rtm:
        rtm.MidiIn.return_value = fake_in
        eng = MidiEngine()
        assert eng.open_port("Device A") is True
        fake_in.open_port.assert_called_once_with(0)
        fake_in.set_callback.assert_called_once()
        fake_in.ignore_types.assert_called_once()


def test_open_port_failure_returns_false() -> None:
    with patch("babblecast.client.qt.midi.engine.HAS_RTMIDI", True), patch(
        "babblecast.client.qt.midi.engine.rtmidi"
    ) as rtm:
        rtm.MidiIn.side_effect = RuntimeError("ALSA busy")
        eng = MidiEngine()
        assert eng.open_port("Device A") is False
