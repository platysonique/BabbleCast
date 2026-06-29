"""Tests for locally remembered room passwords."""

from babblecast.config import UserSettings
from babblecast.room_secrets import (
    forget_room_password,
    get_room_password,
    remember_room_password,
    room_password_admin_display,
    room_secret_key,
)


def test_room_secret_round_trip() -> None:
    settings = UserSettings()
    remember_room_password(settings, "192.168.1.10", 9513, "room-abc", "secret123", persist=False)
    assert get_room_password(settings, "192.168.1.10", 9513, "room-abc") == "secret123"
    forget_room_password(settings, "192.168.1.10", 9513, "room-abc", persist=False)
    assert get_room_password(settings, "192.168.1.10", 9513, "room-abc") == ""


def test_room_secret_key_normalizes_host() -> None:
    assert room_secret_key("  HOST.Local  ", 9513, "id") == "host.local:9513:id"


def test_room_password_admin_display() -> None:
    visible, text = room_password_admin_display({"name": "Lounge", "password_protected": False})
    assert visible is False
    assert text == ""

    visible, text = room_password_admin_display(
        {"name": "Lounge", "password_protected": True},
        remembered_password="hush",
    )
    assert visible is True
    assert text == "Lounge password: hush"

    visible, text = room_password_admin_display({"name": "Lounge", "password_protected": True})
    assert visible is True
    assert "protected" in text
