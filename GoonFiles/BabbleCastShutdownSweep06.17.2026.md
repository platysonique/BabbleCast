# BabbleCast Shutdown Sweep — 06.17.2026

## Critical fix applied (user crash on exit)

**Symptom:** `RuntimeError: wrapped C/C++ object of type _UiSignals has been deleted` when closing `bbc` after input monitoring was active.

**Root cause:** `closeEvent` called `disconnect_all()` but left `_monitoring_requested=True`, so PortAudio mic kept firing `_on_mic_level` → Qt signal emit after widgets destroyed.

**Fix:**
- `BridgeManager.shutdown()` — flag, null callbacks, force audio teardown
- `MicCapture.stop()` — `_enabled=False`, clear `_on_level` before stream close
- `main_window.closeEvent` — `_closing` guard, block signals, `bridge.shutdown()` before destroy
- `NoiseSuppressor` — skip noisereduce on 960-sample frames (scipy nperseg warning)

## Goon audit findings — ALL FIXED

| Severity | Item | Status |
|----------|------|--------|
| Medium | `SpeakerOutput.stop()` joins mix worker | Fixed |
| Medium | Mobile `stop_all()` uses `bridge.shutdown()` + unschedule tick | Fixed |
| Medium | `discovery.stop()` clears `on_update` | Fixed |
| Medium | `embedded.stop()` clears callbacks | Fixed |
| Low | Session WS handlers during partial disconnect | Fixed — `_handle` ignores when `_running` is false |
| Low | Tap dialog close ordering | Fixed — dismiss in `stop_all` / `closeEvent` |
