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

**Status:** Fixed (2026-06-17)  
**Reported:** 2026-06-17 (Pop!_OS 24.04, Python 3.12, PipeWire/PulseAudio + ALSA via PortAudio)  
**Affects:** Client audio startup (`SpeakerOutput.start` in `babblecast/audio/engine.py`, triggered from `ClientSession._start_audio`)

### Symptom

Running `bbc` may print a scipy warning, then ALSA/PortAudio errors, fail to open the output device, and abort with a core dump in Opus/silk after the speaker stream fails.

### Log / traceback

```
/home/papaya/Projects/BabbleCast/.venv/lib/python3.12/site-packages/scipy/signal/_spectral_py.py:1613: UserWarning: nperseg = 1024 is greater than input length  = 960, using nperseg = 960
  freqs, time, Zxx = _spectral_helper(x, x, fs, window, nperseg, noverlap,
Expression 'ret' failed in 'src/hostapi/alsa/pa_linux_alsa.c', line: 1736
...
sounddevice.PortAudioError: Error opening OutputStream: Device unavailable [PaErrorCode -9985]
Fatal (internal) error in silk/resampler.c, line 184: assertion failed: inLen >= S->Fs_in_kHz
Aborted (core dumped)
```

### Cause

1. **PortAudio `-9985`** — default ALSA output device unavailable; PipeWire/Pulse devices were not tried as fallbacks.
2. **Partial startup** — mic could start, speaker fail, leaving a broken audio path.
3. **Opus silk abort** — invalid/short PCM reached the encoder after startup failure.
4. **scipy warning** — `noisereduce` on 960-sample frames (harmless noise).

### Fix

- `babblecast/audio/portaudio.py` — try devices in order: saved preference → default (PipeWire before Pulse before ALSA) → all outputs.
- `SpeakerOutput.start` / `MicCapture.start` — iterate fallbacks; roll back worker thread on failure.
- `ClientSession._start_audio` — start speaker first; stop both on error; show dialog instead of crashing.
- `BridgeManager._ensure_audio` — same cleanup; connect continues for chat if audio fails.
- `OpusCodec` — pad/validate frame size; empty decode returns silence.
- `NoiseSuppressor` — skip processing on frames shorter than 1024 samples.

### Workaround (older builds or broken system audio)

- Confirm audio works in other apps (browser, `speaker-test`, system settings).
- On Pop!_OS / Ubuntu with PipeWire: ensure user session audio is running (`pipewire`, `wireplumber`, or PulseAudio compatibility).
- In BabbleCast, pick a different **output device** in settings before connect.
- Retry after `systemctl --user restart pipewire wireplumber` (or log out/in).

---

## Linux: immediate Opus `silk/resampler` abort on launch

**Status:** Open  
**Reported:** 2026-06-17 (Pop!_OS 24.04, Python 3.12, post–PortAudio-fix builds)  
**Affects:** Client launch (`bbc`) — process aborts before or without a useful Python traceback

### Symptom

Running `bbc` exits immediately with a native Opus assertion. No Python stack trace is printed; the shell only shows:

```
Fatal (internal) error in silk/resampler.c, line 184: assertion failed: inLen >= S->Fs_in_kHz
Aborted (core dumped)
```

### Log

```
papaya@pop-os:~$ bbc
Fatal (internal) error in silk/resampler.c, line 184: assertion failed: inLen >= S->Fs_in_kHz
Aborted (core dumped)
```

### Cause (likely)

Opus/SILK internal resampler received **too few input samples** (`inLen` smaller than one millisecond at the input sample rate). This usually means empty, truncated, or mis-sized PCM reached `opuslib` encode/decode — often when:

- Audio startup partially fails but the voice pipeline still runs
- A zero-length or sub-frame buffer is passed to the encoder/decoder
- A background thread encodes before mic capture is producing valid 20 ms frames

Related to the earlier PortAudio startup issue ([above](#linux-portaudio-alsa-output-failure-and-opus-crash-on-startup)), but this variant can appear **without** visible ALSA/PortAudio log lines if the crash happens quickly or stderr is not flushed.

Relevant code: `babblecast/audio/codec.py` (`OpusCodec`), `babblecast/client/session.py` (voice loop), `babblecast/audio/engine.py` (capture/playback).

### Workarounds

- Ensure system audio is healthy (PipeWire/Pulse running; output device works in other apps).
- Run `bbc server` (headless, no local mic/speaker) to confirm the crash is client-audio-specific.
- Update to the latest `master` after each fix; re-run `bash packaging/linux/install.sh`.

### Proposed fix

- Never call Opus encode/decode on buffers shorter than `FRAME_SAMPLES` (960 @ 48 kHz).
- Guard all codec entry points; return silence instead of calling native Opus on invalid input.
- Defer starting the voice/encode loop until both mic and speaker streams are confirmed open.
- Catch native abort paths by validating PCM length in Python before every `opuslib` call.

