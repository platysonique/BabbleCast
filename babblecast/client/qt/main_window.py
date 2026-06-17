"""Main BabbleCast PyQt6 window — multi-server bridge + Tap."""

from __future__ import annotations

import html
import socket
import time
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QDialog,
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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from babblecast.audio.devices import list_input_devices, list_output_devices
from babblecast.client.bridge import BridgeManager
from babblecast.client.qt.credentials_dialog import ConnectCredentialsDialog, HostCredentialsDialog
from babblecast.client.qt.detail_drawer import DetailDrawer
from babblecast.client.qt.participant_widget import ParticipantWidget
from babblecast.client.qt.server_link_widget import ServerLinkWidget
from babblecast.client.qt.styles import STYLESHEET
from babblecast.client.qt.tap_chat_dialog import TapChatDialog
from babblecast.config import get_settings, save_settings
from babblecast.constants import composite_participant_key
from babblecast.discovery import DiscoveredServer, ServerDiscovery
from babblecast.client.room_controller import (
    chat_lines,
    purge_room_chat,
    record_incoming_chat,
    resolve_room,
    should_disconnect_failed_connect,
)
from babblecast.protocol import is_name_taken_error
from babblecast.server.embedded import EmbeddedServer
from babblecast.taps import get_tap_store


class _UiSignals(QObject):
    """Marshals background-thread callbacks onto the Qt GUI thread."""

    link_connected = pyqtSignal(str)
    link_disconnected = pyqtSignal(str, str)
    presence = pyqtSignal(str, str, list)
    chat = pyqtSignal(str, dict)
    rooms = pyqtSignal(str, list)
    joined = pyqtSignal(str, str, str)
    room_deleted = pyqtSignal(str, str)
    error = pyqtSignal(str, str, str)
    tap_received = pyqtSignal(str, dict)
    tap_chat = pyqtSignal(str, dict)
    tap_open = pyqtSignal(str, str)
    tap_end = pyqtSignal(str, str)
    servers_found = pyqtSignal(list)
    embedded_started = pyqtSignal(str, int)
    embedded_failed = pyqtSignal(str)
    embedded_stopped = pyqtSignal()
    local_mic_level = pyqtSignal(float)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BabbleCast")
        self.setMinimumSize(1024, 680)
        self.setStyleSheet(STYLESHEET)
        self._settings = get_settings()
        self._ui = _UiSignals()
        self._ui.servers_found.connect(self._on_servers_discovered)
        self._ui.link_connected.connect(self._on_link_connected)
        self._ui.link_disconnected.connect(self._on_link_disconnected)
        self._ui.error.connect(self._on_error)
        self._ui.presence.connect(self._on_presence)
        self._ui.chat.connect(self._on_chat)
        self._ui.rooms.connect(self._on_rooms)
        self._ui.joined.connect(self._on_joined)
        self._ui.room_deleted.connect(self._on_room_deleted)
        self._ui.tap_received.connect(self._on_tap_received)
        self._ui.tap_chat.connect(self._on_tap_chat)
        self._ui.tap_open.connect(self._on_tap_open)
        self._ui.tap_end.connect(self._on_tap_end)
        self._ui.embedded_started.connect(self._on_embedded_started)
        self._ui.embedded_failed.connect(self._on_embedded_failed)
        self._ui.embedded_stopped.connect(self._on_embedded_stopped)
        self._ui.local_mic_level.connect(self._on_local_mic_level)

        self._bridge = BridgeManager(
            on_link_connected=lambda lid: self._ui.link_connected.emit(lid),
            on_link_disconnected=lambda lid, r: self._ui.link_disconnected.emit(lid, r),
            on_presence=lambda lid, rid, p: self._ui.presence.emit(lid, rid, p),
            on_chat=lambda lid, d: self._ui.chat.emit(lid, d),
            on_rooms=lambda lid, r: self._ui.rooms.emit(lid, r),
            on_joined=lambda lid, rid, rn: self._ui.joined.emit(lid, rid, rn),
            on_room_deleted=lambda lid, rid: self._ui.room_deleted.emit(lid, rid),
            on_error=lambda lid, m, ec=None: self._ui.error.emit(lid, m, ec or ""),
            on_tap_received=lambda lid, d: self._ui.tap_received.emit(lid, d),
            on_tap_chat=lambda lid, d: self._ui.tap_chat.emit(lid, d),
            on_tap_open=lambda lid, tid: self._ui.tap_open.emit(lid, tid),
            on_tap_end=lambda lid, tid: self._ui.tap_end.emit(lid, tid),
            on_local_mic_level=lambda lvl: self._ui.local_mic_level.emit(lvl),
        )
        self._embedded: EmbeddedServer | None = None
        self._discovery = ServerDiscovery(on_update=lambda s: self._ui.servers_found.emit(s))
        self._participant_widgets: dict[str, ParticipantWidget] = {}
        self._link_widgets: dict[str, ServerLinkWidget] = {}
        self._presence_by_link: dict[str, list[dict]] = {}
        self._active_link_id: str | None = None
        self._self_muted = False
        self._ptt_held = False
        self._servers: list[DiscoveredServer] = []
        self._tap_ids: dict[tuple[str, str], str] = {}
        self._tap_dialogs: dict[tuple[str, str], TapChatDialog] = {}
        self._peer_participant_data: dict[str, dict] = {}
        self._peer_names: dict[tuple[str, str], str] = {}
        self._room_by_link: dict[str, tuple[str, str]] = {}
        self._pending_embedded_connect = False
        self._embedded_host: str = "127.0.0.1"
        self._embedded_port: int = 8765

        self._build_ui()
        self._load_devices()
        self._discovery.start()

        if self._settings.window_geometry and len(self._settings.window_geometry) == 4:
            self.setGeometry(*self._settings.window_geometry)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        left = QVBoxLayout()
        title = QLabel("BabbleCast")
        title.setObjectName("title")
        left.addWidget(title)

        self._status = QLabel("Offline — connect to one or more servers")
        self._status.setObjectName("status")
        self._status.setWordWrap(True)
        left.addWidget(self._status)

        discover_group = QGroupBox("Discover")
        discover_layout = QVBoxLayout(discover_group)
        self._server_list = QListWidget()
        self._server_list.itemDoubleClicked.connect(self._connect_selected_server)
        discover_layout.addWidget(self._server_list)
        discover_btns = QHBoxLayout()
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._connect_selected_server)
        self._host_server_btn = QPushButton("Host Server")
        self._host_server_btn.clicked.connect(self._toggle_host)
        discover_btns.addWidget(self._connect_btn)
        discover_btns.addWidget(self._host_server_btn)
        discover_layout.addLayout(discover_btns)
        left.addWidget(discover_group)

        connected_group = QGroupBox("Connected (mixed audio)")
        connected_layout = QVBoxLayout(connected_group)
        self._connected_scroll = QScrollArea()
        self._connected_scroll.setWidgetResizable(True)
        self._connected_container = QWidget()
        self._connected_layout = QVBoxLayout(self._connected_container)
        self._connected_layout.addStretch()
        self._connected_scroll.setWidget(self._connected_container)
        connected_layout.addWidget(self._connected_scroll)
        hint = QLabel("🔊 = mute hearing · 🎤 = mute mic to that server only")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #565f89; font-size: 11px;")
        connected_layout.addWidget(hint)
        left.addWidget(connected_group)

        room_group = QGroupBox("Rooms (active server)")
        room_layout = QVBoxLayout(room_group)
        room_hint = QLabel("Click a room to switch · right-click to delete")
        room_hint.setStyleSheet("color: #888; font-size: 11px;")
        room_layout.addWidget(room_hint)
        self._room_list = QListWidget()
        self._room_list.itemClicked.connect(self._join_room_item)
        self._room_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._room_list.customContextMenuRequested.connect(self._room_context_menu)
        room_layout.addWidget(self._room_list)
        room_row = QHBoxLayout()
        self._new_room_edit = QLineEdit()
        self._new_room_edit.setPlaceholderText("New room name…")
        self._create_room_btn = QPushButton("Create")
        self._create_room_btn.clicked.connect(self._create_room)
        room_row.addWidget(self._new_room_edit)
        room_row.addWidget(self._create_room_btn)
        room_layout.addLayout(room_row)
        self._current_room_label = QLabel("In room: —")
        self._current_room_label.setStyleSheet("color: #7aa2f7; font-weight: 600;")
        room_layout.addWidget(self._current_room_label)
        left.addWidget(room_group)

        left.addStretch()
        root.addLayout(left, 1)

        center = QVBoxLayout()
        part_group = QGroupBox("In room — double-click a name for controls")
        part_layout = QVBoxLayout(part_group)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._participants_container = QWidget()
        self._participants_layout = QVBoxLayout(self._participants_container)
        self._participants_layout.addStretch()
        scroll.setWidget(self._participants_container)
        part_layout.addWidget(scroll)
        center.addWidget(part_group, 2)

        chat_group = QGroupBox("Text chat (active server)")
        chat_layout = QVBoxLayout(chat_group)
        self._chat_log = QTextEdit()
        self._chat_log.setReadOnly(True)
        chat_layout.addWidget(self._chat_log)
        chat_input_row = QHBoxLayout()
        self._mute_btn = QPushButton("🎤")
        self._mute_btn.setCheckable(True)
        self._mute_btn.setToolTip("Mute your mic on all servers")
        self._mute_btn.setFixedWidth(44)
        self._mute_btn.toggled.connect(self._toggle_mute)
        self._ptt_btn = QPushButton("PTT")
        self._ptt_btn.setCheckable(True)
        self._ptt_btn.setToolTip("Push-to-talk (hold Space when mic muted)")
        self._ptt_btn.setFixedWidth(52)
        self._ptt_btn.pressed.connect(lambda: self._set_ptt(True))
        self._ptt_btn.released.connect(lambda: self._set_ptt(False))
        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText("Type a message, then hit ↵")
        self._chat_input.returnPressed.connect(self._send_chat)
        chat_input_row.addWidget(self._mute_btn)
        chat_input_row.addWidget(self._ptt_btn)
        chat_input_row.addWidget(self._chat_input, stretch=1)
        chat_layout.addLayout(chat_input_row)
        center.addWidget(chat_group, 1)
        root.addLayout(center, 3)

        self._drawer = DetailDrawer(
            on_gate=self._bridge.set_gate_db,
            on_noise=self._bridge.set_noise_suppression,
            on_input_device=self._bridge.set_input_device,
            on_output_device=self._bridge.set_output_device,
            on_master_volume=self._bridge.set_master_output_volume,
            on_mic_volume=self._bridge.set_input_volume,
            on_peer_volume=self._bridge.set_participant_volume,
            on_peer_listen_mute=self._bridge.set_participant_muted,
            on_peer_tap=self._send_tap,
            on_peer_tap_chat=self._open_tap_for_peer,
            on_reopen_tap=self._reinsert_saved_tap,
            panel_expanded=self._settings.ui_panel_expanded,
            self_audio_expanded=self._settings.ui_self_audio_expanded,
        )
        self._drawer.panel_expanded_changed.connect(self._on_panel_expanded_changed)
        self._drawer.self_audio_expanded_changed.connect(self._on_self_audio_expanded_changed)
        self._drawer.input_monitoring_changed.connect(self._on_input_monitoring_changed)
        self._drawer.set_self_levels(
            self._settings.gate_threshold_db,
            self._settings.noise_suppression * 100,
            self._settings.output_volume * 100,
            self._settings.input_volume * 100,
        )
        root.addWidget(self._drawer, 0)
        if self._settings.ui_panel_expanded and self._settings.ui_self_audio_expanded:
            self._bridge.ensure_input_monitoring()

    def _load_devices(self) -> None:
        self._input_devices = list_input_devices()
        self._output_devices = list_output_devices()
        sel_in = sel_out = 0
        for i, dev in enumerate(self._input_devices):
            if self._settings.input_device == dev.storage_key:
                sel_in = i
        for i, dev in enumerate(self._output_devices):
            if self._settings.output_device == dev.storage_key:
                sel_out = i
        self._drawer.populate_devices(self._input_devices, self._output_devices, sel_in, sel_out)

    def _on_local_mic_level(self, level: float) -> None:
        self._drawer.set_local_mic_level(level)

    def _on_panel_expanded_changed(self, expanded: bool) -> None:
        self._settings.ui_panel_expanded = expanded
        save_settings(self._settings)

    def _on_self_audio_expanded_changed(self, expanded: bool) -> None:
        self._settings.ui_self_audio_expanded = expanded
        save_settings(self._settings)

    def _on_input_monitoring_changed(self, needed: bool) -> None:
        if needed:
            self._bridge.ensure_input_monitoring()
        else:
            self._bridge.release_input_monitoring()

    def _on_servers_discovered(self, servers: list[DiscoveredServer]) -> None:
        self._servers = servers
        self._server_list.clear()
        for s in servers:
            item = QListWidgetItem(s.label)
            item.setData(Qt.ItemDataRole.UserRole, (s.host, s.ws_port))
            self._server_list.addItem(item)

    def _already_connected(self, host: str, port: int) -> bool:
        for link in self._bridge.links:
            if link.host == host and link.port == port and link.connected:
                return True
        return False

    def _connect_selected_server(self) -> None:
        item = self._server_list.currentItem()
        if item:
            host, port = item.data(Qt.ItemDataRole.UserRole)
            self._connect(host, port, label=item.text())

    def _connect(self, host: str, port: int, label: str | None = None) -> None:
        if self._already_connected(host, port):
            self._status.setText(f"Already connected to {host}:{port}")
            return
        server_label = label or f"{host}:{port}"
        dlg = ConnectCredentialsDialog(
            self._settings.display_name or socket.gethostname(),
            server_label,
            self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._settings.display_name = dlg.display_name
        save_settings(self._settings)
        self._bridge.update_settings(self._settings)
        self._status.setText(f"Connecting to {host}:{port}…")
        self._bridge.connect(host, port, label=label)

    def _toggle_host(self) -> None:
        if self._embedded and self._embedded.running:
            self._embedded.stop()
            self._embedded = None
            self._host_server_btn.setText("Host Server")
            self._status.setText("Server stopped")
            return
        default_server = (
            self._settings.hosted_server_name
            or self._settings.display_name
            or socket.gethostname()
        )
        dlg = HostCredentialsDialog(
            default_server,
            self._settings.display_name or socket.gethostname(),
            self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name = dlg.server_name
        self._settings.hosted_server_name = name
        self._settings.display_name = dlg.display_name
        save_settings(self._settings)
        self._bridge.update_settings(self._settings)
        self._pending_embedded_connect = True
        self._status.setText(f"Starting server “{name}”…")

        def _on_started(host: str, port: int) -> None:
            self._ui.embedded_started.emit(host, port)

        def _on_failed(reason: str) -> None:
            self._ui.embedded_failed.emit(reason)

        def _on_stopped() -> None:
            self._ui.embedded_stopped.emit()

        self._embedded = EmbeddedServer(
            server_name=name,
            on_started=_on_started,
            on_failed=_on_failed,
            on_stopped=_on_stopped,
        )
        self._embedded.start()

    def _on_embedded_started(self, host: str, port: int) -> None:
        self._embedded_host = host
        self._embedded_port = port
        self._host_server_btn.setText("Stop Server")
        self._status.setText(f"Hosting on {host}:{port} — connecting…")
        if self._pending_embedded_connect and self._embedded and self._embedded.running:
            self._pending_embedded_connect = False
            if not self._already_connected(host, port):
                self._connect(host, port)
            else:
                self._status.setText(f"Hosting on {host}:{port} — already connected")

    def _on_embedded_failed(self, reason: str) -> None:
        self._pending_embedded_connect = False
        self._embedded = None
        self._host_server_btn.setText("Host Server")
        self._status.setText("Server failed to start")
        detail = reason
        if "98" in reason or "already in use" in reason.lower():
            detail = (
                f"{reason}\n\nPort 8765 is already in use. "
                "Another BabbleCast may be running — use Connect instead of Host."
            )
        QMessageBox.critical(self, "BabbleCast — host failed", detail)

    def _on_embedded_stopped(self) -> None:
        self._pending_embedded_connect = False
        if self._embedded and not self._embedded.running:
            self._embedded = None
        self._host_server_btn.setText("Host Server")

    def _add_link_widget(self, link_id: str) -> None:
        link = self._bridge.get_link(link_id)
        if not link or link_id in self._link_widgets:
            return
        w = ServerLinkWidget(link_id, link.label)
        w.listen_mute_toggled.connect(self._on_listen_mute)
        w.mic_mute_toggled.connect(self._on_mic_mute)
        w.disconnect_requested.connect(self._disconnect_link)
        w.selected.connect(self._set_active_link)
        self._link_widgets[link_id] = w
        self._connected_layout.insertWidget(self._connected_layout.count() - 1, w)
        if not self._active_link_id:
            self._set_active_link(link_id)

    def _remove_link_widget(self, link_id: str) -> None:
        w = self._link_widgets.pop(link_id, None)
        if w:
            w.deleteLater()
        self._presence_by_link.pop(link_id, None)
        if self._active_link_id == link_id:
            remaining = list(self._link_widgets.keys())
            self._active_link_id = remaining[0] if remaining else None
            self._room_list.clear()
            if self._active_link_id:
                self._bridge.request_rooms(self._active_link_id)
        self._rebuild_participants()

    def _on_link_connected(self, link_id: str) -> None:
        link = self._bridge.get_link(link_id)
        label = link.label if link else link_id
        self._add_link_widget(link_id)
        if link:
            self._link_widgets[link_id].update_label(link.label)
        self._bridge.request_rooms(link_id)
        self._refresh_status()
        self._status.setText(f"Connected — {label}")
        if link_id == self._active_link_id:
            self._reload_chat_log(link_id)

    def _on_link_disconnected(self, link_id: str, reason: str) -> None:
        self._remove_link_widget(link_id)
        for key in list(self._tap_ids):
            if key[0] == link_id:
                self._tap_ids.pop(key, None)
        for key, dlg in list(self._tap_dialogs.items()):
            if key[0] == link_id:
                dlg.close()
                self._tap_dialogs.pop(key, None)
        self._refresh_status()
        if not self._bridge.links:
            self._status.setText(f"Offline — {reason}")

    def _on_error(self, link_id: str, message: str, error_code: str = "") -> None:
        link = self._bridge.get_link(link_id)
        label = link.label if link else link_id
        code = error_code or None
        if is_name_taken_error(code, message):
            QMessageBox.warning(
                self,
                "Name taken",
                f"“{self._settings.display_name}” is already on {label}.\n\n"
                "Pick another display name when you connect (e.g. Cam A, Director 2).",
            )
        else:
            QMessageBox.warning(self, "BabbleCast", f"{label}: {message}")
        if link and should_disconnect_failed_connect(code, message, connected=link.connected):
            self._bridge.disconnect(link_id)
            self._status.setText(message)

    def _set_active_link(self, link_id: str) -> None:
        self._active_link_id = link_id
        for lid, w in self._link_widgets.items():
            w.set_active(lid == link_id)
        link = self._bridge.get_link(link_id)
        if link:
            self._status.setText(f"Active server: {link.label}")
        self._bridge.request_rooms(link_id)
        self._reload_chat_log(link_id)

    def _on_joined(self, link_id: str, room_id: str, room_name: str) -> None:
        self._room_by_link[link_id] = (room_id, room_name)
        if link_id == self._active_link_id:
            self._current_room_label.setText(f"In room: {room_name}")
            self._reload_chat_log(link_id)
            self._highlight_current_room(room_id)

    def _on_room_deleted(self, link_id: str, room_id: str) -> None:
        link = self._bridge.get_link(link_id)
        if link:
            purge_room_chat(link.host, link.port, room_id)
        if self._room_by_link.get(link_id, ("", ""))[0] == room_id:
            self._room_by_link.pop(link_id, None)
        if link_id == self._active_link_id:
            self._reload_chat_log(link_id)

    def _highlight_current_room(self, room_id: str) -> None:
        for i in range(self._room_list.count()):
            item = self._room_list.item(i)
            if item and str(item.data(Qt.ItemDataRole.UserRole)) == room_id:
                self._room_list.setCurrentItem(item)
                return

    def _reload_chat_log(self, link_id: str | None = None) -> None:
        lid = link_id or self._active_link_id
        if not lid:
            self._chat_log.clear()
            self._current_room_label.setText("In room: —")
            return
        link = self._bridge.get_link(lid)
        session = self._bridge.get_session(lid)
        if not link or not session or not session.room_id:
            self._chat_log.clear()
            self._chat_log.append("<i>Waiting for room…</i>")
            return
        room_id, room_name = resolve_room(
            lid,
            session.room_id,
            self._room_by_link,
        )
        lines = chat_lines(link.host, link.port, room_id)
        self._chat_log.clear()
        label = link.label
        self._current_room_label.setText(f"In room: {room_name}")
        self._chat_log.append(f"<i>Chat — {html.escape(label)} / {html.escape(room_name)}</i>")
        for line in lines:
            ts = datetime.fromtimestamp(line.ts).strftime("%H:%M")
            self._chat_log.append(
                f"<b>[{ts}] {html.escape(line.name)}</b>: {html.escape(line.text)}"
            )

    def _record_chat(self, link_id: str, data: dict) -> None:
        link = self._bridge.get_link(link_id)
        session = self._bridge.get_session(link_id)
        if not link or not session:
            return
        room_id = str(data.get("room_id") or session.room_id or "")
        room_name = resolve_room(link_id, session.room_id, self._room_by_link)[1]
        record_incoming_chat(link.host, link.port, room_id, data, room_name=room_name)

    def _append_chat_line(self, name: str, text: str, *, ts: float | None = None) -> None:
        stamp = datetime.fromtimestamp(ts or time.time()).strftime("%H:%M")
        self._chat_log.append(
            f"<b>[{stamp}] {html.escape(name)}</b>: {html.escape(text)}"
        )

    def _on_listen_mute(self, link_id: str, muted: bool) -> None:
        self._bridge.set_listen_muted(link_id, muted)
        w = self._link_widgets.get(link_id)
        if w:
            w._listen_btn.setText("🔇" if muted else "🔊")

    def _on_mic_mute(self, link_id: str, muted: bool) -> None:
        self._bridge.set_mic_muted(link_id, muted)
        w = self._link_widgets.get(link_id)
        if w:
            w._mic_btn.setText("🎤✕" if muted else "🎤")

    def _disconnect_link(self, link_id: str) -> None:
        self._bridge.disconnect(link_id)

    def _on_presence(self, link_id: str, _room_id: str, participants: list[dict]) -> None:
        self._presence_by_link[link_id] = participants
        self._rebuild_participants()

    def _rebuild_participants(self) -> None:
        seen: set[str] = set()
        link = self._bridge.get_link
        for lid, participants in self._presence_by_link.items():
            ls = link(lid)
            server_label = ls.label if ls else lid
            my_id = ls.client_id if ls else ""
            for p in participants:
                cid = str(p.get("client_id", ""))
                composite = composite_participant_key(lid, cid)
                seen.add(composite)
                self._peer_names[(lid, cid)] = str(p.get("name", "?"))
                self._peer_participant_data[composite] = dict(p)
                pending = ls.pending_taps if ls else set()
                if composite not in self._participant_widgets:
                    w = ParticipantWidget(
                        composite,
                        str(p.get("name", "?")),
                        server_label,
                        is_self=(cid == my_id),
                    )
                    w.double_clicked.connect(self._toggle_peer_drawer)
                    self._participant_widgets[composite] = w
                    self._participants_layout.insertWidget(self._participants_layout.count() - 1, w)
                w = self._participant_widgets[composite]
                w.set_tapped(cid in pending)
                local_muted = self._settings.per_user_muted.get(composite, False)
                local_vol = self._settings.per_user_volumes.get(
                    composite, float(p.get("volume", 1.0))
                )
                w.update_state(
                    name=str(p.get("name", "?")),
                    voice_level=float(p.get("voice_level", 0)),
                    muted=local_muted,
                    speaking=bool(p.get("speaking", False)),
                    volume=local_vol,
                    server_label=server_label,
                )
                if self._drawer.is_peer_open(composite):
                    self._drawer.update_peer_meter(
                        float(p.get("voice_level", 0)),
                        bool(p.get("speaking", False)),
                        local_vol,
                        local_muted,
                    )
        for key in list(self._participant_widgets):
            if key not in seen:
                if self._drawer.is_peer_open(key):
                    self._drawer.close_peer()
                self._participant_widgets.pop(key).deleteLater()
                self._peer_participant_data.pop(key, None)

    def _toggle_peer_drawer(self, composite: str) -> None:
        link_id, _, client_id = composite.partition(":")
        p = self._peer_participant_data.get(composite, {})
        w = self._participant_widgets.get(composite)
        if not w:
            return
        link = self._bridge.get_link(link_id)
        server_label = w.server_label
        tapped = bool(link and client_id in link.pending_taps)
        local_muted = self._settings.per_user_muted.get(composite, False)
        local_vol = self._settings.per_user_volumes.get(composite, float(p.get("volume", 1.0)))
        tech_lines = [
            f"client_id: {client_id}",
            f"link_id: {link_id}",
            f"server: {server_label}",
            f"composite: {composite}",
            f"voice_level: {float(p.get('voice_level', 0)):.3f}",
            f"speaking: {p.get('speaking', False)}",
            f"ptt_active: {p.get('ptt_active', False)}",
            f"server-reported muted: {p.get('muted', False)}",
        ]
        self._drawer.toggle_peer(
            composite,
            name=str(p.get("name", "?")),
            server_label=server_label,
            link_id=link_id,
            client_id=client_id,
            voice_level=float(p.get("voice_level", 0)),
            speaking=bool(p.get("speaking", False)),
            muted=local_muted,
            volume=local_vol,
            tapped=tapped,
            is_self=w.is_self,
            tech_lines=tech_lines,
        )

    def _on_chat(self, link_id: str, data: dict) -> None:
        self._record_chat(link_id, data)
        if link_id != self._active_link_id:
            return
        name = str(data.get("name", "?"))
        text = str(data.get("text", ""))
        self._append_chat_line(name, text)

    def _on_rooms(self, link_id: str, rooms: list[dict]) -> None:
        if link_id != self._active_link_id:
            return
        session = self._bridge.get_session(link_id)
        current_rid = ""
        if session and session.room_id:
            current_rid = session.room_id
        elif link_id in self._room_by_link:
            current_rid = self._room_by_link[link_id][0]
        self._room_list.clear()
        for r in rooms:
            rid = str(r.get("room_id", ""))
            label = f"{r.get('name', 'Room')} ({r.get('member_count', 0)})"
            if rid == current_rid:
                label = f"▸ {label}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, rid)
            self._room_list.addItem(item)
        if current_rid:
            self._highlight_current_room(current_rid)

    def _create_room(self) -> None:
        if not self._active_link_id:
            return
        name = self._new_room_edit.text().strip()
        if name:
            self._bridge.create_room(self._active_link_id, name)
            self._new_room_edit.clear()

    def _join_room_item(self, item: QListWidgetItem) -> None:
        if not self._active_link_id:
            return
        room_id = str(item.data(Qt.ItemDataRole.UserRole))
        if not room_id:
            return
        session = self._bridge.get_session(self._active_link_id)
        if session and session.room_id == room_id:
            return
        self._bridge.join_room(self._active_link_id, room_id)
        self._status.setText("Switching room…")

    def _room_context_menu(self, pos) -> None:
        if not self._active_link_id:
            return
        item = self._room_list.itemAt(pos)
        if not item:
            return
        room_id = str(item.data(Qt.ItemDataRole.UserRole))
        if not room_id:
            return
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.addAction("Join room", lambda: self._join_room_item(item))
        if self._room_list.count() > 1:
            menu.addAction("Delete room", lambda: self._delete_room(room_id, item.text().lstrip("▸ ")))
        menu.exec(self._room_list.mapToGlobal(pos))

    def _delete_room(self, room_id: str, label: str) -> None:
        if not self._active_link_id:
            return
        answer = QMessageBox.question(
            self,
            "Delete room",
            f"Delete “{label.split(' (')[0]}”?\n\nEveryone in that room moves to another room. "
            "Local chat history for this room is removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._bridge.delete_room(self._active_link_id, room_id)

    def _join_selected_room(self) -> None:
        item = self._room_list.currentItem()
        if item:
            self._join_room_item(item)

    def _send_chat(self) -> None:
        if not self._active_link_id:
            QMessageBox.information(
                self,
                "BabbleCast",
                "Connect to a server first (Host Server or pick one from Discover).",
            )
            return
        session = self._bridge.get_session(self._active_link_id)
        if not session or not session.room_id:
            QMessageBox.information(self, "BabbleCast", "Join a room before chatting.")
            return
        text = self._chat_input.text().strip()
        if not text:
            return
        self._bridge.send_chat(self._active_link_id, text)
        self._chat_input.clear()

    def _toggle_mute(self, checked: bool) -> None:
        self._self_muted = checked
        self._mute_btn.setText("🎤✕" if checked else "🎤")
        self._bridge.set_global_muted(checked)

    def _set_ptt(self, active: bool) -> None:
        self._ptt_held = active
        self._ptt_btn.setObjectName("pttActive" if active else "")
        self._ptt_btn.setStyleSheet("")
        self._bridge.set_global_ptt(active)

    def _send_tap(self, link_id: str, target_id: str) -> None:
        self._bridge.send_tap(link_id, target_id)

    def _on_tap_received(self, link_id: str, data: dict) -> None:
        tap_id = str(data.get("tap_id", ""))
        from_id = str(data.get("from_id", ""))
        from_name = str(data.get("from_name", "?"))
        target_id = str(data.get("target_id", ""))
        target_name = str(data.get("target_name", ""))
        peer_id = target_id if data.get("self_sent") else from_id
        peer_name = target_name if data.get("self_sent") else from_name
        if tap_id and peer_id:
            self._tap_ids[(link_id, peer_id)] = tap_id
            self._peer_names[(link_id, peer_id)] = peer_name
        if not data.get("self_sent"):
            self._rebuild_participants()
            link = self._bridge.get_link(link_id)
            if link:
                self._status.setText(f"Tap from {from_name} on {link.label} — click their name")

    def _open_tap_for_peer(self, link_id: str, peer_id: str) -> None:
        tap_id = self._tap_ids.get((link_id, peer_id))
        if not tap_id:
            return
        key = (link_id, tap_id)
        if key in self._tap_dialogs:
            self._tap_dialogs[key].raise_()
            self._tap_dialogs[key].activateWindow()
            return
        link = self._bridge.get_link(link_id)
        peer_name = self._peer_names.get((link_id, peer_id), peer_id)
        dlg = TapChatDialog(
            self._bridge,
            link_id,
            tap_id,
            peer_id,
            peer_name,
            link.label if link else link_id,
            parent=self,
        )
        dlg.finished.connect(lambda _r, k=key: self._tap_dialogs.pop(k, None))
        self._tap_dialogs[key] = dlg
        dlg.show()

    def _on_tap_chat(self, link_id: str, data: dict) -> None:
        tap_id = str(data.get("tap_id", ""))
        key = (link_id, tap_id)
        dlg = self._tap_dialogs.get(key)
        if dlg:
            dlg.append_message(data)

    def _on_tap_open(self, link_id: str, tap_id: str) -> None:
        pass

    def _on_tap_end(self, link_id: str, tap_id: str) -> None:
        key = (link_id, tap_id)
        dlg = self._tap_dialogs.pop(key, None)
        if dlg:
            dlg.close()

    def _reinsert_saved_tap(self, link_id: str, save_id: str) -> None:
        for tap in get_tap_store().items:
            if tap.save_id == save_id:
                lines = [f"{m.get('name', '?')}: {m.get('text', '')}" for m in tap.messages]
                summary = "\n".join(lines) or tap.reminder
                if self._active_link_id == link_id and summary:
                    self._bridge.send_chat(link_id, f"[Saved tap — {tap.reminder}]\n{summary}")
                break

    def _refresh_status(self) -> None:
        n = sum(1 for l in self._bridge.links if l.connected)
        if n:
            self._status.setText(f"{n} server(s) connected — mixed audio active")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat() and self._self_muted:
            self._set_ptt(True)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat() and self._self_muted:
            self._set_ptt(False)
        super().keyReleaseEvent(event)

    def closeEvent(self, event) -> None:
        geo = self.geometry()
        self._settings.window_geometry = [geo.x(), geo.y(), geo.width(), geo.height()]
        save_settings(self._settings)
        self._discovery.stop()
        self._bridge.disconnect_all()
        if self._embedded and self._embedded.running:
            self._embedded.stop()
        super().closeEvent(event)
