"""BabbleCast CLI — `bbc` command."""

from __future__ import annotations

import argparse
import socket
import sys

from babblecast.constants import DEFAULT_UDP_PORT, DEFAULT_WS_PORT


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="bbc",
        description="BabbleCast — team live communication hub",
    )
    sub = parser.add_subparsers(dest="command")

    server_p = sub.add_parser("server", help="Run headless BabbleCast server")
    server_p.add_argument("--host", default="0.0.0.0", help="Bind address")
    server_p.add_argument("--ws-port", type=int, default=DEFAULT_WS_PORT)
    server_p.add_argument("--udp-port", type=int, default=DEFAULT_UDP_PORT)
    server_p.add_argument("--name", default=socket.gethostname(), help="Server display name")

    sub.add_parser("client", help="Launch BabbleCast GUI client")

    args = parser.parse_args()

    if args.command == "server":
        from babblecast.server.hub import run_server

        run_server(host=args.host, ws_port=args.ws_port, udp_port=args.udp_port, server_name=args.name)
        return

    # Default: GUI client
    from babblecast.client.qt.app import run_gui

    sys.exit(run_gui())


if __name__ == "__main__":
    main()
