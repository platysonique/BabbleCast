#!/usr/bin/env bash
# Build BabbleCast Android APK (sideload with: adb install -r mobile/bin/*.apk)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${ROOT}"

export ANDROID_HOME="${HOME}/Android/Sdk"
export ANDROID_SDK_ROOT="${ANDROID_HOME}"
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
export PATH="${JAVA_HOME}/bin:${HOME}/Android/cmdline-tools/latest/bin:${ANDROID_HOME}/platform-tools:${PATH}"

# Buildozer/p4a expect cmdline-tools inside ANDROID_HOME (legacy paths too).
SDK_TOOLS="${ANDROID_HOME}/tools/bin"
SDK_CLT="${ANDROID_HOME}/cmdline-tools/latest"
if [[ ! -x "${SDK_CLT}/bin/sdkmanager" ]]; then
  mkdir -p "${ANDROID_HOME}/cmdline-tools"
  ln -sfn "${HOME}/Android/cmdline-tools/latest" "${SDK_CLT}"
fi
if [[ ! -x "${SDK_TOOLS}/sdkmanager" ]]; then
  mkdir -p "${SDK_TOOLS}"
  ln -sfn "${HOME}/Android/cmdline-tools/latest/bin/sdkmanager" "${SDK_TOOLS}/sdkmanager"
fi

if [[ ! -d "${ROOT}/.venv" ]]; then
  python3 -m venv "${ROOT}/.venv"
fi
# shellcheck disable=SC1091
source "${ROOT}/.venv/bin/activate"
pip install -q -U pip wheel Cython buildozer

echo "== Building BabbleCast Android debug APK =="
echo "SDK: ${ANDROID_HOME}"
cd "${ROOT}/mobile"
buildozer android debug

APK="$(find "${ROOT}/mobile/bin" -name '*.apk' -type f 2>/dev/null | head -1)"
RELEASE_DIR="${ROOT}/packaging/android/releases"
mkdir -p "${RELEASE_DIR}"
if [[ -n "${APK}" ]]; then
  RELEASE_APK="${RELEASE_DIR}/$(basename "${APK}")"
  cp -f "${APK}" "${RELEASE_APK}"
  echo ""
  echo "APK ready: ${APK}"
  echo "Release copy: ${RELEASE_APK}"
  echo "Sideload: adb install -r \"${RELEASE_APK}\""
else
  echo "Build finished but no APK found under mobile/bin/" >&2
  exit 1
fi
