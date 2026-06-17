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

---

## Linux: PortAudio ALSA output failure and Opus crash on startup

**Status:** Open  
**Reported:** 2026-06-17 (Pop!_OS 24.04, Python 3.12, PipeWire/PulseAudio + ALSA via PortAudio)  
**Affects:** Client audio startup (`SpeakerOutput.start` in `babblecast/audio/engine.py`, triggered from `ClientSession._start_audio`)

### Symptom

Running `bbc` may print a scipy warning, then ALSA/PortAudio errors, fail to open the output device, and abort with a core dump in Opus/silk after the speaker stream fails.

### Log / traceback

```
/home/papaya/Projects/BabbleCast/.venv/lib/python3.12/site-packages/scipy/signal/_spectral_py.py:1613: UserWarning: nperseg = 1024 is greater than input length  = 960, using nperseg = 960
  freqs, time, Zxx = _spectral_helper(x, x, fs, window, nperseg, noverlap,
Expression 'ret' failed in 'src/hostapi/alsa/pa_linux_alsa.c', line: 1736
Expression 'AlsaOpen( &alsaApi->baseHostApiRep, params, streamDir, &self->pcm )' failed in 'src/hostapi/alsa/pa_linux_alsa.c', line: 1904
Expression 'PaAlsaStreamComponent_Initialize( &self->playback, alsaApi, outParams, StreamDirection_Out, NULL != callback )' failed in 'src/hostapi/alsa/pa_linux_alsa.c', line: 2175
Expression 'PaAlsaStream_Initialize( stream, alsaHostApi, inputParameters, outputParameters, sampleRate, framesPerBuffer, callback, streamFlags, userData )' failed in 'src/hostapi/alsa/pa_linux_alsa.c', line: 2839
Failed to start audio devices
Traceback (most recent call last):
  File "/home/papaya/Projects/BabbleCast/babblecast/client/session.py", line 262, in _start_audio
    self._speaker.start()
  File "/home/papaya/Projects/BabbleCast/babblecast/audio/engine.py", line 204, in start
    self._stream = sd.OutputStream(
                   ^^^^^^^^^^^^^^^^
  File "/home/papaya/Projects/BabbleCast/.venv/lib/python3.12/site-packages/sounddevice.py", line 1532, in __init__
    _StreamBase.__init__(self, kind='output', wrap_callback='array',
  File "/home/papaya/Projects/BabbleCast/.venv/lib/python3.12/site-packages/sounddevice.py", line 914, in __init__
    _check(_lib.Pa_OpenStream(self._ptr, iparameters, oparameters,
  File "/home/papaya/Projects/BabbleCast/.venv/lib/python3.12/site-packages/sounddevice.py", line 2838, in _check
    raise PortAudioError(errormsg, err)
sounddevice.PortAudioError: Error opening OutputStream: Device unavailable [PaErrorCode -9985]
Fatal (internal) error in silk/resampler.c, line 184: assertion failed: inLen >= S->Fs_in_kHz
Aborted (core dumped)
```

### Notes

1. **scipy UserWarning** — noise suppression (`noisereduce`) uses a spectral helper on short frames (960 samples vs 1024 `nperseg`). Harmless warning; not the root cause.
2. **PortAudio `-9985` / ALSA `Device unavailable`** — output device could not be opened. Common on Linux when the default output device is busy, suspended, wrong, or PipeWire/PulseAudio is not routing ALSA clients correctly.
3. **`silk/resampler.c` abort** — secondary crash after audio startup failure; Opus hits an internal assertion when fed invalid/empty audio state. Treat as follow-on to the PortAudio failure, not a separate Opus install bug.

### Workarounds

- Confirm audio works in other apps (browser, `speaker-test`, system settings).
- On Pop!_OS / Ubuntu with PipeWire: ensure user session audio is running (`pipewire`, `wireplumber`, or PulseAudio compatibility).
- In BabbleCast, pick a different **output device** in settings if the UI allows it before connect.
- Close apps holding exclusive or broken ALSA handles (some games, misconfigured JACK/Pulse bridges).
- Retry after `systemctl --user restart pipewire wireplumber` (or log out/in).

### Proposed fix

- Catch `PortAudioError` in `SpeakerOutput.start` / `_start_audio` without proceeding to Opus encode/decode on a dead stream.
- Default to a valid output device (or PipeWire/Pulse host API) when ALSA default fails.
- Clamp or skip `noisereduce` on frames shorter than `nperseg` to silence the scipy warning.

