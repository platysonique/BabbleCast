"""Tests for MIDI binding engine."""

from babblecast.client.qt.midi.binding_engine import BindingEngine


def test_serialize_round_trip() -> None:
    eng = BindingEngine()
    eng.map_midi("cc", 1, 7, "global.master_volume", "value", port_name="Test Device")
    rows = eng.serialize_maps()
    eng2 = BindingEngine()
    eng2.load_maps(rows)
    assert len(eng2.all_maps()) == 1
    m = eng2.all_maps()[0]
    assert m.midi_type == "cc"
    assert m.midi_number == 7
    assert m.target_id == "global.master_volume"


def test_conflict_replace() -> None:
    eng = BindingEngine()
    eng.map_midi("cc", 1, 7, "global.master_volume", "value")
    eng.map_midi("cc", 1, 7, "global.mic_volume", "value")
    assert len(eng.all_maps()) == 1
    assert eng.all_maps()[0].target_id == "global.mic_volume"


def test_cc_to_value_setter() -> None:
    eng = BindingEngine()
    seen: list[int] = []
    eng.register_target("global.gate", "value", lambda v: seen.append(v))
    eng.map_midi("cc", 0, 1, "global.gate", "value")
    eng.on_midi_cc(1, 64, 0)
    assert seen == [64]


def test_cc_release_for_ptt() -> None:
    eng = BindingEngine()
    pressed: list[bool] = []
    eng.register_target("global.ptt", "value", lambda v: pressed.append(True))
    eng.register_target("global.ptt", "release", lambda _v: pressed.append(False))
    eng.map_midi("cc", 0, 64, "global.ptt", "ptt")
    eng.on_midi_cc(64, 127, 0)
    eng.on_midi_cc(64, 0, 0)
    assert pressed == [True, False]


def test_note_trigger_and_release() -> None:
    eng = BindingEngine()
    events: list[str] = []
    eng.register_target("global.mute", "trigger", lambda _v: events.append("on"))
    eng.register_target("global.ptt", "release", lambda _v: events.append("off"))
    eng.map_midi("note", 0, 60, "global.mute", "trigger")
    eng.map_midi("note", 0, 61, "global.ptt", "ptt")
    eng.on_midi_note(60, 100, 0)
    eng.on_midi_note_off(61, 0)
    assert events == ["on", "off"]


def test_ctrl_idx_mismatch_ignored() -> None:
    eng = BindingEngine()
    seen: list[int] = []
    eng.register_target("global.gate", "value", lambda v: seen.append(v))
    eng.map_midi("cc", 0, 1, "global.gate", "value", ctrl_idx=1, port=0)
    eng.on_midi_cc(1, 64, 0, ctrl_idx=0, port=0)
    assert seen == []
