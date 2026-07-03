#!/usr/bin/env python3
"""Wipe Platysonique app credentials when a machine is kill-switched."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

KILLSWITCH_CACHE = Path.home() / ".cache" / "platysonique" / "killswitch.json"

BABBLECAST_SETTINGS = Path.home() / ".config" / "babblecast" / "settings.json"
OBS_WS_CONFIG = Path.home() / ".config" / "obs-studio" / "obs-websocket" / "config.json"
POMBOMB_ETC_DIR = Path("/etc/pombomb-sweet")
SUDO_KEYRING = Path(os.environ.get("POMBOMB_SUDO_KEYRING", "/home/papaya/pombomb-obs/scripts/sudo-keyring.sh"))

CHROMIUM_PROFILES = (
    Path.home() / ".config" / "chromium",
    Path.home() / ".config" / "google-chrome",
    Path.home() / ".config" / "BraveSoftware" / "Brave-Browser",
)


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _redact_json_keys(path: Path, keys: list[str], dict_keys: list[str] | None = None) -> bool:
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    changed = False
    for key in keys:
        if key in data and data[key]:
            data[key] = "" if not isinstance(data[key], dict) else {}
            changed = True
    for key in dict_keys or []:
        if data.get(key):
            data[key] = {}
            changed = True
    if changed:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return changed


def _clear_yaml_password(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    out: list[str] = []
    changed = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("hub_password:") or stripped.startswith("password:"):
            indent = line[: len(line) - len(stripped)]
            key = stripped.split(":", 1)[0]
            out.append(f'{indent}{key}: ""')
            changed = True
        else:
            out.append(line)
    if changed:
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return changed


def _clear_libsecret_sudo() -> bool:
    if not shutil.which("secret-tool"):
        return False
    proc = subprocess.run(
        ["secret-tool", "clear", "service", "sudo"],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def _gh_logout() -> bool:
    if not shutil.which("gh"):
        return False
    proc = subprocess.run(["gh", "auth", "logout", "--hostname", "github.com"], capture_output=True, text=True)
    return proc.returncode == 0


def _wipe_chromium_local_storage() -> int:
    removed = 0
    for root in CHROMIUM_PROFILES:
        if not root.is_dir():
            continue
        for profile in root.iterdir():
            if not profile.is_dir():
                continue
            for sub in ("Local Storage", "Session Storage", "IndexedDB"):
                target = profile / sub
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                    removed += 1
    return removed


def _sudo_clear_etc_pombomb() -> int:
    if not POMBOMB_ETC_DIR.is_dir():
        return 0
    if not SUDO_KEYRING.is_file():
        return 0
    cleared = 0
    for yaml_path in POMBOMB_ETC_DIR.glob("*.yaml"):
        tmp = Path("/tmp") / f"pombomb-wipe-{yaml_path.name}"
        try:
            text = yaml_path.read_text(encoding="utf-8")
        except OSError:
            continue
        new_lines: list[str] = []
        changed = False
        for line in text.splitlines():
            s = line.lstrip()
            if s.startswith("hub_password:") or s.startswith("password:"):
                indent = line[: len(line) - len(s)]
                key = s.split(":", 1)[0]
                new_lines.append(f'{indent}{key}: ""')
                changed = True
            else:
                new_lines.append(line)
        if not changed:
            continue
        tmp.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        proc = subprocess.run(
            [str(SUDO_KEYRING), "cp", str(tmp), str(yaml_path)],
            capture_output=True,
            text=True,
        )
        tmp.unlink(missing_ok=True)
        if proc.returncode == 0:
            cleared += 1
    return cleared


def wipe_credentials(*, quiet: bool = False) -> int:
    actions = 0

    if KILLSWITCH_CACHE.exists():
        KILLSWITCH_CACHE.unlink(missing_ok=True)
        actions += 1
        if not quiet:
            _log("cleared killswitch cache")

    if _redact_json_keys(BABBLECAST_SETTINGS, ["host_password"], ["room_passwords"]):
        actions += 1
        if not quiet:
            _log(f"cleared BabbleCast passwords in {BABBLECAST_SETTINGS}")

    if _redact_json_keys(OBS_WS_CONFIG, ["server_password"]):
        actions += 1
        if not quiet:
            _log(f"cleared OBS WebSocket password in {OBS_WS_CONFIG}")

    for yaml_name in ("backstageview-client.yaml", "backstageview.yaml"):
        yaml_path = POMBOMB_ETC_DIR / yaml_name
        if _clear_yaml_password(yaml_path):
            actions += 1
            if not quiet:
                _log(f"cleared passwords in {yaml_path}")

    etc_cleared = _sudo_clear_etc_pombomb()
    if etc_cleared:
        actions += etc_cleared
        if not quiet:
            _log(f"cleared {etc_cleared} file(s) under {POMBOMB_ETC_DIR} (sudo)")

    if _clear_libsecret_sudo():
        actions += 1
        if not quiet:
            _log("cleared sudo password in GNOME keyring")

    if _gh_logout():
        actions += 1
        if not quiet:
            _log("logged out GitHub CLI")

    browser_dirs = _wipe_chromium_local_storage()
    if browser_dirs:
        actions += browser_dirs
        if not quiet:
            _log(f"cleared browser storage in {browser_dirs} Chromium profile dir(s)")

    if not quiet:
        _log(f"credential wipe finished ({actions} action(s))")
    return actions


def main() -> None:
    parser = argparse.ArgumentParser(description="Wipe Platysonique credentials on this machine")
    parser.add_argument("--apply", action="store_true", help="Run the wipe (default when no other flags)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    wipe_credentials(quiet=args.quiet)


if __name__ == "__main__":
    main()
