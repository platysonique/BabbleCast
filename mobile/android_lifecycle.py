"""Android activity lifecycle helpers for BabbleCast mobile."""

from __future__ import annotations


def android_activity_is_finishing() -> bool:
    """True when the Android activity is actually exiting (not just screen off)."""
    try:
        from kivy.utils import platform

        if platform != "android":
            return True
    except Exception:
        return True

    try:
        from jnius import autoclass

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        if activity is None:
            return True
        return bool(activity.isFinishing())
    except Exception:
        return True


def should_run_in_background(voice_session_active: bool) -> bool:
    """Keep the Kivy app unpauseable while BabbleCast voice is active."""
    return voice_session_active
