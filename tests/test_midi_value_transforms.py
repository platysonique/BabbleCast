"""Tests for MIDI value transforms."""

from babblecast.client.qt.midi.value_transforms import (
    cc_toggle_fire,
    midi_to_bridge,
    midi_to_gate_db,
    midi_to_suppression,
    toggle_fire,
)


def test_midi_to_bridge_max() -> None:
    assert abs(midi_to_bridge("absolute", 127) - 2.0) < 0.01


def test_gate_db_range() -> None:
    assert midi_to_gate_db(0) == -80.0
    assert midi_to_gate_db(127) == 0.0


def test_suppression() -> None:
    assert midi_to_suppression(64) == 64 / 127.0


def test_toggle_thresholds() -> None:
    assert toggle_fire(1) is True
    assert toggle_fire(0) is False
    assert cc_toggle_fire(63) is False
    assert cc_toggle_fire(64) is True
