# BabbleCast Android Addressing Sweep — 2026-06-17

**Scope:** `mobile/`, shared `babblecast/` modules used by Android, `mobile/buildozer.spec`, `packaging/android/`  
**Auditor:** codebase-gatherer (Goon Squad)  
**Focus:** Scalable 11.2.x.x addressing on Android/KivyMD

---

## Summary

| Category | Count |
|----------|-------|
| **FIXED** (fully wired) | 12 |
| **OPEN** | 0 |
| **INFO** (parity notes, not bugs) | 3 |

**Critical APK blockers:** 0 — O-01 (`MAX_NAME_LEN` import) fixed.

---

## FIXED — Addressing system wired on Android

### F-01 | FIXED | `babblecast/address.py` + `babblecast/constants.py`
**Severity:** N/A (verified)  
**Issue:** Fixed prefix 11.2.x.x with scalable third/fourth octets.  
**Evidence:** `BABBLECAST_FIXED_OCTETS = (11, 2)`, `is_babblecast_ip()` enforces octets 2–3 in 1–254.  
**TIMESTAMP:** [2026-06-17 14:00]

### F-02 | FIXED | `babblecast/address.py:83-107` + `mobile/credentials_dialog.py:211-212`
**Severity:** N/A (verified)  
**Issue:** Auto allocation always uses 11.2.9.x when custom checkbox OFF.  
**Evidence:** `allocate_babblecast_ip(custom=False)` calls `_first_free_host_in_domain(BABBLECAST_AUTO_DOMAIN)` where `BABBLECAST_AUTO_DOMAIN = 9`. Host dialog passes `custom=bool(custom_cb.active)`.  
**TIMESTAMP:** [2026-06-17 14:00]

### F-03 | FIXED | `mobile/credentials_dialog.py:131-177`
**Severity:** N/A (verified)  
**Issue:** Custom BabbleCast address checkbox on host dialog (parity with Qt password-protect row pattern).  
**Evidence:** `MDCheckbox` "Custom BabbleCast address", suffix field `hint_text=f"After {prefix}. — e.g. 9 or 9.10"`, disabled when unchecked, `validate_address_suffix()` on accept.  
**TIMESTAMP:** [2026-06-17 14:01]

### F-04 | FIXED | `mobile/controller.py:197-199`
**Severity:** N/A (verified)  
**Issue:** Manual connect validates BabbleCast IP, mDNS hostname, loopback.  
**Evidence:** Rejects hosts unless `127.0.0.1`, `localhost`, `is_babblecast_ip(host)`, or `host.endswith(".babblecast.local")`. User-facing message references `babblecast_prefix().x.x`.  
**TIMESTAMP:** [2026-06-17 14:01]

### F-05 | FIXED | `babblecast/address.py:27-37`
**Severity:** N/A (verified)  
**Issue:** `is_babblecast_ip` enforces 1–254 for third/fourth octets (not 0 or 255).  
**Evidence:** `all(1 <= o <= 254 for o in octets[2:])` plus fixed first two octets `(11, 2)`. Covered by `tests/test_network_subnet.py`.  
**TIMESTAMP:** [2026-06-17 14:01]

### F-06 | FIXED | `babblecast/discovery.py:266-306` → `babblecast/network_scan.py:14-41`
**Severity:** N/A (verified)  
**Issue:** Discovery fallback scan uses `discovery_scan_domains` (11.2.9.x + custom domain hint).  
**Evidence:** `ServerDiscovery._scan_loop()` calls `scan_local_subnets_for_servers()` (alias of `scan_babblecast_subnet_for_servers`). Domain hint from `settings.babblecast_ip` or `babblecast_custom_address` + `babblecast_address_suffix`. `discovery_scan_domains()` inserts custom domain before auto domain 9. Mobile controller uses same `ServerDiscovery` class (`mobile/controller.py:72-74`).  
**TIMESTAMP:** [2026-06-17 14:02]

### F-07 | FIXED | `babblecast/config.py:35-37,64-66` + `mobile/credentials_dialog.py:217-222`
**Severity:** N/A (verified)  
**Issue:** Settings persist `babblecast_ip`, `babblecast_custom_address`, `babblecast_address_suffix`.  
**Evidence:** `UserSettings` dataclass fields; load/save in `settings.json`; host dialog calls `save_settings(settings)` on accept. Android path via `babblecast/paths.py` (`ANDROID_PRIVATE` / `app_storage_path()`).  
**TIMESTAMP:** [2026-06-17 14:02]

### F-08 | FIXED | `babblecast/server/hub.py:616-632` + `babblecast/network.py:122-129`
**Severity:** N/A (verified)  
**Issue:** Hosted server mDNS advertises configured BabbleCast IP.  
**Evidence:** `advertise_hosts_for_settings()` returns `[settings.babblecast_ip]` when valid; `EmbeddedServer` → `BabbleCastHub(advertise=True)` used by mobile host flow.  
**TIMESTAMP:** [2026-06-17 14:03]

### F-09 | FIXED | `mobile/screens.py:62-72` + `mobile/controller.py:170-172`
**Severity:** N/A (verified)  
**Issue:** Connect UI copy reflects scalable addressing (not 11.2.9-only).  
**Evidence:** Manual label uses `babblecast_prefix().x.x` and `babblecast_auto_subnet()`; discovery empty state mentions scanning auto subnet.  
**TIMESTAMP:** [2026-06-17 14:03]

### F-10 | FIXED | `mobile/android_network.py:12-36` + `mobile/controller.py:116-117`
**Severity:** N/A (verified)  
**Issue:** Android mDNS multicast lock acquired before discovery.  
**Evidence:** `acquire_multicast_lock()` via JNI `WifiManager.MulticastLock`; called in `start_discovery()` and on location permission grant.  
**TIMESTAMP:** [2026-06-17 14:03]

### F-11 | FIXED | `mobile/permissions.py:33-58` + `mobile/buildozer.spec:25`
**Severity:** N/A (verified)  
**Issue:** Android discovery permissions declared and requested at runtime.  
**Evidence:** `ACCESS_FINE_LOCATION`, `CHANGE_WIFI_MULTICAST_STATE`, `NEARBY_WIFI_DEVICES` (API 33+), `BLUETOOTH_CONNECT` (API 31+); mirrored in `buildozer.spec` `android.permissions`.  
**TIMESTAMP:** [2026-06-17 14:04]

### F-12 | FIXED | `mobile/credentials_dialog.py:115-224` vs `babblecast/client/qt/credentials_dialog.py:83-184`
**Severity:** N/A (verified)  
**Issue:** Host dialog feature parity with Qt desktop (custom address, suffix validation, allocate, persist).  
**Evidence:** Same `allocate_babblecast_ip`, `validate_address_suffix`, `babblecast_auto_subnet` help text pattern; mobile uses KivyMD widgets, Qt uses QCheckBox/QLineEdit — behavior aligned.  
**TIMESTAMP:** [2026-06-17 14:04]

---

## OPEN — Issues requiring attention

_All former open items (O-01 through O-07) fixed 06.17.2026._

### O-01 | FIXED | `mobile/controller.py:22`
**Fix:** Added `MAX_NAME_LEN` to constants import.

### O-02 | FIXED | `babblecast/network_scan.py`
**Fix:** `last_server_host` used as domain hint when valid BabbleCast IP.

### O-03–O-04 | FIXED | dead imports removed from `mobile/credentials_dialog.py`, `mobile/screens.py`.

### O-05 | FIXED | `_join_local_host()` removed from `mobile/controller.py`.

### O-06 | FIXED | Discovery empty-state copy updated to BabbleCast addressing.

### O-07 | FIXED | Removed no-op `merge_scan_with_client_subnets`; discovery calls scan directly.

---

## INFO — Parity and design notes (not open bugs)

### I-01 | INFO | `mobile/controller.py:197` vs Qt `main_window.py`
**Severity:** INFO  
**Issue:** Android has manual IP connect with validation; Qt desktop has discovery-list connect only (no manual host field, no `is_babblecast_ip` gate in `_connect`).  
**Context:** Android is ahead on manual-connect validation; not a ship blocker.  
**TIMESTAMP:** [2026-06-17 14:08]

### I-02 | INFO | `mobile/controller.py:197`
**Severity:** INFO  
**Issue:** Bare hostname `babblecast.local` is rejected; only `*.babblecast.local` (slug hostnames from mDNS) accepted. Consistent with `service_hostname()` in `discovery.py:28-29`.  
**Context:** Matches actual advertisement format; bare `babblecast.local` is not a valid connect target in this architecture.  
**TIMESTAMP:** [2026-06-17 14:08]

### I-03 | INFO | `grep 11.2.9` across `mobile/`
**Severity:** INFO  
**Issue:** No stale 11.2.9-only-only model in mobile code. Remaining `11.2.9` references are correct auto-subnet documentation (`babblecast_auto_subnet()`, example host default domain=9).  
**TIMESTAMP:** [2026-06-17 14:08]

---

## Architecture trace (codebase-gatherer)

### Entry points
- **APK entry:** `mobile/main.py` → `BabbleCastMobileApp` (`mobile/app.py`)
- **Discovery start:** `app.py:55` schedules `controller.start_discovery()`
- **Build:** `packaging/android/build.sh` → `mobile/buildozer.spec`

### Data flow — host
```
ConnectScreen._host() → controller.host_server()
  → prompt_host() [allocate + save settings]
  → _start_host_with_name() → _start_host()
  → EmbeddedServer.start() → BabbleCastHub [mDNS advertises babblecast_ip]
  → _on_embedded_started() → connect_to(127.0.0.1)
```

### Data flow — connect
```
ConnectScreen._connect() → controller.connect_to() [is_babblecast_ip gate]
  → prompt_connect() → connect_selected() → BridgeManager.connect()
```

### Data flow — discovery
```
ServerDiscovery [mDNS thread + _scan_loop]
  → scan_local_subnets_for_servers()
  → discovery_scan_domains(domain_hint) → scan_domains_for_servers()
  → controller._apply_servers() → ConnectScreen.update_servers()
```

### Tech stack (Android path)
- Kivy 2.3.1 / KivyMD 1.2.0, Python 3.11.8, buildozer API 33
- Shared: zeroconf, websockets, `babblecast.address`, `babblecast.discovery`, `babblecast.config`
- Android JNI: multicast lock (`pyjnius`), permissions (`android.permissions`)

**TIMESTAMP:** [2026-06-17 14:09]

---

## APK ship verdict

| Blocker | Status |
|---------|--------|
| Addressing model wired end-to-end | **Yes** |
| Settings persistence on Android | **Yes** |
| Discovery + permissions | **Yes** |
| Host crash on Start | **Fixed** — `MAX_NAME_LEN` import |

**Ship recommendation:** Addressing is clear for APK ship. Device smoke on phone still manual.
