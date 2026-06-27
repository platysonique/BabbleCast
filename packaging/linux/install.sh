#!/usr/bin/env bash
# Install BabbleCast on Linux with `bbc` command in PATH.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="${ROOT}/.venv"
SUDO="${SUDO:-sudo-keyring}"

APT_PACKAGES=(
	python3-venv
	python3-pip
	libportaudio2
	libopus0
	libxkbcommon-x11-0
	libgl1
	libegl1
	libxcb-cursor0
	libxcb-xinerama0
)

install_system_deps() {
	if ! command -v apt-get &>/dev/null; then
		echo "install.sh: apt-get not found; see INSTALL.md for manual system packages." >&2
		return 1
	fi
	"$SUDO" apt-get update
	"$SUDO" apt-get install -y "${APT_PACKAGES[@]}"
}

echo "== BabbleCast system dependencies =="
if ! install_system_deps; then
	echo "install.sh: could not install system packages. Run:" >&2
	echo "  sudo apt-get install -y ${APT_PACKAGES[*]}" >&2
	exit 1
fi

echo "== Python virtualenv + dependencies =="
python3 -m venv "$VENV"
"$VENV/bin/pip" install -U pip wheel
"$VENV/bin/pip" install -r "${ROOT}/requirements-dev.txt"
"$VENV/bin/pip" install -e "$ROOT"

WRAPPER="$(mktemp)"
cat > "${WRAPPER}" <<EOF
#!/usr/bin/env bash
exec "${VENV}/bin/bbc" "\$@"
EOF
chmod +x "${WRAPPER}"

BBC_PATH=""
if "$SUDO" install -m 755 "${WRAPPER}" /usr/local/bin/bbc 2>/dev/null; then
	BBC_PATH="/usr/local/bin/bbc"
else
	INSTALL_DIR="${HOME}/.local/bin"
	mkdir -p "${INSTALL_DIR}"
	install -m 755 "${WRAPPER}" "${INSTALL_DIR}/bbc"
	BBC_PATH="${INSTALL_DIR}/bbc"

	MARKER="# BabbleCast PATH"
	if [[ -f "${HOME}/.profile" ]] && ! grep -qF "${MARKER}" "${HOME}/.profile"; then
		cat >>"${HOME}/.profile" <<'EOF'

# BabbleCast PATH
if [ -d "$HOME/.local/bin" ]; then
	PATH="$HOME/.local/bin:$PATH"
fi
EOF
	fi
	if [[ -f "${HOME}/.bashrc" ]] && ! grep -qF "${MARKER}" "${HOME}/.bashrc"; then
		cat >>"${HOME}/.bashrc" <<'EOF'

# BabbleCast PATH
if [ -d "$HOME/.local/bin" ]; then
	PATH="$HOME/.local/bin:$PATH"
fi
EOF
	fi
fi
rm -f "${WRAPPER}"

DESKTOP_DIR="${HOME}/.local/share/applications"
mkdir -p "${DESKTOP_DIR}"
cat > "${DESKTOP_DIR}/babblecast.desktop" <<EOF
[Desktop Entry]
Name=BabbleCast
Comment=Team live communication hub
Exec=${BBC_PATH}
Icon=${ROOT}/assets/icon.png
Terminal=false
Type=Application
Categories=Network;Chat;
EOF

echo "BabbleCast installed: ${BBC_PATH}"
echo "Run: bbc"
echo "See INSTALL.md if anything fails."
