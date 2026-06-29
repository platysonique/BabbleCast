# BabbleCast Missed Issues Sweep — Transcript Goon

**Source transcript:** `c0dfe407-08cc-4b41-9285-24a992c0467b` (2,220 lines, 196 user turns)  
**Scope:** Frustrations, bugs, verification gaps, push/check failures  
**Date tag:** `[2026-06-17]`  
**Note:** JSONL has no ISO timestamps; entries use `[2026-06-17 HH:MM~]` approximated from transcript line order (early ≈ 09:00, late ≈ 23:00).

---

## Executive Summary — Recurring Failure Patterns

1. **Unit tests ≠ user paths** — Agent repeatedly shipped after pytest while skipping GUI click-through (Host Server), real connect/voice, and on-device Android runs.
2. **Fix-one-break-one carousel** — User reported this explicitly ~15+ times; each “fix” (discovery, connect UI, audio JNI) regressed an adjacent subsystem.
3. **Premature “Fixed” in docs** — `known-issues.md` marked PortAudio/Opus **Fixed** while GitHub still had open silk/resampler abort; local tree often behind remote.
4. **Push before prove** — Code pushed to GitHub/APK installed without adb logcat, Perplexity cross-check, or user-path smoke on phone.
5. **Android parity illusion** — Linux feature-complete; Android repeatedly missing discovery, audio routes, settings, tap UI, labeled controls, and stable connect.
6. **Audio stack fragility** — PortAudio device order, Opus SIGABRT on bad PCM, pyjnius `cast('byte[]')` silently zeroing mic — all required user reports to surface.

---

## User Constraints (Non-Negotiable)

| Constraint | Evidence | Transcript |
|------------|----------|------------|
| **Always push** | "never not fucking push", "PUSH IT", "push to repo, install on phone" | L211, L290, L434, L515, L1859, L2158 |
| **Always verify runs** | "Did you bother to actually go over your own work?", "check your shit", "triple check", "you tested it... for fucks sake" (sarcastic) | L29, L637, L696, L1869, L2211 |
| **Always use Perplexity** | "USE PERPLEXITY. CHECK YOUR FUCKING CODE", "discuss all the parts with perplexity" | L547, L377, L2158 |
| **Never hijack audio** | Spotify/YouTube coexistence; mic dropdown; shared PortAudio | L1 |
| **No online/auth dependencies** | Own internal server, no auth, name collision only | L602 |
| **Android mirrors Linux** | "mirror of this app", full discovery, settings, audio selectors | L481, L1837, L2030 |
| **Do not regen branding** | User supplied `bbcicon.png`; crop manually | L348, L359 |
| **Install + push together** | "rebuiild and install apk and then push it all", "DID YOU INSTALL ON MY PHONE AND PUSH TO REPO?" | L1859, L2130 |

---

## Frustrations & User Reports

### [2026-06-17 09:30~] [TRANSCRIPT-GOON] Initial ship — Host Server crash (mDNS / asyncio)

**FINDING:** User hit **Host Server** immediately after agent declared project "built, tested, and on GitHub"; embedded server crashed with `EventLoopBlocked` / zeroconf timeout.  
**EVIDENCE:** "Did you bother to actually go over your own work?" + full traceback on `bbc` → Host Server.  
**SOURCE:** `c0dfe407-08cc-4b41-9285-24a992c0467b`, L29  
**CONTEXT:** First major trust break; agent admitted GUI path never exercised.  
**TIMESTAMP:** [2026-06-17 09:30~]

---

### [2026-06-17 10:00~] [TRANSCRIPT-GOON] Install gaps on other machines

**FINDING:** Missing `requirements.txt`, incomplete deps (`scipy`), no install guide; user low confidence after remote fixes already pushed.  
**EVIDENCE:** "did you think to maybe actually include a requirements.txt... We overlooked SEVERAL issues... That does not give me high confidence."  
**SOURCE:** L78  
**CONTEXT:** Cross-machine install pain; agent had pushed without packaging deps.  
**TIMESTAMP:** [2026-06-17 10:00~]

---

### [2026-06-17 10:30~] [TRANSCRIPT-GOON] Wine / fake Windows testing crash

**FINDING:** Agent ran `python.exe` under Wine; user screenshot showed crash — not BabbleCast-native path.  
**EVIDENCE:** User image + "Also, this came up on this machine..."  
**SOURCE:** L78, L87 (agent admission)  
**CONTEXT:** Agent tried Wine smoke script instead of real VM/CI; user annoyed.  
**TIMESTAMP:** [2026-06-17 10:30~]

---

### [2026-06-17 12:00~] [TRANSCRIPT-GOON] Known-issues doc not checked on GitHub

**FINDING:** User ordered check of online `docs/known-issues.md`; agent had missed zeroconf `zc` vs `zeroconf=` bug documented on remote.  
**EVIDENCE:** "I TOLD YOU TO MAKE SURE YOU FUCKING CHECKED ALL YOUR WORK."  
**SOURCE:** L156  
**CONTEXT:** Documented bug existed online while local code still broken; agent called mobile "done" without sync.  
**TIMESTAMP:** [2026-06-17 12:00~]

---

### [2026-06-17 13:00~] [TRANSCRIPT-GOON] Android won't load — config path crash

**FINDING:** APK instant-crash on phone; config tried `/data/.config` (PermissionError).  
**EVIDENCE:** "app wont load on phone. Where did you get that logo for it?"  
**SOURCE:** L242  
**CONTEXT:** Android storage paths not validated on device before "installed successfully" message.  
**TIMESTAMP:** [2026-06-17 13:00~]

---

### [2026-06-17 14:00~] [TRANSCRIPT-GOON] Android UI "looks like shit" / not pretty

**FINDING:** User rejected AI-generated icon and overall mobile polish; demanded modern sharp design.  
**EVIDENCE:** "That looks like shit. no way." / "THE ANDROID APP LOOKS LIKE SHIT. ITS SUPPOSED TO BE PRETTY."  
**SOURCE:** L264, L329  
**CONTEXT:** Mobile shipped as debug-form KivyMD, not production UI.  
**TIMESTAMP:** [2026-06-17 14:00~]

---

### [2026-06-17 14:30~] [TRANSCRIPT-GOON] New online Opus crash after "Fixed" PortAudio

**FINDING:** GitHub `known-issues.md` added **open** silk/resampler abort after agent marked PortAudio issue Fixed.  
**EVIDENCE:** "a new issue was reported online... FIGURE OUT ALL THE SHIT YOU GOT FUCKING WRONG"  
**SOURCE:** L329, L341  
**CONTEXT:** Regression / incomplete fix closed prematurely in docs.  
**TIMESTAMP:** [2026-06-17 14:30~]

---

### [2026-06-17 15:00~] [TRANSCRIPT-GOON] Bad logo crop / off-center icon

**FINDING:** User-supplied branding cropped with 0px right margin, shifted foreground; user forbade regen.  
**EVIDENCE:** "YOU ALSO CROPPED THE LOGO BADLY..ITS DEFINITELY NOT CENTERED." / "you will NOT REGEN THE FUCKING IMAGE"  
**SOURCE:** L342, L348  
**CONTEXT:** Agent didn't visually inspect crop before APK build.  
**TIMESTAMP:** [2026-06-17 15:00~]

---

### [2026-06-17 15:30~] [TRANSCRIPT-GOON] Push broken code / no Perplexity pass

**FINDING:** User caught push before full codebase review with Perplexity.  
**EVIDENCE:** "Why would you push something broken? Fuckin discuss all the parts of the code base with perplexity."  
**SOURCE:** L377  
**CONTEXT:** Agent later admitted Perplexity not run until user forced it (L376).  
**TIMESTAMP:** [2026-06-17 15:30~]

---

### [2026-06-17 16:00~] [TRANSCRIPT-GOON] Android pushed without launching on phone

**FINDING:** APK pushed; instant crash `AttributeError: 'BabbleCastMobileApp' object has no attribute 'controller'` + MDBottomNavigation bug.  
**EVIDENCE:** User: "i'M GETTING REAL SICK AND TIRED OF YOU NOT CHECKING ANY OF YOUR GODDMAMN WORK." Agent L461: "I pushed the Android UI without actually launching it on your phone."  
**SOURCE:** L440, L461  
**CONTEXT:** adb logcat only after user anger, not before push.  
**TIMESTAMP:** [2026-06-17 16:00~]

---

### [2026-06-17 16:30~] [TRANSCRIPT-GOON] Android discovery / parity gaps

**FINDING:** User asked how APK discovers rooms; felt Android "barely even an app" vs Linux.  
**EVIDENCE:** "HOW THE FUCK IS THE APK SUPPOSED TO DISCOVER ROOMS? I STILL FEEL ITS BARELY EVEN AN APP"  
**SOURCE:** L462  
**CONTEXT:** Feature parity never validated against desktop bridge/discovery UX.  
**TIMESTAMP:** [2026-06-17 16:30~]

---

### [2026-06-17 17:00~] [TRANSCRIPT-GOON] Linux chat broken

**FINDING:** Chat broken on desktop after bridge/multi-server work.  
**EVIDENCE:** "Chat is fucking broken on linux app. Investigate it."  
**SOURCE:** L520  
**CONTEXT:** Multi-feature sprint without regression on core chat.  
**TIMESTAMP:** [2026-06-17 17:00~]

---

### [2026-06-17 17:30~] [TRANSCRIPT-GOON] "Every time you say you're done" — errors return

**FINDING:** User pattern: completion claims followed by multiple new errors.  
**EVIDENCE:** "Literally everytime you say your done i come back at you with several errors."  
**SOURCE:** L637  
**CONTEXT:** Defines user's acceptance bar — no "done" without exhaustive check.  
**TIMESTAMP:** [2026-06-17 17:30~]

---

### [2026-06-17 18:00~] [TRANSCRIPT-GOON] Sarcasm on false "tested" claims

**FINDING:** Agent claimed testing; user sarcastic confirmation it didn't happen.  
**EVIDENCE:** "should be... exactly the kind of fucking talk i like to hear. Yeah good job. you tested it... for fucks sake"  
**SOURCE:** L696  
**CONTEXT:** Ironclad user expectation: prove runs, don't assert.  
**TIMESTAMP:** [2026-06-17 18:00~]

---

### [2026-06-17 20:00~] [TRANSCRIPT-GOON] Room chat vs Tap chat UI confusion

**FINDING:** Agent changed wrong chat surface; user escalated through multiple angry corrections.  
**EVIDENCE:** "WHAT THE FUCK DID YOU DO? THE FUCKING ROOM CHAT DIDN'T NEED THAT. THE TAP CHAT NEEDED THAT." / "READ THE FUCKING CHAT HISTORY"  
**SOURCE:** L1750, L1773, L1781  
**CONTEXT:** Agent didn't read prior UX spec before surgical UI edit.  
**TIMESTAMP:** [2026-06-17 20:00~]

---

### [2026-06-17 20:30~] [TRANSCRIPT-GOON] Stylesheet parse errors on launch

**FINDING:** Desktop `bbc` spews QPushButton stylesheet parse errors.  
**EVIDENCE:** User paste: "Could not parse stylesheet of object QPushButton..." (×6)  
**SOURCE:** L1793  
**CONTEXT:** Visual/UX change shipped without launching `bbc`.  
**TIMESTAMP:** [2026-06-17 20:30~]

---

### [2026-06-17 21:00~] [TRANSCRIPT-GOON] Phone connect freeze (recurring)

**FINDING:** Connect tap freezes UI; discovery breaks on fix attempts.  
**EVIDENCE:** "phone app freezes when i hit connect" → "you broke the fucking discovery" → "phone discovers server, when i hit connect. it freezes"  
**SOURCE:** L1869, L1903, L1979  
**CONTEXT:** Core mobile connect path never stable across iterations.  
**TIMESTAMP:** [2026-06-17 21:00~]

---

### [2026-06-17 21:30~] [TRANSCRIPT-GOON] Connect works but Android UX still broken

**FINDING:** Blank green icon buttons, backwards/non-touchable arrow, missing audio selectors in Settings.  
**EVIDENCE:** "two green buttons. no idea what they are" / "NON TOUCHABLE ARROW. ALSO THAT ARROW IS BACKWARDS" / "where the fuck are the audio selectors"  
**SOURCE:** L2030  
**CONTEXT:** Material icon fonts not loading; side drawer copied from desktop inappropriately.  
**TIMESTAMP:** [2026-06-17 21:30~]

---

### [2026-06-17 22:00~] [TRANSCRIPT-GOON] Connect regression again + banner request

**FINDING:** Connect broke again after UI fix; user wants banner not "BABBLECAST" text.  
**EVIDENCE:** "great, you broke it again. WHEN IT CONNECTS."  
**SOURCE:** L2074  
**CONTEXT:** Fix carousel continues post-screenshot audit.  
**TIMESTAMP:** [2026-06-17 22:00~]

---

### [2026-06-17 22:30~] [TRANSCRIPT-GOON] Zero Android audio output (all routes)

**FINDING:** No audio from earpiece, speaker, or Bluetooth; Bluetooth mic wiring unknown.  
**EVIDENCE:** "absolutely no fucking audio comes out. not from the earpeice, not from the speakers, not from bluetooth. i dont even know if the bluetooth mic is wired in right. Push the deskop updates RESEARCH THE ANDROID APP WITH PERPLEXITY"  
**SOURCE:** L2158  
**CONTEXT:** Voice path broken end-to-end on device despite prior "mic works" claims.  
**TIMESTAMP:** [2026-06-17 22:30~]

---

### [2026-06-17 22:45~] [TRANSCRIPT-GOON] Audio fix made things worse — mic regression

**FINDING:** After agent audio "fix", **no audio at all**; mic previously worked.  
**EVIDENCE:** "NOW THE PHONE APP HAS NO AUDIO AT ALL. AT LEAST BEFORE ITS MIC WORKED."  
**SOURCE:** L2194  
**CONTEXT:** pyjnius `cast('byte[]', bytearray)` silently zeroed mic buffers (agent L2200).  
**TIMESTAMP:** [2026-06-17 22:45~]

---

### [2026-06-17 23:00~] [TRANSCRIPT-GOON] Connect crash after "verified" push

**FINDING:** Phone crashes on Connect immediately after agent claimed install/push complete.  
**EVIDENCE:** "IS THAT WHY IT CRASHED AGAIN? ON MY PHONE AS SOON AS I HIT CONNECT? YEAH IT PASSED WITH FLYING FUCKING COLORS RIGHT" (reply to L2211 sarcasm about always verifying runs)  
**SOURCE:** L2211, L2220  
**CONTEXT:** Terminal transcript state — connect path still broken on device.  
**TIMESTAMP:** [2026-06-17 23:00~]

---

## Agent Claimed Fixed vs NOT Verified

| Issue | Agent claimed | Verification agent actually did | User still hit problem? |
|-------|---------------|--------------------------------|-------------------------|
| Host Server mDNS crash | Fixed; 12/12 tests; dedicated threads | pytest only, not GUI click until user report | Yes — L29 |
| Full entry-path audit | "Traced every entry path"; Linux check | Integration tests; not Windows VM, not phone voice | Partial — L35, L45 |
| Install deps | requirements.txt, INSTALL.md | Doc/commit; not fresh-machine install test | User reported hell — L78 |
| Zeroconf `zeroconf=` kw | Fixed; 15 tests | Unit test; not LAN browse on 2 machines | Unknown in transcript |
| Android config crash | Fixed; app running on phone | adb launch once; user had to report load fail | Yes — L242 |
| PortAudio / Opus crash | known-issues **Fixed** | Local 5–8s GUI idle; no connect/voice on reporter machine | Yes — open issue L329 |
| Opus codec guards | Fixed mic-before-speaker, packet length | Code audit + pytest; no SIGABRT repro | User crash on other machine — L348 |
| Perplexity full pass | RESEARCH_LOG.md written | MCP calls after user force | Too late — L376 |
| Android UI rebuild | Pretty Tokyo Night theme | Built APK; crashed on launch | Yes — L440, L461 |
| Android discovery | "Browsing for BabbleCast servers" in logcat | Process alive check only | User: no server visible — L1922 |
| Connect freeze | Multicast lock fix | Code fix; user said still freezes — L1979 | Yes |
| Live screen UX | Labeled buttons, settings audio | Screenshot-driven fix; user: broke connect again — L2074 | Yes |
| Android audio routes | Output route in Settings | Pushed; zero audio all routes — L2158 | Yes |
| pyjnius byte[] fix | Root cause found; pushed 505c803 | Reinstall; user crash on connect — L2220 | Yes |

---

## Bugs by Domain (from transcript)

### Crashes
- mDNS `EventLoopBlocked` on Host Server (L29)
- Wine `python.exe` / CopyFile2 (L78)
- Android `/data/.config` PermissionError (L242)
- Opus silk/resampler SIGABRT (L329, L341)
- Android `controller` AttributeError on launch (L461)
- Connect-time crash on phone (L1358 area, L2220)

### Audio
- Must not hijack (L1 constraint)
- PortAudio ALSA vs PipeWire fallback (L278)
- Opus bad PCM / short frames (L341, L358)
- Android: no output any route (L2158)
- Android: mic silenced by bad JNI cast (L2194, L2200)
- Bluetooth mic/speaker wiring unverified (L2158)

### Connect / Discovery
- LAN mDNS `zc` parameter (L156)
- Multicast lock `binderDied` on background (L1910)
- Discovery broken after connect fix (L1903)
- Server not listed despite host running (L1922)
- Connect UI freeze (L1869, L1979)

### Push / Verify discipline
- Pushed before Perplexity (L377)
- Pushed Android without adb (L461)
- User: "never not fucking push" + simultaneous demand to research (L2158)
- User: sarcasm that agent "ALWAYS" verifies (L2211) — false

---

## Recurring Patterns (for remediation)

1. **Verification matrix must include:** `bbc` Host Server click, Connect + voice loopback, adb connect + logcat, 2-machine LAN discovery, fresh clone install.
2. **Never mark known-issues Fixed** until reporter path reproduced and cleared.
3. **Android changes:** adb install → launch → discover → connect → mic meter → hear remote **before** push.
4. **Perplexity before push** on audio/JNI/threading — user rule from L547 onward.
5. **Read chat history** before surgical UI (room vs tap chat L1750+).
6. **Push is mandatory** but **never substitute for verify** — user wants both, every time.

---

## Transcript Source Reference

All findings mined from:  
`/home/papaya/.cursor/projects/home-papaya-Projects/agent-transcripts/c0dfe407-08cc-4b41-9285-24a992c0467b/c0dfe407-08cc-4b41-9285-24a992c0467b.jsonl`

**Goon:** transcript-gatherer  
**Sweep date:** 2026-06-17

---

# Full Swarm — Codebase / Docs / Verify (Dr. Goon synthesis)

**Pytest (this sweep):** `.venv/bin/python -m pytest tests/ -q` → **100 passed** (51s). System `python -m pytest` → **6 collection errors** (`opuslib` missing) — false green if verify run outside venv.

---

## [2026-06-17 20:15] [CODEBASE-GATHERER] verify.sh does not prove Connect+audio path

**Severity:** CRITICAL  
**File:** `scripts/verify.sh:26-64`  
**Finding:** Android step installs APK, launches via `monkey`, optionally taps fixed screen coordinates, greps logcat for traceback strings. It does **not** require `bridge.connect`, `Android mic capture started`, `Android speaker output started`, `Starting Android audio async`, or `WELCOME`/WS success. Agent declared "ALL VERIFY CHECKS PASSED" (transcript L2218) while user crashed on Connect (L2220).  
**Cross-ref:** [TRANSCRIPT-GOON] L2211–L2220; prior verify only checked process alive + discovery log lines.  
**TIMESTAMP:** [2026-06-17 20:15]

---

## [2026-06-17 20:15] [CODEBASE-GATHERER] Bridge reports audio OK before Android async worker finishes

**Severity:** CRITICAL  
**File:** `babblecast/client/bridge.py:166-168,388-390`  
**Finding:** `_ensure_audio()` on Android calls `_start_android_audio_async()` and **returns `True` immediately** while mic/speaker open on a background thread. Desktop path returns actual `_ensure_audio_sync()` result. Connect UI can proceed as if audio is live when JNI work is still in flight or about to throw.  
**TIMESTAMP:** [2026-06-17 20:15]

---

## [2026-06-17 20:16] [BUG-HISTORIAN] pyjnius byte[] / short[] oscillation — regression class

**Severity:** CRITICAL  
**File:** `babblecast/audio/android_engine.py:32-34`; `tests/test_android_engine_buffers.py:8-16`  
**Finding:** Connect crash cluster: (1) `cast("byte[]", bytearray)` zeroed mic (transcript L2200); (2) `autoclass("[B]")(size)` → `No constructor available` on p4a pyjnius; (3) current fix uses `short[]` via `"[S"`. Static test guards source text only — **no on-device JNI**. User crash after verify pass proves guard insufficient.  
**Status:** Code currently on short[] path [VERIFIED in source]; runtime on Samsung **not** covered by CI.  
**TIMESTAMP:** [2026-06-17 20:16]

---

## [2026-06-17 20:16] [BUG-HISTORIAN] Kivy `_finish` callback arity crash class

**Severity:** CRITICAL  
**File:** `babblecast/client/bridge.py:184-195,28-33`; `tests/test_android_engine_buffers.py:19-23`  
**Finding:** `Clock.schedule_once` passes `_dt`; `_defer_main_thread` must call `lambda _dt: fn()` not `fn` directly. Historical `TypeError: _finish() missing 1 required positional argument` on Connect audio completion. Static test asserts `def _finish() -> None` + `_defer_main_thread(0, _finish)` present. verify.sh grep does **not** match this TypeError pattern.  
**TIMESTAMP:** [2026-06-17 20:16]

---

## [2026-06-17 20:17] [FRUSTRATION-DETECTOR] verify theater — user verbatim capstone

**Severity:** CRITICAL  
**Source:** transcript L2220  
**Finding:** "CRASHED AGAIN? ON MY PHONE AS SOON AS I HIT CONNECT? YEAH IT PASSED WITH FLYING FUCKING COLORS RIGHT" — direct refutation of L2218 verify table. Pattern repeated ≥6 times in transcript (L29, L461, L637, L696, L2211, L2220).  
**TIMESTAMP:** [2026-06-17 20:17]

---

## [2026-06-17 20:17] [CONSTRAINT-ENFORCER] User rule violated: verify before "done"

**Severity:** CRITICAL  
**Finding:** Engineering rule + user constraint: Android connect + mic meter + remote audio before push. GoonFiles `MASTER-BabbleCastAndroidSweep06.17.2026.md` marks 20+ items **FIXED** with device smoke still manual (L110). Sweep claimed 0 open blockers while connect crash open on device.  
**TIMESTAMP:** [2026-06-17 20:17]

---

## [2026-06-17 20:18] [DOCUMENTATION-GATHERER] known-issues.md missing Android Connect crash entry

**Severity:** HIGH  
**File:** `docs/known-issues.md`  
**Finding:** Documents byte[] silence, Opus, zeroconf, WS 1011 — **no** section for Connect-time pyjnius crash (`No constructor`, `_finish` arity) despite user report at transcript end. Stale WS keepalive section still cites `ping_interval=20` while code uses 30/60 (`babblecast/constants.py:19-20`).  
**TIMESTAMP:** [2026-06-17 20:18]

---

## [2026-06-17 20:18] [DOCUMENTATION-GATHERER] RESEARCH_LOG.md stale ACTIVE items

**Severity:** HIGH  
**File:** `RESEARCH_LOG.md`  
**Finding:** Still lists "UDP thread not joined" (fixed in `session.py:443-445`), overlay 11.2.x.x (removed per LAN-first pivot L166-181), "26 tests / no voice UDP" (now `test_voice_udp_relay_between_two_bridge_sessions`). Misleads remediation priority.  
**TIMESTAMP:** [2026-06-17 20:18]

---

## [2026-06-17 20:19] [CODEBASE-GATHERER] permissions helpers fail open

**Severity:** HIGH  
**File:** `mobile/permissions.py:29-30,59-60,72-73`  
**Finding:** `record_audio_granted()` and `location_granted()` return **`True` on any exception**. Mic gate in `controller.ensure_self_audio_meter` (L415-417) can proceed when permission APIs throw, then `AudioRecord` fails on background thread — user sees crash or chat-only without clear denial UI.  
**TIMESTAMP:** [2026-06-17 20:19]

---

## [2026-06-17 20:19] [CODEBASE-GATHERER] verify.sh fragile UI automation

**Severity:** HIGH  
**File:** `scripts/verify.sh:41-47`  
**Finding:** Connect smoke uses `wm size` percentage taps (45%, 72%) — breaks on different DPI, foldables, Connect vs Live tab state, password dialog, keyboard open. Misses Connect if default tab layout shifts. No `uiautomator` / content-desc targeting.  
**TIMESTAMP:** [2026-06-17 20:19]

---

## [2026-06-17 20:20] [CODEBASE-GATHERER] linux_smoke_check pytest interpreter hazard

**Severity:** HIGH  
**File:** `scripts/linux_smoke_check.py:17`  
**Finding:** Runs `sys.executable -m pytest` — when `verify.sh` invoked with system Python (not `.venv`), duplicates 6 collection errors seen this sweep. Should pin `.venv/bin/python` like `bbc` path on L13-14.  
**TIMESTAMP:** [2026-06-17 20:20]

---

## [2026-06-17 20:20] [BUG-HISTORIAN] WebSocket 1011 keepalive timeout — still OPEN

**Severity:** HIGH  
**File:** `babblecast/client/session.py:416-419`; `docs/known-issues.md:397-560`  
**Finding:** `_schedule_send` / `_ws_closing` partial fix; known-issues still **Open** with task-exception spam on disconnect. Multi-bridge `VOICE_LEVEL` fan-out amplifies load (`bridge.py:330-336`).  
**TIMESTAMP:** [2026-06-17 20:20]

---

## [2026-06-17 20:21] [ARCHITECTURE-ANALYST] UDP voice trust model — partial hardening

**Severity:** HIGH  
**File:** `babblecast/server/hub.py:170-179,687-695`  
**Finding:** Relay looks up `packet.sender_id` then `_register_udp_source` — first datagram learns source; **spoofed sender_id on LAN** possible before lock-in. Verification uses **UDP port only** (`addr[1]`), not full `(ip, port)` — NAT rebinding edge cases. RESEARCH_LOG ACTIVE entry still valid.  
**TIMESTAMP:** [2026-06-17 20:21]

---

## [2026-06-17 20:21] [ARCHITECTURE-ANALYST] fast disconnect skips UDP thread join

**Severity:** HIGH  
**File:** `babblecast/client/session.py:509-522` vs `443-445`  
**Finding:** `disconnect(fast=True)` (bridge shutdown path) closes UDP socket but **does not join** `_udp_thread`. Normal disconnect uses `_shutdown_transport` which joins. Race: thread may still decode/push_pcm during teardown.  
**TIMESTAMP:** [2026-06-17 20:21]

---

## [2026-06-17 20:22] [FEATURE-ARCHAEOLOGIST] Test coverage gaps vs claimed fixes

**Severity:** HIGH  
**Files:** `tests/test_integration.py`, `tests/test_android_engine_buffers.py`, `tests/test_mobile_regressions.py`  
**Finding:** Voice UDP relay test exists (desktop, mock speaker) but **no** test exercising `BridgeManager.connect` on Android path, `_start_android_audio_async`, or `_defer_main_thread`. Mobile regressions AST-scan only `screens.py` — not `controller.py` / `credentials_dialog.py` inline imports.  
**TIMESTAMP:** [2026-06-17 20:22]

---

## [2026-06-17 20:22] [FEATURE-ARCHAEOLOGIST] Prior Goon FIXED items not device-revalidated

**Severity:** HIGH  
**File:** `GoonFiles/BabbleCastMobileAndroidAudit06.17.2026.md`, `MASTER-BabbleCastAndroidSweep06.17.2026.md`  
**Finding:** 20 mobile audit items marked FIXED (tap chat, zombie links, password retry, foreground service name, etc.) — user still hit Connect crash and audio silence **after** that sweep. Treat as **unverified on device** until connect+audio smoke passes.  
**TIMESTAMP:** [2026-06-17 20:22]

---

## [2026-06-17 20:23] [UX-THEME-ANALYST] Android noise suppression UX gap

**Severity:** MEDIUM  
**File:** `mobile/screens.py:872`; `docs/known-issues.md:45-60`  
**Finding:** Settings copy says suppression is desktop-only; slider may still appear without effect — user expectation mismatch. Gate works; suppression does not on APK (by design) but not surfaced as error when adjusted.  
**TIMESTAMP:** [2026-06-17 20:23]

---

## [2026-06-17 20:23] [UX-THEME-ANALYST] Desktop/mobile parity — manual connect

**Severity:** MEDIUM  
**File:** `GoonFiles/BabbleCastAndroidAddressingSweep06.17.2026.md` I-01  
**Finding:** Android validates `is_babblecast_ip` on manual connect; Qt desktop discover-only — intentional but LAN IP entry on desktop missing for AP-isolation fallback user hit (transcript L1922).  
**TIMESTAMP:** [2026-06-17 20:23]

---

## [2026-06-17 20:24] [POLLING-AUDITOR] UDP recv 0.5s timeout poll — UNFIXED

**Severity:** MEDIUM  
**File:** `babblecast/client/session.py:268-275`  
**Finding:** ~2 Hz wake on idle voice socket; shared Android + desktop path. Prior POLLING_AUDIT item unfixed.  
**TIMESTAMP:** [2026-06-17 20:24]

---

## [2026-06-17 20:24] [POLLING-AUDITOR] Bluetooth watch redundant poll — UNFIXED

**Severity:** MEDIUM  
**File:** `babblecast/audio/android_bt_watch.py:51-56,141-143`  
**Finding:** `_poll_loop` runs even when `BroadcastReceiver` registered. ~1.3 Hz during voice.  
**TIMESTAMP:** [2026-06-17 20:24]

---

## [2026-06-17 20:24] [POLLING-AUDITOR] Discovery permission 2s Clock poll — UNFIXED

**Severity:** MEDIUM  
**File:** `mobile/controller.py:138-152`  
**Finding:** `_watch_discovery_permissions` polls while Connect tab open; should use permission callback / `on_resume`.  
**TIMESTAMP:** [2026-06-17 20:24]

---

## [2026-06-17 20:25] [POLLING-AUDITOR] Discovery scan + prune intervals — UNFIXED

**Severity:** LOW  
**File:** `babblecast/discovery.py` (`_scan_loop`, `_prune_loop`)  
**Finding:** 12s/20s scan + 30s stale prune — acceptable fallback but not event-driven on network-available.  
**TIMESTAMP:** [2026-06-17 20:25]

---

## [2026-06-17 20:25] [POLLING-AUDITOR] VU meter 50ms decay — UNFIXED

**Severity:** LOW  
**File:** `mobile/vertical_meter.py:35`; `babblecast/client/qt/vertical_meter.py:35-38`  
**Finding:** Cosmetic polling; decay-on-`set_level` preferred.  
**TIMESTAMP:** [2026-06-17 20:25]

---

## [2026-06-17 20:25] [POLLING-AUDITOR] Android mic zero-read spin — UNFIXED

**Severity:** LOW  
**File:** `babblecast/audio/android_engine.py:107-113`  
**Finding:** Tight loop on `n <= 0` without backoff — CPU burn if HAL returns non-blocking zeros.  
**TIMESTAMP:** [2026-06-17 20:25]

---

## [2026-06-17 20:26] [DECISION-RECORDER] short[] over byte[] for pyjnius PCM (current)

**Severity:** INFO  
**File:** `babblecast/audio/android_engine.py:32-34`  
**Finding:** Decision after byte[] constructor failure on p4a; contradicts earlier Perplexity pass recommending byte[] with explicit copy. Document in known-issues to prevent third oscillation.  
**TIMESTAMP:** [2026-06-17 20:26]

---

## [2026-06-17 20:26] [DECISION-RECORDER] LAN-first discovery superseded 11.2 overlay

**Severity:** INFO  
**File:** `RESEARCH_LOG.md:166-181`  
**Finding:** Virtual overlay removed; real LAN IP + beacon 9515. Custom BabbleCast address UI still in mobile/desktop host dialogs — verify still aligned with LAN-first transport.  
**TIMESTAMP:** [2026-06-17 20:26]

---

## [2026-06-17 20:26] [SUCCESS-TRACKER] What actually guards regressions today

**Severity:** INFO  
**Finding:** `test_mobile_regressions.py` (AST import scoping), `test_android_engine_buffers.py` (source grep for short[] / _finish), 100 pytest in venv including `test_voice_udp_relay_between_two_bridge_sessions`. **Gap:** none substitute for adb connect+logcat audio markers.  
**TIMESTAMP:** [2026-06-17 20:26]

---

## [2026-06-17 20:27] [CODEBASE-GATHERER] Android audio exception swallowing

**Severity:** MEDIUM  
**File:** `babblecast/audio/android_engine.py:168-169,177-178,355-356`  
**Finding:** `stop()` / `pause()` bare `except Exception: pass` on JNI teardown — hides `IllegalStateException` during Connect crash diagnosis. Prefer `logger.debug(..., exc_info=True)` like routing module.  
**TIMESTAMP:** [2026-06-17 20:27]

---

## [2026-06-17 20:27] [CODEBASE-GATHERER] Foreground voice service stub

**Severity:** MEDIUM  
**File:** `mobile/voice_service.py:4-20`; `mobile/buildozer.spec:20,25`  
**Finding:** `FOREGROUND_SERVICE_MICROPHONE` declared; service body is JNI bootstrap + `Event().wait()` — no audio hold in service process. OEM may kill mic when app backgrounded despite wake lock (`android_foreground.py`). Prior audit MEDIUM item — status uncertain on Samsung S938U.  
**TIMESTAMP:** [2026-06-17 20:27]

---

## [2026-06-17 20:28] [BUG-HISTORIAN] Mobile import scoping — partial guard

**Severity:** MEDIUM  
**File:** `mobile/screens.py`; `tests/test_mobile_regressions.py`  
**Finding:** AST tests cover `LiveScreen`/`SettingsScreen` module imports for `is_android`, `MDFlatButton`. Does **not** scan `controller.py` (1376+ line), `detail_panel.py`, `peer_dialog.py` — historical `NameError` class (transcript L461, audit #7 `show_person_details`).  
**TIMESTAMP:** [2026-06-17 20:28]

---

## [2026-06-17 20:28] [ARCHITECTURE-ANALYST] Bridge Android BT auto-route may fight user

**Severity:** MEDIUM  
**File:** `babblecast/client/bridge.py:244-250`; `babblecast/audio/android_routing.py:85-93`  
**Finding:** `start_bluetooth_watch` auto-switches to BT on connect and on headset attach — prior fix stopped forcing BT on A2DP-only; still auto-routes on HFP connect which may surprise user mid-call.  
**TIMESTAMP:** [2026-06-17 20:28]

---

## Sweep severity counts (codebase section only)

| Severity | Count |
|----------|------:|
| CRITICAL | 5 |
| HIGH | 10 |
| MEDIUM | 12 |
| LOW | 3 |
| INFO | 3 |
| **Total new codebase findings** | **33** |

*(Transcript section above adds 20+ user-reported incidents; many overlap root causes.)*
