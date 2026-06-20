"""Tests for multi MIDI input port filtering."""

from babblecast.client.qt.midi.multi_input import _skip_port


def test_skip_through_port() -> None:
    assert _skip_port("Midi Through Port") is True


def test_skip_rtmidi_monitor() -> None:
    assert _skip_port("RtMidi Monitor") is True


def test_keep_normal_port() -> None:
    assert _skip_port("Akai MPKmini3 MIDI 1") is False
