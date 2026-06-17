"""Embedded server runner for client-initiated hosting."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable

from babblecast.constants import DEFAULT_UDP_PORT, DEFAULT_WS_PORT
from babblecast.server.hub import BabbleCastHub

logger = logging.getLogger(__name__)


class EmbeddedServer:
    def __init__(
        self,
        ws_port: int = DEFAULT_WS_PORT,
        udp_port: int = DEFAULT_UDP_PORT,
        server_name: str = "BabbleCast",
        on_started: Callable[[str, int], None] | None = None,
        on_stopped: Callable[[], None] | None = None,
    ) -> None:
        self._ws_port = ws_port
        self._udp_port = udp_port
        self._server_name = server_name
        self._on_started = on_started
        self._on_stopped = on_stopped
        self._hub: BabbleCastHub | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def host(self) -> str:
        return "127.0.0.1"

    @property
    def ws_port(self) -> int:
        return self._ws_port

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._hub = BabbleCastHub(
            host="0.0.0.0",
            ws_port=self._ws_port,
            udp_port=self._udp_port,
            server_name=self._server_name,
            advertise=True,
        )
        try:
            self._loop.run_until_complete(self._hub.start())
            self._running = True
            if self._on_started:
                self._on_started(self.host, self._ws_port)
            self._loop.run_forever()
        except Exception:
            logger.exception("Embedded server failed")
        finally:
            self._running = False
            if self._hub and self._loop:
                self._loop.run_until_complete(self._hub.stop())
            if self._on_stopped:
                self._on_stopped()
            if self._loop:
                self._loop.close()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="bbc-embedded-server")
        self._thread.start()

    def stop(self) -> None:
        if self._loop and self._running:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        self._running = False
