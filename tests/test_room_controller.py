"""Shared room controller helpers."""

from __future__ import annotations

from babblecast.client.room_controller import (
    should_disconnect_failed_connect,
)
from babblecast.protocol import ErrorCode, is_name_taken_error


def test_name_taken_error_code() -> None:
    assert is_name_taken_error(ErrorCode.NAME_TAKEN.value, "Name already in use")
    assert not is_name_taken_error(ErrorCode.ROOM_NOT_FOUND.value, "Room not found")


def test_should_disconnect_only_for_name_taken() -> None:
    assert should_disconnect_failed_connect(
        ErrorCode.NAME_TAKEN.value,
        "Name already in use",
        connected=False,
    )
    assert not should_disconnect_failed_connect(
        None,
        "Audio unavailable",
        connected=False,
    )
    assert not should_disconnect_failed_connect(
        ErrorCode.NAME_TAKEN.value,
        "Name already in use",
        connected=True,
    )
