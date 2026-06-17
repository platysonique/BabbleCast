"""Main BabbleCast PyQt6 window."""

from __future__ import annotations

import socket
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from babblecast.audio.devices import list_input_devices, list_output_devices
from babblecast.client.qt.participant_widget import ParticipantWidget
from babblecast.client.qt.server_runner import EmbeddedServer
from babblecast.client.qt.styles import STYLESHEET
from babblecast.client.session import ClientSession
from babblecast.config import get_settings, save_settings
from babblecast.discovery import DiscoveredServer, ServerDiscovery


class MainWindow(QMainWindow):
    status_message = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BabbleCast")
        self.setMinimumSize(960, 640)
        self.setStyleSheet(STYLESHEET)
        self._settings = get_settings()
        self._session = ClientSession(
            on_presence=self._on_presence,
            on_chat=self._on_chat,
            on_rooms=self._on_rooms,
            on_connected=self._on_connected,
            on_disconnected=self._on_disconnected,
            on_error=self._on_error,
        )
        self._embedded = EmbeddedServer(server_name=socket.gethostname())
        self._discovery = ServerDiscovery(on_update=self._on_servers_discovered)
        self._participant_widgets: dict[str, ParticipantWidget] = {}
        self._self_muted = False
        self._ptt_held = False
        self._servers: list[DiscoveredServer] = []

        self._build_ui()
        self._load_devices()
        self._discovery.start()

        if self._settings.window_geometry and len(self._settings.window_geometry) == 4:
            self.setGeometry(*self._settings.window_geometry)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_ui_state)
        self._status_timer.start(100)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        # Left — servers & rooms
        left = QVBoxLayout()
        title = QLabel("BabbleCast")
        title.setObjectName("title")
        left.addWidget(title)

        self._status = QLabel("Offline")
        self._status.setObjectName("status")
        left.addWidget(self._status)

        srv_group = QGroupBox("Servers")
        srv_layout = QVBoxLayout(srv_group)
        self._server_list = QListWidget()
        self._server_list.itemDoubleClicked.connect(self._connect_selected_server)
        srv_layout.addWidget(self._server_list)
        srv_btns = QHBoxLayout()
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._connect_selected_server)
        self._host_server_btn = QPushButton("Host Server")
        self._host_server_btn.clicked.connect(self._toggle_host)
        srv_btns.addWidget(self._connect_btn)
        srv_btns.addWidget(self._host_server_btn)
        srv_layout.addLayout(srv_btns)
        left.addWidget(srv_group)

        room_group = QGroupBox("Rooms")
        room_layout = QVBoxLayout(room_group)
        self._room_list = QListWidget()
        self._room_list.itemDoubleClicked.connect(self._join_selected_room)
        room_layout.addWidget(self._room_list)
        room_row = QHBoxLayout()
        self._new_room_edit = QLineEdit()
        self._new_room_edit.setPlaceholderText("New room name…")
        self._create_room_btn = QPushButton("Create")
        self._create_room_btn.clicked.connect(self._create_room)
        room_row.addWidget(self._new_room_edit)
        room_row.addWidget(self._create_room_btn)
        room_layout.addLayout(room_row)
        left.addWidget(room_group)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Your name"))
        self._name_edit = QLineEdit(self._settings.display_name or socket.gethostname())
        self._name_edit.editingFinished.connect(self._save_name)
        name_row.addWidget(self._name_edit)
        left.addLayout(name_row)
        left.addStretch()
        root.addLayout(left, 1)

        # Center — participants
        center = QVBoxLayout()
        part_group = QGroupBox("In Room")
        part_layout = QVBoxLayout(part_group)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._participants_container = QWidget()
        self._participants_layout = QVBoxLayout(self._participants_container)
        self._participants_layout.addStretch()
        scroll.setWidget(self._participants_container)
        part_layout.addWidget(scroll)
        center.addWidget(part_group, 2)

        chat_group = QGroupBox("Text Chat")
        chat_layout = QVBoxLayout(chat_group)
        self._chat_log = QTextEdit()
        self._chat_log.setReadOnly(True)
        chat_layout.addWidget(self._chat_log)
        chat_input_row = QHBoxLayout()
        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText("Type a message…")
        self._chat_input.returnPressed.connect(self._send_chat)
        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self._send_chat)
        chat_input_row.addWidget(self._chat_input)
        chat_input_row.addWidget(send_btn)
        chat_layout.addLayout(chat_input_row)
        center.addWidget(chat_group, 1)
        root.addLayout(center, 3)

        # Right — audio controls
        right = QVBoxLayout()
        audio_group = QGroupBox("Audio")
        audio_layout = QVBoxLayout(audio_group)

        audio_layout.addWidget(QLabel("Microphone"))
        self._input_combo = QComboBox()
        self._input_combo.currentIndexChanged.connect(self._input_changed)
        audio_layout.addWidget(self._input_combo)

        audio_layout.addWidget(QLabel("Speakers"))
        self._output_combo = QComboBox()
        self._output_combo.currentIndexChanged.connect(self._output_changed)
        audio_layout.addWidget(self._output_combo)

        audio_layout.addWidget(QLabel("Noise gate (dB)"))
        self._gate_slider = QSlider(Qt.Orientation.Horizontal)
        self._gate_slider.setRange(-80, 0)
        self._gate_slider.setValue(int(self._settings.gate_threshold_db))
        self._gate_label = QLabel(f"{self._settings.gate_threshold_db:.0f} dB")
        self._gate_slider.valueChanged.connect(self._gate_changed)
        audio_layout.addWidget(self._gate_slider)
        audio_layout.addWidget(self._gate_label)

        audio_layout.addWidget(QLabel("Noise suppression"))
        self._noise_slider = QSlider(Qt.Orientation.Horizontal)
        self._noise_slider.setRange(0, 100)
        self._noise_slider.setValue(int(self._settings.noise_suppression * 100))
        self._noise_label = QLabel(f"{int(self._settings.noise_suppression * 100)}%")
        self._noise_slider.valueChanged.connect(self._noise_changed)
        audio_layout.addWidget(self._noise_slider)
        audio_layout.addWidget(self._noise_label)

        btn_row = QHBoxLayout()
        self._mute_btn = QPushButton("Mute")
        self._mute_btn.setCheckable(True)
        self._mute_btn.setObjectName("danger")
        self._mute_btn.toggled.connect(self._toggle_mute)
        self._ptt_btn = QPushButton("PTT (Space)")
        self._ptt_btn.setCheckable(True)
        self._ptt_btn.pressed.connect(lambda: self._set_ptt(True))
        self._ptt_btn.released.connect(lambda: self._set_ptt(False))
        btn_row.addWidget(self._mute_btn)
        btn_row.addWidget(self._ptt_btn)
        audio_layout.addLayout(btn_row)

        hint = QLabel(
            "Uses shared audio streams — does not hijack Spotify, YouTube, or system audio."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #565f89; font-size: 11px;")
        audio_layout.addWidget(hint)
        right.addWidget(audio_group)
        right.addStretch()
        root.addLayout(right, 1)

    def _load_devices(self) -> None:
        self._input_combo.blockSignals(True)
        self._output_combo.blockSignals(True)
        self._input_combo.clear()
        self._output_combo.clear()
        self._input_devices = list_input_devices()
        self._output_devices = list_output_devices()
        sel_in = 0
        sel_out = 0
        for i, dev in enumerate(self._input_devices):
            self._input_combo.addItem(dev.label, dev.storage_key)
            if self._settings.input_device == dev.storage_key:
                sel_in = i
        for i, dev in enumerate(self._output_devices):
            self._output_combo.addItem(dev.label, dev.storage_key)
            if self._settings.output_device == dev.storage_key:
                sel_out = i
        if self._input_devices:
            self._input_combo.setCurrentIndex(sel_in)
        if self._output_devices:
            self._output_combo.setCurrentIndex(sel_out)
        self._input_combo.blockSignals(False)
        self._output_combo.blockSignals(False)

    def _save_name(self) -> None:
        self._settings.display_name = self._name_edit.text().strip()
        save_settings(self._settings)

    def _on_servers_discovered(self, servers: list[DiscoveredServer]) -> None:
        self._servers = servers
        self._server_list.clear()
        for s in servers:
            item = QListWidgetItem(s.label)
            item.setData(Qt.ItemDataRole.UserRole, (s.host, s.ws_port))
            self._server_list.addItem(item)

    def _connect_selected_server(self) -> None:
        if self._session.connected:
            self._session.disconnect()
            self._status.setText("Disconnected")
            return
        item = self._server_list.currentItem()
        if item:
            host, port = item.data(Qt.ItemDataRole.UserRole)
            self._connect(host, port)

    def _connect(self, host: str, port: int) -> None:
        self._save_name()
        self._settings.display_name = self._name_edit.text().strip()
        save_settings(self._settings)
        self._session.update_settings(self._settings)
        self._status.setText(f"Connecting to {host}:{port}…")
        self._session.connect(host, port)

    def _toggle_host(self) -> None:
        if self._embedded.running:
            self._embedded.stop()
            self._host_server_btn.setText("Host Server")
            self._status.setText("Server stopped")
        else:
            self._embedded.start()
            self._host_server_btn.setText("Stop Server")
            QTimer.singleShot(500, self._auto_connect_local)

    def _auto_connect_local(self) -> None:
        if self._embedded.running and not self._session.connected:
            self._connect(self._embedded.host, self._embedded.ws_port)

    def _on_connected(self) -> None:
        self._status.setText("Connected")
        self._session.request_rooms()

    def _on_disconnected(self, reason: str) -> None:
        self._status.setText(f"Offline — {reason}")
        self._clear_participants()

    def _on_error(self, message: str) -> None:
        QMessageBox.warning(self, "BabbleCast", message)

    def _on_presence(self, _room_id: str, participants: list[dict]) -> None:
        self._last_participants = participants
        self._update_participant_widgets(participants)

    def _on_chat(self, data: dict) -> None:
        name = data.get("name", "?")
        text = data.get("text", "")
        ts = datetime.now().strftime("%H:%M")
        self._chat_log.append(f"<b>[{ts}] {name}</b>: {text}")

    def _on_rooms(self, rooms: list[dict]) -> None:
        self._room_list.clear()
        for r in rooms:
            label = f"{r.get('name', 'Room')} ({r.get('member_count', 0)})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, r.get("room_id"))
            self._room_list.addItem(item)

    def _create_room(self) -> None:
        name = self._new_room_edit.text().strip()
        if name:
            self._session.create_room(name)
            self._new_room_edit.clear()

    def _join_selected_room(self) -> None:
        item = self._room_list.currentItem()
        if item:
            room_id = item.data(Qt.ItemDataRole.UserRole)
            self._session.join_room(str(room_id))

    def _send_chat(self) -> None:
        text = self._chat_input.text().strip()
        if text:
            self._session.send_chat(text)
            self._chat_input.clear()

    def _toggle_mute(self, checked: bool) -> None:
        self._self_muted = checked
        self._session.set_muted(checked)

    def _set_ptt(self, active: bool) -> None:
        self._ptt_held = active
        self._ptt_btn.setObjectName("pttActive" if active else "")
        self._ptt_btn.setStyleSheet("")
        self._session.set_ptt(active)

    def _gate_changed(self, value: int) -> None:
        self._gate_label.setText(f"{value} dB")
        self._session.set_gate_db(float(value))

    def _noise_changed(self, value: int) -> None:
        self._noise_label.setText(f"{value}%")
        self._session.set_noise_suppression(value / 100.0)

    def _input_changed(self, index: int) -> None:
        if index < 0:
            return
        key = self._input_combo.itemData(index)
        self._session.set_input_device(key)

    def _output_changed(self, index: int) -> None:
        if index < 0:
            return
        key = self._output_combo.itemData(index)
        self._session.set_output_device(key)

    def _update_participant_widgets(self, participants: list[dict]) -> None:
        seen = set()
        my_id = self._session.client_id
        for p in participants:
            cid = p.get("client_id", "")
            seen.add(cid)
            if cid not in self._participant_widgets:
                w = ParticipantWidget(cid, p.get("name", "?"), is_self=(cid == my_id))
                w.volume_changed.connect(self._session.set_participant_volume)
                w.mute_toggled.connect(self._session.set_participant_muted)
                self._participant_widgets[cid] = w
                self._participants_layout.insertWidget(self._participants_layout.count() - 1, w)
            self._participant_widgets[cid].update_state(
                name=p.get("name", "?"),
                voice_level=float(p.get("voice_level", 0)),
                muted=bool(p.get("muted", False)),
                speaking=bool(p.get("speaking", False)),
                volume=float(p.get("volume", 1.0)),
            )
        for cid in list(self._participant_widgets):
            if cid not in seen:
                w = self._participant_widgets.pop(cid)
                w.deleteLater()

    def _clear_participants(self) -> None:
        for w in self._participant_widgets.values():
            w.deleteLater()
        self._participant_widgets.clear()

    def _refresh_ui_state(self) -> None:
        if self._session.connected:
            self._connect_btn.setText("Disconnect")
        else:
            self._connect_btn.setText("Connect")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if self._self_muted:
                self._set_ptt(True)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if self._self_muted:
                self._set_ptt(False)
        super().keyReleaseEvent(event)

    def closeEvent(self, event) -> None:
        geo = self.geometry()
        self._settings.window_geometry = [geo.x(), geo.y(), geo.width(), geo.height()]
        save_settings(self._settings)
        self._discovery.stop()
        self._session.disconnect()
        self._embedded.stop()
        super().closeEvent(event)
