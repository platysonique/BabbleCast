"""Background route worker — all AudioManager JNI off the Kivy main thread."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

from babblecast.audio.android_engine import pause_speaker_writes, resume_speaker_writes
from babblecast.audio.android_routing import (
    AUDIO_ROUTE_BLUETOOTH,
    AndroidAudioRouter,
    _schedule_mic_restart,
    resolve_playback_route,
)

logger = logging.getLogger(__name__)

_ROUTE_SOURCE_UI = "ui"
_ROUTE_SOURCE_BT = "bt_watch"
_ROUTE_SOURCE_STARTUP = "startup"
_UI_PRIORITY_SEC = 0.5


@dataclass(frozen=True)
class RouteJob:
    user_route: str
    source: str = _ROUTE_SOURCE_UI
    mic_restart_cb: Callable[[], None] | None = None


class AndroidRouteWorker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._thread: threading.Thread | None = None
        self._running = False
        self._latest: RouteJob | None = None
        self._in_flight = False
        self._router: AndroidAudioRouter | None = None
        self._on_complete: Callable[[str, bool], None] | None = None
        self._last_ui_request_at = 0.0
        self._auto_switch_bt = False

    @property
    def route_changing(self) -> bool:
        with self._lock:
            return self._in_flight or self._latest is not None

    def start(
        self,
        router: AndroidAudioRouter,
        *,
        on_complete: Callable[[str, bool], None],
        auto_switch_bt: bool,
    ) -> None:
        with self._lock:
            if self._thread is not None:
                self._router = router
                self._on_complete = on_complete
                self._auto_switch_bt = auto_switch_bt
                return
            self._router = router
            self._on_complete = on_complete
            self._auto_switch_bt = auto_switch_bt
            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True, name="bbc-android-route")
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
            self._latest = None
            self._cond.notify_all()
            thread = self._thread
            self._thread = None
        if thread is not None:
            thread.join(timeout=2.0)

    def request_route(self, job: RouteJob) -> None:
        with self._lock:
            if not self._running or self._router is None:
                return
            if job.source == _ROUTE_SOURCE_UI:
                self._last_ui_request_at = time.monotonic()
            elif (
                job.source == _ROUTE_SOURCE_BT
                and (time.monotonic() - self._last_ui_request_at) < _UI_PRIORITY_SEC
            ):
                logger.info("Ignoring BT route job — recent UI selection wins")
                return
            self._latest = job
            self._cond.notify()

    def apply_now(self, job: RouteJob) -> bool:
        """Blocking apply for startup on bbc-android-audio thread only."""
        router = self._router
        if router is None:
            return False
        return self._apply_job(router, job)

    def _loop(self) -> None:
        while True:
            with self._lock:
                while self._running and self._latest is None:
                    self._cond.wait(timeout=0.25)
                if not self._running:
                    return
                job = self._latest
                self._latest = None
                self._in_flight = True
                router = self._router
                on_complete = self._on_complete
            if router is None or job is None:
                with self._lock:
                    self._in_flight = False
                continue
            ok = False
            try:
                ok = self._apply_job(router, job)
            except Exception:
                logger.exception("Route worker apply failed for %s", job.user_route)
            finally:
                with self._lock:
                    self._in_flight = False
                    if self._latest is not None:
                        self._cond.notify()
            if on_complete is not None:
                try:
                    on_complete(job.user_route, ok)
                except Exception:
                    logger.exception("Route on_complete callback failed")

    def _apply_job(self, router: AndroidAudioRouter, job: RouteJob) -> bool:
        bt_ok = router.bluetooth_available()
        effective = resolve_playback_route(
            job.user_route,
            bt_hfp_connected=bt_ok,
            auto_switch_bt=self._auto_switch_bt,
        )
        logger.info(
            "Android route worker applying %s → %s (source=%s, thread=%s)",
            job.user_route,
            effective,
            job.source,
            threading.current_thread().name,
        )
        mic_restart_cb = job.mic_restart_cb
        pause_speaker_writes()
        try:
            router.apply_resolved(
                effective,
                user_route=job.user_route,
                mic_restart_cb=None,
            )
            return True
        finally:
            resume_speaker_writes()
            if effective == AUDIO_ROUTE_BLUETOOTH and mic_restart_cb is not None:
                _schedule_mic_restart(mic_restart_cb)


_worker: AndroidRouteWorker | None = None


def get_route_worker() -> AndroidRouteWorker:
    global _worker
    if _worker is None:
        _worker = AndroidRouteWorker()
    return _worker
