from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu, QWidget

from babblecast.client.qt.midi.targets import MidiTarget, global_target

if TYPE_CHECKING:
    from babblecast.client.qt.midi.mapper_service import MidiMapperService


def _midi_footer(menu: QMenu, service: MidiMapperService) -> None:
    menu.addSeparator()
    line = menu.addAction("MIDI unavailable")
    line.setEnabled(False)
    if service.available:
        menu.removeAction(line)


def attach_absolute_menu(widget: QWidget, service: MidiMapperService, target: MidiTarget) -> None:
    widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def open_menu(pos) -> None:
        menu = QMenu(widget)
        menu.addAction("Map to MIDI…", lambda: service.start_learn(target, "value"))
        unlink = menu.addAction("Unlink MIDI")
        unlink.setEnabled(service.is_mapped(target.target_id, "value"))
        unlink.triggered.connect(lambda: service.unlink(target.target_id, "value"))
        if not service.available:
            _midi_footer(menu, service)
        menu.exec(widget.mapToGlobal(pos))

    widget.customContextMenuRequested.connect(open_menu)


def attach_toggle_menu(widget: QWidget, service: MidiMapperService, target: MidiTarget) -> None:
    widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def open_menu(pos) -> None:
        menu = QMenu(widget)
        menu.addAction("Map to MIDI…", lambda: service.start_learn(target, "trigger"))
        unlink = menu.addAction("Unlink MIDI")
        unlink.setEnabled(service.is_mapped(target.target_id, "trigger"))
        unlink.triggered.connect(lambda: service.unlink(target.target_id, "trigger"))
        if not service.available:
            _midi_footer(menu, service)
        menu.exec(widget.mapToGlobal(pos))

    widget.customContextMenuRequested.connect(open_menu)


def attach_momentary_menu(widget: QWidget, service: MidiMapperService, target: MidiTarget) -> None:
    attach_toggle_menu(widget, service, target)


def attach_mic_ptt_menu(btn, service: MidiMapperService) -> None:
    btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def open_menu(pos) -> None:
        menu = QMenu(btn)
        menu.addAction(
            "Map Mute…",
            lambda: service.start_learn(
                MidiTarget(global_target("mute"), "Global mic mute", "toggle", "global"),
                "trigger",
            ),
        )
        menu.addAction(
            "Map PTT…",
            lambda: service.start_learn(
                MidiTarget(global_target("ptt"), "Push-to-talk", "ptt", "global"),
                "ptt",
            ),
        )
        sub = menu.addMenu("Unlink Map")
        mute_act = sub.addAction("Mute")
        mute_act.setEnabled(service.is_mapped(global_target("mute"), "trigger"))
        mute_act.triggered.connect(lambda: service.unlink(global_target("mute"), "trigger"))
        ptt_act = sub.addAction("PTT")
        ptt_act.setEnabled(service.is_mapped(global_target("ptt"), "ptt"))
        ptt_act.triggered.connect(lambda: service.unlink(global_target("ptt"), "ptt"))
        if not service.available:
            _midi_footer(menu, service)
        menu.exec(btn.mapToGlobal(pos))

    btn.customContextMenuRequested.connect(open_menu)
