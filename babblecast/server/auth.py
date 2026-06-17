"""Server password verification (LAN-only shared secret)."""

from __future__ import annotations

import hashlib
import secrets


def make_password_verifier(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    digest = _digest(password, salt)
    return salt, digest


def check_password(password: str, salt: str, digest: str) -> bool:
    if not digest:
        return True
    return _digest(password, salt) == digest


def _digest(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
