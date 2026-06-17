"""mDNS advertiser must not crash when started from an asyncio loop."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from babblecast.server.embedded import EmbeddedServer
from babblecast.discovery import ServerAdvertiser
from babblecast.server.hub import BabbleCastHub


def test_advertiser_from_asyncio_thread() -> None:
    """Reproduces embedded-server path: asyncio loop + mDNS advertise."""
    ready = threading.Event()
    error: list[BaseException] = []

    def run_loop() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def start_hub() -> BabbleCastHub:
            hub = BabbleCastHub(
                host="127.0.0.1",
                ws_port=28765,
                udp_port=28766,
                advertise=True,
            )
            await hub.start()
            return hub

        try:
            hub = loop.run_until_complete(start_hub())
            ready.set()
            loop.run_until_complete(asyncio.sleep(0.5))
            loop.run_until_complete(hub.stop())
        except BaseException as exc:
            error.append(exc)
        finally:
            loop.close()

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()
    assert ready.wait(timeout=5), "hub failed to start (likely mDNS EventLoopBlocked)"
    t.join(timeout=5)
    assert not error, error


def test_advertiser_standalone_thread() -> None:
    adv = ServerAdvertiser("Test", ws_port=28767, udp_port=28768, host="127.0.0.1")
    adv.start()
    time.sleep(0.3)
    adv.stop()


def test_embedded_server_starts() -> None:
    srv = EmbeddedServer(ws_port=28769, udp_port=28770, server_name="pytest")
    srv.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        if srv.running:
            break
        time.sleep(0.1)
    assert srv.running, "EmbeddedServer did not reach running state"
    srv.stop()
