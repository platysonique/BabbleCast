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
