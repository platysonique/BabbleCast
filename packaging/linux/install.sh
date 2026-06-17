#!/usr/bin/env bash
# Install BabbleCast on Linux with `bbc` command in PATH.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="${ROOT}/.venv"

python3 -m venv "$VENV"
"$VENV/bin/pip" install -U pip wheel
"$VENV/bin/pip" install -e "$ROOT[dev]"

INSTALL_DIR="${HOME}/.local/bin"
mkdir -p "$INSTALL_DIR"
cat > "${INSTALL_DIR}/bbc" <<EOF
#!/usr/bin/env bash
exec "${VENV}/bin/bbc" "\$@"
EOF
chmod +x "${INSTALL_DIR}/bbc"

DESKTOP_DIR="${HOME}/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cat > "${DESKTOP_DIR}/babblecast.desktop" <<EOF
[Desktop Entry]
Name=BabbleCast
Comment=Team live communication hub
Exec=${INSTALL_DIR}/bbc
Icon=audio-input-microphone
Terminal=false
Type=Application
Categories=Network;Chat;
EOF

echo "BabbleCast installed. Run: bbc"
echo "Ensure ~/.local/bin is in your PATH."
