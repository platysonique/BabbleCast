#!/usr/bin/env bash
# Connect-path smoke: install APK, tap Connect, require audio startup markers in logcat.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

ADB="${ADB:-adb}"
SERIAL="${ANDROID_SERIAL:-}"
ADB_FLAGS=()
if [[ -n "${SERIAL}" ]]; then
	ADB_FLAGS=(-s "${SERIAL}")
fi

APK="${ROOT}/packaging/android/releases/babblecast-1.0.0-arm64-v8a-debug.apk"
if [[ ! -f "${APK}" ]]; then
	echo "APK missing: ${APK}" >&2
	exit 1
fi
if ! command -v "${ADB}" &>/dev/null; then
	echo "adb not found" >&2
	exit 1
fi
if ! "${ADB}" "${ADB_FLAGS[@]}" get-state &>/dev/null; then
	echo "No Android device connected" >&2
	exit 1
fi

"${ADB}" "${ADB_FLAGS[@]}" install -r "${APK}" >/dev/null
"${ADB}" "${ADB_FLAGS[@]}" logcat -c
"${ADB}" "${ADB_FLAGS[@]}" shell am force-stop org.babblecast.babblecast || true
"${ADB}" "${ADB_FLAGS[@]}" shell monkey -p org.babblecast.babblecast -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
sleep 5

W=$("${ADB}" "${ADB_FLAGS[@]}" shell wm size 2>/dev/null | awk -F'[: x]+' '/Physical size/{print $3; exit}')
H=$("${ADB}" "${ADB_FLAGS[@]}" shell wm size 2>/dev/null | awk -F'[: x]+' '/Physical size/{print $4; exit}')
if [[ -z "${W}" || -z "${H}" ]]; then
	echo "Could not read screen size" >&2
	exit 1
fi

# First server card, then Connect button (Connect tab default).
"${ADB}" "${ADB_FLAGS[@]}" shell input tap "$((W / 2))" "$((H * 45 / 100))"
sleep 1
"${ADB}" "${ADB_FLAGS[@]}" shell input tap "$((W / 2))" "$((H * 72 / 100))"
sleep 10

LOG="$("${ADB}" "${ADB_FLAGS[@]}" logcat -d -t 800)"
if echo "${LOG}" | grep -qE "python.*Traceback|No constructor available|missing 1 required positional argument|NameError"; then
	echo "${LOG}" | grep -E "python.*(Traceback|No constructor|missing 1 required|NameError)" | tail -30
	echo "CONNECT SMOKE FAILED: Python crash" >&2
	exit 1
fi
if echo "${LOG}" | grep -q "Android mic capture started"; then
	echo "CONNECT SMOKE OK: mic capture started"
elif echo "${LOG}" | grep -q "Audio unavailable"; then
	echo "CONNECT SMOKE OK: graceful chat-only (audio unavailable message)"
else
	echo "${LOG}" | grep -E "Starting Android audio|Bridge audio|Android speaker|python" | tail -25
	echo "CONNECT SMOKE FAILED: no mic capture or graceful audio failure" >&2
	exit 1
fi
