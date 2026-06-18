# Known issues

Tracked runtime errors and workarounds for BabbleCast.

---

## mDNS discovery: `ServerDiscovery._on_service()` unexpected keyword `zeroconf`

**Status:** Fixed (2026-06-17)  
**Reported:** 2026-06-17 (Pop!_OS 24.04, Python 3.12, zeroconf 0.149.16)  
**Affects:** Client GUI / server list discovery (`ServerDiscovery` in `babblecast/discovery.py`)

### Symptom

When the client starts browsing for BabbleCast servers on the LAN, a background thread crashes and LAN discovery stops working. The app may otherwise appear to run.

### Traceback

```
Exception in thread zeroconf-ServiceBrowser-_babblecast._tcp-161801:
Traceback (most recent call last):
  File "/usr/lib/python3.12/threading.py", line 1073, in _bootstrap_inner
    self.run()
  File "src/zeroconf/_services/browser.py", line 820, in zeroconf._services.browser.ServiceBrowser.run
  File "src/zeroconf/_services/browser.py", line 730, in zeroconf._services.browser._ServiceBrowserBase._fire_service_state_changed_event
  File "src/zeroconf/_services/browser.py", line 740, in zeroconf._services.browser._ServiceBrowserBase._fire_service_state_changed_event
  File "src/zeroconf/_services/__init__.py", line 59, in zeroconf._services.Signal.fire
TypeError: ServerDiscovery._on_service() got an unexpected keyword argument 'zeroconf'
```

### Cause

`zeroconf` ≥ 0.132 invokes `ServiceBrowser` handlers with a **`zeroconf=` keyword argument**. The callback used `zc` as the first parameter name, so Python rejected the keyword call.

### Fix

Renamed the first parameter to `zeroconf` in `ServerDiscovery._on_service` (`babblecast/discovery.py`).

### Workaround (older builds)

Connect manually to a known server address (Tailscale IP or LAN IP + port) instead of relying on the auto-discovered server list.

---

## Android: noise suppression unavailable

**Status:** Open (by design on mobile)  
**Affects:** Android APK (`mobile/`)

### Symptom

Noise suppression slider has no effect on Android; gate still works.

### Cause

`noisereduce` / `scipy` are not bundled in the Android build (size/complexity). `NoiseSuppressor` skips when `noisereduce` is missing.

### Workaround

Use the noise gate (mute/PTT). Desktop client has full suppression.

---

## iOS build

**Status:** Blocked on Linux  
**Affects:** iOS packaging

Cannot compile or sideload iOS apps without macOS + Xcode. See `packaging/ios/README.md`.

---

## Windows CI (GitHub Actions)

**Status:** Open  
**Affects:** `.github/workflows/windows.yml`

Private-repo Windows runner jobs may fail immediately (`runner_id: 0`). Use a real Windows machine or fix runner billing/access.

---

## Wine on Linux

**Status:** Unsupported  
**Affects:** Anyone trying to run Windows `python.exe` under Wine

Will crash (missing Win32 APIs, no PortAudio/PyQt6). Use native Linux install or a Windows VM.

---

## Linux: PortAudio ALSA output failure and Opus crash on startup

**Status:** Fixed (2026-06-17)  
**Reported:** 2026-06-17 (Pop!_OS 24.04, Python 3.12, PipeWire/PulseAudio + ALSA via PortAudio)  
**Affects:** Client audio startup (`SpeakerOutput.start` in `babblecast/audio/engine.py`, triggered from `ClientSession._start_audio`)

### Symptom

Running `bbc` may print a scipy warning, then ALSA/PortAudio errors, fail to open the output device, and abort with a core dump in Opus/silk after the speaker stream fails.

### Log / traceback

```
/home/papaya/Projects/BabbleCast/.venv/lib/python3.12/site-packages/scipy/signal/_spectral_py.py:1613: UserWarning: nperseg = 1024 is greater than input length  = 960, using nperseg = 960
  freqs, time, Zxx = _spectral_helper(x, x, fs, window, nperseg, noverlap,
Expression 'ret' failed in 'src/hostapi/alsa/pa_linux_alsa.c', line: 1736
...
sounddevice.PortAudioError: Error opening OutputStream: Device unavailable [PaErrorCode -9985]
Fatal (internal) error in silk/resampler.c, line 184: assertion failed: inLen >= S->Fs_in_kHz
Aborted (core dumped)
```

### Cause

1. **PortAudio `-9985`** — default ALSA output device unavailable; PipeWire/Pulse devices were not tried as fallbacks.
2. **Partial startup** — mic could start, speaker fail, leaving a broken audio path.
3. **Opus silk abort** — invalid/short PCM reached the encoder after startup failure.
4. **scipy warning** — `noisereduce` on 960-sample frames (harmless noise).

### Fix

- `babblecast/audio/portaudio.py` — try devices in order: saved preference → default (PipeWire before Pulse before ALSA) → all outputs.
- `SpeakerOutput.start` / `MicCapture.start` — iterate fallbacks; roll back worker thread on failure.
- `ClientSession._start_audio` — start speaker first; stop both on error; show dialog instead of crashing.
- `BridgeManager._ensure_audio` — same cleanup; connect continues for chat if audio fails.
- `OpusCodec` — pad/validate frame size; empty decode returns silence; `decode_plc()` for packet loss.
- `NoiseSuppressor` — skip processing on frames shorter than 1024 samples.
- `ClientSession.connect` — set `_running` before starting UDP receive thread (thread was exiting immediately).
- `ClientSession.disconnect` — join UDP thread; jitter buffer + PLC on receive path.
- `BabbleCastHub` — UDP relay verifies sender socket port (anti-spoof).

---

## Android UI (ScrollView debug layout)

**Status:** Fixed (2026-06-17)  
**Affects:** Android APK (`mobile/main.py`)

### Symptom

Single long ScrollView form; no theme; noise gate missing; looked like a debug screen.

### Fix

Tokyo Night dark theme (`mobile/theme.py`), bottom navigation (Connect / Live / Settings), card-based server list, gate slider on Settings tab. Branding uses hand-prepared assets only (`assets/bbcicon.png`, `assets/icon.png`) — no auto-crop script.

---

## Voice UDP receive thread never ran

**Status:** Fixed (2026-06-17)  
**Affects:** All clients (`babblecast/client/session.py`)

### Symptom

Connected and chat worked, but no incoming voice (relay packets sat in socket buffer).

### Cause

`_start_udp()` ran before `_running = True`, so the receive loop exited immediately.

### Fix

Set `_running = True` before spawning the UDP thread.

### Workaround (older builds or broken system audio)

- Confirm audio works in other apps (browser, `speaker-test`, system settings).
- On Pop!_OS / Ubuntu with PipeWire: ensure user session audio is running (`pipewire`, `wireplumber`, or PulseAudio compatibility).
- In BabbleCast, pick a different **output device** in settings before connect.
- Retry after `systemctl --user restart pipewire wireplumber` (or log out/in).

---

## Linux: immediate Opus `silk/resampler` abort on launch

**Status:** Fixed (2026-06-17)  
**Reported:** 2026-06-17 (Pop!_OS 24.04, Python 3.12, post–PortAudio-fix builds)  
**Affects:** Client launch (`bbc`) — process aborts before or without a useful Python traceback

### Symptom

Running `bbc` exits immediately with a native Opus assertion. No Python stack trace is printed; the shell only shows:

```
Fatal (internal) error in silk/resampler.c, line 184: assertion failed: inLen >= S->Fs_in_kHz
Aborted (core dumped)
```

### Log

```
papaya@pop-os:~$ bbc
Fatal (internal) error in silk/resampler.c, line 184: assertion failed: inLen >= S->Fs_in_kHz
Aborted (core dumped)
```

### Cause (likely)

Opus/SILK internal resampler received **too few input samples** (`inLen` smaller than one millisecond at the input sample rate). This usually means empty, truncated, or mis-sized PCM reached `opuslib` encode/decode — often when:

- Audio startup partially fails but the voice pipeline still runs
- A zero-length or sub-frame buffer is passed to the encoder/decoder
- A background thread encodes before mic capture is producing valid 20 ms frames

Related to the earlier PortAudio startup issue ([above](#linux-portaudio-alsa-output-failure-and-opus-crash-on-startup)), but this variant can appear **without** visible ALSA/PortAudio log lines if the crash happens quickly or stderr is not flushed.

Relevant code: `babblecast/audio/codec.py` (`OpusCodec`), `babblecast/client/session.py` (voice loop), `babblecast/audio/engine.py` (capture/playback).

### Workarounds

- Ensure system audio is healthy (PipeWire/Pulse running; output device works in other apps).
- Run `bbc server` (headless, no local mic/speaker) to confirm the crash is client-audio-specific.
- Update to the latest `master` after each fix; re-run `bash packaging/linux/install.sh`.

### Proposed fix

- Never call Opus encode/decode on buffers shorter than `FRAME_SAMPLES` (960 @ 48 kHz).
- Guard all codec entry points; return silence instead of calling native Opus on invalid input.
- Defer starting the voice/encode loop until both mic and speaker streams are confirmed open.
- Catch native abort paths by validating PCM length in Python before every `opuslib` call.

### Fix

- `babblecast/audio/codec.py` — pad/validate PCM; reject short packets; PLC returns silence on error.
- Audio startup defers voice until speaker/mic streams open; failed startup tears down without encoding.

---

## Linux: `QMouseEvent` has no attribute `globalPos` (participant right-click)

**Status:** Fixed (2026-06-17)  
**Reported:** 2026-06-17 (Pop!_OS 24.04, PyQt6 6.11)  
**Affects:** Desktop client — was right-click participant name for saved Taps menu

### Symptom

Right-clicking a participant name crashed the client on PyQt6.

### Fix

Participant rows now use **double-click** to open the detail drawer; right-click menu removed. Use **Tap** from the drawer instead.

---

## Linux: mic switch fails on ALSA hardware device (`PaErrorCode -9985`)

**Status:** Partially fixed (2026-06-17)  
**Reported:** 2026-06-17 (Pop!_OS 24.04, Python 3.12, PortAudio ALSA host API)  
**Affects:** Desktop client — changing **Input mic** in the audio drawer while connected or monitoring (`MicCapture.set_device` via `BridgeManager.set_input_device` / `ClientSession.set_input_device`)

### Symptom

User selects a different microphone in the UI (audio drawer → Input mic combo). Console prints low-level ALSA errors and a PortAudio warning; the requested mic may not actually be used.

### Log (user report)

```
Expression 'ret' failed in 'src/hostapi/alsa/pa_linux_alsa.c', line: 1736
Expression 'AlsaOpen( &alsaApi->baseHostApiRep, params, streamDir, &self->pcm )' failed in 'src/hostapi/alsa/pa_linux_alsa.c', line: 1904
Expression 'PaAlsaStreamComponent_Initialize( &self->capture, alsaApi, inParams, StreamDirection_In, NULL != callback )' failed in 'src/hostapi/alsa/pa_linux_alsa.c', line: 2171
Expression 'PaAlsaStream_Initialize( stream, alsaHostApi, inputParameters, outputParameters, sampleRate, framesPerBuffer, callback, streamFlags, userData )' failed in 'src/hostapi/alsa/pa_linux_alsa.c', line: 2839
Mic open failed on device 12: Error opening InputStream: Device unavailable [PaErrorCode -9985]
```

### Investigation summary

Reproduced locally on the same machine (`papaya@pop-os`) with BabbleCast `f23a2c4`.

#### Device involved

On this system, **PortAudio device index 12** is:

| Index | Name | Type |
|------:|------|------|
| 12 | `USB CAMERA: Audio (hw:2,0)` | Raw ALSA hardware capture node (USB webcam mic) |
| 34 | `default` | System default input (PipeWire/Pulse route) |

The UI lists both in the Input mic dropdown (`detail_drawer.py` → `populate_devices` → all entries from `list_input_devices()`).

#### Call path when user changes mic

1. User picks device in **Input mic** `QComboBox` (`detail_drawer.py::_input_changed`)
2. → `BridgeManager.set_input_device(device_key)` (or `ClientSession.set_input_device` per link)
3. → saves `input_device` to settings, calls `MicCapture.set_device(device_key)`
4. → `stop()` closes current `InputStream`, then `start()` reopens via `iter_input_device_indices(preferred_key)`

Relevant code: `babblecast/audio/engine.py` (`MicCapture.set_device`, `MicCapture.start`), `babblecast/audio/portaudio.py` (`iter_input_device_indices`).

#### Reproduction

```text
Start mic on default (device 34) → switch to USB CAMERA (device 12)
```

Result: **identical ALSA errors** and `Mic open failed on device 12: ... [PaErrorCode -9985]`.

Cold-open of device 12 **succeeds** when no other BabbleCast input stream is active. Failure occurs specifically during **hot-swap** from an already-open stream (typically on `default` / PipeWire route).

After device 12 fails, `MicCapture.start()` **silently falls back** to the next candidate in `iter_input_device_indices` (usually device 34 `default` again). The user may believe they switched to the USB camera while still on the default route.

#### Root causes (multiple, compounding)

1. **Raw ALSA hw node vs PipeWire session routing**  
   Selecting `USB CAMERA: Audio (hw:2,0)` asks PortAudio to open the **direct hardware PCM** (`hw:2,0`). While PipeWire/Pulse already owns or routes that device through the session graph, ALSA returns *device unavailable* (`-9985`). This is distinct from opening `default`, `pipewire`, or `pulse` virtual devices (indices 27–28, 34 on this machine).

2. **Hot-swap stops then reopens with no settle time**  
   `set_device()` calls `stop()` then immediately `start()` on the new index. ALSA/PipeWire may not release the previous handle instantly; the preferred hw device is tried first and fails before fallback.

3. **Fallback masks user intent**  
   `iter_input_device_indices` tries preferred → defaults → all inputs. When the user's pick fails, a warning is logged but **no UI error** is shown; capture may resume on a different device without notice.

4. **`_enabled` flag not restored after `stop()`** (secondary defect)  
   `MicCapture.stop()` sets `_enabled = False`; `start()` never sets it back to `True`. After a device switch, the PortAudio callback returns immediately even if a fallback stream opens — **local meters and transmit can stop working** until app restart.

5. **No error handling on device change**  
   `BridgeManager.set_input_device` / `ClientSession.set_input_device` do not catch `PortAudioError`. If every candidate fails, the exception propagates into the Qt signal handler (potential crash). If fallback succeeds, the user sees only stderr noise.

6. **Host-API preference ineffective on this OS**  
   PortAudio reports all devices as host API **ALSA** (including `pipewire` / `pulse` plugin devices). `_host_rank()` in `portaudio.py` cannot prefer PipeWire over raw hw nodes for fallback ordering beyond index sort order.

7. **Device list includes entries unsuitable for hot-swap**  
   Dropdown exposes raw `hw:X,Y` nodes, ALSA plugins (`lavrate`, `speexrate`, …), and virtual routes side-by-side with no guidance. Users can pick hardware nodes that work in isolation but fail under an active PipeWire session.

#### What this is NOT

- Not a missing `libportaudio2` install (capture works on `default` at startup).
- Not an Opus/codec issue (failure occurs before encode, at `sd.InputStream` open).
- Not the same as the earlier **output** `-9985` at first launch (that path was partially fixed); this is **input capture** during **runtime device change**.

### Workarounds

- Prefer **`default`**, **`pipewire`**, or **`pulse`** entries in Input mic — avoid raw `hw:…` USB/HDA nodes unless you know they are free.
- Close other apps using the mic (browser, OBS, Zoom) before switching.
- If switch fails: restart `bbc`, or log out/in to reset PipeWire (`systemctl --user restart pipewire wireplumber`).
- After a failed switch, verify the meter still moves; if not, restart the app (see `_enabled` bug above).

### Proposed fix (not implemented — report only)

- Surface mic-switch failures in the UI (toast/dialog) when preferred device fails, including whether fallback was used.
- After successful `start()`, set `_enabled = True`; preserve/restore level callback in `stop()`/`start()`.
- Wrap `set_device()` / `set_input_device()` in try/except; on total failure, leave previous device or show recoverable error.
- Prefer virtual routes (`default` / `pipewire` / `pulse`) in the dropdown or mark raw hw nodes as advanced.
- Optional delay or retry after `stop()` before opening new device; or use PipeWire-native device selection when available.
- Consider opening only devices that match the active host route rather than arbitrary hw indices during hot-swap.

### Fix applied (2026-06-17)

- `MicCapture.stop(teardown=False)` no longer clears `_enabled` / `_on_level` during hot-swap; `start()` sets `_enabled = True` after open.
- Brief settle delay (50 ms) after stop before reopen on device change.
- Full teardown paths (`bridge` / `session` shutdown) call `stop(teardown=True)`.

Remaining: UI feedback when preferred hw device fails; prefer `default`/`pipewire` in device list labels.

---

## LAN discovery: real IPs + beacon + mesh probe

**Status:** By design (2026-06-17)  
**Affects:** `babblecast/network.py`, `babblecast/network_scan.py`, `babblecast/discovery_beacon.py`, `babblecast/mesh_probe.py`

### How it works

- Servers advertise **real private LAN IPs** (`192.168.x.x`, `10.x`, etc.) via mDNS A records and hostname `name.babblecast.local`.
- **UDP beacon** on port `9515` carries `{name, lan, ws}`; the server **unicasts** a reply when it hears `BABBLE_DISCOVER` — this crosses Google/Nest Wifi mesh subnets.
- **Mesh probe** uses `ip route get` to find routable sibling-subnet IPs and probes TCP `9513` — no blind `/24` sweeps.
- Clients connect directly to the LAN IP (or mDNS hostname). **Self-connect on the same machine** still uses `127.0.0.1`.

### Note on mDNS

mDNS is link-local and does **not** cross Wi‑Fi/wired subnet boundaries on consumer mesh routers. The **beacon + mesh probe** path is the cross-subnet discovery fallback.

### Deprecated: virtual `11.2.x.x` overlay

The `11.2.x.x` virtual address space and `overlay_net` / `overlay_route` modules were removed. Mesh routers route real `192.168.x.x` internally but treat `11.2.x.x` as unknown internet-bound traffic.

---

## ~~LAN discovery: BabbleCast address scan (`11.2.x.x`)~~

**DEPRECATED** (2026-06-17): Replaced by LAN-first discovery (see above).

---

## ~~LAN discovery: virtual `11.2.x.x` addresses not reachable on physical network~~

**DEPRECATED** (2026-06-17): Confirmed by live network tests — overlay does not work cross-subnet without router static routes Google Wifi cannot add.

---

## ~~LAN discovery: phone and PC on different subnets~~

**DEPRECATED** (2026-06-17): Wrong approach — added `192.168.*` gateway probing instead of targeted beacon/mesh probe. Removed.

---

## WebSocket disconnect: `keepalive ping timeout` (1011) and `_send` task spam

**Status:** Open  
**Reported:** 2026-06-17 (Pop!_OS 24.04, Python 3.12, `websockets` 16.0)  
**Affects:** Desktop client — any connected session (`ClientSession` in `babblecast/client/session.py`), especially bridge/multi-server mode (`BridgeManager` in `babblecast/client/bridge.py`)

### Symptom

While connected (or shortly after), the terminal prints `WebSocket session ended`, then a primary traceback ending in:

```
websockets.exceptions.ConnectionClosedError: sent 1011 (internal error) keepalive ping timeout; no close frame received
```

That is followed by dozens or **hundreds** of identical lines:

```
Task exception was never retrieved
future: <Task finished name='Task-NNNNN' coro=<ClientSession._send() ...>
TimeoutError: timed out while closing connection
...
websockets.exceptions.ConnectionClosedError: sent 1011 (internal error) keepalive ping timeout; no close frame received
```

The GUI may show the server link as dropped; voice/chat on that link stops. The app may otherwise keep running (other links, local mic monitoring).

### Log (user report, abbreviated)

```
WebSocket session ended
TimeoutError: timed out while closing connection
...
File ".../babblecast/client/session.py", line 385, in _thread_main
    self._loop.run_until_complete(self._run_ws())
File ".../babblecast/client/session.py", line 349, in _run_ws
    async for raw in ws:
...
websockets.exceptions.ConnectionClosedError: sent 1011 (internal error) keepalive ping timeout; no close frame received
Task exception was never retrieved
future: <Task finished name='Task-33583' coro=<ClientSession._send() done, defined at .../session.py:234> ...>
(repeated for Task-33584 … Task-34705 — ~170+ pending send tasks in one burst)
```

User launched `bbc` twice in the same shell session before the errors appeared (two client instances may have been running).

### Investigation summary

Reproduced by code review on branch `cursor/room-switch-delete-chat-persistence` @ `8f3183e` (same tree as user install).

#### What `1011 keepalive ping timeout` means

Both client and server open WebSocket with **`ping_interval=20`, `ping_timeout=20`**:

```346:346:babblecast/client/session.py
        async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
```

```655:660:babblecast/server/hub.py
        self._ws_server = await websockets.serve(
            self._ws_handler,
            self.host,
            self.ws_port,
            ping_interval=20,
            ping_timeout=20,
```

In `websockets` 16, a background **keepalive task** sends a WebSocket ping every 20 seconds and waits up to 20 seconds for a pong. If no pong arrives, the **local** endpoint closes with WebSocket code **1011** and reason **`keepalive ping timeout`**. The error text **`sent 1011`** means **this client** initiated the close (the server did not send a clean close frame first — hence `no close frame received`).

So the immediate failure is: **the client stopped receiving timely pongs from the server** (or could not process them on its asyncio loop in time). Underlying causes are environmental or architectural, not a single bad JSON message.

#### Client WebSocket architecture

| Component | Role |
|-----------|------|
| `_thread_main` | Dedicated thread; runs one `asyncio` event loop |
| `_run_ws` | Connects, then **`async for raw in ws:`** — sole consumer of inbound frames |
| `_send` / `_send_async` | Outbound JSON control messages |
| `_on_voice_level` | Called from **PortAudio audio callback thread** (~50 Hz); schedules `_send(VOICE_LEVEL)` via `asyncio.run_coroutine_threadsafe` |

Critical paths:

```184:193:babblecast/client/session.py
    def _on_voice_level(self, level: float) -> None:
        if not self._loop or not self._ws:
            return
        if abs(level - self._last_level_sent) < 0.04 and (level > 0.05) == (self._last_level_sent > 0.05):
            return
        self._last_level_sent = level
        asyncio.run_coroutine_threadsafe(
            self._send(encode_msg(MsgType.VOICE_LEVEL, level=level)),
            self._loop,
        )
```

```520:522:babblecast/client/session.py
    def _send_async(self, message: str) -> None:
        if self._loop and self._ws:
            asyncio.run_coroutine_threadsafe(self._send(message), self._loop)
```

Every mute/PTT/chat/presence/volume action from the UI thread uses the same **`run_coroutine_threadsafe`** pattern. **No `Future` is awaited or given a done-callback**, so any exception in `_send` becomes **"Task exception was never retrieved"**.

#### Why so many `_send` task errors?

Task names in the log (`Task-33583` … `Task-34705`) indicate **~170+ concurrent/completed send coroutines** failing in one disconnect window. Contributing factors:

1. **High scheduling rate from audio** — `MicCapture._callback` invokes `_on_level` on **every 20 ms frame** (~50/s). Throttling skips small level deltas, but during speech or noise the client can still emit many `VOICE_LEVEL` messages per second.

2. **Bridge fan-out** — `BridgeManager._on_mic_level` calls `session.send_voice_level(level)` for **each connected server link**, multiplying WS send pressure:

```208:211:babblecast/client/bridge.py
        for link_id, session in list(self._sessions.items()):
            link = self._links.get(link_id)
            if link and not link.mic_muted and session.connected:
                session.send_voice_level(level)
```

3. **Server echo load** — Each `VOICE_LEVEL` can trigger `_send_presence` on the hub (throttled to ≥100 ms when level delta > 0.05), broadcasting full participant lists back to every room member. That increases inbound traffic the client must read while also processing outbound sends.

4. **No send gate after disconnect starts** — When keepalive fails, `_ws` remains non-`None` until `_shutdown_transport` runs in `finally`. The audio thread **continues scheduling `_send`** during teardown, so each queued send raises the same `ConnectionClosedError`.

5. **Secondary `TimeoutError`** — While closing an already-dead socket, `websockets` may also log `TimeoutError: timed out while closing connection` during the close handshake; this is a follow-on symptom, not the root cause.

#### Likely root causes (ranked)

1. **Network path loss or latency** — Wi‑Fi sleep/roam, VPN/Tailscale hiccup, server host sleeping, firewall/NAT dropping idle TCP, or connecting over a high-latency link. With only **20 s** ping timeout, brief outages trigger 1011.

2. **Server process stopped or wedged** — If `bbc server` exits, crashes, or its asyncio loop blocks >20 s, pongs stop. UDP voice may appear to work briefly (separate socket) while WS control is dead.

3. **Client asyncio loop lag** (possible amplifier) — The WS thread serves both the recv loop and all `run_coroutine_threadsafe` send tasks. A burst of sends + large `PRESENCE` payloads could delay I/O; keepalive runs as its own task on the same loop, so sustained starvation could contribute on a loaded client.

4. **Multiple client instances** — User ran `bbc` twice; two GUIs share the same mic/PipeWire stack and may open duplicate sessions to the same server, increasing load and confusion (not required for the bug, but observed).

#### What this is NOT

- Not an application-level `MsgType.PING` protocol error (hub handles app `ping`/`pong` separately in `_handle_message`).
- Not UDP/voice-path failure (voice uses a different socket; this error is **control WebSocket only**).
- Not a missing Python package — `websockets` 16.0 is installed and behaving as designed.
- Not user-fixable by reinstall alone unless paired with network/server checks.

#### User-visible impact

- Server link drops; chat, presence, taps, and room sync on that link stop until reconnect.
- Terminal flooded with repetitive tracebacks (noise for debugging).
- `ClientSession.connected` stays `True` while `_running and _ws` until teardown — UI may briefly think it is still connected.

### Workarounds

- **Reconnect** — Disconnect and reconnect to the server in the UI, or restart `bbc`.
- **Stabilize network** — Prefer wired Ethernet or reliable LAN; avoid sleep/suspend during calls; if using Tailscale/mesh VPN, verify the peer is reachable (`ping <server-ip>`) before connecting.
- **Keep server alive** — Run `bbc server` on a stable host; confirm it is still running when clients drop (no OOM kill, no laptop lid-close).
- **Reduce load while testing** — Single `bbc` instance; mute mic on links you are not actively using (stops `VOICE_LEVEL` WS traffic for that link); fewer simultaneous bridge links.
- **Ignore log spam** — The repeated `_send` errors are a **symptom of teardown**, not separate failures; fixing reconnect/network addresses the functional issue.

### Proposed fix (not implemented — report only)

- **Handle send futures** — Wrap `run_coroutine_threadsafe` in a helper that attaches `add_done_callback` to log once and swallow `ConnectionClosedError` after disconnect.
- **Send gate** — Set a `_ws_closing` flag when keepalive fails; make `_send_async` / `_on_voice_level` no-op immediately; cancel pending send tasks on disconnect.
- **Soften keepalive** — Increase `ping_interval` / `ping_timeout` (e.g. 30/60) or expose settings for WAN/Tailscale links.
- **Throttle client `VOICE_LEVEL` WS sends** — Move level metering to UI refresh rate (e.g. 10 Hz max) instead of scheduling one coroutine per audio frame evaluation.
- **Auto-reconnect** — Exponential backoff reconnect with user notification; clear stale `_send` queue on drop.
- **Bridge** — Single shared mic level broadcast task rather than N × `send_voice_level` per frame per link.
- **Server** — Ensure `_handle_message` never blocks the event loop; consider debouncing presence broadcasts further under load.

### Related code

- `babblecast/client/session.py` — `_run_ws`, `_send`, `_send_async`, `_on_voice_level`, `_thread_main`, `_shutdown_transport`
- `babblecast/client/bridge.py` — `_on_mic_level` fan-out
- `babblecast/server/hub.py` — `VOICE_LEVEL` → `_send_presence`, `websockets.serve` keepalive settings
- `babblecast/audio/engine.py` — `MicCapture._callback` (~50 Hz `on_level`)

