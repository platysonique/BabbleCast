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
| mDNS discovery thread crash (`unexpected keyword argument 'zeroconf'`) | Fixed in current tree — see [docs/known-issues.md](docs/known-issues.md) |
| `PortAudioError: Device unavailable` / ALSA errors / Opus `silk/resampler` abort | Fixed in current tree — see [docs/known-issues.md](docs/known-issues.md); try another output device if audio still fails |

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

---

## Android (sideload)

### Build (Linux)

Requires Android SDK/NDK, Java 17 JDK, and buildozer:

```bash
bash packaging/android/build.sh
```

APK output: `packaging/android/releases/babblecast-*-arm64-v8a-debug.apk` (also copied under `mobile/bin/` during build; about 33 MB).

### Install on your phone

1. Enable **Developer options** → **USB debugging** (or copy the APK to the phone and allow **Install unknown apps**).
2. Connect USB, or transfer the APK (email, Drive, `adb push`, etc.).
3. Install:

```bash
adb install -r packaging/android/releases/babblecast-1.0.0-arm64-v8a-debug.apk
```

Or open the APK file on the phone and tap Install.

### Connect to a desktop server

1. On your PC: `bbc server --name "Studio"` (or Host Server in the desktop app).
2. Note your PC’s **LAN IP** (e.g. `192.168.1.10`) — not `127.0.0.1` from the phone.
3. In the BabbleCast mobile app: enter that IP, port **8765**, tap **Connect**.
4. Allow **Microphone** when prompted.

Voice uses Android `AudioRecord`/`AudioTrack`; mDNS discovery works on the same Wi‑Fi (manual IP always works).

---

## iOS

**Cannot be built or sideloaded from this Linux machine.** Apple requires **macOS + Xcode** to compile and sign iOS apps.

If you have a Mac: see `packaging/ios/README.md` and `mobile/build_ios.sh`.

Ways to get BabbleCast on iPhone after a Mac build: Xcode → Run on device (free Apple ID), TestFlight, or AltStore/SideStore (still needs an IPA built on Mac first).
