"""Tests for MIDI target IDs and labels."""

from babblecast.client.qt.midi.targets import (
    global_target,
    label_for_target_id,
    parse_peer_target,
    peer_target,
)


def test_peer_target_id() -> None:
    assert peer_target("uuid:alice", "volume") == "peer.uuid:alice.volume"


def test_parse_peer_target_round_trip() -> None:
    tid = peer_target("link1:user42", "listen_mute")
    parsed = parse_peer_target(tid)
    assert parsed == ("link1:user42", "listen_mute")


def test_label_uses_meta() -> None:
    tid = peer_target("x:y", "volume")
    label = label_for_target_id(tid, {"peer_name": "Alice", "link_label": "Studio"})
    assert "Alice" in label
    assert "Studio" in label
    assert global_target("mute") == "global.mute"
