# MASTER — BabbleCast Android Sweep — 06.17.2026

Goon Squad parallel audit of `mobile/` + Android audio paths. Fixes applied in commit following this report.

---

## Goon roster deployed

| Goon | Scope | Output |
|------|--------|--------|
| codebase-gatherer | Full mobile wiring audit | 20 findings |
| bug-historian | Shutdown / lifecycle vs desktop | 9 findings |
| polling-auditor | Timers / poll loops | `_tick_ui` + voice_service |
| ux-theme-analyst | Connect/host/disconnect UX wiring | 7 gaps |

---

## Critical — FIXED

| # | Issue | Fix |
|---|--------|-----|
| 1 | Tap chat never opened (`open_tap_for_peer` only called `bridge.open_tap`) | `_open_tap_dialog()` from detail panel |
| 2 | Zombie bridge links after remote disconnect | `_handle_disconnect` always pops session+link; `disconnect()` delegates cleanup |

## High — FIXED

| # | Issue | Fix |
|---|--------|-----|
| 3 | Status stuck “N servers connected” after disconnect | Count `l.connected`; offline when 0 |
| 4 | Manual IP connect skipped password field | `_password_required_for()` + discovery lookup |
| 5 | Wrong password — status only, no retry | Re-open `prompt_connect(password_required=True)` |
| 6 | Listen/mic icons stale after toggle | `refresh_link_row()` |
| 7 | No `_closing` guard on Clock callbacks | `_alive()` + `stop_all` sets `_closing` first |
| 8 | Stop hosting left client connected to own server | `disconnect(link)` before `embedded.stop()` |

## Medium — FIXED

| # | Issue | Fix |
|---|--------|-----|
| 9 | Active server not highlighted | `set_active_link()` tints card ACCENT |
| 10 | Peer drawer open after link disconnect | `close_peer()` in `_on_link_disconnected` |
| 11 | `on_tap_end` not wired | Bridge callback → dismiss tap dialog |
| 12 | 80ms `_tick_ui` poll for peer meter | Removed; update from `_on_presence` |
| 13 | `VerticalMeter` decay timer never stopped | `stop()` unschedules on app exit |
| 14 | Android mic `read()` blocks past stop | `stopRecording()` before thread join |
| 15 | Tap dialog not dismissed on `stop_all` | Dismiss + clear in `stop_all` |

## Remaining sweep items — FIXED

| # | Issue | Fix |
|---|--------|-----|
| 16 | `show_person_details` dead code with missing imports | Removed; detail panel is the sole path |
| 17 | `voice_service.py` hourly sleep loop | `threading.Event().wait()` — blocks until service stop |
| 18 | Foreground service name vs buildozer `Voice` | Start/stop via `ServiceVoice` Java class + correct intent |
| 19 | `BLUETOOTH_CONNECT` manifest gap | Already in `buildozer.spec`; runtime request gated to API 31+ |
| 20 | Credential dialog silent validation failures | Inline error labels on connect/host dialogs |
| 21 | Force-stop / swipe-away skips cleanup | `on_pause` + `isFinishing()` → `stop_all`; service is non-sticky (`onTaskRemoved` stops self) |

## Codebase gatherer extras — FIXED

| # | Issue | Fix |
|---|--------|-----|
| 8 | Name-taken error dead focus target | Re-opens `prompt_connect` with name field |
| 9 | Tap dialog fragile layout | `MDBoxLayout` content with log + input |
| 14 | Mic permission before self-audio panel | `record_audio_granted()` gate + permission request |
| 16 | PTT icon stale | `ptt_active` binding + icon sync |
| 18 | Detail panel reaches into `_bridge` | Controller wrappers `set_peer_*`, `send_peer_tap` |
| 19 | Duplicate connected-link rows | Guard in `add_connected_link` |
| 20 | Optional password on manual connect | Password field always shown; required only when `auth=1` |

## User-requested parity (not just goon rows) — FIXED

| Request | Fix |
|---------|-----|
| Android gate + suppression sliders (line 820) | Settings tab + detail panel both wire to `BridgeManager` |
| LAN discovery wired PC ↔ Wi‑Fi phone (line 854) | `InterfaceChoice.All`, multi-IP resolve, `connect_host` hostname, `NEARBY_WIFI_DEVICES`, permission watch + multicast lock refresh |
| Shutdown parity desktop → Android (line 905) | `bridge.shutdown()`, mic callback clear, activity finish teardown |

---

## Verification checklist (Android)

- [x] Host → auto-connect, no second name dialog
- [x] Discover tap → password prompt when `auth=1`
- [x] Manual IP to password server → password field shown
- [x] Red ✕ disconnect → confirm + don’t ask again
- [x] Listen/mic icons flip after tap
- [x] Active server card highlighted
- [x] Tap chat opens dialog from peer drawer
- [x] Back out of app — no crash in logcat
- [x] Gate + suppression sliders affect live mic path
- [ ] PC on LAN appears in Discover — requires phone Location + same subnet (code path verified; router AP isolation can still block)
