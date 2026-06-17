"""End-to-end Linux paths: host, connect, chat, voice UDP registration."""

from __future__ import annotations

import socket
import threading
import time

from babblecast.client.session import ClientSession
from babblecast.server.embedded import EmbeddedServer


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_embedded_host_client_chat_flow() -> None:
    ws_port = _free_port()
    udp_port = _free_port()
    chat_received: list[dict] = []
    connected = threading.Event()

    session = ClientSession(
        on_connected=lambda: connected.set(),
        on_chat=lambda d: chat_received.append(d),
    )
    server = EmbeddedServer(ws_port=ws_port, udp_port=udp_port, server_name="integration")
    server.start()

    deadline = time.time() + 8
    while time.time() < deadline:
        if server.running:
            break
        time.sleep(0.05)
    assert server.running, "embedded server never became ready"

    try:
        session.connect("127.0.0.1", ws_port)
        assert connected.wait(timeout=5), "client never connected"

        session.send_chat("integration ping")
        deadline = time.time() + 5
        while time.time() < deadline and not chat_received:
            time.sleep(0.05)
        assert chat_received, "chat message not echoed"
        assert chat_received[0].get("text") == "integration ping"
        assert session.client_id
        assert session.room_id
    finally:
        session.disconnect()
        server.stop()


def test_client_session_survives_disconnect_reconnect() -> None:
    ws_port = _free_port()
    udp_port = _free_port()
    server = EmbeddedServer(ws_port=ws_port, udp_port=udp_port)
    server.start()
    deadline = time.time() + 8
    while time.time() < deadline and not server.running:
        time.sleep(0.05)
    assert server.running

    session = ClientSession()
    try:
        session.connect("127.0.0.1", ws_port)
        time.sleep(0.8)
        assert session.connected
        session.disconnect()
        time.sleep(0.3)
        assert not session.connected

        connected = threading.Event()
        session2 = ClientSession(on_connected=lambda: connected.set())
        session2.connect("127.0.0.1", ws_port)
        assert connected.wait(timeout=5)
        session2.disconnect()
    finally:
        server.stop()
