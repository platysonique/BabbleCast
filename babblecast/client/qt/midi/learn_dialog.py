from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from babblecast.client.qt.midi.multi_input import MultiMidiInput


class MidiLearnDialog(QDialog):
    learned = pyqtSignal(str, int, int, int, int, str)

    def __init__(self, multi: MultiMidiInput, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MIDI Learn")
        self.setFixedSize(340, 170)
        self._captured = False
        self._multi = multi
        self._connections: list[tuple] = []

        layout = QVBoxLayout(self)
        title = QLabel("MIDI Learn")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._info = QLabel("Move any knob, button, or fader on any connected controller.")
        self._info.setWordWrap(True)
        self._info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._info)

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)

        self._on_note = lambda note, vel, ch, ctrl_idx, port: self._handle_note(note, vel, ch, ctrl_idx, port)
        self._on_cc = lambda cc, _val, ch, ctrl_idx, port: self._finish("cc", cc, ch, ctrl_idx, port)
        multi.note_on.connect(self._on_note)
        multi.cc_change.connect(self._on_cc)
        self._connections = [(multi.note_on, self._on_note), (multi.cc_change, self._on_cc)]

    def _handle_note(self, note: int, vel: int, ch: int, ctrl_idx: int, port: int) -> None:
        if vel > 0:
            self._finish("note", note, ch, ctrl_idx, port)

    def _finish(self, mtype: str, num: int, ch: int, ctrl_idx: int, port: int) -> None:
        if self._captured:
            return
        self._captured = True
        port_name = self._multi.port_name_for(ctrl_idx)
        label = f"CC {num} · ch {ch + 1}" if mtype == "cc" else f"Note {num} · ch {ch + 1}"
        self._info.setText(f"Captured: {label}")
        self.learned.emit(mtype, num, ch, ctrl_idx, port, port_name)
        self.accept()

    def closeEvent(self, event) -> None:
        for signal, slot in self._connections:
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self._connections.clear()
        super().closeEvent(event)
