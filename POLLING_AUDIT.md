# BabbleCast — Polling Audit

**Scope:** Focus files (`main_window.py`, `session.py`, `embedded.py`, `hub.py`, `mobile/main.py`, `bridge.py`) plus direct dependencies they invoke (discovery, audio I/O).

**Sector:** host/connect · room updates · presence · chat

---

## Summary — focus areas (no timer abuse found)

| Area | Pattern in focus files | Verdict |
|------|------------------------|---------|
| **Host / connect** | `EmbeddedServer` fires `on_started` / `on_failed` callbacks; UI connects in handler (`main_window.py:401–411`, `mobile/main.py:241–253`). No retry timers or poll-until-ready loops. | Event-driven ✓ |
| **Room updates** | Client pulls once via `request_rooms()` on connect / active-link switch (`main_window.py:465,509`, `mobile/main.py:303,335`). Server pushes `ROOMS` on membership changes (`hub.py:401–409`). | Event-driven ✓ |
| **Presence** | Server pushes `PRESENCE` on state changes; clients update UI from bridge callbacks (`main_window.py:605–607`, `mobile/main.py:452–455`). No client-side refresh timer. | Event-driven ✓ (see hub voice-level note below) |
| **Chat** | WebSocket `CHAT` messages → bridge callback → UI append (`main_window.py:649–655`, `mobile/main.py:602–609`). Local store reload only on room/link change, not on a timer. | Event-driven ✓ |

---

## Findings

### [loop + socket timeout poll] — babblecast/client/session.py (`ClientSession._udp_recv_loop`, L188–217)

- **EVIDENCE**:
  ```python
  while self._running:
      try:
          self._udp_sock.settimeout(0.5)
          data, _ = self._udp_sock.recvfrom(65535)
      except socket.timeout:
          continue
  ```
- **EVENT-DRIVEN ALTERNATIVE**: Register the UDP socket with `asyncio` (`loop.add_reader` / `create_datagram_endpoint` on the client side) or use `selectors.DefaultSelector` with a blocking wait that wakes on datagram arrival and on shutdown (e.g. `selector.register(sock)` + `selector.register(self._shutdown_fd)`). Keeps voice receive off a 500 ms wake loop.
- **SEVERITY**: medium
- **TIMESTAMP**: [2026-06-17 16:24]

---

### [periodic refresh] — babblecast/discovery.py (`ServerDiscovery._prune_loop`, L192–205)

- **EVIDENCE**:
  ```python
  def _prune_loop(self) -> None:
      while not self._stop_event.is_set():
          self._stop_event.wait(5)
          ...
          stale = [k for k, v in self._servers.items() if v.seen_at < cutoff]
  ```
- **EVENT-DRIVEN ALTERNATIVE**: Handle `ServiceStateChange.Removed` in `_on_service` (currently ignored at L186–187) to remove entries immediately; optionally refresh `seen_at` on re-resolve. Drop the 5 s prune thread if mDNS removal events are handled. Used by `main_window.py:107` and `mobile/main.py:64–66` for Discover list.
- **SEVERITY**: medium
- **TIMESTAMP**: [2026-06-17 16:24]

---

### [ignored removal event → forced timer prune] — babblecast/discovery.py (`ServerDiscovery._on_service`, L186–187)

- **EVIDENCE**:
  ```python
  if state_change is ServiceStateChange.Removed:
      return
  ```
- **EVENT-DRIVEN ALTERNATIVE**: On `Removed`, delete the server keyed by host (or service name) and call `_emit()` so Discover UI updates without waiting for `_prune_loop` (up to `DISCOVERY_STALE_SEC` = 30 s).
- **SEVERITY**: high
- **TIMESTAMP**: [2026-06-17 16:24]

---

### [push storm on voice level — presence] — babblecast/server/hub.py (`BabbleCastHub._handle_message` VOICE_LEVEL, L293–297)

- **EVIDENCE**:
  ```python
  if mtype == MsgType.VOICE_LEVEL:
      client.voice_level = float(data.get("level", 0.0))
      client.speaking = client.voice_level > 0.08 and not client.muted
      if client.room_id:
          await self._send_presence(client.room_id)
  ```
  Client sends level on change (`session.py:169–177`, threshold ~0.04) but each send rebroadcasts full participant list to the room.
- **EVENT-DRIVEN ALTERNATIVE**: Not a poll loop, but abusive frequency: debounce/throttle `_send_presence` per room (e.g. max 5–10 Hz), or send lightweight `VOICE_LEVEL` / `SPEAKING` deltas to room members instead of full `PRESENCE` snapshots on every mic tick.
- **SEVERITY**: medium
- **TIMESTAMP**: [2026-06-17 16:24]

---

### [audio mix worker loop] — babblecast/audio/engine.py (`SpeakerOutput._worker_loop`, L191–197)

- **EVIDENCE**:
  ```python
  while self._running:
      frame = self._mix_frame()
      try:
          self._queue.put(frame, timeout=0.05)
  ```
- **EVENT-DRIVEN ALTERNATIVE**: Acceptable for real-time audio: PortAudio output callback (`_callback`) is event-driven; worker fills mix queue at ~20 ms frame rate. Not a substitute for UI/network polling. No change required unless moving to fully callback-driven mix.
- **SEVERITY**: low
- **TIMESTAMP**: [2026-06-17 16:24]

---

### [blocking read loop — mobile audio] — babblecast/audio/android_engine.py (`AndroidMicCapture._loop` L63–84, `AndroidSpeakerOutput._loop` L186–191)

- **EVIDENCE**:
  ```python
  while self._running:
      n = self._record.read(data, 0, buf_size)
  ```
  Speaker path spins `_mix()` → `AudioTrack.write` in a tight loop.
- **EVENT-DRIVEN ALTERNATIVE**: Android `AudioRecord.read` blocks until data; speaker loop is frame-clock driven. Bridge/mobile voice path depends on this (`bridge.py` → `ClientSession` on mobile). Low priority vs UDP/discovery; optional: align speaker loop to `AudioTrack` buffer callbacks if API allows.
- **SEVERITY**: low
- **TIMESTAMP**: [2026-06-17 16:24]

---

### [shutdown join timeout] — babblecast/server/embedded.py (`EmbeddedServer.stop`, L95)

- **EVIDENCE**:
  ```python
  self._thread.join(timeout=10)
  ```
- **EVENT-DRIVEN ALTERNATIVE**: One-shot shutdown wait, not a feature poll. `call_soon_threadsafe` + `loop.stop()` (L91–94) is appropriate. No change needed for host/connect UX.
- **SEVERITY**: low
- **TIMESTAMP**: [2026-06-17 16:24]

---

### [WebSocket keepalive ping] — babblecast/client/session.py L324, babblecast/server/hub.py L504

- **EVIDENCE**:
  ```python
  websockets.connect(uri, ping_interval=20, ping_timeout=20)
  websockets.serve(..., ping_interval=20, ping_timeout=20)
  ```
- **EVENT-DRIVEN ALTERNATIVE**: Library-managed connection health checks; standard for long-lived WS. Not timer abuse for rooms/presence/chat.
- **SEVERITY**: low
- **TIMESTAMP**: [2026-06-17 16:24]

---

### [one-shot UI timers — OK] — mobile/main.py (`Clock.schedule_once`, multiple)

- **EVIDENCE**:
  ```python
  on_link_connected=lambda lid: Clock.schedule_once(lambda _dt, i=lid: self._on_link_connected(i))
  Clock.schedule_once(lambda _dt: self.controller.start_discovery(), 0)
  Clock.schedule_once(lambda _dt: self._open_context_menu(), 0.45)  # long-press
  ```
- **EVENT-DRIVEN ALTERNATIVE**: Correct Kivy pattern for thread→UI marshaling and gesture delays. Not periodic polling. No `Clock.schedule_interval` used for connect, rooms, presence, or chat.
- **SEVERITY**: low (compliant)
- **TIMESTAMP**: [2026-06-17 16:24]

---

### [signal-driven UI — OK] — babblecast/client/qt/main_window.py (`_UiSignals`, L46–90)

- **EVIDENCE**:
  ```python
  self._ui.presence.connect(self._on_presence)
  self._ui.chat.connect(self._on_chat)
  self._ui.rooms.connect(self._on_rooms)
  self._ui.embedded_started.connect(self._on_embedded_started)
  ```
- **EVENT-DRIVEN ALTERNATIVE**: Already event-driven; bridge callbacks marshaled via `pyqtSignal`. No `QTimer` used for host/connect, room list, presence, or chat in this file.
- **SEVERITY**: low (compliant)
- **TIMESTAMP**: [2026-06-17 16:24]

---

### [bridge fan-out — OK] — babblecast/client/bridge.py

- **EVIDENCE**: Mic `on_frame` / `on_level` callbacks fan out to sessions (`L133–148`); session WS handlers invoke `on_presence` / `on_chat` / `on_rooms` lambdas (`L168–183`). No timers or sleep loops in module.
- **EVENT-DRIVEN ALTERNATIVE**: N/A — already callback-driven.
- **SEVERITY**: low (compliant)
- **TIMESTAMP**: [2026-06-17 16:24]

---

## Recommended priority

1. **High:** Handle mDNS `Removed` in `discovery.py` and remove or lengthen-only fallback prune.
2. **Medium:** Replace UDP `settimeout` poll in `session.py` with selector/async reader.
3. **Medium:** Throttle or delta-update presence on `VOICE_LEVEL` in `hub.py`.
