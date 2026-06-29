from __future__ import annotations

import logging
import queue
import re

from PyQt6.QtCore import QObject, Qt, pyqtSignal

logger = logging.getLogger(__name__)

try:
    import rtmidi
    HAS_RTMIDI = True
except ImportError:
    HAS_RTMIDI = False
    rtmidi = None  # type: ignore


class MidiEngine(QObject):
    note_on = pyqtSignal(int, int, int)
    note_off = pyqtSignal(int, int)
    cc_change = pyqtSignal(int, int, int)
    _drain_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._midi_in = None
        self._port_name = ""
        self._queue: queue.Queue = queue.Queue()
        self._drain_requested.connect(self._drain, Qt.ConnectionType.QueuedConnection)

    @staticmethod
    def normalize_port_name(name: str) -> str:
        text = (name or "").strip().casefold()
        text = re.sub(r"\s+\d+:\d+\s*$", "", text)
        return re.sub(r"\s+", " ", text)

    @staticmethod
    def list_input_ports() -> list[str]:
        if not HAS_RTMIDI:
            return []
        try:
            mi = rtmidi.MidiIn()
            return list(mi.get_ports())
        except Exception:
            logger.exception("Failed to list MIDI input ports")
            return []

    @property
    def port_name(self) -> str:
        return self._port_name

    def open_port(self, port_name: str) -> bool:
        if not HAS_RTMIDI or not port_name:
            return False
        self.close()
        try:
            mi = rtmidi.MidiIn()
            ports = mi.get_ports()
            if port_name not in ports:
                return False
            mi.open_port(ports.index(port_name))
            mi.set_callback(self._callback)
            # python-rtmidi 1.5+ uses ignore_types(); older Assimilator samples used dont_ignore_sysex().
            ignore = getattr(mi, "ignore_types", None)
            if callable(ignore):
                ignore(sysex=True, timing=True, active_sense=True)
            self._midi_in = mi
            self._port_name = port_name
            return True
        except Exception:
            logger.exception("Failed to open MIDI port %r", port_name)
            self._midi_in = None
            self._port_name = ""
            return False

    def close(self) -> None:
        if self._midi_in is not None:
            try:
                self._midi_in.cancel_callback()
                self._midi_in.close_port()
            except Exception:
                pass
            self._midi_in = None
        self._port_name = ""

    def _callback(self, event, _data=None) -> None:
        self._queue.put(event)
        self._drain_requested.emit()

    def _drain(self) -> None:
        while True:
            try:
                msg, _delta = self._queue.get_nowait()
            except queue.Empty:
                break
            if not msg:
                continue
            status = msg[0] & 0xF0
            ch = msg[0] & 0x0F
            if status == 0x90 and len(msg) > 2:
                vel = msg[2]
                if vel == 0:
                    self.note_off.emit(msg[1], ch)
                else:
                    self.note_on.emit(msg[1], vel, ch)
            elif status == 0x80 and len(msg) > 1:
                self.note_off.emit(msg[1], ch)
            elif status == 0xB0 and len(msg) > 2:
                self.cc_change.emit(msg[1], msg[2], ch)
