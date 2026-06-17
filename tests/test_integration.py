"""End-to-end Linux paths: host, connect, chat, voice UDP registration."""

from __future__ import annotations

import socket
import threading
import time

from babblecast.client.session import ClientSession
from babblecast.config import UserSettings
from babblecast.constants import FRAME_BYTES, composite_participant_key
from babblecast.server.embedded import EmbeddedServer


class _RecordingSpeaker:
    def __init__(self) -> None:
        self.pushes: list[tuple[str, bytes]] = []

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def push_pcm(self, client_id: str, pcm: bytes) -> None:
        self.pushes.append((client_id, pcm))

    def set_participant_volume(self, _client_id: str, _volume: float) -> None:
        pass

    def set_participant_muted(self, _client_id: str, _muted: bool) -> None:
        pass


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


def test_voice_udp_relay_between_two_bridge_sessions() -> None:
    ws_port = _free_port()
    udp_port = _free_port()
    server = EmbeddedServer(ws_port=ws_port, udp_port=udp_port, server_name="voice-relay")
    server.start()
    deadline = time.time() + 8
    while time.time() < deadline and not server.running:
        time.sleep(0.05)
    assert server.running

    speaker = _RecordingSpeaker()
    ev_a = threading.Event()
    ev_b = threading.Event()
    sessions = [
        ClientSession(link_id="link-a", bridge_speaker=speaker, on_connected=ev_a.set),
        ClientSession(link_id="link-b", bridge_speaker=speaker, on_connected=ev_b.set),
    ]
    sessions[0].update_settings(UserSettings(display_name="Voice A"))
    sessions[1].update_settings(UserSettings(display_name="Voice B"))
    pcm = b"\x00" * FRAME_BYTES

    try:
        sessions[0].connect("127.0.0.1", ws_port)
        sessions[1].connect("127.0.0.1", ws_port)
        assert ev_a.wait(timeout=5)
        assert ev_b.wait(timeout=5)
        time.sleep(0.3)

        sender, listener = sessions[0], sessions[1]
        assert sender.room_id
        assert listener.room_id
        for _ in range(8):
            sender.send_voice_pcm(pcm)
            time.sleep(0.025)

        expected_key = composite_participant_key("link-b", sender.client_id)
        deadline = time.time() + 4
        while time.time() < deadline:
            if any(k == expected_key and len(p) == FRAME_BYTES for k, p in speaker.pushes):
                break
            time.sleep(0.05)
        assert any(k == expected_key and len(p) == FRAME_BYTES for k, p in speaker.pushes)
    finally:
        for session in sessions:
            session.disconnect()
        server.stop()


def test_rejected_display_name_stops_client_threads() -> None:
    ws_port = _free_port()
    udp_port = _free_port()
    server = EmbeddedServer(ws_port=ws_port, udp_port=udp_port, server_name="name-guard")
    server.start()
    deadline = time.time() + 8
    while time.time() < deadline and not server.running:
        time.sleep(0.05)
    assert server.running

    errors: list[str] = []
    ev_a = threading.Event()
    ev_b = threading.Event()
    session_a = ClientSession(on_connected=ev_a.set)
    session_b = ClientSession(on_error=lambda m, _ec=None: errors.append(m), on_connected=ev_b.set)
    session_a.update_settings(UserSettings(display_name="Director"))
    session_b.update_settings(UserSettings(display_name="Director"))

    try:
        session_a.connect("127.0.0.1", ws_port)
        assert ev_a.wait(timeout=5)
        session_b.connect("127.0.0.1", ws_port)
        deadline = time.time() + 5
        while time.time() < deadline and not errors:
            time.sleep(0.05)
        assert errors
        assert "name already in use" in errors[0].lower()
        assert not ev_b.wait(timeout=1)
        time.sleep(0.5)
        assert not session_b._udp_thread or not session_b._udp_thread.is_alive()
    finally:
        session_a.disconnect()
        session_b.disconnect()
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
