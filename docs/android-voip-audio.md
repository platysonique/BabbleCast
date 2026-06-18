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

## References

- Android 14 VoIP routing: `setCommunicationDevice()` replaces deprecated `setSpeakerphoneOn()` / `startBluetoothSco()`
- pyjnius issue #296: use `short[]` for AudioRecord/AudioTrack on p4a
- Perplexity research session 2026-06-17: full production VoIP patterns (WebRTC/Discord-style bridge)
