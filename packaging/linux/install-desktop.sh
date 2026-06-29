#!/usr/bin/env bash
# Install BabbleCast desktop launcher + icon (COSMIC / GNOME / KDE).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="${ROOT}/.venv"
WRAPPER_SRC="${ROOT}/packaging/linux/bbc-wrapper.sh"
SUDO="${SUDO:-sudo-keyring}"

if [[ ! -x "${VENV}/bin/bbc" ]]; then
	echo "install-desktop.sh: run packaging/linux/install.sh first (missing .venv)" >&2
	exit 1
fi

DESKTOP_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons/hicolor/512x512/apps"

# Same path install.sh chose, or existing bbc on PATH, or ~/.local/bin/bbc.
BBC_BIN="${1:-${BBC_PATH:-}}"
if [[ -z "${BBC_BIN}" ]]; then
	if command -v bbc &>/dev/null; then
		BBC_BIN="$(command -v bbc)"
	else
		BBC_BIN="${HOME}/.local/bin/bbc"
	fi
fi

BBC_DIR="$(dirname "${BBC_BIN}")"
WRAPPER_TMP="$(mktemp)"
sed -e "s|@BBC_ROOT@|${ROOT}|g" -e "s|@BBC_VENV@|${VENV}|g" "${WRAPPER_SRC}" > "${WRAPPER_TMP}"
chmod +x "${WRAPPER_TMP}"

if [[ "${BBC_DIR}" == "/usr/local/bin" ]]; then
	"${SUDO}" install -m 755 "${WRAPPER_TMP}" "${BBC_BIN}"
else
	mkdir -p "${BBC_DIR}"
	install -m 755 "${WRAPPER_TMP}" "${BBC_BIN}"
fi
rm -f "${WRAPPER_TMP}"

mkdir -p "${DESKTOP_DIR}" "${ICON_DIR}"

# Same launcher icon as Android (buildozer.spec → assets/icon.png).
ICON_SRC="${ROOT}/assets/icon.png"
ICON_NAME="babblecast"
if [[ -f "${ICON_SRC}" ]]; then
	cp -f "${ICON_SRC}" "${ICON_DIR}/${ICON_NAME}.png"
fi

DESKTOP_FILE="${DESKTOP_DIR}/babblecast.desktop"
cat > "${DESKTOP_FILE}" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=BabbleCast
GenericName=Voice Chat
Comment=Team live communication hub
Exec=${BBC_BIN}
Icon=${ICON_NAME}
Terminal=false
StartupNotify=true
StartupWMClass=BabbleCast
Categories=Network;Chat;AudioVideo;
Keywords=voice;chat;team;lan;
EOF

rm -f "${HOME}/.local/bin/babblecast-gui"

if command -v update-desktop-database &>/dev/null; then
	update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache &>/dev/null; then
	gtk-update-icon-cache -f -t "${HOME}/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo "Installed:"
echo "  bbc:     ${BBC_BIN}"
echo "  Desktop: ${DESKTOP_FILE}"
echo "  Icon:    ${ICON_DIR}/${ICON_NAME}.png (from assets/icon.png — same as Android)"
