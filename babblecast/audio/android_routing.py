"""Android audio route hot-swap (speaker / earpiece / Bluetooth headset)."""

from __future__ import annotations

import logging
import threading
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


def _jni():
    from jnius import autoclass

    return autoclass


class AndroidAudioRouter:
    """Apply VoIP routing via AudioManager without tearing down AudioTrack."""

    def __init__(self) -> None:
        self._route = AUDIO_ROUTE_SPEAKER
        self._am = None
        self._sco_active = False
        self._lock = threading.Lock()

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
            AudioManager = autoclass("android.media.AudioManager")
            activity = PythonActivity.mActivity
            if activity is None:
                return None
            self._am = activity.getSystemService(Context.AUDIO_SERVICE)
            return self._am
        except Exception:
            logger.exception("Failed to get Android AudioManager")
            return None

    def bluetooth_available(self) -> bool:
        """True when an HFP/SCO headset is connected — not A2DP-only (media) devices."""
        am = self._get_manager()
        if am is None:
            return False
        try:
            if bool(am.isBluetoothScoOn()):
                return True
        except Exception:
            pass
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
        """Return (route_id, label, enabled) for UI."""
        bt_ok = self.bluetooth_available()
        return [
            (AUDIO_ROUTE_AUTO, _ROUTE_LABELS[AUDIO_ROUTE_AUTO], True),
            (AUDIO_ROUTE_SPEAKER, _ROUTE_LABELS[AUDIO_ROUTE_SPEAKER], True),
            (AUDIO_ROUTE_EARPIECE, _ROUTE_LABELS[AUDIO_ROUTE_EARPIECE], True),
            (AUDIO_ROUTE_BLUETOOTH, _ROUTE_LABELS[AUDIO_ROUTE_BLUETOOTH], bt_ok),
        ]

    def _stop_sco(self, am) -> None:
        if not self._sco_active:
            return
        try:
            am.setBluetoothScoOn(False)
            am.stopBluetoothSco()
        except Exception:
            logger.debug("Bluetooth SCO stop failed", exc_info=True)
        self._sco_active = False

    def _apply_communication_device(self, am, route: str) -> bool:
        """Android 12+ VoIP routing via setCommunicationDevice (Samsung 14/15 reliable path)."""
        try:
            autoclass = _jni()
            Version = autoclass("android.os.Build$VERSION")
            if int(Version.SDK_INT) < 31:
                return False
            AudioDeviceInfo = autoclass("android.media.AudioDeviceInfo")
            if route == AUDIO_ROUTE_AUTO:
                am.clearCommunicationDevice()
                return True
            preferred_types: list[int] = []
            if route == AUDIO_ROUTE_SPEAKER:
                preferred_types = [int(AudioDeviceInfo.TYPE_BUILTIN_SPEAKER)]
            elif route == AUDIO_ROUTE_EARPIECE:
                preferred_types = [int(AudioDeviceInfo.TYPE_BUILTIN_EARPIECE)]
            elif route == AUDIO_ROUTE_BLUETOOTH:
                preferred_types = [
                    int(AudioDeviceInfo.TYPE_BLUETOOTH_SCO),
                    int(getattr(AudioDeviceInfo, "TYPE_BLE_HEADSET", 26)),
                ]
            devices = am.getAvailableCommunicationDevices()
            if not devices:
                return False
            for dtype in preferred_types:
                for device in devices:
                    if int(device.getType()) == dtype and bool(am.setCommunicationDevice(device)):
                        logger.info("Android communication device set (type=%s route=%s)", dtype, route)
                        return True
            return False
        except Exception:
            logger.debug("setCommunicationDevice unavailable; using legacy routing", exc_info=True)
            return False

    def apply(
        self,
        route: str,
        *,
        mic_restart_cb: Callable[[], None] | None = None,
    ) -> str:
        """Switch output/input route while a session is active."""
        route = normalize_audio_route(route)
        with self._lock:
            self._route = route
            am = self._get_manager()
            if am is None:
                return route
            try:
                AudioManager = _jni()("android.media.AudioManager")
                am.setMode(AudioManager.MODE_IN_COMMUNICATION)
                used_modern = self._apply_communication_device(am, route)
                if route == AUDIO_ROUTE_SPEAKER:
                    self._stop_sco(am)
                    if not used_modern:
                        am.setSpeakerphoneOn(True)
                elif route == AUDIO_ROUTE_EARPIECE:
                    self._stop_sco(am)
                    if not used_modern:
                        am.setSpeakerphoneOn(False)
                elif route == AUDIO_ROUTE_BLUETOOTH:
                    if not used_modern:
                        am.setSpeakerphoneOn(False)
                        am.startBluetoothSco()
                        am.setBluetoothScoOn(True)
                        self._sco_active = True
                else:  # auto — wired/BT/system default without forcing speaker
                    self._stop_sco(am)
                    if not used_modern:
                        am.setSpeakerphoneOn(False)
                logger.info("Android audio route → %s (modern=%s)", route, used_modern)
            except Exception:
                logger.exception("Failed to apply Android audio route %s", route)
                return route

        if route == AUDIO_ROUTE_BLUETOOTH and mic_restart_cb is not None:
            # SCO connects asynchronously; restart mic so BT headset input is picked up.
            for delay in (0.35, 0.9, 1.8):
                threading.Timer(delay, mic_restart_cb).start()
        return route

    def shutdown(self) -> None:
        with self._lock:
            am = self._am
            if am is None:
                return
            try:
                self._stop_sco(am)
                try:
                    autoclass = _jni()
                    Version = autoclass("android.os.Build$VERSION")
                    if int(Version.SDK_INT) >= 31:
                        am.clearCommunicationDevice()
                except Exception:
                    logger.debug("clearCommunicationDevice failed", exc_info=True)
                am.setSpeakerphoneOn(False)
                AudioManager = _jni()("android.media.AudioManager")
                am.setMode(AudioManager.MODE_NORMAL)
            except Exception:
                logger.debug("Audio route shutdown failed", exc_info=True)
            self._am = None
            self._route = AUDIO_ROUTE_SPEAKER


_router: AndroidAudioRouter | None = None


def get_android_router() -> AndroidAudioRouter:
    global _router
    if _router is None:
        _router = AndroidAudioRouter()
    return _router
