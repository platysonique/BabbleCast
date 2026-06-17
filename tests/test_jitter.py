"""Voice jitter buffer tests."""

from __future__ import annotations

from babblecast.audio.jitter import VoiceJitterBuffer


def test_jitter_first_packet() -> None:
    jb = VoiceJitterBuffer()
    out = jb.push(1, b"opus")
    assert out == [b"opus"]


def test_jitter_duplicate_dropped() -> None:
    jb = VoiceJitterBuffer()
    jb.push(1, b"a")
    assert jb.push(1, b"b") == []


def test_jitter_gap_emits_plc() -> None:
    jb = VoiceJitterBuffer()
    jb.push(1, b"a")
    out = jb.push(3, b"c")
    assert out == [None, b"c"]
