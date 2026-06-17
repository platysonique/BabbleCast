"""Room chat persistence and embedded server event callbacks."""

from __future__ import annotations

import socket
import threading
import time

from babblecast.room_chat import get_room_chat_store, room_chat_key
from babblecast.server.embedded import EmbeddedServer


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_room_chat_store_persists_messages(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "babblecast.room_chat.app_config_dir",
        lambda create=False: tmp_path,
    )
    from babblecast.room_chat import RoomChatStore

    store = RoomChatStore()
    store.append("127.0.0.1", 8765, "room-a", "Alice", "hello room")
    store.append("127.0.0.1", 8765, "room-a", "Bob", "hi back", room_name="General")

    reloaded = RoomChatStore()
    lines = reloaded.lines("127.0.0.1", 8765, "room-a")
    assert len(lines) == 2
    assert lines[0].text == "hello room"
    assert lines[1].name == "Bob"
    assert room_chat_key("127.0.0.1", 8765, "room-a") in reloaded._histories


def test_room_chat_store_purge_removes_history(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "babblecast.room_chat.app_config_dir",
        lambda create=False: tmp_path,
    )
    from babblecast.room_chat import RoomChatStore

    store = RoomChatStore()
    store.append("127.0.0.1", 8765, "room-a", "Alice", "hello room")
    store.purge("127.0.0.1", 8765, "room-a")
    assert store.lines("127.0.0.1", 8765, "room-a") == []


def test_embedded_server_on_started_callback() -> None:
    ws_port = _free_port()
    udp_port = _free_port()
    started = threading.Event()
    host_port: list[tuple[str, int]] = []

    def on_started(host: str, port: int) -> None:
        host_port.append((host, port))
        started.set()

    server = EmbeddedServer(
        ws_port=ws_port,
        udp_port=udp_port,
        server_name="event-test",
        on_started=on_started,
    )
    server.start()
    assert started.wait(timeout=8), "on_started never fired"
    assert host_port == [("127.0.0.1", ws_port)]
    assert server.running
    server.stop()


def test_embedded_server_on_failed_callback() -> None:
    ws_port = _free_port()
    udp_port = _free_port()
    failed: list[str] = []
    blocker = EmbeddedServer(ws_port=ws_port, udp_port=udp_port)
    blocker.start()
    deadline = time.time() + 5
    while time.time() < deadline and not blocker.running:
        time.sleep(0.05)
    assert blocker.running

    try:
        server = EmbeddedServer(
            ws_port=ws_port,
            udp_port=udp_port,
            on_failed=lambda msg: failed.append(msg),
        )
        server.start()
        deadline = time.time() + 5
        while time.time() < deadline and not failed:
            time.sleep(0.05)
        assert failed, "on_failed never fired"
    finally:
        blocker.stop()
