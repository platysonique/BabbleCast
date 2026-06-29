# BabbleCast Desktop/Qt Addressing Sweep — 06.17.2026

**Architecture:** PyQt6 / `babblecast/client/qt/` + shared `babblecast/`  
**Auditor:** codebase-gatherer (Goon Squad)

---

## Summary

| Status | Count |
|--------|------:|
| FIXED | 11 |
| OPEN | 0 |
| Blockers | 0 |

**Post-audit fixes:** Discovery connect uses `connect_host`; `_connect()` validates BabbleCast addresses.

---

## Findings

### 1 — `babblecast/address.py` — **FIXED** `[06.17.2026]`
**Issue:** Shared virtual addressing — `11.2.x.x`, auto always `11.2.9.x`.  
**Fix:** `allocate_babblecast_ip(custom=False)` scans only domain octet 9; `is_babblecast_ip` enforces octets 1–254.

### 2 — `babblecast/client/qt/credentials_dialog.py:95-163` — **FIXED** `[06.17.2026]`
**Issue:** Host dialog needs custom checkbox + suffix + allocation on OK.  
**Fix:** Mirrors mobile: `QCheckBox` “Custom BabbleCast address”, suffix field, `allocate_babblecast_ip()`, saves all three settings keys.

### 3 — `babblecast/client/qt/main_window.py:409` — **FIXED** `[06.17.2026]`
**Issue:** Host flow must persist allocated IP before embedded server starts.  
**Fix:** `self._settings.babblecast_ip = dlg.babblecast_ip` (dialog also saves custom flags).

### 4 — `babblecast/network.py:122-139` — **FIXED** `[06.17.2026]`
**Issue:** mDNS must advertise configured virtual IP, not router DHCP IP.  
**Fix:** `advertise_hosts_for_settings()` returns `settings.babblecast_ip`; `primary_lan_ipv4()` same.

### 5 — `babblecast/server/hub.py:616-636` — **FIXED** `[06.17.2026]`
**Issue:** Hub mDNS registration must use BabbleCast IP.  
**Fix:** `adv_hosts = advertise_hosts_for_settings()` first; fallback only if unset.

### 6 — `babblecast/server/embedded.py:49-52` — **FIXED** `[06.17.2026]`
**Issue:** Status “Hosting on …” must show virtual IP for others.  
**Fix:** `lan_host` returns `primary_lan_ipv4()` (babblecast IP); docstring updated.

### 7 — `babblecast/discovery.py` + `network_scan.py` — **FIXED** `[06.17.2026]`
**Issue:** Scan fallback when mDNS empty.  
**Fix:** `discovery_scan_domains()` → `[9]` + custom domain hint; port probe on `11.2.{d}.1-254`.

### 8 — `babblecast/config.py` — **FIXED** `[06.17.2026]`
**Issue:** Settings schema for addressing prefs.  
**Fix:** Three fields persisted in JSON settings.

### 9 — Connect manual IP validation — **N/A** `[06.17.2026]`
**Note:** Qt UI has no manual IP row; connect via Discover list or `*.babblecast.local`. Validation not required on desktop path.

### 10 — `babblecast/constants.py` — **FIXED** `[06.17.2026]`
**Issue:** Document auto domain constant.  
**Fix:** `BABBLECAST_AUTO_DOMAIN = 9`; legacy `babblecast_subnet_prefix()` delegates to `babblecast_prefix()`.

### 11 — Android parity — **FIXED** `[06.17.2026]`
**Issue:** Host credentials UX must match mobile.  
**Fix:** Both platforms: custom checkbox, suffix, auto `11.2.9.x`, same validation rules.

---

## Verification checklist

- [x] `tests/test_network_subnet.py` — 11 tests pass
- [x] `tests/test_discovery.py` — pass
- [ ] Qt visual: Host → custom off → status shows `11.2.9.x` (manual)
- [ ] Qt visual: Host → custom on → suffix `42.10` (manual)
