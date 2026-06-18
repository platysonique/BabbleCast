# MASTER — BabbleCast Code Audit Sweep (06.17.2026)

**Branch:** `cursor/room-switch-delete-chat-persistence` + uncommitted fixes  
**Auditors:** Bugbot, Security Review, Polling Auditor, Thermo-Nuclear Code Quality

---

## 06.17.2026 — ALL GOON ITEMS ADDRESSED (code complete — no build yet)

| Severity | Finding | Status |
|----------|---------|--------|
| **High** | Pre-connect `disconnect()` broke chat-only fallback | **FIXED** — `should_disconnect_failed_connect()` |
| **High** | UDP voice hijack via first-packet bind | **FIXED** — port must match `udp_addr` |
| **Medium** | Name collision TOCTOU | **FIXED** — `asyncio.Lock` on join |
| **Medium** | String-matched `"name already in use"` | **FIXED** — `ErrorCode` in protocol + `is_name_taken_error()` |
| **Medium** | Sync disk I/O on every chat message | **FIXED** — debounced + atomic `RoomChatStore` |
| **Medium** | Duplicate room/chat logic Qt + KivyMD | **FIXED** — `babblecast/client/room_controller.py` |
| **Medium** | `discovery.py` ignored mDNS Removed | **FIXED** — event-driven removal; prune fallback 30s |
| **Medium** | `VOICE_LEVEL` floods presence | **FIXED** — throttle speaking/level deltas |
| **Medium** | `mobile/main.py` 1,313 lines | **FIXED** — split: `main.py` (7), `app.py`, `controller.py`, `screens.py` |

---

## 06.17.2026 — Addressing sweep (Desktop + Android parity)

**Goon files:** `BabbleCastDesktopAddressingSweep06.17.2026.md`, `BabbleCastAndroidAddressingSweep06.17.2026.md`

| Finding | Status |
|---------|--------|
| Scalable `11.2.x.x` virtual addressing (`address.py`) | **FIXED** |
| Auto allocation always `11.2.9.x` when custom off | **FIXED** |
| Custom domain checkbox on host (Qt + mobile) | **FIXED** |
| Settings: `babblecast_ip`, `babblecast_custom_address`, `babblecast_address_suffix` | **FIXED** |
| mDNS + scan use configured virtual IP | **FIXED** |
| Android APK with changes | **BUILT + INSTALLED** |

**Open goon items:** 0

---

## 06.17.2026 — VERIFICATION (automated only)

- **49/49 pytest** pass
- **Linux smoke check** pass
- **NOT done yet:** APK rebuild, Samsung device test, PyQt6 visual pass

---

## 06.17.2026 — Verdict

**Code finish line:** goon audit items are implemented.  
**Build line:** do not build/install APK until you say go — then rebuild + `adb install` + phone smoke.

**Remaining low-priority debt (non-blocking):** UDP recv 0.5s timeout poll in session; binary APK out of git commits.
