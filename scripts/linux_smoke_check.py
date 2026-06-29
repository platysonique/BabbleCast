#!/usr/bin/env python3
"""Manual Linux smoke check — run after code changes."""

from __future__ import annotations

import subprocess
import sys
import time


def main() -> int:
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    venv_python = root / ".venv" / "bin" / "python"
    python_exe = str(venv_python if venv_python.exists() else sys.executable)
    venv_bbc = root / ".venv" / "bin" / "bbc"
    bbc = str(venv_bbc if venv_bbc.exists() else "bbc")

    print("1. pytest …")
    r = subprocess.run([python_exe, "-m", "pytest", "tests/", "-q"], cwd=root)
    if r.returncode != 0:
        return r.returncode

    print("2. bbc --help …")
    r = subprocess.run([bbc, "--help"], cwd=root, capture_output=True, text=True)
    if r.returncode != 0 or "BabbleCast" not in r.stdout:
        print(r.stderr or r.stdout)
        return 1

    print("3. headless server startup …")
    proc = subprocess.Popen(
        [bbc, "server", "--name", "smoke", "--ws-port", "28771", "--udp-port", "28772"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(1.5)
    if proc.poll() is not None:
        out, err = proc.communicate()
        print("server exited early:", err or out)
        return 1
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()

    print("4. import PyQt6 main window …")
    r = subprocess.run(
        [
            sys.executable,
            "-c",
            "from babblecast.client.qt.main_window import MainWindow; "
            "from babblecast.server.embedded import EmbeddedServer; print('ok')",
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(r.stderr)
        return 1

    print("ALL LINUX SMOKE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
