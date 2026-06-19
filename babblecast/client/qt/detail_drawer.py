"""Right column — horizontally sliding panel with collapsible self-audio + peer details."""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from babblecast.client.qt.collapsible_section import CollapsibleSection
from babblecast.client.qt.meter_strip import MeterVolumeStrip
from babblecast.client.qt.vertical_meter import METER_HEIGHT, VerticalMeter
from babblecast.client.qt.tap_note_dialog import TapNoteRowLabel
from babblecast.client.qt.volume_knob import VolumeKnob
from babblecast.taps import get_tap_store


class DetailDrawer(QWidget):
    """Thin edge strip + sliding body: self audio drawer + optional peer panel."""

    peer_closed = pyqtSignal()
    panel_expanded_changed = pyqtSignal(bool)
    self_audio_expanded_changed = pyqtSignal(bool)
    input_monitoring_changed = pyqtSignal(bool)

    def __init__(
        self,
        *,
        on_gate,
        on_noise,
        on_input_device,
        on_output_device,
        on_master_volume,
        on_mic_volume,
        on_host_password,
        on_peer_volume,
        on_peer_listen_mute,
        on_peer_tap,
        on_peer_tap_chat,
        on_reopen_tap,
        on_add_tap_note,
        on_delete_tap_note,
        on_view_tap_note,
        panel_expanded: bool = False,
        self_audio_expanded: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._on_gate = on_gate
        self._on_noise = on_noise
        self._on_input_device = on_input_device
        self._on_output_device = on_output_device
        self._on_master_volume = on_master_volume
        self._on_mic_volume = on_mic_volume
        self._on_host_password = on_host_password
        self._on_peer_volume = on_peer_volume
        self._on_peer_listen_mute = on_peer_listen_mute
        self._on_peer_tap = on_peer_tap
        self._on_peer_tap_chat = on_peer_tap_chat
        self._on_reopen_tap = on_reopen_tap
        self._on_add_tap_note = on_add_tap_note
        self._on_delete_tap_note = on_delete_tap_note
        self._on_view_tap_note = on_view_tap_note

        self._open_composite: str | None = None
        self._peer_client_id = ""
        self._peer_link_id = ""
        self._peer_is_self = False
        self._panel_width = 292
        self._panel_expanded = panel_expanded

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        strip = QVBoxLayout()
        strip.setContentsMargins(0, 8, 0, 0)
        self._panel_toggle = QPushButton("◀" if panel_expanded else "▶")
        self._panel_toggle.setObjectName("drawerToggle")
        self._panel_toggle.setFixedSize(22, 28)
        self._panel_toggle.setToolTip("Expand / collapse right panel")
        self._panel_toggle.clicked.connect(self.toggle_panel)
        strip.addWidget(self._panel_toggle, alignment=Qt.AlignmentFlag.AlignTop)
        strip.addStretch()
        root.addLayout(strip)

        self._panel_body = QWidget()
        self._panel_body.setMaximumWidth(self._panel_width if panel_expanded else 0)
        panel_layout = QVBoxLayout(self._panel_body)
        panel_layout.setContentsMargins(4, 0, 0, 0)
        panel_layout.setSpacing(0)

        self._self_section = CollapsibleSection("Your audio", expanded=self_audio_expanded)
        self._self_section.toggled.connect(self._self_section_toggled)
        self_layout = self._self_section.body_layout()
        self_layout.setSpacing(6)

        audio_row = QHBoxLayout()
        audio_row.setContentsMargins(0, 0, 0, 0)
        audio_row.setSpacing(8)

        self._self_strip = MeterVolumeStrip(
            volume_label="Mic",
            compact=True,
            on_volume=self._mic_volume_changed,
        )
        audio_row.addWidget(self._self_strip, alignment=Qt.AlignmentFlag.AlignTop)

        noise_col = QVBoxLayout()
        noise_col.setContentsMargins(0, 0, 0, 0)
        noise_col.setSpacing(8)

        gate_box = QVBoxLayout()
        gate_box.setSpacing(2)
        gate_title = QLabel("Noise gate")
        gate_title.setStyleSheet("color: #a9b1d6; font-size: 11px;")
        gate_title.setToolTip(
            "Level threshold — mutes audio below this (envelope gate, after suppression)"
        )
        self._gate_slider = QSlider(Qt.Orientation.Horizontal)
        self._gate_slider.setRange(-80, 0)
        self._gate_label = QLabel("-40 dB")
        self._gate_label.setStyleSheet("color: #565f89; font-size: 10px;")
        self._gate_slider.valueChanged.connect(self._gate_changed)
        gate_box.addWidget(gate_title)
        gate_box.addWidget(self._gate_slider)
        gate_box.addWidget(self._gate_label)
        noise_col.addLayout(gate_box)

        noise_box = QVBoxLayout()
        noise_box.setSpacing(2)
        noise_title = QLabel("Noise suppression")
        noise_title.setStyleSheet("color: #a9b1d6; font-size: 11px;")
        noise_title.setToolTip(
            "Spectral noise reduction — reduces steady background noise before the gate"
        )
        self._noise_slider = QSlider(Qt.Orientation.Horizontal)
        self._noise_slider.setRange(0, 100)
        self._noise_label = QLabel("50%")
        self._noise_label.setStyleSheet("color: #565f89; font-size: 10px;")
        self._noise_slider.valueChanged.connect(self._noise_changed)
        noise_box.addWidget(noise_title)
        noise_box.addWidget(self._noise_slider)
        noise_box.addWidget(self._noise_label)
        noise_col.addLayout(noise_box)
        noise_col.addStretch()
        audio_row.addLayout(noise_col, stretch=1)

        knob_col = QVBoxLayout()
        knob_col.setContentsMargins(0, 0, 0, 0)
        knob_col.setSpacing(2)
        master_title = QLabel("Master")
        master_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        master_title.setStyleSheet("color: #a9b1d6; font-size: 11px;")
        self._master_knob = VolumeKnob()
        self._master_knob.valueChanged.connect(self._master_changed)
        knob_col.addWidget(master_title, alignment=Qt.AlignmentFlag.AlignHCenter)
        knob_col.addWidget(
            self._master_knob,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
        )
        knob_col.addStretch()
        knob_host = QWidget()
        knob_host.setLayout(knob_col)
        audio_row.addWidget(knob_host, alignment=Qt.AlignmentFlag.AlignTop)

        self_layout.addLayout(audio_row)

        self._input_combo = QComboBox()
        self._input_combo.currentIndexChanged.connect(self._input_changed)
        self._output_combo = QComboBox()
        self._output_combo.currentIndexChanged.connect(self._output_changed)
        self_layout.addWidget(QLabel("Microphone device"))
        self_layout.addWidget(self._input_combo)
        self_layout.addWidget(QLabel("Speaker device"))
        self_layout.addWidget(self._output_combo)

        self._host_pwd_status = QLabel("Host password: not set")
        self._host_pwd_status.setStyleSheet("color: #565f89; font-size: 11px;")
        self._room_pwd_label = QLabel("")
        self._room_pwd_label.setStyleSheet("color: #7aa2f7; font-size: 11px;")
        self._room_pwd_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._room_pwd_label.setVisible(False)
        self._host_pwd = QLineEdit()
        self._host_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self._host_pwd.setPlaceholderText("Your personal admin password")
        self._host_pwd_save = QPushButton("Save host password")
        self._host_pwd_save.clicked.connect(self._save_host_password)
        self_layout.addWidget(QLabel("Host password"))
        self_layout.addWidget(self._room_pwd_label)
        self_layout.addWidget(self._host_pwd_status)
        self_layout.addWidget(self._host_pwd)
        self_layout.addWidget(self._host_pwd_save)
        panel_layout.addWidget(self._self_section, 0, Qt.AlignmentFlag.AlignTop)

        self._peer_block = QWidget()
        self._peer_block.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._peer_block.setVisible(False)
        peer_block_layout = QVBoxLayout(self._peer_block)
        peer_block_layout.setContentsMargins(0, 8, 0, 0)

        header = QHBoxLayout()
        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedWidth(32)
        self._close_btn.setToolTip("Close person panel (or double-click name again)")
        self._close_btn.clicked.connect(self.close_peer)
        self._peer_title = QLabel("")
        self._peer_title.setStyleSheet("font-weight: bold; color: #7aa2f7;")
        header.addWidget(self._close_btn)
        header.addWidget(self._peer_title, stretch=1)
        peer_block_layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        body_layout = QVBoxLayout(body)

        self._controls_section = CollapsibleSection("Controls", expanded=True)
        controls_layout = self._controls_section.body_layout()

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)
        self._peer_meter = VerticalMeter()
        vol_col = QVBoxLayout()
        vol_col.setSpacing(2)
        self._listen_mute_btn = QPushButton("🔊")
        self._listen_mute_btn.setCheckable(True)
        self._listen_mute_btn.setFixedSize(36, 36)
        self._listen_mute_btn.setToolTip("Mute hearing this person (local only)")
        self._listen_mute_btn.toggled.connect(self._peer_listen_toggled)
        vol_col.addWidget(self._listen_mute_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._peer_vol = QSlider(Qt.Orientation.Vertical)
        self._peer_vol.setRange(0, 200)
        self._peer_vol.setFixedSize(28, METER_HEIGHT)
        self._peer_vol.valueChanged.connect(self._peer_volume_changed)
        vol_col.addWidget(self._peer_vol, alignment=Qt.AlignmentFlag.AlignHCenter)
        vol_lbl = QLabel("Vol")
        vol_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vol_col.addWidget(vol_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)
        ctrl_row.addWidget(self._peer_meter, alignment=Qt.AlignmentFlag.AlignVCenter)
        ctrl_row.addLayout(vol_col)
        ctrl_row.addStretch()
        controls_layout.addLayout(ctrl_row)

        tap_row = QHBoxLayout()
        self._tap_btn = QPushButton("Tap")
        self._tap_btn.clicked.connect(self._do_tap)
        self._tap_chat_btn = QPushButton("Tap chat")
        self._tap_chat_btn.clicked.connect(self._do_tap_chat)
        tap_row.addWidget(self._tap_btn)
        tap_row.addWidget(self._tap_chat_btn)
        controls_layout.addLayout(tap_row)
        body_layout.addWidget(self._controls_section)

        self._tech_section = CollapsibleSection("Technical details", expanded=False)
        tech_layout = self._tech_section.body_layout()
        self._tech_label = QLabel("")
        self._tech_label.setWordWrap(True)
        self._tech_label.setStyleSheet("color: #a9b1d6; font-family: monospace; font-size: 11px;")
        tech_layout.addWidget(self._tech_label)
        body_layout.addWidget(self._tech_section)

        self._taps_section = CollapsibleSection("Tap Notes", expanded=True)
        taps_layout = self._taps_section.body_layout()
        taps_header = QHBoxLayout()
        taps_add = QPushButton("+")
        taps_add.setFixedSize(28, 28)
        taps_add.setToolTip("Add tap note for this person")
        taps_add.clicked.connect(self._add_peer_tap_note)
        taps_header.addStretch()
        taps_header.addWidget(taps_add)
        taps_layout.addLayout(taps_header)
        self._tap_list_host = QWidget()
        self._tap_list_layout = QVBoxLayout(self._tap_list_host)
        self._tap_list_layout.setContentsMargins(0, 0, 0, 0)
        self._tap_list_layout.setSpacing(2)
        taps_layout.addWidget(self._tap_list_host)
        body_layout.addWidget(self._taps_section)

        body_layout.addStretch()
        scroll.setWidget(body)
        peer_block_layout.addWidget(scroll, stretch=1)
        panel_layout.addWidget(self._peer_block, 1)

        root.addWidget(self._panel_body, 0)

        self._anim = QPropertyAnimation(self._panel_body, b"maximumWidth")
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def is_panel_expanded(self) -> bool:
        return self._panel_expanded

    def toggle_panel(self) -> None:
        self.set_panel_expanded(not self._panel_expanded)

    def set_panel_expanded(self, expanded: bool) -> None:
        if self._panel_expanded == expanded:
            return
        self._panel_expanded = expanded
        self._panel_toggle.setText("◀" if expanded else "▶")
        self._animate_panel_width(self._panel_width if expanded else 0)
        self.panel_expanded_changed.emit(expanded)
        self.input_monitoring_changed.emit(
            expanded and self._self_section.is_expanded()
        )

    def _ensure_panel_open(self) -> None:
        if not self._panel_expanded:
            self.set_panel_expanded(True)

    def set_self_levels(
        self, gate_db: float, noise_pct: float, master_pct: float, mic_pct: float
    ) -> None:
        self._gate_slider.blockSignals(True)
        self._noise_slider.blockSignals(True)
        self._master_knob.blockSignals(True)
        self._gate_slider.setValue(int(gate_db))
        self._gate_label.setText(f"{int(gate_db)} dB")
        self._noise_slider.setValue(int(noise_pct))
        self._noise_label.setText(f"{int(noise_pct)}%")
        self._master_knob.setValue(int(master_pct))
        self._self_strip.set_volume_percent(int(mic_pct))
        self._gate_slider.blockSignals(False)
        self._noise_slider.blockSignals(False)
        self._master_knob.blockSignals(False)

    def _self_section_toggled(self, expanded: bool) -> None:
        self.self_audio_expanded_changed.emit(expanded)
        self.input_monitoring_changed.emit(
            expanded and self._panel_expanded
        )

    def populate_devices(self, inputs: list, outputs: list, sel_in: int, sel_out: int) -> None:
        self._input_combo.blockSignals(True)
        self._output_combo.blockSignals(True)
        self._input_combo.clear()
        self._output_combo.clear()
        for dev in inputs:
            self._input_combo.addItem(dev.label, dev.storage_key)
        for dev in outputs:
            self._output_combo.addItem(dev.label, dev.storage_key)
        if inputs:
            self._input_combo.setCurrentIndex(min(sel_in, len(inputs) - 1))
        if outputs:
            self._output_combo.setCurrentIndex(min(sel_out, len(outputs) - 1))
        self._input_combo.blockSignals(False)
        self._output_combo.blockSignals(False)

    def set_local_mic_level(self, level: float) -> None:
        self._self_strip.set_meter_level(level)

    def is_peer_open(self, composite: str) -> bool:
        return self._open_composite == composite and self._peer_block.isVisible()

    def toggle_peer(
        self,
        composite: str,
        *,
        name: str,
        server_label: str,
        link_id: str,
        client_id: str,
        voice_level: float,
        speaking: bool,
        muted: bool,
        volume: float,
        tapped: bool,
        tap_active: bool = False,
        is_self: bool,
        tech_lines: list[str],
    ) -> None:
        if self.is_peer_open(composite):
            self.close_peer()
            return
        self.show_peer(
            composite,
            name=name,
            server_label=server_label,
            link_id=link_id,
            client_id=client_id,
            voice_level=voice_level,
            speaking=speaking,
            muted=muted,
            volume=volume,
            tapped=tapped,
            tap_active=tap_active,
            is_self=is_self,
            tech_lines=tech_lines,
        )

    def show_peer(
        self,
        composite: str,
        *,
        name: str,
        server_label: str,
        link_id: str,
        client_id: str,
        voice_level: float,
        speaking: bool,
        muted: bool,
        volume: float,
        tapped: bool,
        tap_active: bool = False,
        is_self: bool,
        tech_lines: list[str],
    ) -> None:
        self._ensure_panel_open()
        self._open_composite = composite
        self._peer_link_id = link_id
        self._peer_client_id = client_id
        self._peer_is_self = is_self
        suffix = " (you)" if is_self else ""
        self._peer_title.setText(f"{name}{suffix}")
        self._controls_section.set_title(f"{name} controls")
        self._peer_meter.set_level(voice_level if speaking or voice_level > 0 else voice_level)
        self._peer_vol.blockSignals(True)
        self._peer_vol.setValue(int(volume * 100))
        self._peer_vol.blockSignals(False)
        self._listen_mute_btn.blockSignals(True)
        self._listen_mute_btn.setChecked(muted)
        self._listen_mute_btn.setText("🔇" if muted else "🔊")
        self._listen_mute_btn.blockSignals(False)
        self._tap_btn.setVisible(not is_self)
        self._sync_tap_chat_button(tapped=tapped, tap_active=tap_active, is_self=is_self)
        self._tech_label.setText("\n".join(tech_lines))
        self._refresh_tap_list(client_id)
        self._peer_block.setVisible(True)

    def update_peer_meter(self, voice_level: float, speaking: bool, volume: float, muted: bool) -> None:
        if not self._peer_block.isVisible():
            return
        self._peer_meter.set_level(voice_level)
        self._listen_mute_btn.blockSignals(True)
        self._listen_mute_btn.setChecked(muted)
        self._listen_mute_btn.setText("🔇" if muted else "🔊")
        self._listen_mute_btn.blockSignals(False)
        if not self._peer_vol.isSliderDown():
            self._peer_vol.blockSignals(True)
            self._peer_vol.setValue(int(volume * 100))
            self._peer_vol.blockSignals(False)

    def close_peer(self) -> None:
        if not self._peer_block.isVisible():
            return
        self._open_composite = None
        self._peer_block.setVisible(False)
        self.peer_closed.emit()

    def _animate_panel_width(self, target: int) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._panel_body.maximumWidth())
        self._anim.setEndValue(target)
        self._anim.start()

    def has_open_peer(self) -> bool:
        return self._peer_block.isVisible() and bool(self._peer_client_id)

    @property
    def peer_client_id(self) -> str:
        return self._peer_client_id

    @property
    def peer_link_id(self) -> str:
        return self._peer_link_id

    def set_tap_chat_visible(self, visible: bool) -> None:
        """Enable Tap chat when a tap session exists (button stays visible)."""
        if not self._peer_block.isVisible() or self._peer_is_self:
            return
        self._tap_chat_btn.setVisible(True)
        self._tap_chat_btn.setEnabled(visible)

    def update_tap_chat_state(self, *, tapped: bool, tap_active: bool) -> None:
        if not self._peer_block.isVisible():
            return
        self._sync_tap_chat_button(
            tapped=tapped,
            tap_active=tap_active,
            is_self=self._peer_is_self,
        )

    def _sync_tap_chat_button(self, *, tapped: bool, tap_active: bool, is_self: bool) -> None:
        del tapped, tap_active
        if is_self:
            self._tap_chat_btn.setVisible(False)
            return
        self._tap_chat_btn.setVisible(True)
        self._tap_chat_btn.setEnabled(True)
        self._tap_chat_btn.setToolTip(
            "Open private tap chat (starts a tap automatically if needed)"
        )

    def refresh_tap_notes(self) -> None:
        if self._peer_client_id:
            self._refresh_tap_list(self._peer_client_id)

    def _refresh_tap_list(self, client_id: str) -> None:
        while self._tap_list_layout.count():
            item = self._tap_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        saved = get_tap_store().all_for_peer(client_id)
        if not saved:
            empty = QLabel("(no tap notes)")
            empty.setStyleSheet("color: #565f89; font-size: 11px;")
            self._tap_list_layout.addWidget(empty)
            return
        for tap in saved:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            mark = "✓ " if tap.done else "○ "
            label = TapNoteRowLabel(tap.save_id, f"{mark}{tap.display_subject[:48]}")
            label.setStyleSheet("color: #a9b1d6; font-size: 11px;")
            label.double_clicked.connect(self._on_view_tap_note)
            delete_btn = QPushButton("✕")
            delete_btn.setFixedSize(24, 24)
            delete_btn.setStyleSheet(
                "QPushButton { color: #f7768e; font-weight: 700; border: none; }"
                "QPushButton:hover { color: #ff9eaa; }"
            )
            delete_btn.clicked.connect(lambda _c=False, sid=tap.save_id: self._on_delete_tap_note(sid))
            row_layout.addWidget(label, stretch=1)
            row_layout.addWidget(delete_btn)
            self._tap_list_layout.addWidget(row)

    def _add_peer_tap_note(self) -> None:
        if self._peer_link_id and self._peer_client_id:
            self._on_add_tap_note(self._peer_link_id, self._peer_client_id)

    def _gate_changed(self, value: int) -> None:
        self._gate_label.setText(f"{value} dB")
        self._on_gate(float(value))

    def _noise_changed(self, value: int) -> None:
        self._noise_label.setText(f"{value}%")
        self._on_noise(value / 100.0)

    def _master_changed(self, value: int) -> None:
        self._on_master_volume(value / 100.0)

    def _mic_volume_changed(self, value: int) -> None:
        self._self_strip.set_volume_label(f"{value}%")
        self._on_mic_volume(value / 100.0)

    def set_host_password_status(self, is_set: bool) -> None:
        self._host_pwd_status.setText(
            "Host password: set" if is_set else "Host password: not set"
        )

    def set_room_password_display(self, visible: bool, text: str) -> None:
        self._room_pwd_label.setVisible(visible)
        self._room_pwd_label.setText(text if visible else "")

    def _save_host_password(self) -> None:
        pwd = self._host_pwd.text().strip()
        if not pwd:
            return
        self._on_host_password(pwd)
        self._host_pwd.clear()
        self.set_host_password_status(True)

    def _input_changed(self, index: int) -> None:
        if index >= 0:
            self._on_input_device(self._input_combo.itemData(index))

    def _output_changed(self, index: int) -> None:
        if index >= 0:
            self._on_output_device(self._output_combo.itemData(index))

    def _peer_volume_changed(self, value: int) -> None:
        if self._open_composite:
            self._on_peer_volume(self._open_composite, value / 100.0)

    def _peer_listen_toggled(self, muted: bool) -> None:
        if self._open_composite:
            self._listen_mute_btn.setText("🔇" if muted else "🔊")
            self._on_peer_listen_mute(self._open_composite, muted)

    def _do_tap(self) -> None:
        if self._peer_link_id and self._peer_client_id:
            self._on_peer_tap(self._peer_link_id, self._peer_client_id)

    def _do_tap_chat(self) -> None:
        if self._peer_link_id:
            self._on_peer_tap_chat(self._peer_link_id, self._peer_client_id)

