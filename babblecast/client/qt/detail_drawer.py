"""Right column — horizontally sliding panel with collapsible self-audio + peer details."""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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

        self._open_composite: str | None = None
        self._peer_client_id = ""
        self._peer_link_id = ""
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
        self_layout.setSpacing(4)

        self._self_strip = MeterVolumeStrip(
            volume_label="Mic",
            on_volume=self._mic_volume_changed,
        )
        self_layout.addWidget(self._self_strip)

        self._gate_slider = QSlider(Qt.Orientation.Horizontal)
        self._gate_slider.setRange(-80, 0)
        self._gate_label = QLabel("-40 dB")
        self._gate_slider.valueChanged.connect(self._gate_changed)
        self_layout.addWidget(QLabel("Noise gate"))
        self_layout.addWidget(self._gate_slider)
        self_layout.addWidget(self._gate_label)

        self._noise_slider = QSlider(Qt.Orientation.Horizontal)
        self._noise_slider.setRange(0, 100)
        self._noise_label = QLabel("50%")
        self._noise_slider.valueChanged.connect(self._noise_changed)
        self_layout.addWidget(QLabel("Noise suppression"))
        self_layout.addWidget(self._noise_slider)
        self_layout.addWidget(self._noise_label)

        self._master_slider = QSlider(Qt.Orientation.Horizontal)
        self._master_slider.setRange(0, 200)
        self._master_label = QLabel("100%")
        self._master_slider.valueChanged.connect(self._master_changed)
        self_layout.addWidget(QLabel("Master output volume"))
        self_layout.addWidget(self._master_slider)
        self_layout.addWidget(self._master_label)

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

        self._taps_section = CollapsibleSection("Taps", expanded=True)
        taps_layout = self._taps_section.body_layout()
        self._tap_list = QListWidget()
        self._tap_list.itemDoubleClicked.connect(self._tap_list_activated)
        taps_layout.addWidget(self._tap_list)
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
        self._master_slider.blockSignals(True)
        self._gate_slider.setValue(int(gate_db))
        self._gate_label.setText(f"{int(gate_db)} dB")
        self._noise_slider.setValue(int(noise_pct))
        self._noise_label.setText(f"{int(noise_pct)}%")
        self._master_slider.setValue(int(master_pct))
        self._master_label.setText(f"{int(master_pct)}%")
        self._self_strip.set_volume_percent(int(mic_pct))
        self._gate_slider.blockSignals(False)
        self._noise_slider.blockSignals(False)
        self._master_slider.blockSignals(False)

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
        is_self: bool,
        tech_lines: list[str],
    ) -> None:
        self._ensure_panel_open()
        self._open_composite = composite
        self._peer_link_id = link_id
        self._peer_client_id = client_id
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
        self._tap_chat_btn.setVisible(not is_self and tapped)
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

    def _refresh_tap_list(self, client_id: str) -> None:
        self._tap_list.clear()
        saved = get_tap_store().all_for_peer(client_id)
        for tap in saved:
            mark = "✓ " if tap.done else "○ "
            item = QListWidgetItem(f"{mark}{tap.reminder[:48]}")
            item.setData(Qt.ItemDataRole.UserRole, tap.save_id)
            self._tap_list.addItem(item)
        if not saved:
            item = QListWidgetItem("(no saved taps)")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._tap_list.addItem(item)

    def _gate_changed(self, value: int) -> None:
        self._gate_label.setText(f"{value} dB")
        self._on_gate(float(value))

    def _noise_changed(self, value: int) -> None:
        self._noise_label.setText(f"{value}%")
        self._on_noise(value / 100.0)

    def _master_changed(self, value: int) -> None:
        self._master_label.setText(f"{value}%")
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

    def _tap_list_activated(self, item: QListWidgetItem) -> None:
        save_id = item.data(Qt.ItemDataRole.UserRole)
        if save_id and self._peer_link_id:
            self._on_reopen_tap(self._peer_link_id, str(save_id))
