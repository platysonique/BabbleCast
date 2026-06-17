"""Voice UDP round-trip through embedded server."""

from __future__ import annotations

import socket
import threading
import time

from babblecast.audio.codec import OpusCodec
from babblecast.constants import FRAME_BYTES, FRAME_SAMPLES
from babblecast.client.session import ClientSession
from babblecast.server.embedded import EmbeddedServer


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _CollectSpeaker:
    """Minimal speaker stub for voice relay tests."""

    def __init__(self) -> None:
        self.frames: list[bytes] = []

    def push_pcm(self, _key: str, pcm: bytes) -> None:
        self.frames.append(pcm)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def set_participant_volume(self, *_args) -> None:
        pass

    def set_participant_muted(self, *_args) -> None:
        pass


def _wait_server(server: EmbeddedServer, timeout: float = 8) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline and not server.running:
        time.sleep(0.05)
    assert server.running


def test_voice_udp_relay_two_clients() -> None:
    ws_port = _free_port()
    udp_port = _free_port()
    pcm = b"\x00\x10" * FRAME_SAMPLES
    collector = _CollectSpeaker()
    connected_a = threading.Event()
    connected_b = threading.Event()

    session_a = ClientSession(on_connected=lambda: connected_a.set())
    session_b = ClientSession(
        link_id="test-b",
        bridge_speaker=collector,
        listen_muted_getter=lambda: False,
        on_connected=lambda: connected_b.set(),
    )
    server = EmbeddedServer(ws_port=ws_port, udp_port=udp_port, server_name="voice-test")
    server.start()
    _wait_server(server)

    try:
        session_a.connect("127.0.0.1", ws_port)
        session_b.connect("127.0.0.1", ws_port)
        assert connected_a.wait(timeout=5)
        assert connected_b.wait(timeout=5)
        time.sleep(0.5)

        session_a.send_voice_pcm(pcm)
        deadline = time.time() + 3
        while time.time() < deadline and not collector.frames:
            time.sleep(0.05)

        assert collector.frames, "peer never received relayed voice"
        assert len(collector.frames[0]) == FRAME_BYTES
    finally:
        session_a.disconnect()
        session_b.disconnect()
        server.stop()


def test_session_disconnect_joins_udp_thread() -> None:
    ws_port = _free_port()
    udp_port = _free_port()
    connected = threading.Event()
    server = EmbeddedServer(ws_port=ws_port, udp_port=udp_port)
    server.start()
    _wait_server(server)

    session = ClientSession(on_connected=lambda: connected.set())
    try:
        session.connect("127.0.0.1", ws_port)
        assert connected.wait(timeout=5)
        session.disconnect()
        assert session._udp_thread is None  # noqa: SLF001
    finally:
        server.stop()


def test_opus_codec_roundtrip() -> None:
    codec = OpusCodec()
    pcm = b"\x00\x10" * FRAME_SAMPLES
    opus = codec.encode(pcm)
    assert opus
    decoded = codec.decode(opus)
    assert len(decoded) == FRAME_BYTES
