# BabbleCast Android VoIP audio — how it works and why it broke

This is the definitive reference for BabbleCast voice on Android (Samsung 14/15, python-for-android, pyjnius).

## Architecture (one mic, one speaker, many servers)

```
┌─────────────┐     WebSocket + UDP/Opus      ┌──────────────┐
│  Server A   │◄────────────────────────────►│ ClientSession│
└─────────────┘                               │  (bridge)    │
┌─────────────┐                               │              │
│  Server B   │◄────────────────────────────►│ BridgeManager│
└─────────────┘                               │  1× mic      │
                                              │  1× speaker  │
                                              │  mix + route │
                                              └──────┬───────┘
                                                     │
                              pyjnius short[]        │
                              AudioRecord / AudioTrack
                                                     │
                                              ┌──────▼───────┐
                                              │ Android HAL  │
                                              └──────────────┘
```

- **BridgeManager** owns exactly one `AndroidMicCapture` and one `AndroidSpeakerOutput`.
- Each **ClientSession** is bridge-managed: it does not open its own devices; it sends mic via bridge and receives remote voice into the shared speaker mix.
- **Routing** uses `AudioManager.MODE_IN_COMMUNICATION` plus `setCommunicationDevice()` on API 31+ (fallback: legacy speakerphone/SCO on older APIs).

## pyjnius PCM rules (non-negotiable)

| Do | Don't |
|----|--------|
| Allocate Java **`short[]`** via `jarray("short")(n)` or `Array.newInstance(Short.TYPE, n)` | `autoclass('[S')(n)` or `autoclass('[B')(n)` — **No constructor available** |
| `AudioRecord.read(short[], …)` then copy to NumPy | `cast('byte[]', bytearray)` — Java writes a **copy**, Python buffer stays zero |
| `AudioTrack.write(short[], …)` after filling Java array | Assume verify = launch-only means Connect works |

## Bluetooth: HFP vs A2DP

- **A2DP** = high-quality **playback only** (headphones for music). Not valid for two-way VoIP.
- **HFP/SCO** = phone-call profile; mic + earpiece/speaker on headset.
- BabbleCast must only auto-route to Bluetooth when **HEADSET (HFP)** is connected, not when only A2DP is connected.

## Threading

| Thread | Work |
|--------|------|
| Kivy main | UI, `Clock.schedule_once` callbacks only |
| `bbc-android-audio` worker | Open AudioRecord/AudioTrack (blocking JNI) |
| `bbc-android-mic` / `bbc-android-spk` | read/write loops |
| `bbc-android-route` | Route JNI, write-gate coordination, deferred settings persist |
| WS/UDP threads | Opus encode/decode, jitter buffers |

**Never** call `AudioRecord.stop()` / `restart()` from a random `threading.Timer` on a BT callback — schedule mic restart on the capture thread via the bridge's main-thread deferral.

## Android async audio startup (correct behavior)

On Connect, audio **must not** report ready until the background worker has:

1. Created speaker + mic
2. Called `speaker.start(route=…)` and `mic.start()`
3. Set `_audio_started = True`
4. Called `_attach_bridge_speaker_to_sessions()` so UDP voice is not dropped

Until then, `_ensure_audio()` returns **False** and UI may show "Starting audio…" / retry meter polling.

## Permissions (fail-closed)

If `RECORD_AUDIO` is not granted, BabbleCast must **not** pretend the mic works. `record_audio_granted()` returns `False` when check fails or throws.

## Verification definition of done

1. `.venv/bin/python -m pytest tests/ -q` → all pass
2. `bash scripts/verify.sh` with phone connected → logcat contains `Android mic capture started` **or** graceful `Audio unavailable`
3. Manual: Connect → Settings mic meter moves → hear remote voice
4. Only then: `git push` + `adb install -r` APK

## Locked zones (DO NOT EDIT without explicit approval)

- **Mic:** `AndroidMicCapture` entire class in `babblecast/audio/android_engine.py`
- **Hear delivery:** `session._process_voice_datagram`, `push_pcm`, `AndroidSpeakerOutput.push_pcm`, `_mix`, hub WS/UDP voice relay
- **pyjnius PCM:** `short[]` via `jarray("short")` — never `byte[]` cast

## Routing-only zone

- `android_routing.py`, `android_route_worker.py`, `bridge.set_audio_route`, UI route buttons
- `AndroidSpeakerOutput._loop` — write-gate check only (3–5 lines)

## Route hot-swap (correct behavior)

- All `AudioManager` JNI on `bbc-android-route` thread
- Kivy main thread: enqueue job + UI pending state only
- Write gate pauses `AudioTrack.write` during route transition (~20ms gap acceptable)
- `MODE_IN_COMMUNICATION` set once at `session_begin`, not per toggle
- `auto` resolved to `speaker` (or `bluetooth` when HFP + auto_switch) before JNI

## Route hot-swap acceptance (device)

1. Connected, voice active: Earpiece → Speaker → Auto → Bluetooth (if HFP) — no freeze
2. After each toggle: talk and hear work (user confirms)
3. Logcat: `Android route worker applying` on `bbc-android-route`; no route JNI on main thread

```bash
adb -s RFCY81V4G9Y logcat -d -s python:I | grep -iE "route worker|audio route|communication device"
```

## References

- Android 14 VoIP routing: `setCommunicationDevice()` replaces deprecated `setSpeakerphoneOn()` / `startBluetoothSco()`
- pyjnius issue #296: use `short[]` for AudioRecord/AudioTrack on p4a
- Perplexity research session 2026-06-17: full production VoIP patterns (WebRTC/Discord-style bridge)
