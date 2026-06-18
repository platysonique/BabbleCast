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

echo "3/3 Android launch smoke …"
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
	sleep 8
	LOG="$("${ADB}" "${ADB_FLAGS[@]}" logcat -d -t 400)"
	if echo "${LOG}" | grep -qE "python.*Traceback|python.*NameError|python.*ModuleNotFoundError"; then
		echo "${LOG}" | grep -E "python.*(Traceback|NameError|ModuleNotFoundError|ERROR)" | tail -20
		echo "Android verify FAILED: Python crash in logcat" >&2
		exit 1
	fi
	if ! echo "${LOG}" | grep -q "python"; then
		echo "Android verify FAILED: no python log output (app may not have started)" >&2
		exit 1
	fi
	echo "   Android app launched (no Python traceback in logcat)"
fi

echo "ALL VERIFY CHECKS PASSED"
