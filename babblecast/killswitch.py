"""Platysonique remote kill switch enforcement for BabbleCast."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_CANDIDATE_PATHS = (
    Path("/usr/share/platysonique/killswitch.py"),
    Path(__file__).resolve().parents[1] / "scripts" / "killswitch.py",
)


class KillSwitchRevoked(RuntimeError):
    """Raised when this machine is revoked via the online kill switch."""


def enforce_killswitch(app_name: str = "babblecast") -> None:
    for path in _CANDIDATE_PATHS:
        if not path.is_file():
            continue
        env = os.environ.copy()
        env["PLATYSONIQUE_APP"] = app_name
        subprocess.run(
            [sys.executable, str(path), "--check"],
            check=True,
            env=env,
        )
        return


def check_killswitch_or_raise(app_name: str = "babblecast") -> None:
    try:
        enforce_killswitch(app_name)
    except subprocess.CalledProcessError as exc:
        raise KillSwitchRevoked("Installation disabled by remote kill switch.") from exc
