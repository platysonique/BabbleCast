# Known issues

Tracked runtime errors and workarounds for BabbleCast.

---

## mDNS discovery: `ServerDiscovery._on_service()` unexpected keyword `zeroconf`

**Status:** Open  
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

### Likely cause

`zeroconf` ≥ 0.132 invokes `ServiceBrowser` handlers with a **`zeroconf=` keyword argument**. BabbleCast’s callback is defined as:

```python
def _on_service(self, zc: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange) -> None:
```

The first parameter is named `zc`, not `zeroconf`, so Python rejects the keyword call.

Relevant code: `babblecast/discovery.py` — `ServerDiscovery._on_service`, registered via:

```python
ServiceBrowser(zc, SERVICE_TYPE, handlers=[self._on_service])
```

### Workaround (until fixed)

Connect manually to a known server address (Tailscale IP or LAN IP + port) instead of relying on the auto-discovered server list.

### Proposed fix

Rename the first parameter to `zeroconf` (or accept `**kwargs`), e.g.:

```python
def _on_service(
    self,
    zeroconf: Zeroconf,
    service_type: str,
    name: str,
    state_change: ServiceStateChange,
) -> None:
```

Also audit any other `ServiceBrowser` handlers for the same signature mismatch.
