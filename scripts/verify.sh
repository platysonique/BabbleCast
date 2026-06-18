#!/usr/bin/env bash
# Run after every BabbleCast fix — desktop + phone smoke. Exit non-zero on failure.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

PYTHON="${ROOT}/.venv/bin/python"
BBC="${ROOT}/.venv/bin/bbc"
if [[ ! -x "${PYTHON}" ]]; then
	PYTHON="python3"
fi
if [[ ! -x "${BBC}" ]]; then
	BBC="bbc"
fi

ADB="${ADB:-adb}"
SERIAL="${ANDROID_SERIAL:-}"
ADB_FLAGS=()
if [[ -n "${SERIAL}" ]]; then
	ADB_FLAGS=(-s "${SERIAL}")
fi

echo "== BabbleCast verify =="

echo "1/3 Linux smoke (pytest + bbc server + Qt import) …"
"${PYTHON}" scripts/linux_smoke_check.py

echo "2/3 bbc --update …"
if [[ -d "${ROOT}/.git" && -x "${BBC}" ]]; then
	"${BBC}" --update
else
	echo "   skip: not a git checkout or bbc missing"
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
	bash "${ROOT}/scripts/android_connect_smoke.sh"
fi

echo "ALL VERIFY CHECKS PASSED"
