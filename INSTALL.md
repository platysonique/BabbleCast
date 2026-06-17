# BabbleCast installation

## Linux (Ubuntu / Debian / Pop!_OS)

### One command (recommended)

```bash
git clone git@github.com:platysonique/BabbleCast.git
cd BabbleCast
bash packaging/linux/install.sh
bbc
```

`install.sh` installs system libraries (PortAudio, Opus, PyQt6 GL/X11 deps), creates a venv, installs Python packages, and puts `bbc` in `/usr/local/bin` or `~/.local/bin`.

### Manual install

```bash
sudo apt-get update
sudo apt-get install -y \
  python3-venv python3-pip \
  libportaudio2 libopus0 \
  libxkbcommon-x11-0 libgl1 libegl1 libxcb-cursor0 libxcb-xinerama0

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip wheel
pip install -r requirements.txt
pip install -e .
bbc
```

### Headless server only

```bash
pip install -r requirements.txt
pip install -e .
bbc server --name "My Hub"
```

### Troubleshooting Linux

| Symptom | Fix |
|--------|-----|
| `OSError: PortAudio library not found` | `sudo apt-get install libportaudio2` |
| `opuslib` / Opus errors | `sudo apt-get install libopus0` |
| PyQt6 fails to start / GL errors | Install `libgl1 libegl1 libxcb-cursor0 libxkbcommon-x11-0` |
| `bbc: command not found` | Use full path or re-run `install.sh`; check `/usr/local/bin` and `~/.local/bin` |
| mDNS discovery thread crash (`unexpected keyword argument 'zeroconf'`) | See [docs/known-issues.md](docs/known-issues.md) |

---

## Windows

### Prerequisites

1. [Python 3.12+](https://www.python.org/downloads/) — check **“Add python to PATH”**
2. [Microsoft Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist) (x64)
3. Opus runtime: install via [Opus tools](https://opus-codec.org/downloads/) or let PyInstaller bundle it (see build below)

### Manual install

```bat
git clone https://github.com/platysonique/BabbleCast.git
cd BabbleCast
python -m venv .venv
.venv\Scripts\activate
pip install -U pip wheel
pip install -r requirements.txt
pip install -e .
bbc
```

### Build standalone `.exe`

```bat
pip install -r requirements-dev.txt
pip install -e .
pyinstaller packaging\windows\babblecast.spec --noconfirm
```

Output: `dist\BabbleCast.exe`

Or run: `packaging\windows\build.bat`

---

## Verify install

```bash
bbc --help
python -m pytest tests/ -q
```

On Linux: `python scripts/linux_smoke_check.py`

---

## Do NOT use Wine on Linux

BabbleCast is a **native Linux app** on Linux (`bbc` via PyQt6 + PortAudio). Running Windows `python.exe` under Wine is unsupported and will crash (Wine missing `CopyFile2`, PyQt6, PortAudio, etc.).

Use the Linux install path above, or a real Windows machine / VM for Windows builds.
