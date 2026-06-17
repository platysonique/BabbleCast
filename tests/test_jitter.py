"""Voice jitter buffer tests."""

from __future__ import annotations

from babblecast.audio.jitter import VoiceJitterBuffer


def test_jitter_priming_requires_two_packets() -> None:
    jb = VoiceJitterBuffer()
    assert jb.push(1, b"opus") == []
    out = jb.push(2, b"opus2")
    assert out == [b"opus", b"opus2"]


def test_jitter_duplicate_dropped() -> None:
    jb = VoiceJitterBuffer()
    jb.push(1, b"a")
    jb.push(2, b"b")
    assert jb.push(2, b"c") == []


def test_jitter_gap_emits_plc() -> None:
    jb = VoiceJitterBuffer()
    jb.push(1, b"a")
    jb.push(2, b"b")
    out = jb.push(4, b"c")
    assert out == [None, b"c"]
