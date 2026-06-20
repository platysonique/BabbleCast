from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from babblecast.client.qt.midi.engine import HAS_RTMIDI, MidiEngine


def _skip_port(name: str) -> bool:
    low = name.casefold()
    return "through" in low or ("rtmidi" in low and "monitor" in low)


class MultiMidiInput(QObject):
    note_on = pyqtSignal(int, int, int, int, int)
    note_off = pyqtSignal(int, int, int, int)
    cc_change = pyqtSignal(int, int, int, int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._engines: list[MidiEngine] = []
        self._port_by_idx: dict[int, str] = {}
        self._scan_timer = QTimer(self)
        self._scan_timer.setInterval(2000)
        self._scan_timer.timeout.connect(self.rescan_ports)

    def start(self) -> None:
        if not HAS_RTMIDI:
            return
        self.rescan_ports()
        self._scan_timer.start()

    def stop(self) -> None:
        self._scan_timer.stop()
        for eng in self._engines:
            eng.close()
        self._engines.clear()
        self._port_by_idx.clear()

    def port_name_for(self, ctrl_idx: int) -> str:
        return self._port_by_idx.get(ctrl_idx, "")

    def resolve_ctrl_idx(self, port_name: str) -> int | None:
        if not port_name:
            return None
        norm = MidiEngine.normalize_port_name(port_name)
        for idx, name in self._port_by_idx.items():
            if MidiEngine.normalize_port_name(name) == norm:
                return idx
        return None

    def rescan_ports(self) -> None:
        if not HAS_RTMIDI:
            return
        names = [n for n in MidiEngine.list_input_ports() if not _skip_port(n)]
        open_names = {e.port_name for e in self._engines}
        for name in names:
            if name not in open_names:
                self._add_engine(name)
        for eng in list(self._engines):
            if eng.port_name and eng.port_name not in names:
                self._remove_engine(eng)

    def _add_engine(self, port_name: str) -> None:
        eng = MidiEngine(self)
        if not eng.open_port(port_name):
            return
        idx = len(self._engines)
        self._engines.append(eng)
        self._port_by_idx[idx] = port_name
        eng.note_on.connect(lambda n, v, c, i=idx: self.note_on.emit(n, v, c, i, 0))
        eng.note_off.connect(lambda n, c, i=idx: self.note_off.emit(n, c, i, 0))
        eng.cc_change.connect(lambda cc, val, c, i=idx: self.cc_change.emit(cc, val, c, i, 0))

    def _remove_engine(self, eng: MidiEngine) -> None:
        if eng in self._engines:
            self._engines.remove(eng)
        eng.close()
        self._port_by_idx = {i: self._engines[i].port_name for i in range(len(self._engines))}
