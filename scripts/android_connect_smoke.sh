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
sleep 12

# 1080x2340 Samsung: discovered server card ~540,720; credentials dialog accepts via Enter.
"${ADB}" "${ADB_FLAGS[@]}" shell input tap 540 720
sleep 2
"${ADB}" "${ADB_FLAGS[@]}" shell input keyevent 66
sleep 18

LOG="$("${ADB}" "${ADB_FLAGS[@]}" logcat -d -t 1200)"
if echo "${LOG}" | grep -qE "python.*Traceback|No constructor available|missing 1 required positional argument|NameError"; then
	echo "${LOG}" | grep -E "python.*(Traceback|No constructor|missing 1 required|NameError)" | tail -30
	echo "CONNECT SMOKE FAILED: Python crash" >&2
	exit 1
fi
if echo "${LOG}" | grep -q "Android mic capture started"; then
	echo "CONNECT SMOKE OK: mic capture started"
elif echo "${LOG}" | grep -q "Android audio ready"; then
	echo "CONNECT SMOKE OK: bridge reported audio ready"
elif echo "${LOG}" | grep -q "Audio unavailable"; then
	echo "CONNECT SMOKE OK: graceful chat-only (audio unavailable message)"
else
	echo "${LOG}" | grep -E "Bridge audio|Starting Android|Android speaker|connect_selected|python" | tail -30
	echo "CONNECT SMOKE FAILED: no mic capture or graceful audio failure" >&2
	exit 1
fi
