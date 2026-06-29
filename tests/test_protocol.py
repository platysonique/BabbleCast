"""Protocol and voice packet tests."""

from __future__ import annotations

import uuid

import pytest

from babblecast.protocol import (
    ErrorCode,
    MsgType,
    VoicePacket,
    clamp_chat,
    clamp_name,
    decode_msg,
    encode_msg,
    is_name_taken_error,
)


def test_encode_decode_roundtrip() -> None:
    raw = encode_msg(MsgType.CHAT, text="hello", room_id="abc")
    data = decode_msg(raw)
    assert data["type"] == "chat"
    assert data["text"] == "hello"


def test_clamp_name_empty() -> None:
    assert clamp_name("   ") == "Anonymous"


def test_clamp_chat_truncation() -> None:
    assert len(clamp_chat("x" * 5000)) <= 4096


def test_voice_packet_roundtrip() -> None:
    room_id = str(uuid.uuid4())
    sender_id = str(uuid.uuid4())
    payload = b"\x01\x02\x03opus"
    pkt = VoicePacket(room_id=room_id, sender_id=sender_id, sequence=42, opus_payload=payload)
    encoded = pkt.encode()
    decoded = VoicePacket.decode(encoded)
    assert decoded is not None
    assert decoded.room_id == room_id
    assert decoded.sender_id == sender_id
    assert decoded.sequence == 42
    assert decoded.opus_payload == payload


def test_voice_packet_rejects_garbage() -> None:
    assert VoicePacket.decode(b"NOPE") is None


def test_error_message_includes_error_code() -> None:
    raw = encode_msg(MsgType.ERROR, message="Name already in use", error_code=ErrorCode.NAME_TAKEN.value)
    data = decode_msg(raw)
    assert data["error_code"] == "name_taken"
    assert is_name_taken_error(data["error_code"], data["message"])
