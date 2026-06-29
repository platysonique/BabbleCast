"""Android async audio honesty and permission gates."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_permissions_record_audio_fail_closed_on_exception() -> None:
    text = Path(__file__).resolve().parents[1].joinpath("mobile/permissions.py").read_text(
        encoding="utf-8"
    )
    assert "RECORD_AUDIO permission check failed" in text
    assert "return False" in text.split("record_audio_granted")[1].split("def request_android_permissions")[0]


def test_bridge_android_ensure_audio_not_ready_while_starting() -> None:
    from babblecast.client import bridge as bridge_mod

    text = Path(bridge_mod.__file__).read_text(encoding="utf-8")
    assert "return False" in text.split("if platform_name() == \"android\":")[1].split("return self._ensure_audio_sync()")[0]
    assert "audio_ready" in text
    assert "on_audio_ready" in text


def test_bt_watch_supports_auto_switch_flag() -> None:
    text = Path(__file__).resolve().parents[1].joinpath(
        "babblecast/audio/android_bt_watch.py"
    ).read_text(encoding="utf-8")
    assert "auto_switch_on_connect" in text
    assert "a2dp.profile.action.CONNECTION_STATE_CHANGED" not in text


@pytest.mark.parametrize(
    "started,starting,shutting,expected",
    [
        (True, False, False, True),
        (False, True, False, False),
        (False, False, True, False),
    ],
)
def test_ensure_audio_android_returns_started_only_when_ready(
    started: bool, starting: bool, shutting: bool, expected: bool
) -> None:
    from babblecast.client import bridge as bridge_mod
    from babblecast.client.bridge import BridgeManager

    mgr = BridgeManager()
    mgr._audio_started = started
    mgr._audio_starting = starting
    mgr._shutting_down = shutting

    with patch.object(bridge_mod, "platform_name", return_value="android"):
        with patch.object(mgr, "_start_android_audio_async") as mock_async:
            result = mgr._ensure_audio()
            assert result is expected
            if not started and not starting and not shutting:
                mock_async.assert_called_once()


def test_defer_main_thread_calls_zero_arg_callback() -> None:
    from babblecast.client import bridge as bridge_mod

    called: list[str] = []

    def _fn() -> None:
        called.append("ok")

    fake_clock = MagicMock()
    fake_clock.schedule_once.side_effect = lambda cb, _delay: cb(0.0)
    with patch.object(bridge_mod, "Clock", fake_clock, create=True):
        with patch.dict("sys.modules", {"kivy.clock": MagicMock(Clock=fake_clock)}):
            bridge_mod._defer_main_thread(0, _fn)
    assert called == ["ok"]
