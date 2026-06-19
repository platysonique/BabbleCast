"""Android audio route hot-swap (speaker / earpiece / Bluetooth headset)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)

AUDIO_ROUTE_AUTO = "auto"
AUDIO_ROUTE_SPEAKER = "speaker"
AUDIO_ROUTE_EARPIECE = "earpiece"
AUDIO_ROUTE_BLUETOOTH = "bluetooth"

AUDIO_ROUTES = (
    AUDIO_ROUTE_AUTO,
    AUDIO_ROUTE_SPEAKER,
    AUDIO_ROUTE_EARPIECE,
    AUDIO_ROUTE_BLUETOOTH,
)

_ROUTE_LABELS = {
    AUDIO_ROUTE_AUTO: "Auto",
    AUDIO_ROUTE_SPEAKER: "Speaker",
    AUDIO_ROUTE_EARPIECE: "Earpiece",
    AUDIO_ROUTE_BLUETOOTH: "Bluetooth",
}


def normalize_audio_route(route: str | None) -> str:
    if route in AUDIO_ROUTES:
        return route
    return AUDIO_ROUTE_SPEAKER


def resolve_playback_route(
    user_route: str,
    *,
    bt_hfp_connected: bool,
    auto_switch_bt: bool,
) -> str:
    route = normalize_audio_route(user_route)
    if route == AUDIO_ROUTE_AUTO:
        if bt_hfp_connected and auto_switch_bt:
            return AUDIO_ROUTE_BLUETOOTH
        return AUDIO_ROUTE_SPEAKER
    if route == AUDIO_ROUTE_BLUETOOTH and not bt_hfp_connected:
        logger.warning("Bluetooth route requested but no HFP headset — using speaker")
        return AUDIO_ROUTE_SPEAKER
    return route


def _jni():
    from jnius import autoclass

    return autoclass


_BLUETOOTH_AUDIO_TYPE_NAMES = (
    "TYPE_BLUETOOTH_SCO",
    "TYPE_BLUETOOTH_A2DP",
    "TYPE_BLE_HEADSET",
    "TYPE_BLE_SPEAKER",
    "TYPE_HEARING_AID",
)


def bluetooth_audio_type_ids() -> frozenset[int]:
    """AudioDeviceInfo type constants for Bluetooth-class outputs/inputs."""
    try:
        AudioDeviceInfo = _jni()("android.media.AudioDeviceInfo")
    except Exception:
        return frozenset()
    ids: set[int] = set()
    for name in _BLUETOOTH_AUDIO_TYPE_NAMES:
        value = getattr(AudioDeviceInfo, name, None)
        if value is not None:
            ids.add(int(value))
    return frozenset(ids)


def device_types_include_bluetooth(device_types: set[int] | list[int]) -> bool:
    bt_ids = bluetooth_audio_type_ids()
    if not bt_ids:
        return False
    return bool(bt_ids & set(device_types))


class AndroidAudioRouter:
    """Apply VoIP routing via AudioManager without tearing down AudioTrack."""

    def __init__(self) -> None:
        self._route = AUDIO_ROUTE_SPEAKER
        self._am = None
        self._sco_active = False
        self._lock = threading.Lock()
        self._device_callback = None
        self._device_callback_event: threading.Event | None = None
        self._session_mode_active = False

    @property
    def route(self) -> str:
        return self._route

    def _get_manager(self):
        if self._am is not None:
            return self._am
        try:
            autoclass = _jni()
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Context = autoclass("android.content.Context")
            activity = PythonActivity.mActivity
            if activity is None:
                return None
            self._am = activity.getSystemService(Context.AUDIO_SERVICE)
            return self._am
        except Exception:
            logger.exception("Failed to get Android AudioManager")
            return None

    def _connected_audio_device_types(self, am) -> set[int]:
        types: set[int] = set()
        try:
            autoclass = _jni()
            AudioManager = autoclass("android.media.AudioManager")
            for flag_name in ("GET_DEVICES_OUTPUTS", "GET_DEVICES_INPUTS"):
                flag = getattr(AudioManager, flag_name, None)
                if flag is None:
                    continue
                devices = am.getDevices(int(flag))
                if not devices:
                    continue
                for device in devices:
                    types.add(int(device.getType()))
        except Exception:
            logger.debug("AudioManager.getDevices failed", exc_info=True)
        return types

    def bluetooth_available(self) -> bool:
        am = self._get_manager()
        if am is None:
            return False
        try:
            if bool(am.isBluetoothScoOn()):
                return True
        except Exception:
            pass
        try:
            if bool(am.isBluetoothA2dpOn()):
                return True
        except Exception:
            pass
        if device_types_include_bluetooth(self._connected_audio_device_types(am)):
            return True
        try:
            autoclass = _jni()
            BluetoothAdapter = autoclass("android.bluetooth.BluetoothAdapter")
            BluetoothProfile = autoclass("android.bluetooth.BluetoothProfile")
            adapter = BluetoothAdapter.getDefaultAdapter()
            if adapter is None or not adapter.isEnabled():
                return False
            connected = int(BluetoothProfile.STATE_CONNECTED)
            return int(adapter.getProfileConnectionState(BluetoothProfile.HEADSET)) == connected
        except Exception:
            logger.debug("Bluetooth HFP connection check failed", exc_info=True)
            return False

    def list_routes(self) -> list[tuple[str, str, bool]]:
        bt_ok = self.bluetooth_available()
        return [
            (AUDIO_ROUTE_AUTO, _ROUTE_LABELS[AUDIO_ROUTE_AUTO], True),
            (AUDIO_ROUTE_SPEAKER, _ROUTE_LABELS[AUDIO_ROUTE_SPEAKER], True),
            (AUDIO_ROUTE_EARPIECE, _ROUTE_LABELS[AUDIO_ROUTE_EARPIECE], True),
            (AUDIO_ROUTE_BLUETOOTH, _ROUTE_LABELS[AUDIO_ROUTE_BLUETOOTH], bt_ok),
        ]

    def session_begin(self) -> None:
        am = self._get_manager()
        if am is None or self._session_mode_active:
            return
        try:
            AudioManager = _jni()("android.media.AudioManager")
            am.setMode(AudioManager.MODE_IN_COMMUNICATION)
            self._session_mode_active = True
            self._register_device_callback(am)
        except Exception:
            logger.exception("Android audio session_begin failed")

    def _stop_sco(self, am) -> None:
        if not self._sco_active:
            return
        try:
            am.setBluetoothScoOn(False)
            am.stopBluetoothSco()
        except Exception:
            logger.debug("Bluetooth SCO stop failed", exc_info=True)
        self._sco_active = False

    def _apply_communication_device(self, am, effective_route: str) -> bool:
        try:
            autoclass = _jni()
            Version = autoclass("android.os.Build$VERSION")
            if int(Version.SDK_INT) < 31:
                return False
            AudioDeviceInfo = autoclass("android.media.AudioDeviceInfo")
            preferred_types: list[int] = []
            if effective_route == AUDIO_ROUTE_SPEAKER:
                preferred_types = [int(AudioDeviceInfo.TYPE_BUILTIN_SPEAKER)]
            elif effective_route == AUDIO_ROUTE_EARPIECE:
                preferred_types = [int(AudioDeviceInfo.TYPE_BUILTIN_EARPIECE)]
            elif effective_route == AUDIO_ROUTE_BLUETOOTH:
                preferred_types = [int(AudioDeviceInfo.TYPE_BLUETOOTH_SCO)]
                ble = getattr(AudioDeviceInfo, "TYPE_BLE_HEADSET", None)
                if ble is not None:
                    preferred_types.append(int(ble))
            devices = am.getAvailableCommunicationDevices()
            if not devices:
                return False
            for dtype in preferred_types:
                for device in devices:
                    if int(device.getType()) == dtype and bool(am.setCommunicationDevice(device)):
                        logger.info(
                            "Android communication device set (type=%s route=%s)",
                            dtype,
                            effective_route,
                        )
                        return True
            return False
        except Exception:
            logger.debug("setCommunicationDevice unavailable; using legacy routing", exc_info=True)
            return False

    def _expected_device_types(self, effective_route: str) -> list[int]:
        autoclass = _jni()
        AudioDeviceInfo = autoclass("android.media.AudioDeviceInfo")
        if effective_route == AUDIO_ROUTE_SPEAKER:
            return [int(AudioDeviceInfo.TYPE_BUILTIN_SPEAKER)]
        if effective_route == AUDIO_ROUTE_EARPIECE:
            return [int(AudioDeviceInfo.TYPE_BUILTIN_EARPIECE)]
        if effective_route == AUDIO_ROUTE_BLUETOOTH:
            types = [int(AudioDeviceInfo.TYPE_BLUETOOTH_SCO)]
            ble = getattr(AudioDeviceInfo, "TYPE_BLE_HEADSET", None)
            if ble is not None:
                types.append(int(ble))
            return types
        return []

    def _wait_communication_device(self, am, effective_route: str, *, timeout_sec: float) -> bool:
        expected_types = self._expected_device_types(effective_route)
        if not expected_types:
            return True
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if self._device_callback_event is not None:
                self._device_callback_event.wait(timeout=0.05)
                self._device_callback_event.clear()
            try:
                current = am.getCommunicationDevice()
            except Exception:
                current = None
            if current is not None and int(current.getType()) in expected_types:
                return True
            time.sleep(0.05)
        logger.warning(
            "Communication device not confirmed for %s within %.1fs",
            effective_route,
            timeout_sec,
        )
        return False

    def apply_resolved(
        self,
        effective_route: str,
        *,
        user_route: str | None = None,
        mic_restart_cb: Callable[[], None] | None = None,
    ) -> str:
        effective_route = normalize_audio_route(effective_route)
        if effective_route == AUDIO_ROUTE_AUTO:
            effective_route = AUDIO_ROUTE_SPEAKER
        label = user_route or effective_route
        with self._lock:
            self._route = label
            am = self._get_manager()
            if am is None:
                return label
            try:
                used_modern = self._apply_communication_device(am, effective_route)
                if effective_route == AUDIO_ROUTE_SPEAKER:
                    self._stop_sco(am)
                    if not used_modern:
                        am.setSpeakerphoneOn(True)
                elif effective_route == AUDIO_ROUTE_EARPIECE:
                    self._stop_sco(am)
                    if not used_modern:
                        am.setSpeakerphoneOn(False)
                elif effective_route == AUDIO_ROUTE_BLUETOOTH:
                    if not used_modern:
                        am.setSpeakerphoneOn(False)
                        am.startBluetoothSco()
                        am.setBluetoothScoOn(True)
                        self._sco_active = True
                if used_modern:
                    self._wait_communication_device(am, effective_route, timeout_sec=3.0)
                logger.info(
                    "Android audio route → %s effective=%s (modern=%s, thread=%s)",
                    label,
                    effective_route,
                    used_modern,
                    threading.current_thread().name,
                )
            except Exception:
                logger.exception("Failed to apply Android audio route %s", effective_route)
                return label
        if effective_route == AUDIO_ROUTE_BLUETOOTH and mic_restart_cb is not None:
            _schedule_mic_restart(mic_restart_cb)
        return label

    def apply(
        self,
        route: str,
        *,
        mic_restart_cb: Callable[[], None] | None = None,
    ) -> str:
        resolved = resolve_playback_route(
            route,
            bt_hfp_connected=self.bluetooth_available(),
            auto_switch_bt=route in (AUDIO_ROUTE_AUTO, AUDIO_ROUTE_BLUETOOTH),
        )
        return self.apply_resolved(resolved, user_route=route, mic_restart_cb=mic_restart_cb)

    def _register_device_callback(self, am) -> None:
        if self._device_callback is not None:
            return
        try:
            from jnius import PythonJavaClass, java_method

            router = self

            class _RouteDeviceCallback(PythonJavaClass):
                __javainterfaces__ = ["android/media/AudioDeviceCallback"]

                @java_method("([Landroid/media/AudioDeviceInfo;)V")
                def onAudioDevicesAdded(self, devices) -> None:
                    router._signal_device_change()

                @java_method("([Landroid/media/AudioDeviceInfo;)V")
                def onAudioDevicesRemoved(self, devices) -> None:
                    router._signal_device_change()

            self._device_callback = _RouteDeviceCallback()
            self._device_callback_event = threading.Event()
            am.registerAudioDeviceCallback(self._device_callback, None)
        except Exception:
            logger.debug("AudioDeviceCallback registration failed", exc_info=True)
            self._device_callback = None
            self._device_callback_event = None

    def _signal_device_change(self) -> None:
        if self._device_callback_event is not None:
            self._device_callback_event.set()

    def _unregister_device_callback(self, am) -> None:
        cb = self._device_callback
        self._device_callback = None
        self._device_callback_event = None
        if cb is None:
            return
        try:
            am.unregisterAudioDeviceCallback(cb)
        except Exception:
            logger.debug("AudioDeviceCallback unregister failed", exc_info=True)

    def shutdown(self) -> None:
        with self._lock:
            am = self._am
            if am is None:
                return
            try:
                AudioManager = _jni()("android.media.AudioManager")
                self._unregister_device_callback(am)
                self._stop_sco(am)
                try:
                    Version = _jni()("android.os.Build$VERSION")
                    if int(Version.SDK_INT) >= 31:
                        am.clearCommunicationDevice()
                except Exception:
                    logger.debug("clearCommunicationDevice failed", exc_info=True)
                am.setSpeakerphoneOn(False)
                if self._session_mode_active:
                    am.setMode(AudioManager.MODE_NORMAL)
            except Exception:
                logger.debug("Audio route shutdown failed", exc_info=True)
            finally:
                self._session_mode_active = False
                self._am = None
                self._route = AUDIO_ROUTE_SPEAKER


_router: AndroidAudioRouter | None = None
_mic_restart_timer: threading.Timer | None = None


def _schedule_mic_restart(mic_restart_cb: Callable[[], None]) -> None:
    global _mic_restart_timer
    if _mic_restart_timer is not None:
        _mic_restart_timer.cancel()
        _mic_restart_timer = None

    def _fire() -> None:
        global _mic_restart_timer
        _mic_restart_timer = None
        try:
            mic_restart_cb()
        except Exception:
            logger.exception("Mic restart after BT route failed")

    _mic_restart_timer = threading.Timer(0.9, _fire)
    _mic_restart_timer.daemon = True
    _mic_restart_timer.start()


def get_android_router() -> AndroidAudioRouter:
    global _router
    if _router is None:
        _router = AndroidAudioRouter()
    return _router
