"""Locally remembered room passwords (server stores hashes only)."""

from __future__ import annotations

from babblecast.config import UserSettings, save_settings


def room_secret_key(host: str, port: int, room_id: str) -> str:
    return f"{host.strip().lower()}:{int(port)}:{room_id}"


def remember_room_password(
    settings: UserSettings,
    host: str,
    port: int,
    room_id: str,
    password: str,
    *,
    persist: bool = True,
) -> None:
    pwd = password.strip()
    if not pwd or not room_id:
        return
    settings.room_passwords[room_secret_key(host, port, room_id)] = pwd
    if persist:
        save_settings(settings)


def get_room_password(settings: UserSettings, host: str, port: int, room_id: str) -> str:
    if not room_id:
        return ""
    return settings.room_passwords.get(room_secret_key(host, port, room_id), "")


def forget_room_password(
    settings: UserSettings,
    host: str,
    port: int,
    room_id: str,
    *,
    persist: bool = True,
) -> None:
    if not room_id:
        return
    settings.room_passwords.pop(room_secret_key(host, port, room_id), None)
    if persist:
        save_settings(settings)


def room_password_admin_display(
    room_meta: dict | None,
    *,
    remembered_password: str = "",
) -> tuple[bool, str]:
    if not room_meta or not room_meta.get("password_protected"):
        return False, ""
    name = str(room_meta.get("name", "Room"))
    if remembered_password:
        return True, f"{name} password: {remembered_password}"
    return True, f"{name}: 🔒 protected (password not stored on this device)"
