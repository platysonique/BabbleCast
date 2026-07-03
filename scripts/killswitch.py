#!/usr/bin/env python3
"""Platysonique remote kill switch — checks online revocation list."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = (
    "https://raw.githubusercontent.com/platysonique/pombomb-obs/main/security/killswitch.json"
)
CACHE = Path.home() / ".cache" / "platysonique" / "killswitch.json"
APP_NAME = os.environ.get("PLATYSONIQUE_APP", "platysonique")


def machine_id_hash() -> str:
    mid_path = Path("/etc/machine-id")
    if not mid_path.is_file():
        return hashlib.sha256(b"no-machine-id").hexdigest()
    return hashlib.sha256(mid_path.read_bytes()).hexdigest()


def fetch_state(url: str, timeout: float = 8.0) -> dict | None:
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": f"platysonique-killswitch/{APP_NAME}"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, dict):
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(data), encoding="utf-8")
        return data if isinstance(data, dict) else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def load_cached() -> dict | None:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def is_revoked(state: dict, mid_hash: str) -> bool:
    if state.get("globalRevoke") is True:
        return True
    revoked = state.get("revokedMachineIds") or []
    if not isinstance(revoked, list):
        return False
    return mid_hash in revoked


def check(*, url: str | None = None, fail_open_offline: bool = True) -> None:
    url = url or os.environ.get("PLATYSONIQUE_KILLSWITCH_URL", DEFAULT_URL)
    mid = machine_id_hash()
    state = fetch_state(url)
    if state is None:
        state = load_cached()
        if state is None:
            if fail_open_offline:
                return
            print(f"{APP_NAME}: cannot verify installation status (offline).", file=sys.stderr)
            sys.exit(2)
    if is_revoked(state, mid):
        msg = state.get("message") or "This installation has been disabled."
        print(msg, file=sys.stderr)
        print(f"Machine ID hash: {mid}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Platysonique kill switch")
    parser.add_argument("--check", action="store_true", help="Exit 1 if this machine is revoked")
    parser.add_argument("--show-id", action="store_true", help="Print SHA-256 of /etc/machine-id")
    parser.add_argument("--url", default=None, help="Override killswitch JSON URL")
    args = parser.parse_args()

    if args.show_id:
        print(machine_id_hash())
        return

    check(url=args.url)


if __name__ == "__main__":
    main()
