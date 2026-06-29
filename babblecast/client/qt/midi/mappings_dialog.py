from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from babblecast.client.qt.midi.binding_engine import MidiMap
from babblecast.client.qt.midi.targets import MidiTarget, label_for_target_id, parse_link_target, parse_peer_target

if TYPE_CHECKING:
    from babblecast.client.qt.midi.mapper_service import MidiMapperService


class MidiMappingsDialog(QDialog):
    def __init__(self, service: MidiMapperService, parent=None) -> None:
        super().__init__(parent)
        self._service = service
        self.setWindowTitle("MIDI Mappings")
        self.resize(640, 400)

        layout = QVBoxLayout(self)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Control", "MIDI", "Device", "Actions"])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        self._reload()

    def _sort_key(self, m: MidiMap) -> tuple:
        meta = self._service.meta_for(m.target_id)
        if m.target_id.startswith("global."):
            return (0, m.target_id)
        if parse_link_target(m.target_id):
            return (1, meta.get("link_label", m.target_id), m.target_id)
        if parse_peer_target(m.target_id):
            return (2, meta.get("peer_name", ""), m.target_id)
        return (3, m.target_id)

    def _reload(self) -> None:
        maps = sorted(self._service.engine.all_maps(), key=self._sort_key)
        self._table.setRowCount(len(maps))
        for row, m in enumerate(maps):
            meta = self._service.meta_for(m.target_id)
            self._table.setItem(row, 0, QTableWidgetItem(label_for_target_id(m.target_id, meta)))
            if m.midi_type == "cc":
                midi_text = f"CC {m.midi_number} ch {m.midi_channel + 1}"
            else:
                midi_text = f"Note {m.midi_number} ch {m.midi_channel + 1}"
            self._table.setItem(row, 1, QTableWidgetItem(midi_text))
            connected = self._service.multi.resolve_ctrl_idx(m.port_name) is not None
            dev_text = m.port_name if connected and m.port_name else "(not connected)"
            dev_item = QTableWidgetItem(dev_text)
            if not connected:
                dev_item.setForeground(QColor("#565f89"))
            self._table.setItem(row, 2, dev_item)

            actions = QWidget()
            hl = QHBoxLayout(actions)
            hl.setContentsMargins(2, 2, 2, 2)
            relearn = QPushButton("Re-learn")
            unlink = QPushButton("Unlink")
            target = self._service.target_from_map(m)
            relearn.clicked.connect(lambda _c=False, t=target, p=m.param: self._relearn(t, p))
            unlink.clicked.connect(lambda _c=False, tid=m.target_id, p=m.param: self._unlink(tid, p))
            hl.addWidget(relearn)
            hl.addWidget(unlink)
            self._table.setCellWidget(row, 3, actions)

    def _relearn(self, target: MidiTarget, param: str) -> None:
        self._service.start_learn(target, param, parent=self)
        self._reload()

    def _unlink(self, target_id: str, param: str) -> None:
        self._service.unlink(target_id, param)
        self._reload()
