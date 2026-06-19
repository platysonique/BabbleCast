from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

from babblecast.audio.android_route_worker import AndroidRouteWorker, RouteJob
from babblecast.audio.android_routing import (
    AUDIO_ROUTE_BLUETOOTH,
    AUDIO_ROUTE_EARPIECE,
    AUDIO_ROUTE_SPEAKER,
    resolve_playback_route,
)


def test_resolve_playback_route_auto_no_bt_defaults_speaker() -> None:
    assert resolve_playback_route("auto", bt_hfp_connected=False, auto_switch_bt=True) == AUDIO_ROUTE_SPEAKER


def test_resolve_playback_route_auto_with_bt_and_auto_switch() -> None:
    assert resolve_playback_route("auto", bt_hfp_connected=True, auto_switch_bt=True) == AUDIO_ROUTE_BLUETOOTH


def test_resolve_playback_route_bluetooth_without_hfp_falls_back() -> None:
    assert resolve_playback_route("bluetooth", bt_hfp_connected=False, auto_switch_bt=True) == AUDIO_ROUTE_SPEAKER


def test_worker_coalesces_to_latest_route() -> None:
    worker = AndroidRouteWorker()
    router = MagicMock()
    router.bluetooth_available.return_value = False
    done = threading.Event()

    def _complete(_route: str, _ok: bool) -> None:
        done.set()

    with patch("babblecast.audio.android_route_worker.pause_speaker_writes"), patch(
        "babblecast.audio.android_route_worker.resume_speaker_writes"
    ):
        worker.start(router, on_complete=_complete, auto_switch_bt=False)
        worker.request_route(RouteJob(AUDIO_ROUTE_EARPIECE))
        worker.request_route(RouteJob(AUDIO_ROUTE_SPEAKER))
        assert done.wait(timeout=2.0)
        worker.stop()

    assert router.apply_resolved.call_count == 1
    kwargs = router.apply_resolved.call_args.kwargs
    if kwargs:
        assert kwargs.get("user_route") == AUDIO_ROUTE_SPEAKER
    else:
        assert router.apply_resolved.call_args[0][0] == AUDIO_ROUTE_SPEAKER


def test_bt_job_ignored_after_recent_ui_selection() -> None:
    worker = AndroidRouteWorker()
    router = MagicMock()
    router.bluetooth_available.return_value = True
    done = threading.Event()

    def _complete(_route: str, _ok: bool) -> None:
        done.set()

    with patch("babblecast.audio.android_route_worker.pause_speaker_writes"), patch(
        "babblecast.audio.android_route_worker.resume_speaker_writes"
    ):
        worker.start(router, on_complete=_complete, auto_switch_bt=True)
        worker.request_route(RouteJob(AUDIO_ROUTE_EARPIECE, source="ui"))
        worker.request_route(RouteJob(AUDIO_ROUTE_BLUETOOTH, source="bt_watch"))
        assert done.wait(timeout=2.0)
        worker.stop()

    for call in router.apply_resolved.call_args_list:
        assert call.kwargs.get("user_route") != AUDIO_ROUTE_BLUETOOTH
