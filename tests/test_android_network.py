"""Tests for Android multicast lock helper."""

from __future__ import annotations

import mobile.android_network as net


class _FakeLock:
    def __init__(self, *, held: bool = True, alive: bool = True) -> None:
        self._held = held
        self._alive = alive
        self.release_calls = 0

    def isHeld(self) -> bool:
        if not self._alive:
            raise RuntimeError("binder died")
        return self._held

    def release(self) -> None:
        self.release_calls += 1
        self._held = False


def test_lock_held_false_when_missing() -> None:
    net._multicast_lock = None
    assert net._lock_held() is False


def test_lock_held_false_when_binder_dead() -> None:
    net._multicast_lock = _FakeLock(held=True, alive=False)
    assert net._lock_held() is False


def test_release_lock_quietly_clears_reference() -> None:
    lock = _FakeLock(held=True)
    net._multicast_lock = lock
    net._release_lock_quietly()
    assert net._multicast_lock is None
    assert lock.release_calls == 1


def test_discovery_bump_emits_current_servers() -> None:
    from babblecast.discovery import DiscoveredServer, ServerDiscovery

    seen: list[int] = []

    def on_update(servers) -> None:
        seen.append(len(servers))

    discovery = ServerDiscovery(on_update=on_update)
    discovery._servers["x"] = DiscoveredServer(
        service_name="x",
        name="Test",
        host="192.168.1.10",
        ws_port=9513,
        udp_port=9514,
        properties={},
        seen_at=1.0,
    )
    discovery.bump()
    assert seen == [1]
