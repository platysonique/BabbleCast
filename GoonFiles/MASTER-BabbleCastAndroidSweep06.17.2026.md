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

## Open (lower priority — not fixed this pass)

| # | Issue | Severity |
|---|--------|----------|
| 16 | `show_person_details` missing imports (dead code) | Low |
| 17 | `voice_service.py` hourly sleep loop | Low |
| 18 | Foreground service name vs buildozer `Voice` | Medium — verify on device |
| 19 | `BLUETOOTH_CONNECT` manifest gap | Medium |
| 20 | Credential dialog silent validation failures | Low |
| 21 | Force-stop skips `on_stop` (platform) | Low — document only |

---

## Verification checklist (Android)

- [ ] Host → auto-connect, no second name dialog
- [ ] Discover tap → password prompt when `auth=1`
- [ ] Manual IP to password server → password field shown
- [ ] Red ✕ disconnect → confirm + don’t ask again
- [ ] Listen/mic icons flip after tap
- [ ] Active server card highlighted
- [ ] Tap chat opens dialog from peer drawer
- [ ] Back out of app — no crash in logcat
- [ ] PC on LAN appears in Discover (same Wi‑Fi, Location granted)
