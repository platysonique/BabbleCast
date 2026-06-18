#!/usr/bin/env bash
# Connect-path smoke via intent extra (Kivy ignores adb input tap).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

ADB="${ADB:-adb}"
SERIAL="${ANDROID_SERIAL:-}"
ADB_FLAGS=()
if [[ -n "${SERIAL}" ]]; then
	ADB_FLAGS=(-s "${SERIAL}")
fi

SERVER_HOST="${BBC_SMOKE_SERVER:-192.168.1.141}"
SERVER_PORT="${BBC_SMOKE_PORT:-9513}"
SMOKE_TARGET="${SERVER_HOST}:${SERVER_PORT}"

APK="${ROOT}/packaging/android/releases/babblecast-1.0.0-arm64-v8a-debug.apk"
PKG="org.babblecast.babblecast"
ACTIVITY="org.kivy.android.PythonActivity"

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
"${ADB}" "${ADB_FLAGS[@]}" shell am force-stop "${PKG}" || true
"${ADB}" "${ADB_FLAGS[@]}" shell am start -n "${PKG}/${ACTIVITY}" -e bbc_smoke_connect "${SMOKE_TARGET}" >/dev/null
echo "Launched with smoke connect → ${SMOKE_TARGET}"
sleep 28

# Do NOT use tail — presence DEBUG floods logcat and pushes mic/audio lines out.
PYLOG="$("${ADB}" "${ADB_FLAGS[@]}" logcat -d | grep "I python" || true)"

if echo "${PYLOG}" | grep -qE "No constructor available|missing 1 required positional argument"; then
	echo "${PYLOG}" | grep -E "No constructor|missing 1 required|Traceback" | tail -20
	echo "CONNECT SMOKE FAILED: JNI/audio constructor crash" >&2
	exit 1
fi
if echo "${PYLOG}" | grep -q "Bridge audio startup failed"; then
	echo "${PYLOG}" | grep -E "Bridge audio|No constructor|Traceback" | tail -20
	echo "CONNECT SMOKE FAILED: bridge audio startup failed" >&2
	exit 1
fi
if echo "${PYLOG}" | grep -q "babblecast/.*Traceback"; then
	echo "${PYLOG}" | grep -E "babblecast/|Traceback|JavaException" | tail -20
	echo "CONNECT SMOKE FAILED: BabbleCast Python crash" >&2
	exit 1
fi
if echo "${PYLOG}" | grep -q "Android mic capture started"; then
	echo "CONNECT SMOKE OK: mic capture started"
	echo "${PYLOG}" | grep -iE "Smoke connect|bridge.connect|mic capture|speaker output|audio ready" | head -10
	exit 0
fi
if echo "${PYLOG}" | grep -q "Android audio ready"; then
	echo "CONNECT SMOKE OK: bridge reported audio ready"
	exit 0
fi
if echo "${PYLOG}" | grep -q "Audio unavailable"; then
	echo "CONNECT SMOKE OK: graceful chat-only (audio unavailable message)"
	exit 0
fi
if echo "${PYLOG}" | grep -qE "Smoke connect intent|bridge.connect"; then
	echo "${PYLOG}" | grep -iE "Smoke connect|Starting Android|Bridge audio|Android mic|Android speaker|audio ready|Traceback" | tail -25
	echo "CONNECT SMOKE FAILED: connect ran but audio never started" >&2
	exit 1
fi

echo "${PYLOG}" | grep -iE "Smoke|python" | tail -25
echo "CONNECT SMOKE FAILED: smoke intent did not run" >&2
exit 1
