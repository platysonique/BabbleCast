# BabbleCast

Team live communication hub — voice + text chat for LAN and Tailscale networks.

## Features

- **Server/client combo** — host from the app or run headless `bbc server`
- **Auto-connect** when you host from the client
- **Network discovery** via mDNS (`_babblecast._tcp`)
- **Shared audio streams** — does not hijack system audio (Spotify/YouTube keep playing)
- **Microphone selector** with human-readable device names
- **Mute / Unmute / PTT** with adjustable noise gate and noise suppression
- **Multiple rooms** with presence list and per-user volume/mute
- **Text chat** with voice activity meters
- **Cross-platform**: Linux, Windows, Android, iOS

## Quick start (Linux)

```bash
git clone git@github.com:platysonique/BabbleCast.git
cd BabbleCast
bash packaging/linux/install.sh
bbc
```

Or without install:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
bbc
```

### Headless server

```bash
bbc server --name "Studio-A"
```

## Windows

```bat
packaging\windows\build.bat
```

Run `dist\BabbleCast.exe` or build installer with Inno Setup (`packaging\windows\installer.iss`).

## Android

```bash
cd mobile
pip install buildozer cython
buildozer android debug
```

APK output: `mobile/bin/`.

## iOS

See `mobile/build_ios.sh` — requires macOS + kivy-ios toolchain.

## Audio model

BabbleCast opens normal **shared** PortAudio input/output streams (same model as Discord/Zoom). It never requests exclusive device access on Windows WASAPI, PulseAudio, or PipeWire.

## Tailscale

Start the server on any machine in your tailnet. Clients discover via mDNS when on the same LAN; for remote peers, connect manually to the Tailscale IP (shown in server list when discoverable on that network segment).

## License

MIT
