# BabbleCast

Team live communication hub — voice + text chat for LAN and Tailscale networks.

## Quick start (Linux)

```bash
git clone git@github.com:platysonique/BabbleCast.git
cd BabbleCast
bash packaging/linux/install.sh
bbc
```

**Manual install** (other machine, no install script):

```bash
sudo apt-get install -y python3-venv python3-pip libportaudio2 libopus0 \
  libxkbcommon-x11-0 libgl1 libegl1 libxcb-cursor0 libxcb-xinerama0
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip wheel
pip install -r requirements.txt
pip install -e .
bbc
```

Full platform details: **[INSTALL.md](INSTALL.md)**

## Features

- **Server/client combo** — host from the app or run headless `bbc server`
- **Auto-connect** when you host from the client
- **Network discovery** via mDNS (`_babblecast._tcp`)
- **Shared audio streams** — does not hijack system audio (Spotify/YouTube keep playing)
- **Microphone selector** with human-readable device names
- **Mute / Unmute / PTT** with adjustable noise gate and noise suppression
- **Multiple rooms** with presence list and per-user volume/mute
- **Text chat** with voice activity meters

## Dependencies

| File | Purpose |
|------|---------|
| `requirements.txt` | Runtime Python packages |
| `requirements-dev.txt` | + pytest, PyInstaller |
| `requirements-lock.txt` | Pinned versions for reproducible installs |

System libraries (PortAudio, Opus, PyQt6 GL/X11) are **not** in pip — see `INSTALL.md`.

### Headless server

```bash
bbc server --name "Studio-A"
```

## Windows

See **[INSTALL.md](INSTALL.md)** — `pip install -r requirements.txt`, then `pip install -e .`, or run `packaging\windows\build.bat`.

## Android / iOS

See `INSTALL.md` and `mobile/`.

## License

MIT
