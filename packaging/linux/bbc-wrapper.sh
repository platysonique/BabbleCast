#!/usr/bin/env bash
# BabbleCast CLI wrapper — GUI launches as "BabbleCast" in the dock (not python3).
set -euo pipefail

ROOT="@BBC_ROOT@"
VENV="@BBC_VENV@"
BBC="${VENV}/bin/bbc"

if [[ ! -x "${BBC}" ]]; then
	echo "bbc: missing install at ${VENV}" >&2
	echo "Run: bash ${ROOT}/packaging/linux/install.sh" >&2
	exit 1
fi

cd "${ROOT}"

_launch_gui() {
	# Do not use exec -a with python — it breaks venv site-packages detection.
	# Dock identity comes from Qt setDesktopFileName("babblecast") in app.py.
	exec "${BBC}" client "$@"
}

case "${1:-}" in
	server|--update|-h|--help)
		exec "${BBC}" "$@"
		;;
	client)
		shift
		_launch_gui "$@"
		;;
	"")
		_launch_gui
		;;
	*)
		exec "${BBC}" "$@"
		;;
esac
