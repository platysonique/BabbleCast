#!/usr/bin/env bash
# Run after every BabbleCast fix — desktop + phone smoke. Exit non-zero on failure.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

ADB="${ADB:-adb}"
SERIAL="${ANDROID_SERIAL:-}"
ADB_FLAGS=()
if [[ -n "${SERIAL}" ]]; then
	ADB_FLAGS=(-s "${SERIAL}")
fi

echo "== BabbleCast verify =="

echo "1/3 Linux smoke (pytest + bbc server + Qt import) …"
python scripts/linux_smoke_check.py

echo "2/3 bbc --update …"
if [[ -d "${ROOT}/.git" ]]; then
	"${ROOT}/.venv/bin/bbc" --update
else
	echo "   skip: not a git checkout"
fi

	echo "3/3 Android launch + connect smoke …"
APK="${ROOT}/packaging/android/releases/babblecast-1.0.0-arm64-v8a-debug.apk"
if ! command -v "${ADB}" &>/dev/null; then
	echo "   skip: adb not found"
elif ! "${ADB}" "${ADB_FLAGS[@]}" get-state &>/dev/null; then
	echo "   skip: no Android device"
elif [[ ! -f "${APK}" ]]; then
	echo "   skip: APK missing (${APK})"
else
	"${ADB}" "${ADB_FLAGS[@]}" install -r "${APK}" >/dev/null
	"${ADB}" "${ADB_FLAGS[@]}" logcat -c
	"${ADB}" "${ADB_FLAGS[@]}" shell am force-stop org.babblecast.babblecast || true
	"${ADB}" "${ADB_FLAGS[@]}" shell monkey -p org.babblecast.babblecast -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
	sleep 5
	# Tap first server card then Connect (Connect tab is default).
	W="${ADB}" "${ADB_FLAGS[@]}" shell wm size 2>/dev/null | awk -F'[: x]+' '/Physical size/{print $3; exit}'
	H=$("${ADB}" "${ADB_FLAGS[@]}" shell wm size 2>/dev/null | awk -F'[: x]+' '/Physical size/{print $4; exit}')
	if [[ -n "${W}" && -n "${H}" ]]; then
		"${ADB}" "${ADB_FLAGS[@]}" shell input tap "$((W / 2))" "$((H * 45 / 100))" 2>/dev/null || true
		sleep 1
		"${ADB}" "${ADB_FLAGS[@]}" shell input tap "$((W / 2))" "$((H * 72 / 100))" 2>/dev/null || true
		sleep 8
	fi
	LOG="$("${ADB}" "${ADB_FLAGS[@]}" logcat -d -t 600)"
	if echo "${LOG}" | grep -qE "python.*Traceback|python.*NameError|python.*ModuleNotFoundError|No constructor available|missing 1 required positional argument"; then
		echo "${LOG}" | grep -E "python.*(Traceback|NameError|ModuleNotFoundError|No constructor|missing 1 required|ERROR)" | tail -25
		echo "Android verify FAILED: crash on connect or audio startup" >&2
		exit 1
	fi
	if echo "${LOG}" | grep -q "Bridge audio startup failed"; then
		echo "${LOG}" | grep -E "Bridge audio|No constructor|Traceback" | tail -15
		echo "Android verify FAILED: bridge audio startup failed" >&2
		exit 1
	fi
	if ! echo "${LOG}" | grep -q "python"; then
		echo "Android verify FAILED: no python log output (app may not have started)" >&2
		exit 1
	fi
	echo "   Android app launched (no Python traceback in logcat)"
fi

echo "ALL VERIFY CHECKS PASSED"
