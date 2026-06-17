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
