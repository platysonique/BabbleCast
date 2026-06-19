# BabbleCast Research Log

Structured findings from Perplexity + codebase cross-audit (2026-06-17).

---

### Opus silk/resampler abort on voice path
**Date**: 2026-06-17
**Trigger**: Online report on other machine; user demand for full Perplexity audit before push
**Source**: perplexity_ask + perplexity_reason (Opus + bridge architecture)
**Findings**:
- SIGABRT from libopus `silk/resampler.c` is **not catchable in Python** — must never pass invalid PCM/packets to native codec
- Valid encode at 48 kHz mono = exactly **960 samples / 1920 bytes** per 20 ms frame
- Bare `bbc` GUI launch does **not** call Opus; crash is on connect/host/voice path
- Padding short PCM to silence then encoding can still produce tiny packets; decode of sub-4-byte packets is risky
- Perplexity Severity-1 gaps still open: UDP thread not joined on disconnect; no proper PLC (null decode); mic buffer not copied when fanning to N sessions
**Codebase Findings** (2026-06-17):
- `ClientSession.__init__` creates `OpusCodec()` immediately (harmless until encode/decode)
- `connect()` starts UDP thread before WELCOME; encode gated by `_room_id` in bridge path only
- `disconnect()` joins WS thread but **never joins `_udp_thread`** — race with codec during teardown
- Partial fixes in working tree: codec guards, speaker-before-mic, frame size checks in push_pcm
- **No jitter buffer**; sequence number sent but **never checked on receive**
- Tests: unit codec tests only; integration test connects chat but **never sends/receives voice UDP**
**Relevance**: Root cause of other-machine crash; do not mark Fixed until voice UDP integration test passes
**Status**: ACTIVE

---

### Android audio system — comprehensive architecture & routing research
**Date**: 2026-06-19
**Trigger**: Hear works (locked); app freezes on earpiece↔speaker route toggle; user demanded full Perplexity/arXiv research before any further code edits
**Source**: WebSearch + Android official docs (developer.android.com VoIP routing, BLE audio manager guide, ANR docs) + Google Oboe Bluetooth wiki + LiveKit/react-native-webrtc production issues + Fora Soft 2026 Kotlin playbook + codebase read (`bridge.py`, `android_engine.py`, `android_routing.py`, `session.py`, `hub.py`, `docs/android-voip-audio.md`) + conversation transcript. Perplexity MCP unavailable this session; arXiv API timed out — academic papers on Android `setCommunicationDevice` are sparse; platform docs + production VoIP issues are authoritative.

**End game (product)**:
- Team live comm hub: WS control + Opus voice, multi-server bridge with ONE shared mic + ONE shared speaker
- Non-hijacking audio: shared PortAudio on desktop; AudioRecord/AudioTrack on Android — coexist with Spotify/YouTube
- Talk + hear both working on phone after WS voice downlink fallback for cross-subnet UDP; **mic/talk + speaker delivery paths are DO NOT TOUCH**

**As-built threading (Android)** — updated 2026-06-19 after route hot-swap fix:
| Thread | Role |
|--------|------|
| Kivy main | UI only; `set_audio_route()` enqueues job + pending UI state |
| `bbc-android-audio` | Blocking open of AudioRecord/AudioTrack |
| `bbc-android-route` | Route JNI, write-gate coordination, deferred `save_settings` |
| `bbc-android-mic` | AudioRecord.read loop → gate/suppress → bridge fan-out |
| `bbc-android-spk` | Mix participant queues → AudioTrack.write loop (write-gated during route apply) |
| Per-session WS | Decode Opus → `_process_voice_datagram` → `push_pcm` |
| Per-session UDP | Same ingest path |
| Hub asyncio | UDP relay; WS binary fallback when `!_udp_reachable(peer)` |

**External findings — threading**:
- Android docs + ANR guide: **never block main thread** with audio policy JNI; input-dispatch ANRs = user-visible freeze
- Kivy/pyjnius community: AudioRecord/AudioTrack read/write loops must be on worker threads (we do this for capture/playback loops)
- **Gap**: route hot-swap (`AudioManager.setMode` + `setCommunicationDevice` + `setSpeakerphoneOn`) runs on UI thread inside `android_routing.apply()` while `bbc-android-spk` concurrently calls `AudioTrack.write` — known OEM deadlock/freeze pattern (Samsung S24/S25 class)

**External findings — routing (API 31+, user on API 35)**:
- Canonical 2024–2026 flow: `MODE_IN_COMMUNICATION` → register `AudioDeviceCallback` → `getAvailableCommunicationDevices()` → `setCommunicationDevice()` → **wait for callback** (up to 30s per Google) → `clearCommunicationDevice()` on teardown
- `setSpeakerphoneOn` / `startBluetoothSco` deprecated Android 14; BabbleCast still uses legacy fallback when `setCommunicationDevice` returns false
- Android 12+ auto-resets `MODE_IN_COMMUNICATION` after ~6s if misused — can fight manual routing
- HFP/SCO for two-way voice; A2DP playback-only — BabbleCast BT watch correctly gates on HFP
- Long-term Google recommendation: Telecom Jetpack library for VoIP apps (heavy migration)

**External findings — network/voice transport**:
- UDP uplink working + UDP downlink failing on different /24 is **classic asymmetric routing / NAT** — does NOT contradict WS "connected"
- Industry fix ladder: STUN → symmetric RTP/latching → TURN/SBC relay → **TCP/WebSocket media fallback**
- BabbleCast WS binary downlink is valid production pattern when UDP unreachable; trades latency/bandwidth for reachability on established socket

**Freeze root cause (high confidence)**:
- User tapped Earpiece then Speaker in Settings/detail panel → `_route_pressed` → `bridge.set_audio_route` → `speaker.set_route` → `AndroidAudioRouter.apply()` on **main thread** while active `AudioTrack.write` on `bbc-android-spk`
- Not a hear/delivery bug; not mic bug; **routing orchestration bug**

**Correct fix direction (when approved — routing layer only, NOT speaker delivery/mic)**:
1. Serialize route changes on dedicated audio worker (same worker that opened devices), never Kivy main thread
2. Register `AudioDeviceCallback`; update UI only after `communicationDevice` confirms (async)
3. Coordinate with playback thread: pause/drain or gate writes during route transition (option B from research ranking)
4. Do NOT recreate AudioTrack per toggle unless callback proves device stuck (last resort)
5. Debounce rapid earpiece↔speaker taps; move `save_settings` off UI critical path
6. Consider Telecom Jetpack only as long-term architectural upgrade

**Code vs docs mismatches**:
- `docs/android-voip-audio.md` says main thread = UI only — route change violates this
- `start()` forces `auto`→speaker playback but `set_route("auto")` later calls `clearCommunicationDevice` + earpiece — intentional inconsistency undermines hear fix when user selects Auto

**Implementation (2026-06-19)** — Phases 0–5 per `android_route_hot-swap` plan:
- `android_route_worker.py`: `bbc-android-route` thread; coalesce queue; BT/UI priority (500ms); `pause_speaker_writes`/`resume_speaker_writes` around `apply_resolved`
- `bridge.set_audio_route`: non-blocking enqueue; `save_settings` deferred to worker `on_complete` on main thread via Clock
- `android_routing.py`: `resolve_playback_route`, `session_begin`/`shutdown`, `AudioDeviceCallback`, 3s confirmation poll
- `android_engine.py`: write gate in `_loop` only; `set_route` label-only (no JNI)
- UI: pending “Switching…” state; 750ms route list cache on controller
- Tests: `test_android_route_worker.py`, `test_bridge_audio_route.py`, extended routing tests — 126 pytest pass
- APK built + installed on RFCY81V4G9Y (`babblecast-1.0.0-arm64-v8a-debug.apk`)

**Device proof**: Toggle Earpiece→Speaker→Auto during active voice on user server; logcat `adb -s RFCY81V4G9Y logcat -d -s python:I | grep -iE "route worker|audio route|communication device"` — expect `bbc-android-route` thread lines, no ANR/freeze.

**Status**: RESOLVED (implementation shipped) — user voice-session route toggle confirmation pending

---

### Server UDP voice relay trust model
**Date**: 2026-06-17
**Trigger**: Perplexity UDP security audit
**Source**: perplexity_ask (custom UDP Opus relay)
**Findings**:
- Relaying raw UDP without binding `(src_ip, src_port)` to authenticated session allows sender_id spoofing on LAN
- Minimum LAN hardening: server assigns sender_id; verify datagram source matches registered `udp_addr`
- No jitter buffer / PLC on client = glitches on Wi-Fi even if no crash
**Codebase Findings** (2026-06-17):
- `hub._VoiceProtocol.datagram_received` looks up client by **`packet.sender_id` from packet** — not by source address
- Client sets `udp_addr` via unauthenticated `udp_endpoint` WS message with self-reported host/port
- No rate limiting on UDP relay
**Relevance**: Security + reliability; LAN spoofing possible today
**Status**: ACTIVE

---


---

### BridgeManager multi-server shared audio
**Date**: 2026-06-17
**Trigger**: Perplexity architecture review
**Source**: perplexity_reason (multi-server bridge)
**Findings**:
- Single mic → N encoders is OK if each session has own OpusCodec (we do)
- Must not share encoder across threads; must copy PCM when fanning out
- Single speaker mixer thread/owner with per-session queues (we use queue per participant in SpeakerOutput)
- Multiple UDP recv threads (one per ClientSession) all call `push_pcm` on shared speaker — needs lock (engine has `_mix_lock` on mix only, push uses per-participant queues)
**Codebase Findings** (2026-06-17):
- `bridge._on_mic_frame` passes same `pcm` bytes object to all sessions without copy
- `SpeakerOutput.push_pcm` uses per-client queues; `_mix_frame` under `_mix_lock` — pattern is mostly correct
- `_ensure_audio` now speaker-before-mic (working tree)
**Relevance**: Multi-server bridge is core feature; races under load
**Status**: ACTIVE

---


---

### Android mobile client
**Date**: 2026-06-17
**Trigger**: User: app looks like shit; Perplexity mobile audit
**Source**: perplexity_ask (Android AudioRecord + KivyMD UI)
**Findings**:
- `STREAM_VOICE_CALL` + `VOICE_COMMUNICATION` can be OEM-fragile on Samsung; test routing early
- Android 14+ needs foreground service type `microphone` for sustained capture — **we do not have a foreground service**
- Permissions must be granted before audio start; order matters
- mDNS on Android is best-effort; need manual IP fallback (we have manual connect)
- UI: avoid single ScrollView debug form; use MDScreenManager, MDTopAppBar, bottom nav, cards, Tokyo Night palette
**Codebase Findings** (2026-06-17):
- `mobile/main.py`: one giant ScrollView, no theme, no MDScreenManager, no gate sliders (removed in bridge refactor)
- `permissions.py`: requests RECORD_AUDIO etc. but swallows all errors; no foreground service
- `android_engine.py`: 48 kHz 960-sample frames — correct size; no device-specific routing
- Icon: user hand-cropped `assets/bbcicon.png` → `icon.png` (working tree, not pushed)
**Relevance**: Android UX + reliability blockers
**Status**: ACTIVE

---


---

### PyQt6 desktop threading
**Date**: 2026-06-17
**Trigger**: Perplexity Qt threading audit
**Source**: perplexity_ask (PyQt6 background threads)
**Findings**:
- All GUI updates must go through queued signals — direct widget access from WS/UDP threads crashes
- closeEvent must stop workers, disconnect signals, join threads before destroy
**Codebase Findings** (2026-06-17):
- `_UiSignals` QObject bridge with pyqtSignal — **correct pattern**
- `closeEvent`: stops discovery, bridge.disconnect_all, embedded server — good
- Discovery/session callbacks use signals — good
- Remaining risk: long-lived daemon UDP threads per session on disconnect (see Opus entry)
**Relevance**: Desktop stability
**Status**: PARTIALLY RESOLVED

---

### mDNS discovery
**Date**: 2026-06-17
**Trigger**: Perplexity + known-issues history
**Source**: perplexity_ask (zeroconf Android) + codebase
**Findings**:
- mDNS blocked on many routers; Android especially flaky; manual IP required
- zeroconf must not run inside asyncio loop — dedicated threads required
**Codebase Findings** (2026-06-17):
- `discovery.py`: dedicated threads for advertise + browse — **fixed pattern**
- `_on_service` uses `zeroconf=` param — known issue marked Fixed
- Server list keyed by host IP — duplicate names on different ports can collide
**Relevance**: Discover UX; Android may show empty list often
**Status**: PARTIALLY RESOLVED

---

### LAN discovery: cross-subnet Wi‑Fi vs wired (phone still not finding server)
**Date**: 2026-06-17  (updated after blind-fix push `6360b0f`)
**Trigger**: User report — phone still not discovering hosted PC; demand for Perplexity research before more fixes
**Source**: `perplexity_research` (Android mDNS across routed /24 subnets, TCP scan fallback, LinkProperties routes, Tailscale advertise, MulticastLock; second pass on desktop-vs-phone overlay routing and VPN split-tunnel)
**Findings**:
- mDNS uses link-local multicast `224.0.0.251` — **not routed across /24 boundaries** even when ICMP/TCP unicast works
- **Desktop B on same LAN as host** discovers via mDNS (same broadcast domain) and/or scan once host binds `11.2.x.x`
- **Phone NordVPN** routes `11.2.9.1` via `tun0` (table 1050), stealing BabbleCast scan traffic off Wi‑Fi — Perplexity §3.1
- **Host must bind overlay** (`ip route local 11.2.0.0/16 dev lo` + `ip addr` on LAN iface) or `11.2.9.x:9513` never answers even though `0.0.0.0:9513` listens
- Phone CAN reach `192.168.1.141:9513` — proves mesh routes real LAN IP but not virtual `11.2.x` without overlay + route
**Codebase Findings** (2026-06-17):
- Runtime: host `babblecast_ip=11.2.9.1`, PC `192.168.1.141`, phone `192.168.86.72`
- `adb shell ip route get 11.2.9.1` → `dev tun0` (VPN), not wlan0
- No `overlay_net` existed — hosting did not configure OS for virtual IP
**Resolution** (2026-06-17):
- `babblecast/overlay_net.py` — bind `11.2.0.0/16` local + host IP on `lo` and primary LAN iface when hub advertises
- `mobile/android_connect.py` + `babblecast/transport_probe.py` — TCP scan uses Wi‑Fi `Network.bindSocket()` so VPN does not hijack `11.2.x` probes
- Still `11.2.x.x` scan + mDNS unchanged
- Mesh cross-subnet may need router static route `11.2.0.0/16 → host LAN IP` (Perplexity §2.2)
**Status**: RESOLVED (pending host restart + phone smoke test)

---

### Cross-subnet 11.2.x.x reachability (phone still not connecting) — Perplexity deep research
**Date**: 2026-06-17 (evening)
**Trigger**: User: improved lag but phone still not connecting; demand Perplexity with full code/goals context
**Source**: `perplexity_research` (high reasoning) — custom overlay 11.2.0.0/16 across Google Wifi mesh /24 subnets, Android bindSocket vs routing, Tailscale/ZeroTier patterns
**Findings**:
- Binding `11.2.9.1/32` on Linux host is **necessary but not sufficient** — only affects packets that **arrive at the PC**; intermediate routers must know where 11.2.x.x lives
- Phone `192.168.86.72` → `11.2.9.1`: kernel sends to Wi‑Fi gateway `192.168.86.1`; mesh has **no route** for 11.2.0.0/16 → packets never reach PC (verified: ping 11.2.9.1 100% loss, ping 192.168.1.141 OK, TCP 9513 to 192.168.1.141 OK from phone)
- `Network.bindSocket()` fixes VPN hijack but **cannot create routes** to unreachable prefixes
- Consumer Google/Nest Wifi **cannot add static routes** for 11.2.0.0/16 in normal UI
- Proxy ARP / host-only DNAT **do not work cross-subnet** (ARP does not cross routers)
- Correct pattern (Tailscale/ZeroTier/Hamachi): **endpoint-managed overlay** — capture 11.2.0.0/16 locally (Android `VpnService` long-term) and map to underlay LAN IP for transport
- Pragmatic near-term: **overlay→underlay mapping** at app layer + **UDP discovery beacon** (overlay IP in UI, dial `192.168.1.141` on wire); mDNS `lan` TXT property for same-subnet; optional router static route for power users
**Codebase Findings** (2026-06-17):
- Prior code probed/scanned `11.2.9.1–254` over physical network — **cannot work** cross-/24 without router routes
- Host overlay (`overlay_net.py`) correct for local accept once packets arrive
**Resolution** (2026-06-17):
- `babblecast/overlay_route.py` — map overlay↔underlay, `resolve_transport_host()`, persist `last_server_underlay`
- `babblecast/discovery_beacon.py` — UDP 9515 beacon; server **unicasts** reply to `BABBLE_DISCOVER` (cross-mesh)
- `transport_probe.py` / `session.connect` / `DiscoveredServer.connect_host` — dial underlay, keep 11.2.x.x identity
- `network_scan.bootstrap_overlay_from_underlay()` — beacon + known underlay probe before overlay sweep
- mDNS advertiser adds `lan` property; WELCOME includes `babblecast_ip`
- **Long-term**: Android `VpnService` split-tunnel for 11.2.0.0/16 (Perplexity §6–7)
**Status**: SUPERSEDED — see LAN-first pivot below

---

### LAN-first discovery pivot (drop 11.2.x.x overlay)
**Date**: 2026-06-17
**Trigger**: User approval after Perplexity research + live network proof
**Source**: Perplexity research, `adb shell ping`, TCP probe phone→PC
**Findings**:
- Phone → `192.168.1.141` ping/TCP 9513 **works** across mesh subnets
- Phone → `11.2.9.1` **100% packet loss** — mesh has no route for virtual overlay
- mDNS does not cross `/24` boundaries on Google Wifi (by design)
- Overlay actively **breaks** cross-subnet discovery; real LAN IPs are the correct transport
**Resolution**:
- Removed `overlay_net.py`, `overlay_route.py`
- mDNS + beacon advertise **real LAN IPs**; connect dials LAN IP directly
- `discover_lan_servers()` — UDP beacon (9515) + mesh-aware TCP probe, dedupe by IP
- Host dialog: name + password only (no custom BabbleCast address)
- Legacy `address.py` kept for migration tests only
**Status**: IMPLEMENTED — pending smoke test (restart `bbc` host, NordVPN off on phone)

---

### Room-level password protection
**Date**: 2026-06-17
**Trigger**: User request — per-room boss control without admin roles
**Resolution**:
- `CREATE_ROOM` accepts optional `password`; creator stored as `creator_id`
- `JOIN_ROOM` requires password when room is protected; wrong/missing password rejected
- `DELETE_ROOM` only allowed by room creator (General/system room unchanged)
- `RoomInfo` broadcasts `password_protected` + `creator_id`; UI shows 🔒 and prompts password only when needed
**Status**: IMPLEMENTED

---

### Test coverage gaps
**Date**: 2026-06-17
**Trigger**: Codebase audit
**Source**: direct investigation
**Findings**:
- 26 tests pass but voice UDP path largely untested end-to-end
- `test_bridge.py` only tests empty manager stubs
- `test_integration.py`: chat only, no Opus round-trip, no multi-server bridge
- No test for disconnect/teardown race
**Relevance**: Cannot claim crash fixed without voice integration test
**Status**: ACTIVE

---


**Date**: 2026-06-19
**Trigger**: Hear works (locked); app freezes on earpiece↔speaker route toggle; user demanded full Perplexity/arXiv research before any further code edits
**Source**: WebSearch + Android official docs (developer.android.com VoIP routing, BLE audio manager guide, ANR docs) + Google Oboe Bluetooth wiki + LiveKit/react-native-webrtc production issues + Fora Soft 2026 Kotlin playbook + codebase read (`bridge.py`, `android_engine.py`, `android_routing.py`, `session.py`, `hub.py`, `docs/android-voip-audio.md`) + conversation transcript. Perplexity MCP unavailable this session; arXiv API timed out — academic papers on Android `setCommunicationDevice` are sparse; platform docs + production VoIP issues are authoritative.

**End game (product)**:
- Team live comm hub: WS control + Opus voice, multi-server bridge with ONE shared mic + ONE shared speaker
- Non-hijacking audio: shared PortAudio on desktop; AudioRecord/AudioTrack on Android — coexist with Spotify/YouTube
- Talk + hear both working on phone after WS voice downlink fallback for cross-subnet UDP; **mic/talk + speaker delivery paths are DO NOT TOUCH**

**As-built threading (Android)** — updated 2026-06-19 after route hot-swap fix:
| Thread | Role |
|--------|------|
| Kivy main | UI only; `set_audio_route()` enqueues job + pending UI state |
| `bbc-android-audio` | Blocking open of AudioRecord/AudioTrack |
| `bbc-android-route` | Route JNI, write-gate coordination, deferred `save_settings` |
| `bbc-android-mic` | AudioRecord.read loop → gate/suppress → bridge fan-out |
| `bbc-android-spk` | Mix participant queues → AudioTrack.write loop (write-gated during route apply) |
| Per-session WS | Decode Opus → `_process_voice_datagram` → `push_pcm` |
| Per-session UDP | Same ingest path |
| Hub asyncio | UDP relay; WS binary fallback when `!_udp_reachable(peer)` |

**External findings — threading**:
- Android docs + ANR guide: **never block main thread** with audio policy JNI; input-dispatch ANRs = user-visible freeze
- Kivy/pyjnius community: AudioRecord/AudioTrack read/write loops must be on worker threads (we do this for capture/playback loops)
- **Gap**: route hot-swap (`AudioManager.setMode` + `setCommunicationDevice` + `setSpeakerphoneOn`) runs on UI thread inside `android_routing.apply()` while `bbc-android-spk` concurrently calls `AudioTrack.write` — known OEM deadlock/freeze pattern (Samsung S24/S25 class)

**External findings — routing (API 31+, user on API 35)**:
- Canonical 2024–2026 flow: `MODE_IN_COMMUNICATION` → register `AudioDeviceCallback` → `getAvailableCommunicationDevices()` → `setCommunicationDevice()` → **wait for callback** (up to 30s per Google) → `clearCommunicationDevice()` on teardown
- `setSpeakerphoneOn` / `startBluetoothSco` deprecated Android 14; BabbleCast still uses legacy fallback when `setCommunicationDevice` returns false
- Android 12+ auto-resets `MODE_IN_COMMUNICATION` after ~6s if misused — can fight manual routing
- HFP/SCO for two-way voice; A2DP playback-only — BabbleCast BT watch correctly gates on HFP
- Long-term Google recommendation: Telecom Jetpack library for VoIP apps (heavy migration)

**External findings — network/voice transport**:
- UDP uplink working + UDP downlink failing on different /24 is **classic asymmetric routing / NAT** — does NOT contradict WS "connected"
- Industry fix ladder: STUN → symmetric RTP/latching → TURN/SBC relay → **TCP/WebSocket media fallback**
- BabbleCast WS binary downlink is valid production pattern when UDP unreachable; trades latency/bandwidth for reachability on established socket

**Freeze root cause (high confidence)**:
- User tapped Earpiece then Speaker in Settings/detail panel → `_route_pressed` → `bridge.set_audio_route` → `speaker.set_route` → `AndroidAudioRouter.apply()` on **main thread** while active `AudioTrack.write` on `bbc-android-spk`
- Not a hear/delivery bug; not mic bug; **routing orchestration bug**

**Correct fix direction (when approved — routing layer only, NOT speaker delivery/mic)**:
1. Serialize route changes on dedicated audio worker (same worker that opened devices), never Kivy main thread
2. Register `AudioDeviceCallback`; update UI only after `communicationDevice` confirms (async)
3. Coordinate with playback thread: pause/drain or gate writes during route transition (option B from research ranking)
4. Do NOT recreate AudioTrack per toggle unless callback proves device stuck (last resort)
5. Debounce rapid earpiece↔speaker taps; move `save_settings` off UI critical path
6. Consider Telecom Jetpack only as long-term architectural upgrade

**Code vs docs mismatches**:
- `docs/android-voip-audio.md` says main thread = UI only — route change violates this
- `start()` forces `auto`→speaker playback but `set_route("auto")` later calls `clearCommunicationDevice` + earpiece — intentional inconsistency undermines hear fix when user selects Auto

**Implementation (2026-06-19)** — Phases 0–5 per `android_route_hot-swap` plan:
- `android_route_worker.py`: `bbc-android-route` thread; coalesce queue; BT/UI priority (500ms); `pause_speaker_writes`/`resume_speaker_writes` around `apply_resolved`
- `bridge.set_audio_route`: non-blocking enqueue; `save_settings` deferred to worker `on_complete` on main thread via Clock
- `android_routing.py`: `resolve_playback_route`, `session_begin`/`shutdown`, `AudioDeviceCallback`, 3s confirmation poll
- `android_engine.py`: write gate in `_loop` only; `set_route` label-only (no JNI)
- UI: pending “Switching…” state; 750ms route list cache on controller
- Tests: `test_android_route_worker.py`, `test_bridge_audio_route.py`, extended routing tests — 126 pytest pass
- APK built + installed on RFCY81V4G9Y (`babblecast-1.0.0-arm64-v8a-debug.apk`)

**Device proof**: Toggle Earpiece→Speaker→Auto during active voice on user server; logcat `adb -s RFCY81V4G9Y logcat -d -s python:I | grep -iE "route worker|audio route|communication device"` — expect `bbc-android-route` thread lines, no ANR/freeze.

**Status**: RESOLVED (implementation shipped) — user voice-session route toggle confirmation pending
