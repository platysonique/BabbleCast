from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QWidget

from babblecast.client.bridge import BridgeManager
from babblecast.client.qt.midi.binding_engine import BindingEngine, MidiMap
from babblecast.client.qt.midi.engine import HAS_RTMIDI
from babblecast.client.qt.midi.learn_dialog import MidiLearnDialog
from babblecast.client.qt.midi.multi_input import MultiMidiInput
from babblecast.client.qt.midi.targets import (
    MidiTarget,
    global_target,
    link_target,
    parse_link_target,
    parse_peer_target,
    peer_target,
)
from babblecast.client.qt.midi.value_transforms import (
    cc_toggle_fire,
    midi_to_bridge,
    midi_to_gate_db,
    midi_to_suppression,
    toggle_fire,
)
from babblecast.config import get_settings, save_settings


class MidiMapperService(QWidget):
    def __init__(self, bridge: BridgeManager, main_window, drawer, parent=None) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._main = main_window
        self._drawer = drawer
        self._engine = BindingEngine()
        self._multi = MultiMidiInput(self)
        self._meta: dict[str, dict] = {}
        self._link_widgets: dict[str, object] = {}

        self._multi.note_on.connect(
            lambda n, v, c, ci, p: self._engine.on_midi_note(n, v, c, ci, p)
        )
        self._multi.note_off.connect(
            lambda n, c, ci, p: self._engine.on_midi_note_off(n, c, ci, p)
        )
        self._multi.cc_change.connect(
            lambda cc, val, c, ci, p: self._engine.on_midi_cc(cc, val, c, ci, p)
        )

        self._register_global_setters()
        self._load_from_settings()
        if HAS_RTMIDI:
            self._multi.start()

    @property
    def engine(self) -> BindingEngine:
        return self._engine

    @property
    def multi(self) -> MultiMidiInput:
        return self._multi

    @property
    def available(self) -> bool:
        return HAS_RTMIDI

    def meta_for(self, target_id: str) -> dict:
        return dict(self._meta.get(target_id, {}))

    def target_from_map(self, m: MidiMap) -> MidiTarget:
        meta = self.meta_for(m.target_id)
        if m.target_id.startswith("global."):
            action = m.target_id.split(".", 1)[1]
            kind = "ptt" if action == "ptt" else ("toggle" if action == "mute" else "absolute")
            return MidiTarget(m.target_id, m.target_id, kind, "global")  # type: ignore[arg-type]
        parsed = parse_link_target(m.target_id)
        if parsed:
            link_id, action = parsed
            return MidiTarget(
                m.target_id,
                meta.get("link_label", link_id),
                "toggle",
                "link",
                link_id=link_id,
                link_label=meta.get("link_label", ""),
            )
        parsed = parse_peer_target(m.target_id)
        if parsed:
            composite, action = parsed
            link_id, _, _client_id = composite.partition(":")
            kind = "momentary" if action == "send_tap" else ("toggle" if action == "listen_mute" else "absolute")
            return MidiTarget(
                m.target_id,
                meta.get("peer_name", "Peer"),
                kind,  # type: ignore[arg-type]
                "peer",
                link_id=link_id,
                composite=composite,
                peer_name=meta.get("peer_name", ""),
                link_label=meta.get("link_label", ""),
            )
        return MidiTarget(m.target_id, m.target_id, "absolute", "global")

    def shutdown(self) -> None:
        self._multi.stop()

    def is_mapped(self, target_id: str, param: str) -> bool:
        return self._engine.is_mapped(target_id, param)

    def _register_global_setters(self) -> None:
        drawer = self._drawer
        main = self._main
        bridge = self._bridge

        def sync_self_levels() -> None:
            s = get_settings()
            drawer.set_self_levels(
                s.gate_threshold_db,
                s.noise_suppression * 100,
                s.output_volume * 100,
                s.input_volume * 100,
            )

        self._engine.register_target(
            global_target("mic_volume"),
            "value",
            lambda raw: (bridge.set_input_volume(midi_to_bridge("absolute", raw)), sync_self_levels()),
        )
        self._engine.register_target(
            global_target("master_volume"),
            "value",
            lambda raw: (bridge.set_master_output_volume(midi_to_bridge("absolute", raw)), sync_self_levels()),
        )
        self._engine.register_target(
            global_target("gate"),
            "value",
            lambda raw: (bridge.set_gate_db(midi_to_gate_db(raw)), sync_self_levels()),
        )
        self._engine.register_target(
            global_target("suppression"),
            "value",
            lambda raw: (bridge.set_noise_suppression(midi_to_suppression(raw)), sync_self_levels()),
        )

        def toggle_mute(_raw: int) -> None:
            new = not main._self_muted
            main._mute_btn.blockSignals(True)
            main._mute_btn.setChecked(new)
            main._mute_btn.blockSignals(False)
            main._toggle_mute(new)

        self._engine.register_target(global_target("mute"), "trigger", toggle_mute)

        def ptt_press(_raw: int) -> None:
            if main._self_muted:
                main._set_ptt(True)

        def ptt_release(_raw: int) -> None:
            if main._self_muted:
                main._set_ptt(False)

        self._engine.register_target(global_target("ptt"), "value", ptt_press)
        self._engine.register_target(global_target("ptt"), "release", ptt_release)

    def register_link_targets(self, link_id: str, label: str, widget) -> None:
        self._link_widgets[link_id] = widget
        lid = link_id

        def flip_listen(raw: int) -> None:
            if not toggle_fire(raw) and raw < 64:
                return
            link = self._bridge.get_link(lid)
            if not link:
                return
            new = not link.listen_muted
            self._bridge.set_listen_muted(lid, new)
            widget.set_listen_muted(new)

        def flip_mic(raw: int) -> None:
            if not toggle_fire(raw) and raw < 64:
                return
            link = self._bridge.get_link(lid)
            if not link:
                return
            new = not link.mic_muted
            self._bridge.set_mic_muted(lid, new)
            widget.set_mic_muted(new)

        self._engine.register_target(link_target(lid, "listen_mute"), "trigger", flip_listen)
        self._engine.register_target(link_target(lid, "mic_mute"), "trigger", flip_mic)
        self._meta.setdefault(link_target(lid, "listen_mute"), {})["link_label"] = label
        self._meta.setdefault(link_target(lid, "mic_mute"), {})["link_label"] = label
        attach = getattr(widget, "attach_midi_menus", None)
        if callable(attach):
            attach(self, link_id, label)

    def unregister_link_targets(self, link_id: str) -> None:
        self._link_widgets.pop(link_id, None)
        self._engine.unregister_target(link_target(link_id, "listen_mute"))
        self._engine.unregister_target(link_target(link_id, "mic_mute"))

    def ensure_peer_setters(
        self,
        composite: str,
        link_id: str,
        client_id: str,
        peer_name: str,
        link_label: str,
    ) -> None:
        drawer = self._drawer
        main = self._main

        def vol(raw: int) -> None:
            v = midi_to_bridge("absolute", raw)
            self._bridge.set_participant_volume(composite, v)
            if drawer.is_peer_open(composite) and not drawer._peer_vol.isSliderDown():
                drawer._peer_vol.blockSignals(True)
                drawer._peer_vol.setValue(int(v * 100))
                drawer._peer_vol.blockSignals(False)

        def flip_listen(raw: int) -> None:
            if not toggle_fire(raw):
                return
            s = get_settings()
            cur = s.per_user_muted.get(composite, False)
            new = not cur
            self._bridge.set_participant_muted(composite, new)
            if drawer.is_peer_open(composite):
                drawer._listen_mute_btn.blockSignals(True)
                drawer._listen_mute_btn.setChecked(new)
                drawer._listen_mute_btn.setText("🔇" if new else "🔊")
                drawer._listen_mute_btn.blockSignals(False)

        def tap(_raw: int) -> None:
            if toggle_fire(_raw) or cc_toggle_fire(_raw):
                main._send_tap(link_id, client_id)

        tid_v = peer_target(composite, "volume")
        tid_m = peer_target(composite, "listen_mute")
        tid_t = peer_target(composite, "send_tap")
        self._engine.register_target(tid_v, "value", vol)
        self._engine.register_target(tid_m, "trigger", flip_listen)
        self._engine.register_target(tid_t, "trigger", tap)
        for tid in (tid_v, tid_m, tid_t):
            self._meta.setdefault(tid, {})["peer_name"] = peer_name
            self._meta[tid]["link_label"] = link_label

    def start_learn(self, target: MidiTarget, param: str, parent: QWidget | None = None) -> None:
        dlg = MidiLearnDialog(self._multi, parent or self._main)

        def on_learned(mtype, num, ch, ctrl_idx, port, port_name) -> None:
            self._apply_learn(target, param, mtype, num, ch, ctrl_idx, port, port_name)

        dlg.learned.connect(on_learned)
        dlg.exec()

    def _apply_learn(
        self,
        target: MidiTarget,
        param: str,
        mtype: str,
        num: int,
        ch: int,
        ctrl_idx: int,
        port: int,
        port_name: str,
    ) -> None:
        if target.scope == "peer" and target.composite:
            plink, _, pclient = target.composite.partition(":")
            self.ensure_peer_setters(
                target.composite,
                target.link_id or plink,
                pclient,
                target.peer_name or "",
                target.link_label or "",
            )
        self._engine.map_midi(
            mtype,
            ch,
            num,
            target.target_id,
            param,
            ctrl_idx=ctrl_idx,
            port=port,
            port_name=port_name,
        )
        prev = self._meta.get(target.target_id, {})
        self._meta[target.target_id] = {
            "link_label": target.link_label or prev.get("link_label", ""),
            "peer_name": target.peer_name or prev.get("peer_name", ""),
        }
        self._persist()

    def unlink(self, target_id: str, param: str | None = None) -> None:
        self._engine.unmap_target(target_id, param)
        self._persist()

    def unlink_all(self, parent: QWidget) -> None:
        if not self._engine.all_maps():
            return
        ans = QMessageBox.question(
            parent,
            "Unlink all MIDI mappings",
            "Remove every saved MIDI mapping?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._engine.clear_maps()
        self._persist()

    def _persist(self) -> None:
        s = get_settings()
        rows = self._engine.serialize_maps()
        for row in rows:
            row["meta"] = self._meta.get(row["tgt"], {})
        s.midi_maps = rows
        save_settings(s)

    def _load_from_settings(self) -> None:
        rows = list(get_settings().midi_maps)
        for row in rows:
            self._meta[row["tgt"]] = dict(row.get("meta") or {})
            idx = self._multi.resolve_ctrl_idx(str(row.get("port_name", "")))
            if idx is not None:
                row["ctrl_idx"] = idx
            parsed = parse_peer_target(row["tgt"])
            if parsed:
                composite, _ = parsed
                link_id, _, client_id = composite.partition(":")
                meta = row.get("meta") or {}
                self.ensure_peer_setters(
                    composite,
                    link_id,
                    client_id,
                    meta.get("peer_name", ""),
                    meta.get("link_label", ""),
                )
        self._engine.load_maps(rows)

    def attach_peer_menus(
        self,
        drawer,
        composite: str,
        link_id: str,
        client_id: str,
        peer_name: str,
        link_label: str,
    ) -> None:
        from babblecast.client.qt.midi.context_menus import (
            attach_absolute_menu,
            attach_momentary_menu,
            attach_toggle_menu,
        )

        tgt_vol = MidiTarget(
            peer_target(composite, "volume"),
            peer_name,
            "absolute",
            "peer",
            composite=composite,
            link_id=link_id,
            peer_name=peer_name,
            link_label=link_label,
        )
        tgt_mute = MidiTarget(
            peer_target(composite, "listen_mute"),
            peer_name,
            "toggle",
            "peer",
            composite=composite,
            link_id=link_id,
            peer_name=peer_name,
            link_label=link_label,
        )
        tgt_tap = MidiTarget(
            peer_target(composite, "send_tap"),
            peer_name,
            "momentary",
            "peer",
            composite=composite,
            link_id=link_id,
            peer_name=peer_name,
            link_label=link_label,
        )
        attach_absolute_menu(drawer._peer_vol, self, tgt_vol)
        attach_toggle_menu(drawer._listen_mute_btn, self, tgt_mute)
        if drawer._tap_btn.isVisible():
            attach_momentary_menu(drawer._tap_btn, self, tgt_tap)
        drawer._midi_peer_attached = True

    def detach_peer_menus(self, drawer) -> None:
        for w in (drawer._peer_vol, drawer._listen_mute_btn, drawer._tap_btn):
            w.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        drawer._midi_peer_attached = False

    def open_mappings_dialog(self, parent: QWidget) -> None:
        from babblecast.client.qt.midi.mappings_dialog import MidiMappingsDialog

        MidiMappingsDialog(self, parent).exec()
