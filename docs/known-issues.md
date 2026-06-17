# Known issues

Tracked runtime errors and workarounds for BabbleCast.

---

## mDNS discovery: `ServerDiscovery._on_service()` unexpected keyword `zeroconf`

**Status:** Fixed (2026-06-17)  
**Reported:** 2026-06-17 (Pop!_OS 24.04, Python 3.12, zeroconf 0.149.16)  
**Affects:** Client GUI / server list discovery (`ServerDiscovery` in `babblecast/discovery.py`)

### Symptom

When the client starts browsing for BabbleCast servers on the LAN, a background thread crashes and LAN discovery stops working. The app may otherwise appear to run.

### Traceback

```
Exception in thread zeroconf-ServiceBrowser-_babblecast._tcp-161801:
Traceback (most recent call last):
  File "/usr/lib/python3.12/threading.py", line 1073, in _bootstrap_inner
    self.run()
  File "src/zeroconf/_services/browser.py", line 820, in zeroconf._services.browser.ServiceBrowser.run
  File "src/zeroconf/_services/browser.py", line 730, in zeroconf._services.browser._ServiceBrowserBase._fire_service_state_changed_event
  File "src/zeroconf/_services/browser.py", line 740, in zeroconf._services.browser._ServiceBrowserBase._fire_service_state_changed_event
  File "src/zeroconf/_services/__init__.py", line 59, in zeroconf._services.Signal.fire
TypeError: ServerDiscovery._on_service() got an unexpected keyword argument 'zeroconf'
```

### Cause

`zeroconf` ≥ 0.132 invokes `ServiceBrowser` handlers with a **`zeroconf=` keyword argument**. The callback used `zc` as the first parameter name, so Python rejected the keyword call.

### Fix

Renamed the first parameter to `zeroconf` in `ServerDiscovery._on_service` (`babblecast/discovery.py`).

### Workaround (older builds)

Connect manually to a known server address (Tailscale IP or LAN IP + port) instead of relying on the auto-discovered server list.

---

## Android: noise suppression unavailable

**Status:** Open (by design on mobile)  
**Affects:** Android APK (`mobile/`)

### Symptom

Noise suppression slider has no effect on Android; gate still works.

### Cause

`noisereduce` / `scipy` are not bundled in the Android build (size/complexity). `NoiseSuppressor` skips when `noisereduce` is missing.

### Workaround

Use the noise gate (mute/PTT). Desktop client has full suppression.

---

## iOS build

**Status:** Blocked on Linux  
**Affects:** iOS packaging

Cannot compile or sideload iOS apps without macOS + Xcode. See `packaging/ios/README.md`.

---

## Windows CI (GitHub Actions)

**Status:** Open  
**Affects:** `.github/workflows/windows.yml`

Private-repo Windows runner jobs may fail immediately (`runner_id: 0`). Use a real Windows machine or fix runner billing/access.

---

## Wine on Linux

**Status:** Unsupported  
**Affects:** Anyone trying to run Windows `python.exe` under Wine

Will crash (missing Win32 APIs, no PortAudio/PyQt6). Use native Linux install or a Windows VM.
