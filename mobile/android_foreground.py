"""Start/stop Android foreground service while BabbleCast voice is active."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_wake_lock = None
_service_started = False


def start_voice_foreground() -> None:
    global _wake_lock, _service_started
    if _service_started:
        return
    try:
        from kivy.utils import platform

        if platform != "android":
            return
    except Exception:
        return

    try:
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        Context = autoclass("android.content.Context")
        PowerManager = autoclass("android.os.PowerManager")
        pm = activity.getSystemService(Context.POWER_SERVICE)
        _wake_lock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "babblecast:voice")
        _wake_lock.setReferenceCounted(False)
        _wake_lock.acquire()

        ServiceVoice = autoclass("org.babblecast.babblecast.ServiceVoice")
        intent = ServiceVoice.getDefaultIntent(
            activity, "", "BabbleCast", "Voice active on set", ""
        )
        if hasattr(activity, "startForegroundService"):
            activity.startForegroundService(intent)
        else:
            activity.startService(intent)
        _service_started = True
        logger.info("Android voice foreground service started")
    except Exception:
        logger.exception("Failed to start Android voice foreground service")


def stop_voice_foreground() -> None:
    global _wake_lock, _service_started
    if not _service_started and _wake_lock is None:
        return
    try:
        from kivy.utils import platform

        if platform != "android":
            return
    except Exception:
        return

    try:
        from jnius import autoclass

        try:
            from mobile.voice_service import request_stop

            request_stop()
        except Exception:
            pass

        if _wake_lock is not None:
            try:
                if _wake_lock.isHeld():
                    _wake_lock.release()
            except Exception:
                pass
            _wake_lock = None

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        ServiceVoice = autoclass("org.babblecast.babblecast.ServiceVoice")
        ServiceVoice.stop(activity)
        _service_started = False
        logger.info("Android voice foreground service stopped")
    except Exception:
        logger.exception("Failed to stop Android voice foreground service")
