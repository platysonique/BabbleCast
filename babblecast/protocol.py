"""JSON control-plane message types and UDP voice framing."""

from __future__ import annotations

import json
import struct
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from babblecast.constants import (
    FRAME_SAMPLES,
    MAX_CHAT_LEN,
    MAX_NAME_LEN,
    MAX_ROOM_NAME_LEN,
    UDP_MAGIC,
)


class ErrorCode(str, Enum):
    NAME_TAKEN = "name_taken"
    PASSWORD_REQUIRED = "password_required"
    PASSWORD_WRONG = "password_wrong"
    ROOM_PASSWORD_REQUIRED = "room_password_required"
    ROOM_PASSWORD_WRONG = "room_password_wrong"
    NOT_ROOM_OWNER = "not_room_owner"
    ROOM_NOT_FOUND = "room_not_found"
    LAST_ROOM = "last_room"
    USER_NOT_FOUND = "user_not_found"
    TAP_NOT_FOUND = "tap_not_found"
    TAP_NOT_PARTICIPANT = "tap_not_participant"
    TAP_NOT_OPEN = "tap_not_open"
    GENERIC = "generic"


class MsgType(str, Enum):
    HELLO = "hello"
    WELCOME = "welcome"
    ROOM_LIST = "room_list"
    ROOMS = "rooms"
    CREATE_ROOM = "create_room"
    ROOM_CREATED = "room_created"
    JOIN_ROOM = "join_room"
    JOINED = "joined"
    DELETE_ROOM = "delete_room"
    ROOM_DELETED = "room_deleted"
    LEAVE_ROOM = "leave_room"
    PRESENCE = "presence"
    CHAT = "chat"
    PTT = "ptt"
    MUTE = "mute"
    VOLUME = "volume"
    VOICE_LEVEL = "voice_level"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"
    TAP = "tap"
    TAP_RECEIVED = "tap_received"
    TAP_OPEN = "tap_open"
    TAP_CHAT = "tap_chat"
    TAP_END = "tap_end"


def new_id() -> str:
    return str(uuid.uuid4())


def encode_msg(msg_type: MsgType | str, **payload: Any) -> str:
    t = msg_type.value if isinstance(msg_type, MsgType) else str(msg_type)
    body = {"type": t, **payload}
    return json.dumps(body, separators=(",", ":"))


def decode_msg(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    data = json.loads(raw)
    if "type" not in data:
        raise ValueError("missing message type")
    return data


def parse_error_code(data: dict[str, Any]) -> str | None:
    code = data.get("error_code")
    if code is None:
        return None
    return str(code)


def is_room_password_error(error_code: str | None, message: str = "") -> bool:
    if error_code in (
        ErrorCode.ROOM_PASSWORD_REQUIRED.value,
        ErrorCode.ROOM_PASSWORD_WRONG.value,
    ):
        return True
    lowered = message.lower()
    return "room password" in lowered or (
        "password" in lowered and "room" in lowered and ("wrong" in lowered or "required" in lowered)
    )


def is_name_taken_error(error_code: str | None, message: str = "") -> bool:
    if error_code == ErrorCode.NAME_TAKEN.value:
        return True
    return "name already in use" in message.lower()


def is_password_error(error_code: str | None, message: str = "") -> bool:
    if error_code in (ErrorCode.PASSWORD_REQUIRED.value, ErrorCode.PASSWORD_WRONG.value):
        return True
    lowered = message.lower()
    return "password" in lowered and ("wrong" in lowered or "required" in lowered or "incorrect" in lowered)


def clamp_name(name: str) -> str:
    cleaned = name.strip()[:MAX_NAME_LEN]
    return cleaned or "Anonymous"


def clamp_room_name(name: str) -> str:
    cleaned = name.strip()[:MAX_ROOM_NAME_LEN]
    return cleaned or "Room"


def clamp_chat(text: str) -> str:
    return text.strip()[:MAX_CHAT_LEN]


@dataclass
class Participant:
    client_id: str
    name: str
    muted: bool = False
    ptt_active: bool = False
    voice_level: float = 0.0
    volume: float = 1.0
    speaking: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "name": self.name,
            "muted": self.muted,
            "ptt_active": self.ptt_active,
            "voice_level": round(self.voice_level, 3),
            "volume": round(self.volume, 3),
            "speaking": self.speaking,
        }


@dataclass
class RoomInfo:
    room_id: str
    name: str
    member_count: int = 0
    password_protected: bool = False
    creator_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "room_id": self.room_id,
            "name": self.name,
            "member_count": self.member_count,
            "password_protected": self.password_protected,
            "creator_id": self.creator_id,
        }


@dataclass
class VoicePacket:
    room_id: str
    sender_id: str
    sequence: int
    opus_payload: bytes

    _HEADER = struct.Struct("!4s16s16sI")

    def encode(self) -> bytes:
        room_b = uuid.UUID(self.room_id).bytes
        sender_b = uuid.UUID(self.sender_id).bytes
        return self._HEADER.pack(UDP_MAGIC, room_b, sender_b, self.sequence) + self.opus_payload

    @classmethod
    def decode(cls, data: bytes) -> VoicePacket | None:
        if len(data) < cls._HEADER.size:
            return None
        magic, room_b, sender_b, sequence = cls._HEADER.unpack_from(data)
        if magic != UDP_MAGIC:
            return None
        payload = data[cls._HEADER.size :]
        if not payload:
            return None
        return cls(
            room_id=str(uuid.UUID(bytes=room_b)),
            sender_id=str(uuid.UUID(bytes=sender_b)),
            sequence=sequence,
            opus_payload=payload,
        )


def pcm_frame_size() -> int:
    return FRAME_SAMPLES
