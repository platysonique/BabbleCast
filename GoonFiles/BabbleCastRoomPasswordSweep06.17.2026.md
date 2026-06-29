# BabbleCast Room Password Admin — Goon Sweep

**Date:** 06.17.2026  
**Branch:** `cursor/room-switch-delete-chat-persistence`  
**Scope:** Room password display in Host admin + local remember/cache layer

---

## Bugbot findings (06.17.2026)

| # | Severity | Issue | Status |
|---|----------|-------|--------|
| 1 | High | Pending create password applied on any `JOINED`, not only matching create | **Fixed** — match by room name |
| 2 | High | Join password saved before server accepts join | **Fixed** — defer to `_handle_joined` with room_id match |
| 3 | Medium | Pending passwords not cleared on disconnect | **Fixed** — pop both pending dicts in `_handle_disconnect` |
| 4 | Medium | Password forgotten before delete confirms | **Fixed** — forget only in `_handle_room_deleted` |
| 5 | Medium | Qt admin label stale after disconnect | **Fixed** — refresh on `_on_link_disconnected` |

---

## Thermo-nuclear code quality findings (06.17.2026)

| # | Issue | Status |
|---|-------|--------|
| 1 | Duplicated session/room lookup in Qt + mobile controllers | **Fixed** — `BridgeManager.admin_room_password_display()` |
| 2 | Mobile refresh via private `_refresh_room_pwd_status` poke | **Fixed** — `SideDetailPanel.set_room_password_display()` push model |
| 3 | `controller.room_password_admin_display()` name collision with import | **Fixed** — method removed |
| 4 | Binary APK in source diff | **Fixed** — restored from git |
| 5 | Double forget on delete | **Fixed** — single path via room_deleted event |

---

## Architecture (post-fix)

- **`room_secrets.py`** — key format, persist/get/forget, display string formatting
- **`bridge.py`** — lifecycle: pending create (name+pwd), pending join (room_id+pwd), remember on confirmed `JOINED`, forget on `ROOM_DELETED`, clear pending on disconnect
- **UI (Qt + mobile)** — dumb label push via `set_room_password_display`; refresh on join/rooms/delete/active-link/disconnect

---

## Residual notes

- Plaintext room passwords live in local `settings.json` (`room_passwords`) — intentional for admin recall; server still stores hashes only.
- Server operator who bypasses join without typing password sees “protected (not stored on this device)” unless they created/joined with password on this device.
- `main_window.py` / `controller.py` remain large (>1k / ~990 lines) — pre-existing; this change net-shrunk controller duplication.

---

## Tests

- `tests/test_room_secrets.py` — 3 passed (key round-trip, normalization, display formatting)
