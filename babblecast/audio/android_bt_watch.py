"""Detect Bluetooth headset connect/disconnect while BabbleCast voice is active."""

from __future__ import annotations

import logging
import threading
from typing import Callable

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 0.75

_watch_lock = threading.Lock()
_watch_thread: threading.Thread | None = None
_watch_stop = threading.Event()
_broadcast_receiver = None
_callbacks: tuple[Callable[[], None], Callable[[], None]] | None = None
_on_availability_changed: Callable[[], None] | None = None
_last_connected = False
_auto_switch_on_connect = True


def _dispatch(callback: Callable[[], None]) -> None:
    try:
        from kivy.clock import Clock

        Clock.schedule_once(lambda _dt: callback(), 0)
    except Exception:
        try:
            callback()
        except Exception:
            logger.exception("Bluetooth route callback failed")


def _notify_if_changed() -> None:
    global _last_connected
    from babblecast.audio.android_routing import get_android_router

    connected = get_android_router().bluetooth_available()
    if connected == _last_connected:
        return
    _last_connected = connected
    if _on_availability_changed is not None:
        _dispatch(_on_availability_changed)
    if _callbacks is None:
        return
    if connected:
        if _auto_switch_on_connect:
            logger.info("Bluetooth headset connected — auto-switching audio route")
            _dispatch(_callbacks[0])
    else:
        if _auto_switch_on_connect:
            logger.info("Bluetooth headset disconnected — reverting audio route")
            _dispatch(_callbacks[1])


def _poll_loop() -> None:
    while not _watch_stop.wait(POLL_INTERVAL_SEC):
        try:
            _notify_if_changed()
        except Exception:
            logger.exception("Bluetooth watch poll failed")


def _register_broadcast() -> object | None:
    try:
        from jnius import PythonJavaClass, autoclass, java_method

        BluetoothProfile = autoclass("android.bluetooth.BluetoothProfile")
        connected_state = int(BluetoothProfile.STATE_CONNECTED)
        disconnected_state = int(BluetoothProfile.STATE_DISCONNECTED)

        class BtRouteReceiver(PythonJavaClass):
            __javainterfaces__ = ["android/content/BroadcastReceiver"]

            @java_method("(Landroid/content/Context;Landroid/content/Intent;)V")
            def onReceive(self, context, intent) -> None:
                try:
                    state = int(intent.getIntExtra(BluetoothProfile.EXTRA_STATE, -1))
                    if state == connected_state:
                        global _last_connected
                        was = _last_connected
                        _last_connected = True
                        if not was and _on_availability_changed is not None:
                            _dispatch(_on_availability_changed)
                        if not was and _callbacks and _auto_switch_on_connect:
                            logger.info("Bluetooth connect broadcast — auto-switching audio route")
                            _dispatch(_callbacks[0])
                    elif state == disconnected_state:
                        was = _last_connected
                        _last_connected = False
                        if was and _on_availability_changed is not None:
                            _dispatch(_on_availability_changed)
                        if was and _callbacks and _auto_switch_on_connect:
                            logger.info("Bluetooth disconnect broadcast — reverting audio route")
                            _dispatch(_callbacks[1])
                except Exception:
                    logger.debug("Bluetooth broadcast handling failed", exc_info=True)
                    _notify_if_changed()

        IntentFilter = autoclass("android.content.IntentFilter")
        BluetoothHeadset = autoclass("android.bluetooth.BluetoothHeadset")
        BluetoothAdapter = autoclass("android.bluetooth.BluetoothAdapter")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        if activity is None:
            return None

        filt = IntentFilter()
        filt.addAction(BluetoothAdapter.ACTION_CONNECTION_STATE_CHANGED)
        filt.addAction(BluetoothHeadset.ACTION_CONNECTION_STATE_CHANGED)
        filt.addAction("android.bluetooth.headset.profile.action.CONNECTION_STATE_CHANGED")

        receiver = BtRouteReceiver()
        activity.registerReceiver(receiver, filt)
        logger.info("Bluetooth route broadcast receiver registered")
        return receiver
    except Exception:
        logger.debug("Bluetooth broadcast receiver unavailable; poll-only watch", exc_info=True)
        return None


def _unregister_broadcast(receiver: object | None) -> None:
    if receiver is None:
        return
    try:
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        if activity is not None:
            activity.unregisterReceiver(receiver)
    except Exception:
        logger.debug("Bluetooth broadcast unregister failed", exc_info=True)


def start_bluetooth_watch(
    on_connected: Callable[[], None],
    on_disconnected: Callable[[], None],
    *,
    auto_switch_on_connect: bool = True,
    on_availability_changed: Callable[[], None] | None = None,
) -> None:
    """Begin watching for BT headset changes until ``stop_bluetooth_watch``."""
    global _watch_thread, _callbacks, _broadcast_receiver, _last_connected, _auto_switch_on_connect
    global _on_availability_changed
    with _watch_lock:
        stop_bluetooth_watch()
        _auto_switch_on_connect = auto_switch_on_connect
        _on_availability_changed = on_availability_changed
        _callbacks = (on_connected, on_disconnected)
        from babblecast.audio.android_routing import get_android_router

        _last_connected = get_android_router().bluetooth_available()
        if _on_availability_changed is not None:
            _dispatch(_on_availability_changed)
        if _last_connected and auto_switch_on_connect:
            _dispatch(on_connected)
        _watch_stop.clear()
        _watch_thread = threading.Thread(target=_poll_loop, daemon=True, name="bbc-bt-watch")
        _watch_thread.start()
        _broadcast_receiver = _register_broadcast()


def stop_bluetooth_watch() -> None:
    global _watch_thread, _callbacks, _broadcast_receiver, _last_connected, _on_availability_changed
    with _watch_lock:
        _watch_stop.set()
        thread = _watch_thread
        _watch_thread = None
        _callbacks = None
        _on_availability_changed = None
        receiver = _broadcast_receiver
        _broadcast_receiver = None
        _last_connected = False
    _unregister_broadcast(receiver)
    if thread is not None:
        thread.join(timeout=2.0)
