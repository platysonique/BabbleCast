# BabbleCast — Polling Audit (Android sector)

**Scope:** `mobile/` Android-specific paths, `babblecast/audio/android_engine.py`, and shared deps invoked only from the Android/Kivy mobile stack (discovery browse, client UDP voice).

**Sector tag:** `android-mobile`

---

## Summary

| Area | Verdict |
|------|---------|
| Foreground service / wake lock / multicast lock | Event-driven start/stop on voice connect/disconnect ✓ |
| Bridge → UI marshaling (`Clock.schedule_once`) | Correct thread→main-thread pattern ✓ |
| mDNS browse | Event-driven via zeroconf `ServiceBrowser`; 30 s stale prune is fallback only |
| Voice UDP receive | 500 ms socket timeout poll loop (shared `session.py`) |
| Peer detail panel meters | 80 ms UI tick polls participant dict despite presence callbacks |
| Android audio I/O | Blocking/tight-loop frame paths (expected for AudioRecord/AudioTrack) |

---

## Findings

### [QTimer poll — Kivy Clock interval] — mobile/controller.py (`BabbleController._tick_ui`, L92, L290–299)

- **EVIDENCE**:
  ```python
  self._tick_ev = Clock.schedule_interval(self._tick_ui, 0.08)
  ...
  def _tick_ui(self, _dt: float) -> bool:
      ...
      if panel and panel._peer_key and panel._peer_open:
          p = self._participant_by_composite.get(panel._peer_key)
          if p:
              panel.update_peer(p)
  ```
- **EVENT-DRIVEN ALTERNATIVE**: `_on_presence` already updates `_participant_by_composite` (L586–594). When the detail panel is open for a peer, call `panel.update_peer(p)` from `_on_presence` (filter by `panel._peer_key`) and drop `Clock.schedule_interval`. Local mic meter already uses `on_local_mic_level` → `set_self_mic_level` (L64–65, L285–288).
- **SEVERITY**: medium
- **TIMESTAMP**: [2026-06-17 18:40]

---

### [loop + sleep — foreground service keep-alive] — mobile/voice_service.py (`main`, L4–8)

- **EVIDENCE**:
  ```python
  while True:
      time.sleep(3600)
  ```
  Registered in `mobile/buildozer.spec` L20 as `services = Voice:mobile/voice_service.py:foreground`.
- **EVENT-DRIVEN ALTERNATIVE**: Replace with `threading.Event().wait()` (or `wait(timeout=...)`) and set the event from service teardown if python-for-android exposes a stop hook; or omit the Python thread entirely and rely on the Android `PythonService` process staying alive via `START_STICKY` / foreground notification only. Avoids a pointless hourly wake.
- **SEVERITY**: medium
- **TIMESTAMP**: [2026-06-17 18:40]

---

### [loop + socket timeout poll] — babblecast/client/session.py (`ClientSession._udp_recv_loop`, L191–200)

- **EVIDENCE**:
  ```python
  while self._running:
      try:
          self._udp_sock.settimeout(0.5)
          data, _ = self._udp_sock.recvfrom(65535)
      except socket.timeout:
          continue
  ```
  Mobile voice uses `BridgeManager` → `ClientSession` with `create_speaker`/`create_mic` from `babblecast/audio/factory.py` (Android branch).
- **EVENT-DRIVEN ALTERNATIVE**: Register UDP socket with `selectors.DefaultSelector` (or fold into the existing asyncio loop via `loop.add_reader` / `create_datagram_endpoint`) so recv wakes only on datagram or explicit shutdown fd. Removes 2 Hz idle wake on Android.
- **SEVERITY**: medium
- **TIMESTAMP**: [2026-06-17 18:40]

---

### [periodic refresh — stale server prune] — babblecast/discovery.py (`ServerDiscovery._prune_loop`, L228–242)

- **EVIDENCE**:
  ```python
  while not self._stop_event.is_set():
      self._stop_event.wait(30)
      ...
      stale = [k for k, v in self._servers.items() if v.seen_at < cutoff]
  ```
  Started from `mobile/controller.py` `start_discovery()` → `ServerDiscovery.start()` (L104–107, L69).
- **EVENT-DRIVEN ALTERNATIVE**: `_on_service` already handles `ServiceStateChange.Removed` (L218–222). Consider removing the prune thread or extending `DISCOVERY_STALE_SEC` to a rare safety net only; refresh `seen_at` on re-resolve to avoid false stale drops on Android Wi‑Fi sleep.
- **SEVERITY**: low
- **TIMESTAMP**: [2026-06-17 18:40]

---

### [QTimer poll — meter peak decay] — mobile/vertical_meter.py (`VerticalMeter.__init__` / `_decay_peak`, L35, L46–51)

- **EVIDENCE**:
  ```python
  Clock.schedule_interval(self._decay_peak, 0.05)
  ...
  def _decay_peak(self, _dt: float) -> bool:
      if self._peak <= self._level:
          return True
      self._peak = max(self._level, self._peak - 0.018)
  ```
  Used by `mobile/detail_panel.py` for self/peer meters on Live screen.
- **EVENT-DRIVEN ALTERNATIVE**: Decay peak inside `set_level` using elapsed time (`Clock.get_time()` delta) or a single `Clock.schedule_once` chain only while `_peak > _level`; avoids 20 Hz timer when meters are idle.
- **SEVERITY**: low
- **TIMESTAMP**: [2026-06-17 18:40]

---

### [tight loop — mic read spin on zero] — babblecast/audio/android_engine.py (`AndroidMicCapture._loop`, L70–73)

- **EVIDENCE**:
  ```python
  while self._running:
      n = self._record.read(data, 0, buf_size)
      if n <= 0:
          continue
  ```
- **EVENT-DRIVEN ALTERNATIVE**: If `AudioRecord.read` returns 0 without blocking (error/transient), insert brief `threading.Event().wait(0.001)` or use Android `AudioRecord.OnRecordPositionUpdateListener` / `setRecordPositionUpdateListener` to pull frames only when the HAL signals new data. Verify blocking mode via `AudioRecord.read` overload with `READ_BLOCKING`.
- **SEVERITY**: low
- **TIMESTAMP**: [2026-06-17 18:40]

---

### [tight loop — speaker frame clock] — babblecast/audio/android_engine.py (`AndroidSpeakerOutput._loop`, L190–195)

- **EVIDENCE**:
  ```python
  while self._running:
      frame = self._mix()
      pcm = (frame * 32767.0).astype(np.int16)
      self._track.write(pcm.tobytes(), 0, len(pcm) * 2)
  ```
- **EVENT-DRIVEN ALTERNATIVE**: `AudioTrack` in `MODE_STREAM` requires a steady frame cadence; this is real-time playback, not state polling. Optional: block on `queue.Queue.get(timeout=frame_duration)` when all participant buffers are empty instead of mixing silence in a busy loop, or use `AudioTrack.write` blocking semantics to pace the thread.
- **SEVERITY**: low
- **TIMESTAMP**: [2026-06-17 18:40]

---

### [blocking read loop — mic capture] — babblecast/audio/android_engine.py (`AndroidMicCapture._loop`, L67–87)

- **EVIDENCE**:
  ```python
  while self._running:
      n = self._record.read(data, 0, buf_size)
      ...
      self._on_frame(gated.tobytes(), level)
  ```
- **EVENT-DRIVEN ALTERNATIVE**: Standard Android capture pattern when `read` blocks until `buf_size` bytes. Acceptable; levels already push to UI via `on_local_mic_level` callback (event-driven). No change unless zero-read spin (above) is observed on device.
- **SEVERITY**: low (acceptable)
- **TIMESTAMP**: [2026-06-17 18:40]

---

## Compliant (no action)

### [event-driven — Android foreground + wake lock] — mobile/android_foreground.py (`start_voice_foreground` / `stop_voice_foreground`)

- **EVIDENCE**: Started/stopped from `_sync_voice_foreground()` on link connect/disconnect (`mobile/controller.py` L425–429, L446, L459). No timers.
- **EVENT-DRIVEN ALTERNATIVE**: N/A — already tied to bridge link lifecycle.
- **SEVERITY**: low (compliant)
- **TIMESTAMP**: [2026-06-17 18:40]

---

### [event-driven — Wi‑Fi multicast lock] — mobile/android_network.py

- **EVIDENCE**: `acquire_multicast_lock()` once at discovery start; `release_multicast_lock()` at shutdown. No poll loop.
- **EVENT-DRIVEN ALTERNATIVE**: N/A.
- **SEVERITY**: low (compliant)
- **TIMESTAMP**: [2026-06-17 18:40]

---

### [one-shot timers — OK] — mobile/controller.py, mobile/app.py, mobile/screens.py

- **EVIDENCE**:
  ```python
  Clock.schedule_once(lambda _dt, i=lid: self._on_link_connected(i))  # bridge callbacks
  Clock.schedule_once(lambda _dt: self.controller.start_discovery(), 0)
  Clock.schedule_once(fire_long, 0.6)  # long-press gesture
  ```
- **EVENT-DRIVEN ALTERNATIVE**: Correct Kivy patterns for thread→UI marshaling and gesture delay; not periodic polling.
- **SEVERITY**: low (compliant)
- **TIMESTAMP**: [2026-06-17 18:40]

---

## Recommended priority (Android)

1. **Medium:** Remove `_tick_ui` interval; refresh open peer panel from `_on_presence`.
2. **Medium:** Replace UDP `settimeout` poll in `session.py` with selector/async reader (mobile voice path).
3. **Medium:** Replace `voice_service.py` sleep loop with event-based or service-native keep-alive.
4. **Low:** Tighten meter peak decay and review mic read zero-spin on hardware.
