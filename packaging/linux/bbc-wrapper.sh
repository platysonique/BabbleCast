#!/usr/bin/env bash
# BabbleCast CLI wrapper — GUI launches as "BabbleCast" in the dock (not python3).
set -euo pipefail

ROOT="@BBC_ROOT@"
VENV="@BBC_VENV@"
BBC="${VENV}/bin/bbc"
PY="${VENV}/bin/python"

if [[ ! -x "${BBC}" ]]; then
	echo "bbc: missing install at ${VENV}" >&2
	echo "Run: bash ${ROOT}/packaging/linux/install.sh" >&2
	exit 1
fi

cd "${ROOT}"

_launch_gui() {
	# exec -a sets WM_CLASS / Wayland app id for COSMIC/GNOME dock grouping.
	exec -a BabbleCast "${PY}" -m babblecast.cli client "$@"
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
