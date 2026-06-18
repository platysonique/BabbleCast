# MASTER — BabbleCast Missed Issues Sweep — 06.17.2026

**Dr. Goon full swarm:** transcript-gatherer + codebase-gatherer + documentation-gatherer + bug-historian + frustration-detector + constraint-enforcer + feature-archaeologist + decision-recorder + architecture-analyst + ux-theme-analyst + success-tracker + polling-auditor

**Working file:** `GoonFiles/BabbleCastMissedIssuesSweep06.17.2026.md`  
**Pytest:** 100 passed (`.venv`); 6 collection errors (system Python, no `opuslib`)

---

## Executive verdict

`scripts/verify.sh` created a **false sense of safety**. It proved APK launch + absence of traceback strings in ~600 logcat lines — **not** Connect → WebSocket WELCOME → Android audio JNI → mic meter → speaker frame. User crash on Connect (transcript L2220) is the capstone of a repeated pattern: pytest green, verify green, device red.

Code fixes for `byte[]` / `_finish` may be in tree (`short[]`, zero-arg `_finish` + `_defer_main_thread`) but **guards are static source tests only**. Until verify exercises the real Connect path on device, regressions will recur.

---

## Severity totals (combined codebase swarm)

| Severity | Count | Notes |
|----------|------:|-------|
| **CRITICAL** | 5 | Verify gap, async audio lie, JNI/callback classes, user capstone |
| **HIGH** | 10 | Docs stale, permissions fail-open, WS 1011, UDP trust, test gaps |
| **MEDIUM** | 12 | Polling, parity, exception swallowing, FGS stub, import scan gap |
| **LOW** | 3 | Meter decay, prune/scan timers, mic spin |
| **INFO** | 3 | Decision log items |
| **Transcript incidents** | 20+ | See working file — frustrations not all unique root causes |

---

## P0 — Fix before next push (ordered)

### 1. Harden `scripts/verify.sh` Android Connect+audio gate
**Why:** Root of user fury — verify passed, Connect crashed.  
**Do:**
- After taps, **require** logcat markers: `connect_selected: bridge.connect` OR `Starting Android audio async`, and within 15s either `Android mic capture started` or explicit `Audio unavailable` (chat-only) — **fail** on any Python traceback including `TypeError`, `No constructor available`, `missing 1 required positional argument`.
- Add grep for `jnius` / `PythonActivity` exceptions.
- Pin `.venv/bin/python` for all pytest invocations (mirror `linux_smoke_check.py` fix).
- Optional: start headless `bbc server` on host so Connect has a real WS target during verify.

**Files:** `scripts/verify.sh`, `scripts/linux_smoke_check.py`

---

### 2. Stop lying about Android audio readiness
**Why:** `_ensure_audio()` returns `True` before async worker completes (`bridge.py:166-168`).  
**Do:**
- Return `False` until `_audio_started` is set in `_finish` callback, or expose `audio_pending` state to UI ("Starting audio…").
- On worker failure, ensure `_on_error` fires **and** UI does not show voice-ready.

**Files:** `babblecast/client/bridge.py:162-197,388-390`

---

### 3. Lock pyjnius PCM + Clock callback regressions (runtime, not grep-only)
**Why:** byte[] ↔ short[] ↔ cast oscillation; `_finish` arity crash class.  
**Do:**
- Extend `tests/test_android_engine_buffers.py` to import `_defer_main_thread` and assert scheduled callback accepts `_dt` (mock Clock).
- Add `tests/test_bridge_android_audio.py`: mock `platform_name=android`, patch `create_mic`/`create_speaker`, assert `_start_android_audio_async` calls `_finish` without TypeError.
- Document final decision in `docs/known-issues.md` — **short[]** path for p4a pyjnius.

**Files:** `tests/`, `docs/known-issues.md`

---

### 4. Fail-closed Android permissions
**Why:** `record_audio_granted()` returns `True` on exception (`permissions.py:29-30`).  
**Do:**
- Return `False` on exception; log once; block `ensure_self_audio_meter` with Settings deep-link.

**Files:** `mobile/permissions.py`, `mobile/controller.py:415-464`

---

### 5. Device smoke script (minimal) — mandatory before push
**Why:** Coordinate taps in verify are fragile; user device ≠ dev tap math.  
**Do:**
- Add `scripts/android_connect_smoke.sh`: adb logcat -c → launch → input text for known test server IP → Connect → wait for audio log lines → exit 1 on traceback.
- Wire as verify step 3b when `ANDROID_CONNECT_SMOKE=1` or always when device serial set.

**Files:** new script + `scripts/verify.sh`

---

### 6. Refresh `docs/known-issues.md` + `RESEARCH_LOG.md`
**Why:** Missing Android Connect crash; stale WS ping values (doc says 20s, code 30/60); RESEARCH_LOG still says UDP not joined.  
**Do:**
- Add **Android Connect: pyjnius JNI failures** section (byte[] constructor, _finish arity, short[] fix).
- Mark RESEARCH_LOG items resolved/superseded; point test coverage to `test_voice_udp_relay_*`.

**Files:** `docs/known-issues.md`, `RESEARCH_LOG.md`

---

### 7. WebSocket 1011 disconnect spam (HIGH → P0 if multi-server daily driver)
**Why:** Still **Open** in known-issues; floods terminal, drops links.  
**Do:**
- Ensure all `run_coroutine_threadsafe` paths use done-callback; cancel pending sends on `_ws_closing` (partially done — audit remaining).

**Files:** `babblecast/client/session.py`, `babblecast/client/bridge.py`

---

### 8. `disconnect(fast=True)` UDP thread join
**Why:** Shutdown race during Connect crash recovery / force-stop.  
**Do:** Join `_udp_thread` in fast path or set flag checked in recv loop.

**Files:** `babblecast/client/session.py:509-522`

---

### 9. Re-validate prior Goon "FIXED" mobile items on device
**Why:** MASTER Android sweep claimed 0 open; user still crashed.  
**Do:** Manual checklist: tap chat, password retry, zombie links, foreground service, listen/mic icons — **on phone after P0 verify passes**.

**Files:** `GoonFiles/MASTER-BabbleCastAndroidSweep06.17.2026.md` checklist

---

### 10. Expand mobile AST regression scope
**Why:** `test_mobile_regressions.py` only scans `screens.py`.  
**Do:** Add `controller.py`, `credentials_dialog.py` to module-import AST guard.

**Files:** `tests/test_mobile_regressions.py`

---

## P1 — Next sprint

| # | Item | Severity |
|---|------|----------|
| 11 | UDP recv selector/async reader (`session.py:268-275`) | MEDIUM |
| 12 | BT watch poll fallback-only (`android_bt_watch.py`) | MEDIUM |
| 13 | Discovery permission event-driven (`controller.py:138-152`) | MEDIUM |
| 14 | Hub UDP verify full `(ip,port)` not port-only | HIGH |
| 15 | Android noise suppression slider disable/hide on APK | MEDIUM |
| 16 | Qt desktop manual LAN IP connect (parity) | MEDIUM |
| 17 | JNI teardown logging in `android_engine.stop()` | MEDIUM |
| 18 | Foreground mic service policy validation on Samsung | MEDIUM |

---

## P2 — Polish / performance

- VU meter decay without 50ms timer (Qt + mobile)
- Discovery scan/prune event-driven refinement
- Android mic zero-read backoff

---

## Verification matrix (definition of done)

| Step | Command / action | Pass criteria |
|------|------------------|---------------|
| 1 | `.venv/bin/python -m pytest tests/ -q` | 100 passed |
| 2 | `bash scripts/verify.sh` | exit 0 |
| 3 | Phone: Discover → Connect → Live | No traceback; mic meter moves |
| 4 | Phone: hear desktop / desktop hears phone | Opus UDP round-trip |
| 5 | `adb logcat` | `Android mic capture started`, no `No constructor` |
| 6 | Only then | `git push` + APK install |

---

## Top 10 P0 items (quick reference)

1. **verify.sh** — require Connect + audio logcat markers, not launch-only  
2. **bridge.py** — don't return audio OK before async Android worker finishes  
3. **Runtime tests** — pyjnius short[] + `_defer_main_thread` callback arity  
4. **permissions.py** — fail-closed, not fail-open on exception  
5. **android_connect_smoke.sh** — dedicated device Connect script  
6. **known-issues.md** — document Android Connect JNI crash class  
7. **RESEARCH_LOG.md** — sync resolved items (UDP join, overlay removed)  
8. **session.py** — WS 1011 send-gate audit  
9. **session.py** — fast disconnect UDP thread join  
10. **Re-run** prior Android Goon FIXED checklist on device  

---

## Output paths

- **Working sweep:** `/home/papaya/Projects/BabbleCast/GoonFiles/BabbleCastMissedIssuesSweep06.17.2026.md`
- **This MASTER:** `/home/papaya/Projects/BabbleCast/GoonFiles/MASTER-BabbleCastMissedIssuesSweep06.17.2026.md`

**Goon Squad:** Dr. Goon — 2026-06-17
