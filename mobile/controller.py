"""BabbleCast mobile — shared bridge/discovery controller."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from kivy.clock import Clock
from kivymd.uix.dialog import MDDialog

from babblecast.active_tap_chats import get_active_tap_chat_store
from babblecast.client.bridge import BridgeManager
from babblecast.client.room_controller import (
    chat_lines,
    purge_room_chat,
    record_incoming_chat,
    resolve_room,
    should_disconnect_failed_connect,
)
from babblecast.config import get_settings, save_settings
from babblecast.constants import DEFAULT_WS_PORT, MAX_NAME_LEN, composite_participant_key
from babblecast.discovery import ServerDiscovery
from babblecast.network import primary_lan_ipv4
from babblecast.network import is_local_host, is_valid_connect_target
from babblecast.protocol import is_name_taken_error, is_password_error

logger = logging.getLogger(__name__)
from babblecast.server.embedded import EmbeddedServer
from babblecast.taps import SavedTap, get_tap_store
from mobile.android_network import acquire_multicast_lock, release_multicast_lock
from mobile.android_foreground import start_voice_foreground, stop_voice_foreground
from mobile.permissions import location_granted, record_audio_granted, request_android_permissions

if TYPE_CHECKING:
    from mobile.app import BabbleCastMobileApp


class BabbleController:
    """Shared bridge / discovery / tap logic for all mobile screens."""

    def __init__(self, app: BabbleCastMobileApp) -> None:
        self.app = app
        self._settings = get_settings()
        self._bridge = BridgeManager(
            on_link_connected=lambda lid: Clock.schedule_once(lambda _dt, i=lid: self._on_link_connected(i)),
            on_link_disconnected=lambda lid, r: Clock.schedule_once(
                lambda _dt, i=lid, reason=r: self._on_link_disconnected(i, reason)
            ),
            on_presence=lambda lid, rid, p: Clock.schedule_once(
                lambda _dt, i=lid, parts=p: self._on_presence(i, parts)
            ),
            on_chat=lambda lid, d: Clock.schedule_once(lambda _dt, i=lid, msg=d: self._on_chat(i, msg)),
            on_rooms=lambda lid, r: Clock.schedule_once(lambda _dt, i=lid, rooms=r: self._on_rooms(i, rooms)),
            on_joined=lambda lid, rid, rn: Clock.schedule_once(
                lambda _dt, i=lid, room_id=rid, room_name=rn: self._on_joined(i, room_id, room_name)
            ),
            on_room_deleted=lambda lid, rid: Clock.schedule_once(
                lambda _dt, i=lid, room_id=rid: self._on_room_deleted(i, room_id)
            ),
            on_error=lambda lid, m, ec=None: Clock.schedule_once(
                lambda _dt, i=lid, msg=m, code=ec: self._on_connect_error(i, msg, code)
            ),
            on_tap_received=lambda lid, d: Clock.schedule_once(
                lambda _dt, i=lid, data=d: self._on_tap_received(i, data)
            ),
            on_tap_chat=lambda lid, d: Clock.schedule_once(lambda _dt, data=d: self._on_tap_chat(data)),
            on_tap_end=lambda lid, tid: Clock.schedule_once(
                lambda _dt, i=lid, tap_id=tid: self._on_tap_end(i, tap_id)
            ),
            on_local_mic_level=lambda lvl: Clock.schedule_once(
                lambda _dt, level=lvl: self._on_local_mic_level(level)
            ),
            on_audio_route_changed=lambda route: Clock.schedule_once(
                lambda _dt, r=route: self._on_audio_route_changed(r)
            ),
        )
        self._discovery = ServerDiscovery(
            on_update=lambda s: Clock.schedule_once(lambda _dt, sv=s: self._apply_servers(sv))
        )
        self._embedded: EmbeddedServer | None = None
        self._active_link_id: str | None = None
        self._presence: dict[str, list] = {}
        self._rooms: dict[str, list] = {}
        self._tap_ids: dict[tuple[str, str], str] = {}
        self._tap_messages: list[dict] = []
        self._tap_dialog: MDDialog | None = None
        self._tap_link_id = ""
        self._tap_id = ""
        self._tap_peer_name = ""
        self._pending_host: str | None = None
        self._pending_port: int | None = None
        self._room_by_link: dict[str, tuple[str, str]] = {}
        self._pending_embedded_connect = False
        self._own_server_password = ""
        self._closing = False
        self.current_room_text = "In room: —"
        self.status_text = "Offline — connect to one or more servers"
        self.chat_text = ""
        self.is_muted = False
        self.ptt_active = False
        self._participant_by_composite: dict[str, dict] = {}
        self._discovery_watch = None
        self._last_server_signature: tuple[tuple[str, str, int], ...] | None = None

    def _alive(self) -> bool:
        return not self._closing and not self._bridge.shutting_down

    @property
    def settings(self):
        return self._settings

    def set_status(self, text: str) -> None:
        if not self._alive():
            return
        self.status_text = text
        live = self.app.screen("live")
        if hasattr(live, "status_text"):
            live.status_text = text

    def start_discovery(self) -> None:
        request_android_permissions()
        acquire_multicast_lock()
        self._discovery.start()
        self.refresh_discovery_ui(force=True)
        screen = self.app.screen("connect")
        if location_granted():
            screen.set_discovery_status(
                f"Scanning your network for BabbleCast servers ({primary_lan_ipv4()})…"
            )
        else:
            screen.set_discovery_status(
                "Grant Location for auto-discover, or enter a LAN IP below"
            )
        if self._discovery_watch is None:
            self._discovery_watch = Clock.schedule_interval(self._watch_discovery_permissions, 2.0)

    def _watch_discovery_permissions(self, _dt: float) -> None:
        if not self._alive():
            if self._discovery_watch is not None:
                self._discovery_watch.cancel()
                self._discovery_watch = None
            return
        if location_granted():
            acquire_multicast_lock()
            if getattr(self.app, "_screen_manager", None) and self.app._screen_manager.current == "connect":
                self.refresh_discovery_ui()
            else:
                self._apply_servers(self._discovery.servers)

    def stop_all(self) -> None:
        self._closing = True
        if self._discovery_watch is not None:
            self._discovery_watch.cancel()
            self._discovery_watch = None
        if self._tap_dialog:
            self._tap_dialog.dismiss()
            self._tap_dialog = None
        live = self.app.screen("live")
        panel = getattr(live, "detail_panel", None)
        if panel:
            panel.close_peer()
            for meter in (getattr(panel, "_self_meter", None), getattr(panel, "_peer_meter", None)):
                if meter and hasattr(meter, "stop"):
                    meter.stop()
        self._bridge.shutdown()
        self._discovery.stop()
        release_multicast_lock()
        if self._embedded and self._embedded.running:
            self._embedded.stop()
            self._embedded = None
        stop_voice_foreground()

    def _apply_servers(self, servers) -> None:
        if not self._alive():
            return
        signature = tuple((s.service_name, s.host, s.ws_port) for s in servers)
        if signature == self._last_server_signature:
            return
        self._last_server_signature = signature
        screen = self.app.screen("connect")
        screen.update_servers(servers)
        self._set_discovery_status(len(servers))

    def _set_discovery_status(self, count: int) -> None:
        screen = self.app.screen("connect")
        if count:
            screen.set_discovery_status(f"{count} server(s) on your network — tap one to connect")
        elif location_granted():
            screen.set_discovery_status(
                "No servers yet — scanning your network, or enter a LAN IP below"
            )
        else:
            screen.set_discovery_status(
                "Grant Location for auto-discover, or enter a LAN IP below"
            )

    def refresh_discovery_ui(self, *, force: bool = False) -> None:
        """Re-acquire mDNS lock and repaint Connect tab server list."""
        if not self._alive():
            return
        acquire_multicast_lock()
        if force:
            self._last_server_signature = None
            screen = self.app.screen("connect")
            if hasattr(screen, "_server_signature"):
                screen._server_signature = None
        self._discovery.bump()
        self._set_discovery_status(len(self._discovery.servers))

    def _password_required_for(self, host: str, port: int) -> bool:
        host = host.strip().lower()
        for server in self._discovery.servers:
            if server.ws_port != port:
                continue
            if server.host == host or server.connect_host.lower() == host:
                return server.password_required
        return False

    def connect_to(
        self,
        host: str,
        port: int,
        display_name: str | None = None,
        *,
        password: str = "",
        password_required: bool = False,
        skip_name_prompt: bool = False,
    ) -> None:
        host = host.strip()
        if not host:
            self.set_status("Enter a server IP or hostname")
            return
        if host and not is_valid_connect_target(host):
            self.set_status("Use a LAN IP, name.babblecast.local, or 127.0.0.1")
            return
        try:
            port = int(port)
        except (TypeError, ValueError):
            self.set_status(f"Port must be a number (usually {DEFAULT_WS_PORT})")
            return
        self._pending_host = host
        self._pending_port = port
        own = self._is_own_server(host, port)
        if own and not password:
            password = self._own_server_password
        if display_name and (skip_name_prompt or own):
            self.connect_selected(display_name, host=host, port=port, password=password)
            return
        if skip_name_prompt or own:
            name = self._settings.display_name or ""
            if name:
                self.connect_selected(name, host=host, port=port, password=password)
                return
        if not password_required:
            password_required = self._password_required_for(host, port)
        from mobile.credentials_dialog import prompt_connect

        prompt_connect(
            host,
            port,
            f"{host}:{port}",
            lambda name, pwd: self.connect_selected(name, host=host, port=port, password=pwd),
            password_required=password_required,
        )

    def connect_discovered(self, host: str, port: int, label: str, *, password_required: bool) -> None:
        connect_host = host
        for server in self._discovery.servers:
            if server.host == host and server.ws_port == port:
                connect_host = server.connect_host
                break
        own = self._is_own_server(connect_host, port) or self._is_own_server(host, port)
        if own:
            self.connect_to(
                connect_host,
                port,
                self._settings.display_name,
                password=self._own_server_password,
                skip_name_prompt=True,
            )
            return
        from mobile.credentials_dialog import prompt_connect

        prompt_connect(
            connect_host,
            port,
            label,
            lambda name, pwd: self.connect_selected(name, host=connect_host, port=port, password=pwd),
            password_required=password_required,
        )

    def connect_selected(
        self,
        display_name: str,
        *,
        host: str | None = None,
        port: int | None = None,
        password: str = "",
    ) -> None:
        host = (host or self._pending_host or self._settings.last_server_host or "").strip()
        port = port or self._pending_port or self._settings.last_server_port or DEFAULT_WS_PORT
        if not host:
            self.set_status("Pick a discovered server or enter IP:port below")
            return
        for link in self._bridge.links:
            if link.host == host and link.port == port and link.connected:
                self.set_status(f"Already on {host}:{port}")
                return
        self._settings.display_name = display_name.strip()
        self._settings.last_server_host = host
        self._settings.last_server_port = port
        save_settings(self._settings)
        self._bridge.update_settings(self._settings)
        self.set_status(f"Connecting {host}:{port}…")
        self.app.switch_tab("live")

        def _finish_connect(_dt: float) -> None:
            if not self._alive():
                return
            self._bridge.connect(
                host,
                port,
                password=password,
                server_operator=self._is_own_server(host, port) or is_local_host(host),
            )
            self._sync_input_monitoring()

        Clock.schedule_once(_finish_connect, 0)

    def host_server(self) -> None:
        if self._embedded and self._embedded.running:
            self.stop_hosting()
            return
        from mobile.credentials_dialog import prompt_host

        prompt_host(lambda server, name, pwd: self._start_host_with_name(server, name, pwd))

    def _start_host_with_name(
        self, server_name: str, display_name: str, password: str = ""
    ) -> None:
        self._settings.display_name = display_name
        self._own_server_password = password
        self._start_host(server_name)

    def stop_hosting(self) -> None:
        if self._embedded and self._embedded.running:
            host = self._embedded.host
            port = self._embedded.ws_port
            for link in list(self._bridge.links):
                if link.host == host and link.port == port and link.connected:
                    self._bridge.disconnect(link.link_id)
            self._embedded.stop()
            self._embedded = None
            self._own_server_password = ""
            self.set_status("Server stopped")
        self.refresh_host_ui()

    def refresh_host_ui(self) -> None:
        screen = self.app.screen("connect")
        if hasattr(screen, "set_hosting"):
            screen.set_hosting(bool(self._embedded and self._embedded.running))

    def set_master_volume(self, volume: float) -> None:
        self._bridge.set_master_output_volume(volume)

    def set_input_volume(self, volume: float) -> None:
        self._bridge.set_input_volume(volume)

    def list_audio_routes(self) -> list[tuple[str, str, bool]]:
        return self._bridge.list_audio_routes()

    def set_audio_route(self, route: str) -> None:
        self._bridge.set_audio_route(route)

    def set_noise_suppression(self, strength: float) -> None:
        self._bridge.set_noise_suppression(strength)

    def set_audio_panel_expanded(self, expanded: bool) -> None:
        self._settings.ui_panel_expanded = expanded
        save_settings(self._settings)
        self._sync_input_monitoring()

    def set_self_audio_expanded(self, expanded: bool) -> None:
        self._settings.ui_self_audio_expanded = expanded
        save_settings(self._settings)
        self._sync_input_monitoring()

    def _sync_input_monitoring(self) -> None:
        if not (self._settings.ui_panel_expanded and self._settings.ui_self_audio_expanded):
            self._bridge.release_input_monitoring()
            return
        if not record_audio_granted():
            self.set_status("Grant microphone permission for self-audio meters")
            request_android_permissions()
            return
        if not self._bridge.ensure_input_monitoring():
            self.set_status("Microphone unavailable — chat-only mode")

    def set_peer_muted(self, composite_key: str, muted: bool) -> None:
        self._bridge.set_participant_muted(composite_key, muted)

    def set_peer_volume(self, composite_key: str, volume: float) -> None:
        self._bridge.set_participant_volume(composite_key, volume)

    def send_peer_tap(self, link_id: str, client_id: str) -> None:
        self._bridge.send_tap(link_id, client_id)

    def on_live_enter(self) -> None:
        Clock.schedule_once(lambda _dt: self._on_live_enter_deferred(), 0)

    def _on_live_enter_deferred(self) -> None:
        if not self._alive():
            return
        live = self.app.screen("live")
        panel = getattr(live, "detail_panel", None)
        if panel:
            panel.sync_from_settings()
        self._refresh_admin_room_password()
        self._sync_input_monitoring()
        self.refresh_tap_notes_ui()

    def _on_local_mic_level(self, level: float) -> None:
        if not self._alive():
            return
        live = self.app.screen("live")
        if live and getattr(live, "detail_panel", None):
            live.detail_panel.set_self_mic_level(level)

    def _on_audio_route_changed(self, route: str) -> None:
        if not self._alive():
            return
        live = self.app.screen("live")
        panel = getattr(live, "detail_panel", None)
        if panel:
            panel.sync_from_settings()

    def open_user_panel(self, link_id: str, participant: dict) -> None:
        from babblecast.constants import composite_participant_key

        cid = str(participant.get("client_id", ""))
        composite = composite_participant_key(link_id, cid)
        link = self._bridge.get_link(link_id)
        my_id = link.client_id if link else ""
        live = self.app.screen("live")
        if not getattr(live, "detail_panel", None):
            return
        tap_active = (link_id, cid) in self._tap_ids
        tapped = bool(link and cid in link.pending_taps)
        live.detail_panel.toggle_peer(
            composite,
            participant,
            link_id=link_id,
            server=link.label if link else link_id,
            is_self=(cid == my_id),
            tap_active=tap_active,
            tapped=tapped,
        )

    def open_tap_for_peer(self, link_id: str, peer_id: str) -> None:
        tap_id = self._tap_ids.get((link_id, peer_id))
        if not tap_id:
            return
        from babblecast.constants import composite_participant_key

        composite = composite_participant_key(link_id, peer_id)
        p = self._participant_by_composite.get(composite, {})
        peer_name = str(p.get("name", peer_id))
        self._open_tap_dialog(link_id, tap_id, peer_id, peer_name)

    def reinsert_saved_tap(self, link_id: str, save_id: str) -> None:
        tap = get_tap_store().get(save_id)
        if not tap or self._active_link_id != link_id:
            return
        body = tap.detail.strip() or tap.display_subject
        self._bridge.send_chat(link_id, f"[Tap note — {tap.display_subject}]\n{body}")

    def _start_host(self, name: str) -> None:
        clean = name.strip()[:MAX_NAME_LEN]
        self._settings.hosted_server_name = clean
        save_settings(self._settings)
        self._pending_embedded_connect = True
        self.set_status(f"Starting server “{clean}”…")

        def on_started(host: str, port: int) -> None:
            Clock.schedule_once(lambda _dt: self._on_embedded_started(host, port), 0)

        def on_failed(reason: str) -> None:
            Clock.schedule_once(lambda _dt: self._on_embedded_failed(reason), 0)

        def on_stopped() -> None:
            Clock.schedule_once(lambda _dt: self._on_embedded_stopped(), 0)

        self._embedded = EmbeddedServer(
            server_name=clean,
            server_password=self._own_server_password,
            host_password=self._settings.host_password,
            on_started=on_started,
            on_failed=on_failed,
            on_stopped=on_stopped,
        )
        self._embedded.start()

    def _on_embedded_started(self, host: str, port: int) -> None:
        from babblecast.discovery import service_hostname, slugify_server_name

        self.refresh_host_ui()
        lan = self._embedded.lan_host if self._embedded else host
        slug_host = service_hostname(slugify_server_name(self._settings.hosted_server_name or "BabbleCast"))
        self.set_status(f"Hosting on {lan}:{port} — others: {slug_host} or Discover")
        screen = self.app.screen("connect")
        if getattr(screen, "_host_field", None) and self._settings.last_server_host:
            screen._host_field.text = self._settings.last_server_host
        if self._pending_embedded_connect and self._embedded and self._embedded.running:
            self._pending_embedded_connect = False
            screen = self.app.screen("connect")
            already = any(
                l.host == host and l.port == port and l.connected for l in self._bridge.links
            )
            if not already:
                self.connect_to(
                    host,
                    port,
                    self._settings.display_name,
                    password=self._own_server_password,
                    skip_name_prompt=True,
                )
            else:
                self.set_status(f"Hosting on {lan}:{port} — already connected")

    def _on_embedded_failed(self, reason: str) -> None:
        self._pending_embedded_connect = False
        self._embedded = None
        self.refresh_host_ui()
        detail = reason
        if "98" in reason or "already in use" in reason.lower():
            detail = (
                f"{reason} — port {DEFAULT_WS_PORT} in use. Connect to the existing server instead of hosting."
            )
        self.set_status(f"Host failed: {detail}")

    def _on_embedded_stopped(self) -> None:
        self._pending_embedded_connect = False
        if self._embedded and not self._embedded.running:
            self._embedded = None
        self.refresh_host_ui()

    def _is_own_server(self, host: str, port: int) -> bool:
        if not self._embedded or not self._embedded.running:
            return False
        if port != self._embedded.ws_port:
            return False
        return is_local_host(host)

    def _on_connect_error(self, link_id: str, message: str, error_code: str | None = None) -> None:
        if not self._alive():
            return
        link = self._bridge.get_link(link_id)
        label = link.label if link else link_id
        host = link.host if link else self._pending_host or ""
        port = link.port if link else self._pending_port or DEFAULT_WS_PORT
        if is_name_taken_error(error_code, message):
            self.set_status(f"Name taken on {label} — pick another display name")
            from mobile.credentials_dialog import prompt_connect

            prompt_connect(
                host,
                port,
                label,
                lambda name, pwd: self.connect_selected(name, host=host, port=port, password=pwd),
                password_required=self._password_required_for(host, port),
            )
        elif is_password_error(error_code, message):
            self.set_status(f"{label}: {message}")
            from mobile.credentials_dialog import prompt_connect

            prompt_connect(
                host,
                port,
                label,
                lambda name, pwd: self.connect_selected(name, host=host, port=port, password=pwd),
                password_required=True,
            )
        else:
            self.set_status(f"{label}: {message}")
        if link and should_disconnect_failed_connect(error_code, message, connected=link.connected):
            self._bridge.disconnect(link_id)

    def _sync_voice_foreground(self) -> None:
        if any(l.connected for l in self._bridge.links):
            start_voice_foreground()
        else:
            stop_voice_foreground()

    def _on_link_connected(self, link_id: str) -> None:
        if not self._alive():
            return
        link = self._bridge.get_link(link_id)
        if not link:
            return
        if not self._active_link_id:
            self._active_link_id = link_id
        self._bridge.request_rooms(link_id)
        try:
            live = self.app.screen("live")
            live.add_connected_link(link_id, link)
            live.set_active_link(link_id)
            rooms = self._rooms.get(link_id, [])
            live.update_rooms(rooms, self._active_link_id == link_id, self._current_room_id(link_id))
            if link_id == self._active_link_id:
                self._reload_chat(link_id)
        except Exception:
            logger.exception("Live UI update failed after connect")
            self.set_status("Connected — UI refresh failed; try Live tab")
        n = sum(1 for l in self._bridge.links if l.connected)
        self.set_status(f"{n} server(s) connected")
        self._sync_voice_foreground()
        self._restore_active_taps(link_id)

    def _restore_active_taps(self, link_id: str) -> None:
        participants = self._presence.get(link_id, [])
        restored = self._bridge.restore_active_tap_ids(link_id, participants)
        self._tap_ids.update(restored)
        if restored:
            self.refresh_tap_notes_ui()
            live = self.app.screen("live")
            live.refresh_people(self._presence, self._bridge, self._tap_ids, self._active_link_id)

    def _on_link_disconnected(self, link_id: str, reason: str) -> None:
        if not self._alive():
            return
        live = self.app.screen("live")
        panel = getattr(live, "detail_panel", None)
        if panel and panel._peer_key and panel._peer_key.startswith(f"{link_id}:"):
            panel.close_peer()
        live.remove_connected_link(link_id)
        self._presence.pop(link_id, None)
        self._rooms.pop(link_id, None)
        for key in list(self._tap_ids):
            if key[0] == link_id:
                self._tap_ids.pop(key, None)
        if self._active_link_id == link_id:
            remaining = live.connected_link_ids()
            self._active_link_id = remaining[0] if remaining else None
        live.refresh_people(self._presence, self._bridge, self._tap_ids, self._active_link_id)
        n = sum(1 for l in self._bridge.links if l.connected)
        if n == 0:
            self.set_status(f"Offline — {reason}")
        else:
            self.set_status(f"{n} server(s) connected")
        self._sync_voice_foreground()
        self._refresh_admin_room_password()

    def set_active_link(self, link_id: str) -> None:
        self._active_link_id = link_id
        link = self._bridge.get_link(link_id)
        if link:
            self.set_status(f"Active: {link.label}")
        live = self.app.screen("live")
        live.set_active_link(link_id)
        rooms = self._rooms.get(link_id, [])
        live.update_rooms(rooms, True, self._current_room_id(link_id))
        self._reload_chat(link_id)
        self._refresh_admin_room_password()

    def _refresh_admin_room_password(self) -> None:
        live = self.app.screen("live")
        panel = getattr(live, "detail_panel", None)
        if not panel:
            return
        link_id = self._active_link_id
        if not link_id:
            panel.set_room_password_display(False, "")
            return
        visible, text = self._bridge.admin_room_password_display(link_id)
        panel.set_room_password_display(visible, text)

    def _current_room_id(self, link_id: str) -> str:
        session = self._bridge.get_session(link_id)
        if session and session.room_id:
            return session.room_id
        return self._room_by_link.get(link_id, ("", ""))[0]

    def _on_joined(self, link_id: str, room_id: str, room_name: str) -> None:
        self._room_by_link[link_id] = (room_id, room_name)
        if link_id == self._active_link_id:
            self.current_room_text = f"In room: {room_name}"
            live = self.app.screen("live")
            if hasattr(live, "current_room_text"):
                live.current_room_text = self.current_room_text
            self._reload_chat(link_id)
            rooms = self._rooms.get(link_id, [])
            live.update_rooms(rooms, True, room_id)
            self._refresh_admin_room_password()

    def _on_room_deleted(self, link_id: str, room_id: str) -> None:
        link = self._bridge.get_link(link_id)
        if link:
            purge_room_chat(link.host, link.port, room_id)
        if link_id == self._active_link_id:
            self._reload_chat(link_id)
            rooms = self._rooms.get(link_id, [])
            live = self.app.screen("live")
            live.update_rooms(rooms, True, self._current_room_id(link_id))
            self._refresh_admin_room_password()

    def _reload_chat(self, link_id: str | None = None) -> None:
        lid = link_id or self._active_link_id
        live = self.app.screen("live")
        if not lid:
            self.chat_text = ""
            live.chat_text = ""
            return
        link = self._bridge.get_link(lid)
        session = self._bridge.get_session(lid)
        if not link or not session or not session.room_id:
            self.chat_text = "Waiting for room…\n"
            live.chat_text = self.chat_text
            return
        room_id, room_name = resolve_room(lid, session.room_id, self._room_by_link)
        self.current_room_text = f"In room: {room_name}"
        if hasattr(live, "current_room_text"):
            live.current_room_text = self.current_room_text
        lines = chat_lines(link.host, link.port, room_id)
        parts = [f"Chat — {link.label} / {room_name}\n"]
        for line in lines:
            ts = datetime.fromtimestamp(line.ts).strftime("%H:%M")
            parts.append(f"[{ts}] {line.name}: {line.text}\n")
        self.chat_text = "".join(parts)
        live.chat_text = self.chat_text

    def _record_chat(self, link_id: str, data: dict) -> None:
        link = self._bridge.get_link(link_id)
        session = self._bridge.get_session(link_id)
        if not link or not session:
            return
        room_id = str(data.get("room_id") or session.room_id or "")
        room_name = resolve_room(link_id, session.room_id, self._room_by_link)[1]
        record_incoming_chat(link.host, link.port, room_id, data, room_name=room_name)

    def toggle_listen(self, link_id: str) -> None:
        link = self._bridge.get_link(link_id)
        if link:
            self._bridge.set_listen_muted(link_id, not link.listen_muted)
            live = self.app.screen("live")
            live.refresh_link_row(link_id, self._bridge.get_link(link_id))

    def toggle_mic(self, link_id: str) -> None:
        link = self._bridge.get_link(link_id)
        if link:
            self._bridge.set_mic_muted(link_id, not link.mic_muted)
            live = self.app.screen("live")
            live.refresh_link_row(link_id, self._bridge.get_link(link_id))

    def disconnect_link(self, link_id: str) -> None:
        link = self._bridge.get_link(link_id)
        if not link:
            return
        label = link.label

        def do_disconnect(skip_future: bool) -> None:
            if skip_future:
                self._settings.skip_disconnect_confirm = True
                save_settings(self._settings)
            self._bridge.disconnect(link_id)
            self.set_status(f"Disconnected from {label}")

        if self._settings.skip_disconnect_confirm:
            do_disconnect(False)
            return
        from mobile.credentials_dialog import prompt_disconnect

        prompt_disconnect(label, do_disconnect)

    def toggle_mute(self) -> None:
        self.is_muted = not self.is_muted
        self._bridge.set_global_muted(self.is_muted)
        live = self.app.screen("live")
        live.is_muted = self.is_muted

    def set_ptt(self, active: bool) -> None:
        self.ptt_active = active
        self._bridge.set_global_ptt(active)
        live = self.app.screen("live")
        live.ptt_active = self.ptt_active

    def show_server_info(self, link_id: str) -> None:
        from kivymd.uix.button import MDFlatButton
        from kivymd.uix.dialog import MDDialog
        from kivymd.uix.label import MDLabel

        from babblecast.client.link_stats import (
            build_link_info_rows,
            format_link_info_text,
            link_display_name,
        )

        link = self._bridge.get_link(link_id)
        if not link:
            return
        session = self._bridge.get_session(link_id)
        room_name = ""
        if session and session.room_id:
            room_name = self._room_by_link.get(link_id, ("", ""))[1]
        rows = build_link_info_rows(
            link,
            session,
            presence_count=len(self._presence.get(link_id, [])),
            current_room_name=room_name,
            is_active=(link_id == self._active_link_id),
        )
        body = MDLabel(
            text=format_link_info_text(rows),
            theme_text_color="Custom",
            text_color=(0.66, 0.69, 0.82, 1),
            font_style="Body2",
            size_hint_y=None,
        )
        body.bind(texture_size=lambda _l, s: setattr(body, "height", s[1]))
        dialog = MDDialog(
            title=f"Server — {link_display_name(link)}",
            type="custom",
            content_cls=body,
            buttons=[MDFlatButton(text="Close", on_release=lambda *_: dialog.dismiss())],
        )
        dialog.open()

    def refresh_tap_notes_ui(self) -> None:
        if not self._alive():
            return
        live = self.app.screen("live")
        panel = getattr(live, "detail_panel", None)
        if panel and panel._peer_open and panel._peer_client_id:
            panel._refresh_taps()
        self._refresh_tap_dialog_notes()

    def _refresh_tap_dialog_notes(self) -> None:
        from kivy.metrics import dp
        from kivymd.uix.boxlayout import MDBoxLayout
        from kivymd.uix.button import MDIconButton
        from kivymd.uix.label import MDLabel

        from babblecast.taps import get_tap_store
        from mobile.tap_note_dialog import TapNoteListRow

        box = getattr(self, "_tap_notes_box", None)
        peer_id = getattr(self, "_tap_peer_id", None)
        if not box or not peer_id:
            return
        box.clear_widgets()
        notes = [t for t in get_tap_store().items if t.peer_id == peer_id]
        notes.sort(key=lambda t: t.created_at, reverse=True)
        if not notes:
            box.add_widget(
                MDLabel(
                    text="(no tap notes yet)",
                    theme_text_color="Custom",
                    text_color=(0.55, 0.58, 0.68, 1),
                    font_style="Caption",
                )
            )
            return
        for tap in notes:
            mark = "✓" if tap.done else "○"
            row = MDBoxLayout(size_hint_y=None, height=dp(32), spacing=dp(4))
            row.add_widget(
                TapNoteListRow(
                    tap.save_id,
                    f"{mark} {tap.display_subject[:40]}",
                    on_open=lambda sid, c=self: c.view_tap_note(sid),
                )
            )
            row.add_widget(MDBoxLayout(size_hint_x=1))
            row.add_widget(
                MDIconButton(
                    icon="close",
                    theme_text_color="Custom",
                    text_color=(0.97, 0.46, 0.56, 1),
                    on_release=lambda *_t, sid=tap.save_id: self.delete_tap_note(sid),
                )
            )
            box.add_widget(row)

    def view_tap_note(self, save_id: str) -> None:
        from mobile.tap_note_dialog import show_tap_note_viewer

        tap = get_tap_store().get(save_id)
        if tap:
            show_tap_note_viewer(tap, on_saved=self.refresh_tap_notes_ui)

    def _compose_tap_note(
        self,
        *,
        link_id: str | None,
        peer_id: str,
        peer_name: str,
        default_subject: str = "",
        on_saved: Callable[[], None] | None = None,
    ) -> None:
        from mobile.tap_note_dialog import prompt_compose_tap_note

        link = self._bridge.get_link(link_id) if link_id else None

        def on_save(subject: str, detail: str) -> None:
            get_tap_store().add(
                SavedTap.create(
                    peer_id=peer_id,
                    peer_name=peer_name,
                    server_label=link.label if link else "",
                    subject=subject,
                    detail=detail,
                )
            )
            self.refresh_tap_notes_ui()
            if on_saved:
                on_saved()

        prompt_compose_tap_note(
            default_subject=default_subject or f"Follow up with {peer_name}",
            on_save=on_save,
        )

    def prompt_add_tap_note(
        self,
        *,
        link_id: str | None = None,
        peer_id: str | None = None,
        peer_name: str | None = None,
        default_subject: str = "",
    ) -> None:
        lid = link_id or self._active_link_id
        live = self.app.screen("live")
        panel = getattr(live, "detail_panel", None)
        if peer_id is None and panel and panel._peer_open and panel._peer_client_id:
            peer_id = panel._peer_client_id
            lid = panel._peer_link_id or lid
            p = self._participant_by_composite.get(f"{lid}:{peer_id}" if lid else "", {})
            peer_name = peer_name or str(p.get("name", "Note"))
        from mobile.tap_note_dialog import prompt_compose_tap_note

        link = self._bridge.get_link(lid) if lid else None

        def on_save(subject: str, detail: str) -> None:
            get_tap_store().add(
                SavedTap.create(
                    peer_id=peer_id or "",
                    peer_name=peer_name or "Note",
                    server_label=link.label if link else "",
                    subject=subject,
                    detail=detail,
                )
            )
            self.refresh_tap_notes_ui()

        prompt_compose_tap_note(
            default_subject=default_subject or (f"Follow up with {peer_name}" if peer_name else ""),
            on_save=on_save,
        )

    def add_tap_note_for_peer(self, link_id: str, peer_id: str) -> None:
        from babblecast.constants import composite_participant_key

        composite = composite_participant_key(link_id, peer_id)
        p = self._participant_by_composite.get(composite, {})
        peer_name = str(p.get("name", peer_id))
        self.prompt_add_tap_note(
            link_id=link_id,
            peer_id=peer_id,
            peer_name=peer_name,
            default_subject=f"Follow up with {peer_name}",
        )

    def delete_tap_note(self, save_id: str) -> None:
        def do_delete(skip_future: bool) -> None:
            if skip_future:
                self._settings.skip_tap_delete_confirm = True
                save_settings(self._settings)
            get_tap_store().delete(save_id)
            self.refresh_tap_notes_ui()

        if self._settings.skip_tap_delete_confirm:
            do_delete(False)
            return
        from mobile.credentials_dialog import prompt_confirm_checkbox

        prompt_confirm_checkbox(
            "Delete tap note",
            "Delete this tap note permanently?",
            "Delete",
            do_delete,
            confirm_color=(0.97, 0.46, 0.56, 1),
        )

    def open_tap_note(self, save_id: str) -> None:
        self.view_tap_note(save_id)

    def send_chat(self, text: str) -> None:
        if not self._active_link_id:
            self.set_status("Connect to a server first")
            return
        session = self._bridge.get_session(self._active_link_id)
        if not session or not session.room_id:
            self.set_status("Join a room before chatting")
            return
        if not text.strip():
            return
        self._bridge.send_chat(self._active_link_id, text.strip())

    def _on_presence(self, link_id: str, participants) -> None:
        if not self._alive():
            return
        self._presence[link_id] = participants
        from babblecast.constants import composite_participant_key

        for p in participants:
            cid = str(p.get("client_id", ""))
            self._participant_by_composite[composite_participant_key(link_id, cid)] = dict(p)
        self._restore_active_taps(link_id)
        live = self.app.screen("live")
        live.refresh_people(self._presence, self._bridge, self._tap_ids, self._active_link_id)
        panel = getattr(live, "detail_panel", None)
        if panel and panel._peer_key and panel._peer_open:
            p = self._participant_by_composite.get(panel._peer_key)
            if p:
                panel.update_peer(p)

    def _on_rooms(self, link_id: str, rooms: list) -> None:
        self._rooms[link_id] = rooms
        live = self.app.screen("live")
        live.update_rooms(rooms, self._active_link_id == link_id, self._current_room_id(link_id))
        if link_id == self._active_link_id:
            self._refresh_admin_room_password()

    def join_room(self, room_id: str) -> None:
        if not self._active_link_id:
            return
        session = self._bridge.get_session(self._active_link_id)
        if session and session.room_id == room_id:
            return
        room_meta = session.room_by_id(room_id) if session else None
        if room_meta and room_meta.get("password_protected") and not self._bridge.is_server_operator(
            self._active_link_id
        ):
            from mobile.credentials_dialog import prompt_room_password

            room_name = str(room_meta.get("name", "Room"))

            def proceed(password: str) -> None:
                self._bridge.join_room(self._active_link_id, room_id, password=password)
                self.set_status("Switching room…")

            prompt_room_password(room_name, proceed)
            return
        self._bridge.join_room(self._active_link_id, room_id)
        self.set_status("Switching room…")

    def delete_room(self, room_id: str, room_name: str) -> None:
        if not self._active_link_id:
            return
        session = self._bridge.get_session(self._active_link_id)
        room_meta = session.room_by_id(room_id) if session else None
        if not room_meta or not self._bridge.can_delete_room(self._active_link_id, room_meta):
            self.set_status("You cannot delete this room")
            return
        from kivymd.uix.button import MDFlatButton, MDRaisedButton
        from kivymd.uix.dialog import MDDialog

        needs_password = self._bridge.delete_room_needs_host_password(self._active_link_id, room_meta)

        def finish_delete(host_password: str = "") -> None:
            self._bridge.delete_room(self._active_link_id, room_id, host_password=host_password)
            self.set_status(f"Deleting room “{room_name}”…")

        def confirm(_btn) -> None:
            dialog.dismiss()
            if needs_password:
                from mobile.credentials_dialog import prompt_host_password

                prompt_host_password(
                    lambda pwd: finish_delete(pwd),
                    title="Confirm delete",
                    hint="Your host password",
                )
            else:
                finish_delete()

        def cancel(_btn) -> None:
            dialog.dismiss()

        host_note = ""
        if needs_password:
            host_note = "\n\nEnter your host password to confirm deletion."
        elif self._bridge.is_server_operator(self._active_link_id):
            creator_id = str(room_meta.get("creator_id", ""))
            if creator_id and session and creator_id != session.client_id:
                host_note = (
                    "\n\nSet a host password in Your audio → Host admin "
                    "to lock down admin deletes."
                )

        dialog = MDDialog(
            title="Delete room",
            text=(
                f"Delete “{room_name}”?\n\n"
                "Everyone in that room moves to another room. "
                "Local chat history for this room is removed."
                f"{host_note}"
            ),
            buttons=[
                MDFlatButton(text="Cancel", on_release=cancel),
                MDRaisedButton(text="Delete", on_release=confirm),
            ],
        )
        dialog.open()

    def create_room(self, name: str) -> None:
        if not self._active_link_id:
            return
        from mobile.credentials_dialog import prompt_create_room

        def proceed(room_name: str, password: str) -> None:
            self._bridge.create_room(self._active_link_id, room_name, password=password)
            self.set_status(f"Creating room “{room_name}”…")

        prompt_create_room(name.strip(), proceed)

    def _on_chat(self, link_id: str, data: dict) -> None:
        self._record_chat(link_id, data)
        if link_id != self._active_link_id:
            return
        line = f"{data.get('name', '?')}: {data.get('text', '')}\n"
        self.chat_text += line
        live = self.app.screen("live")
        live.chat_text = self.chat_text

    def set_host_password(self, password: str) -> None:
        self._settings.host_password = password.strip()
        save_settings(self._settings)
        if self._embedded and self._embedded.running:
            self._embedded.set_host_password(self._settings.host_password)

    def set_gate_db(self, value: float) -> None:
        self._bridge.set_gate_db(value)

    def _send_tap(self, link_id: str, target_id: str) -> None:
        self._bridge.send_tap(link_id, target_id)

    def _open_tap_chat(self, link_id: str, peer_id: str, name: str) -> None:
        tap_id = self._tap_ids.get((link_id, peer_id))
        if tap_id:
            self._open_tap_dialog(link_id, tap_id, peer_id, name)

    def _on_tap_received(self, link_id: str, data: dict) -> None:
        tap_id = str(data.get("tap_id", ""))
        from_id = str(data.get("from_id", ""))
        from_name = str(data.get("from_name", "?"))
        target_id = str(data.get("target_id", ""))
        target_name = str(data.get("target_name", ""))
        peer_id = target_id if data.get("self_sent") else from_id
        if tap_id and peer_id:
            self._tap_ids[(link_id, peer_id)] = tap_id
            live = self.app.screen("live")
            panel = getattr(live, "detail_panel", None)
            if panel and panel._peer_open and panel._peer_client_id == peer_id:
                panel.set_tap_chat_visible(True)
        if not data.get("self_sent"):
            live = self.app.screen("live")
            live.refresh_people(self._presence, self._bridge, self._tap_ids, self._active_link_id)
            self.set_status(f"Tap from {from_name} — tap message icon to open")
        elif target_name:
            self.set_status(f"Tap sent to {target_name}")

    def _open_tap_dialog(self, link_id: str, tap_id: str, peer_id: str, peer_name: str) -> None:
        if (
            self._tap_dialog
            and getattr(self, "_tap_link_id", None) == link_id
            and getattr(self, "_tap_id", None) == tap_id
        ):
            return
        if self._tap_dialog:
            self._tap_dialog.dismiss()
            self._tap_dialog = None
            self._tap_messages.clear()

        from kivy.metrics import dp
        from kivymd.uix.boxlayout import MDBoxLayout
        from kivymd.uix.button import MDFlatButton, MDRaisedButton
        from kivymd.uix.label import MDLabel
        from kivymd.uix.textfield import MDTextField

        from mobile.theme import DANGER, SUNFLOWER

        self._tap_link_id = link_id
        self._tap_id = tap_id
        self._tap_peer_id = peer_id
        self._tap_peer_name = peer_name
        self._tap_messages = []
        self._bridge.open_tap(link_id, tap_id)
        self._bridge.clear_pending_tap(link_id, peer_id)

        tap_input = MDTextField(hint_text="Tap message…", size_hint_y=None, height=dp(48))
        tap_log = MDLabel(text="", size_hint_y=None)
        tap_log.bind(texture_size=lambda _l, s: setattr(tap_log, "height", s[1]))
        stored = get_active_tap_chat_store().get(tap_id)
        if stored:
            for msg in stored.messages:
                line = f"[{msg.get('ts', '')}] {msg.get('name', '?')}: {msg.get('text', '')}\n"
                tap_log.text += line
                self._tap_messages.append(msg)

        toolbar = MDBoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        toolbar.add_widget(MDBoxLayout(size_hint_x=1))

        def clear_tap_chat(*_args) -> None:
            from mobile.credentials_dialog import prompt_confirm_checkbox

            def do_clear(skip_future: bool) -> None:
                if skip_future:
                    self._settings.skip_clear_chat_confirm = True
                    save_settings(self._settings)
                get_active_tap_chat_store().clear_messages(tap_id)
                self._tap_messages.clear()
                tap_log.text = ""

            if self._settings.skip_clear_chat_confirm:
                do_clear(False)
                return
            prompt_confirm_checkbox(
                "Clear Chat",
                "Clear all messages in this tap chat?",
                "Clear",
                do_clear,
                confirm_color=DANGER,
            )

        toolbar.add_widget(
            MDRaisedButton(
                text="Clear Chat",
                size_hint_x=None,
                width=dp(110),
                md_bg_color=DANGER,
                on_release=clear_tap_chat,
            )
        )

        def save_tap(*_args) -> None:
            def on_saved() -> None:
                self._tap_note_added = True
                self.set_status("Tap note saved")

            self._compose_tap_note(
                link_id=link_id,
                peer_id=peer_id,
                peer_name=peer_name,
                default_subject=f"Follow up with {peer_name}",
                on_saved=on_saved,
            )

        toolbar.add_widget(
            MDRaisedButton(
                text="+ Tap Note",
                size_hint_x=None,
                width=dp(110),
                md_bg_color=SUNFLOWER,
                text_color=(0.1, 0.11, 0.15, 1),
                on_release=save_tap,
            )
        )
        toolbar.add_widget(MDBoxLayout(size_hint_x=1))

        content = MDBoxLayout(
            orientation="vertical",
            spacing=dp(8),
            size_hint_y=None,
            adaptive_height=True,
        )
        content.add_widget(toolbar)
        content.add_widget(tap_log)
        content.add_widget(tap_input)
        content.add_widget(
            MDLabel(
                text="Tap Notes",
                theme_text_color="Custom",
                text_color=(0.75, 0.78, 0.88, 1),
                font_style="Body1",
                bold=True,
                size_hint_y=None,
                height=dp(24),
            )
        )
        self._tap_notes_box = MDBoxLayout(orientation="vertical", spacing=dp(2), size_hint_y=None)
        self._tap_notes_box.bind(minimum_height=self._tap_notes_box.setter("height"))
        content.add_widget(self._tap_notes_box)

        def send_msg(*_args) -> None:
            text = tap_input.text.strip()
            if text:
                self._bridge.send_tap_chat(link_id, tap_id, text)
                tap_input.text = ""

        def _finish_simple() -> None:
            if self._tap_dialog:
                self._tap_dialog.dismiss()
            self._tap_messages.clear()
            self._tap_dialog = None
            self.refresh_tap_notes_ui()

        def close_tap(*_args) -> None:
            if not self._tap_messages or getattr(self, "_tap_note_added", False):
                _finish_simple()
                return
            if self._settings.skip_tap_note_save_confirm:
                _finish_simple()
                return

            from kivymd.uix.selectioncontrol import MDCheckbox

            skip_cb = MDCheckbox(size_hint=(None, None), size=(dp(32), dp(32)))
            row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(4))
            row.add_widget(skip_cb)
            row.add_widget(MDLabel(text="Do not ask again", size_hint_x=1))
            body = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, adaptive_height=True)
            body.add_widget(
                MDLabel(text="Add a tap note from this conversation before closing?", size_hint_y=None)
            )
            body.add_widget(row)
            holder: list = []

            def dismiss() -> None:
                holder[0].dismiss()

            def confirm_add(*_a) -> None:
                if skip_cb.active:
                    self._settings.skip_tap_note_save_confirm = True
                    save_settings(self._settings)
                dismiss()

                def on_saved() -> None:
                    self._tap_note_added = True
                    _finish_simple()

                self._compose_tap_note(
                    link_id=link_id,
                    peer_id=peer_id,
                    peer_name=peer_name,
                    default_subject=f"Follow up with {peer_name}",
                    on_saved=on_saved,
                )

            dialog = MDDialog(
                title="+ Tap Note",
                type="custom",
                content_cls=body,
                buttons=[
                    MDFlatButton(
                        text="Close without note",
                        on_release=lambda *_: (dismiss(), _finish_simple()),
                    ),
                    MDRaisedButton(text="Add tap note", on_release=confirm_add),
                ],
            )
            holder.append(dialog)
            dialog.open()

        self._tap_note_added = False

        self._tap_dialog = MDDialog(
            title=f"Tap — {peer_name}",
            type="custom",
            content_cls=content,
            buttons=[
                MDRaisedButton(text="Send", on_release=send_msg),
                MDFlatButton(text="Close", on_release=close_tap),
            ],
        )
        self._tap_input = tap_input
        self._tap_log = tap_log
        self._refresh_tap_dialog_notes()
        self._tap_dialog.open()
        live = self.app.screen("live")
        live.refresh_people(self._presence, self._bridge, self._tap_ids, self._active_link_id)

    def _on_tap_chat(self, data: dict) -> None:
        if not self._alive():
            return
        if self._tap_dialog and hasattr(self, "_tap_log"):
            ts = datetime.now().strftime("%H:%M")
            name = str(data.get("name", "?"))
            text = str(data.get("text", ""))
            line = f"[{ts}] {name}: {text}\n"
            self._tap_messages.append({"name": name, "text": text, "ts": ts})
            self._tap_log.text += line

    def _on_tap_end(self, link_id: str, tap_id: str) -> None:
        if not self._alive():
            return
        for key in list(self._tap_ids):
            if self._tap_ids.get(key) == tap_id:
                self._tap_ids.pop(key, None)
        if self._tap_dialog and self._tap_id == tap_id and self._tap_link_id == link_id:
            self._tap_dialog.dismiss()
            self._tap_dialog = None
            self._tap_messages.clear()
        self.refresh_tap_notes_ui()


