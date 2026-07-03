"""BabbleCast CLI — `bbc` command."""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
from pathlib import Path

from babblecast.constants import DEFAULT_UDP_PORT, DEFAULT_WS_PORT


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_update() -> None:
    root = _repo_root()
    if not (root / ".git").is_dir():
        print("bbc --update: not a git checkout (missing .git); reinstall with packaging/linux/install.sh", file=sys.stderr)
        sys.exit(1)

    branch = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    print(f"Updating BabbleCast in {root} (branch {branch})…")

    subprocess.run(["git", "-C", str(root), "pull", "--ff-only"], check=True)

    req = root / "requirements-dev.txt"
    if req.is_file():
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req)], check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "-e", str(root)], check=True)

    desktop_install = root / "packaging" / "linux" / "install-desktop.sh"
    if desktop_install.is_file():
        subprocess.run(["bash", str(desktop_install)], check=True)

    print("BabbleCast updated. Restart any running bbc windows to pick up changes.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="bbc",
        description="BabbleCast — team live communication hub",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="git pull and reinstall this checkout (editable install)",
    )
    sub = parser.add_subparsers(dest="command")

    server_p = sub.add_parser("server", help="Run headless BabbleCast server")
    server_p.add_argument("--host", default="0.0.0.0", help="Bind address")
    server_p.add_argument("--ws-port", type=int, default=DEFAULT_WS_PORT)
    server_p.add_argument("--udp-port", type=int, default=DEFAULT_UDP_PORT)
    server_p.add_argument("--name", default=socket.gethostname(), help="Server display name")

    sub.add_parser("client", help="Launch BabbleCast GUI client")

    args = parser.parse_args()

    if args.update:
        _run_update()
        return

    from babblecast.killswitch import enforce_killswitch

    enforce_killswitch("babblecast")

    if args.command == "server":
        from babblecast.server.hub import run_server

        from babblecast.config import get_settings, save_settings

        run_server(
            host=args.host,
            ws_port=args.ws_port,
            udp_port=args.udp_port,
            server_name=args.name,
            host_password=get_settings().host_password,
        )
        return

    # Default: GUI client
    from babblecast.client.qt.app import run_gui

    sys.exit(run_gui())


if __name__ == "__main__":
    main()
