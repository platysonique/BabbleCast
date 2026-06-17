"""Regenerate icon.png and splash.png from assets/logo-full.png or Downloads source."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
DEFAULT_SRC = Path.home() / "Downloads" / "babblecast.png"


def prepare(source: Path | None = None) -> None:
    src_path = source or ASSETS / "logo-full.png"
    if not src_path.is_file():
        src_path = DEFAULT_SRC
    if not src_path.is_file():
        raise FileNotFoundError(f"Logo source not found: {src_path}")

    ASSETS.mkdir(exist_ok=True)
    src = Image.open(src_path).convert("RGBA")
    arr = np.array(src)
    h, w = arr.shape[:2]

    left = arr[:, :680]
    content = (left[:, :, 0] > 25) | (left[:, :, 1] > 25) | (left[:, :, 2] > 25)
    ys, xs = np.where(content)
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    size = max(x1 - x0, y1 - y0) + 40
    half = size // 2
    crop = (max(0, cx - half), max(0, cy - half), min(w, cx + half), min(h, cy + half))
    icon = src.crop(crop)
    iw, ih = icon.size
    if iw != ih:
        s = max(iw, ih)
        square = Image.new("RGBA", (s, s), (0, 0, 0, 255))
        square.paste(icon, ((s - iw) // 2, (s - ih) // 2))
        icon = square
    icon.resize((512, 512), Image.Resampling.LANCZOS).save(ASSETS / "icon.png")

    splash = src.copy()
    sw, sh = splash.size
    scale = min(1600 / sw, 900 / sh, 1.0)
    if scale < 1.0:
        splash = splash.resize((int(sw * scale), int(sh * scale)), Image.Resampling.LANCZOS)
    splash.save(ASSETS / "splash.png")
    src.save(ASSETS / "logo-full.png")
    print(f"Wrote {ASSETS / 'icon.png'} and {ASSETS / 'splash.png'}")


if __name__ == "__main__":
    prepare()
