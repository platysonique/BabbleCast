# BabbleCast Mobile Android Audit — Codebase Gatherer

**Scope:** `/home/papaya/Projects/BabbleCast/mobile/` + `babblecast/client/bridge.py`, `babblecast/audio/android_engine.py`, `mobile/android_network.py`, `mobile/permissions.py`, `mobile/voice_service.py`, `mobile/android_foreground.py`  
**Mode:** Read-only wiring / crash / API audit  
**Date:** 2026-06-17

---

## Entry Points & Tech Stack

**FINDING:** App entry is `mobile/main.py` → `BabbleCastMobileApp().run()` in `mobile/app.py`.  
**EVIDENCE:** `mobile/main.py:5-6`, `mobile/app.py:18-56`  
**SOURCE:** `mobile/main.py`, `mobile/app.py`  
**CONTEXT:** Buildozer `package.main = main.py`; `build()` wires `BabbleController`, three screens, tab bar, deferred discovery start.  
**TIMESTAMP:** [2026-06-17 12:00]

**FINDING:** Android audio backend selected via `babblecast/audio/factory.py` when `kivy.utils.platform == "android"`.  
**EVIDENCE:** `create_mic` / `create_speaker` → `AndroidMicCapture` / `AndroidSpeakerOutput`  
**SOURCE:** `babblecast/audio/factory.py:28-41`  
**CONTEXT:** Shared `BridgeManager` uses factory; no separate mobile audio path.  
**TIMESTAMP:** [2026-06-17 12:00]

**FINDING:** Shutdown path: `MDApp.on_stop` → `controller.stop_all()` → discovery stop, multicast release, embedded stop, `bridge.shutdown()`, `stop_voice_foreground()`.  
**EVIDENCE:** `mobile/app.py:64-65`, `mobile/controller.py:117-127`  
**SOURCE:** `mobile/app.py`, `mobile/controller.py`  
**CONTEXT:** `on_pause` returns `True` (keeps process alive); no stop on pause.  
**TIMESTAMP:** [2026-06-17 12:00]

---

## Numbered Audit Findings (file:line, severity, fix)

### 1. `mobile/controller.py:319-322` — **CRITICAL**
**Issue:** `open_tap_for_peer` only calls `bridge.open_tap()`; never opens tap chat UI. Desktop `_open_tap_for_peer` creates `TapChatDialog` (`main_window.py:872-894`). Detail panel "Tap chat" button calls this broken path (`detail_panel.py:326-328`).  
**Fix:** Resolve `peer_name` from `_participant_by_composite` / presence, then call `_open_tap_dialog(link_id, tap_id, peer_id, peer_name)` (mirror desktop `TapChatDialog.__init__` which opens dialog then `open_tap`).

### 2. `babblecast/client/bridge.py:261-272` — **CRITICAL** (shared; hits mobile)
**Issue:** `_handle_disconnect` removes session/link only when `not was_connected`. After a **remote** drop while connected, zombie `ClientSession` + `ServerLinkState` remain in `_sessions` / `_links` (`connected=False`).  
**Fix:** Always `pop` session and link in `_handle_disconnect` (or pop when `was_connected` too). User-initiated `disconnect()` already pops link after callback; guard double-pop with `link_id not in self._sessions`.

### 3. `mobile/controller.py:448-458` — **HIGH**
**Issue:** `_on_link_disconnected` updates status only when `not self._bridge.links`. Zombie links (finding #2) keep `links` non-empty; status stays e.g. "2 server(s) connected" after all UI rows removed.  
**Fix:** Use `n = sum(1 for l in self._bridge.links if l.connected)`; set status to `f"{n} server(s) connected"` or `f"Offline — {reason}"` when `n == 0`. Depends on #2 fix for accurate counts.

### 4. `mobile/screens.py:105-112` + `mobile/controller.py:137-177` — **HIGH**
**Issue:** Manual Connect never passes `password_required`. Desktop `_connect` looks up discovered server and forces password UI (`main_window.py:369-371`). Password-protected server via typed IP connects with empty password.  
**Fix:** In `connect_to`, scan `self._discovery.servers` for matching `host`/`port`; set `password_required=True` when `DiscoveredServer.password_required` or always show optional password field on manual connect.

### 5. `mobile/controller.py:418-423` — **HIGH**
**Issue:** Wrong password shows status only; no re-prompt with password field. User must disconnect and reconnect without guided retry.  
**Fix:** On `is_password_error`, call `prompt_connect(..., password_required=True)` with same host/port and `connect_selected` callback (desktop pattern in credentials flow).

### 6. `mobile/screens.py:459-472` + `mobile/controller.py:532-540` — **MEDIUM**
**Issue:** Per-link listen/mic toggles update bridge state but **never refresh** `MDIconButton` icons in `LiveScreen._link_items`. Icons frozen at connect-time values.  
**Fix:** After `toggle_listen` / `toggle_mic`, re-read `link.listen_muted` / `link.mic_muted` and update icons on the stored row (or `refresh_connected_links()` helper).

### 7. `mobile/controller.py:644-739` — **MEDIUM**
**Issue:** `show_person_details` uses `TEXT`, `dp`, `MDBoxLayout` without imports → `NameError` if invoked. Not wired from UI today (people use `open_user_panel` / detail panel).  
**Fix:** Add imports from `mobile.theme` and `kivy.metrics` / `kivymd.uix.boxlayout`, or delete dead method.

### 8. `mobile/controller.py:416-417` — **MEDIUM**
**Issue:** Name-taken error focuses `screen._name_field`, but `ConnectScreen` has no `_name_field` (name collected in `credentials_dialog.prompt_connect`). Focus wiring is dead.  
**Fix:** Re-open `prompt_connect` with current host/port, or add name field to connect screen / focus `name_field` inside dialog on error.

### 9. `mobile/controller.py:818-832` — **MEDIUM** (KivyMD)
**Issue:** Tap dialog injects `MDTextField` via `self._tap_dialog.content_cls.parent` — fragile in KivyMD 1.2 custom dialogs; input may not render or lands wrong container.  
**Fix:** Put `tap_log` + `tap_input` in one `MDBoxLayout` `content_cls` (same pattern as `credentials_dialog.py`).

### 10. `mobile/controller.py:63` vs `babblecast/client/bridge.py:242` — **MEDIUM**
**Issue:** Mobile does not register `on_tap_open` / `on_tap_end` on `BridgeManager`. Remote tap end won't dismiss `_tap_dialog`; inconsistent with desktop `tap_end` handler.  
**Fix:** Wire `on_tap_end` to dismiss dialog and clear state; optional `on_tap_open` for peer-initiated taps.

### 11. `mobile/controller.py:240-246` — **MEDIUM**
**Issue:** `stop_hosting()` stops embedded server but does not disconnect bridge link to own host. Client session lingers until WS dies.  
**Fix:** Find link matching `embedded.host`/`ws_port` and `disconnect_link()` before `embedded.stop()`.

### 12. `mobile/android_foreground.py:39` + `mobile/buildozer.spec:20` — **MEDIUM**
**Issue:** Intent uses `putExtra("pythonService", "voice")` but buildozer service name is `Voice` (capital V). p4a service bootstrap may fail to load `mobile/voice_service.py`.  
**Fix:** Align extra with buildozer service name per p4a docs (typically `Voice` or spec-derived string); verify on device logcat.

### 13. `mobile/permissions.py:25` vs `mobile/buildozer.spec:25` — **MEDIUM**
**Issue:** Runtime requests `Permission.BLUETOOTH_CONNECT` but manifest lists `BLUETOOTH` only (no `BLUETOOTH_CONNECT`). Android 12+ may deny or crash on BT APIs.  
**Fix:** Add `BLUETOOTH_CONNECT` to `android.permissions` in `buildozer.spec` if BT permission is required; else remove from `request_permissions` list.

### 14. `babblecast/audio/android_engine.py:89-111` — **MEDIUM**
**Issue:** `AndroidMicCapture.start()` raises if `AudioRecord` fails (permission denied / hardware). `BridgeManager._ensure_audio` catches and falls back to chat-only, but unhandled path if mic started later via `ensure_input_monitoring`.  
**Fix:** Catch `RuntimeError` in `ensure_input_monitoring` / controller `on_live_enter`; surface permission prompt via `RECORD_AUDIO` check before opening panel.

### 15. `mobile/voice_service.py:4-8` — **LOW**
**Issue:** Foreground service entry is infinite `sleep`; no mic hold in service process. Relies on wake lock in `android_foreground.py`. May not satisfy `FOREGROUND_SERVICE_MICROPHONE` policy on strict OEM builds.  
**Fix:** Document tested OEM behavior; consider minimal service loop that references audio activity or remove microphone FGS type if wake lock suffices.

### 16. `mobile/screens.py:340-343` — **LOW**
**Issue:** PTT toggle does not update `_ptt_btn` icon (mute toggle does update at line 338).  
**Fix:** Set icon e.g. `record-circle` vs `record-circle-outline` when `ptt_active` changes.

### 17. `mobile/controller.py:117-127` — **LOW**
**Issue:** `stop_all` does not dismiss open `MDDialog`s (`_tap_dialog`, credentials, disconnect confirm). Callbacks may fire during teardown.  
**Fix:** Dismiss tracked dialogs in `stop_all` before `bridge.shutdown()`.

### 18. `mobile/detail_panel.py:316,320,324` — **LOW**
**Issue:** Panel reaches into `controller._bridge` private API instead of controller methods (`set_participant_muted`, etc.).  
**Fix:** Add thin controller wrappers for consistency and shutdown safety.

### 19. `mobile/screens.py:443-478` — **LOW**
**Issue:** `add_connected_link` has no guard if `link_id` already in `_link_items` (duplicate widget risk).  
**Fix:** If `link_id in self._link_items`, return early or replace row.

### 20. `mobile/credentials_dialog.py:52-53` — **LOW** (password UX)
**Issue:** Password field only shown when `password_required=True`; no optional password on manual connect to unknown servers.  
**Fix:** Always show password field (optional) on connect dialog, or "Advanced" toggle.

---

## Wiring Summary (healthy paths)

| Flow | Status |
|------|--------|
| Discovery → `ServerDiscovery` → `ConnectScreen.update_servers` | OK |
| Discovered tap → `connect_discovered` + `password_required` from mDNS `auth` | OK |
| Host → `prompt_host` → `EmbeddedServer` → auto `connect_to` | OK |
| Disconnect confirm + skip setting | OK (`prompt_disconnect`, `skip_disconnect_confirm`) |
| `on_stop` → `stop_all` → `bridge.shutdown()` | OK |
| Credentials save via `get_settings` / `save_settings` | OK (not raw config write) |
| Multicast lock acquire/release | OK pair in start/stop discovery |
| Voice foreground start/stop on link connect/disconnect | OK (`_sync_voice_foreground`) |

---

## Module Dependency Graph (mobile)

```
main.py → app.py → controller.py → bridge.py → session.py
                  → screens.py → detail_panel.py
                  → credentials_dialog.py
                  → android_network.py, permissions.py, android_foreground.py
bridge.py → audio/factory.py → audio/android_engine.py (on Android)
controller.py → discovery.py, embedded.py, room_controller.py
```
