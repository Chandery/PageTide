#!/usr/bin/env python3
"""Build every PageTide app asset from the two owner-approved source PNGs next to this file.

Sources (copied unchanged from the owner's design delivery of 2026-10-24):
  PageTide-icon.png      1254x1254, transparent outside the bookmark shape, the chosen app icon
  PageTide-wordmark.png  2172x724, transparent, dark-blue "Page" + bright-blue "Tide"

Outputs:
  src-tauri/icons/{32x32,128x128,128x128@2x,icon}.png, icon.icns, icon.ico
  app/static/favicon.png, wordmark.png (light theme), wordmark-dark.png (dark theme)

Dock/Finder icons follow Apple's grid: the artwork fills about 82% of the canvas, centred on its visible
bounds. The Windows .ico and the browser favicon fill more of the canvas (small sizes need the room).
The 1x 16 and 32 px icns slots are ic04/ic05 ("ARGB" + RLE-coded A,R,G,B planes), exactly what Apple's
iconutil writes, NOT PNG under icp4/icp5: macOS decodes icp4/icp5 PNGs as noise on non-Retina displays.

Usage: python3 docs/design/brand/pagetide/build_icons.py   (needs Pillow)
"""
import io
import struct
import sys
from pathlib import Path

try:
    from PIL import Image      # only the build needs Pillow; tests import this module for the stdlib helpers
except ImportError:
    Image = None

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
TAURI = ROOT / "src-tauri" / "icons"
STATIC = ROOT / "app" / "static"
ICON, WORDMARK = HERE / "PageTide-icon.png", HERE / "PageTide-wordmark.png"

DOCK_FILL = 0.82      # artwork share of the canvas for macOS / Tauri PNGs
WIDE_FILL = 0.94      # .ico and favicon
MASTER = 1024
ICNS = [(b"ic11", 32), (b"ic12", 64), (b"ic07", 128), (b"ic13", 256), (b"ic08", 256), (b"ic14", 512),
        (b"ic09", 512), (b"ic10", 1024)]
ICNS_ARGB = [(b"ic04", 16), (b"ic05", 32)]
TAURI_PNGS = {"32x32.png": 32, "128x128.png": 128, "128x128@2x.png": 256, "icon.png": 512}
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
WORDMARK_HEIGHT = 96  # px; the page shows it 24-26 px high (4x for large screens and scaling)
# Dark theme: the deep-blue "Page" becomes near the dark theme's text colour, "Tide" stays blue, a touch brighter.
DARK_PAGE, DARK_TIDE = (236, 241, 250), (56, 136, 255)
LIGHT_PAGE, LIGHT_TIDE = (18, 49, 92), (0, 92, 245)


def visible_box(image):
    """Bounds of the visible artwork: faint stray pixels (alpha <= 8) in the delivered PNGs are ignored."""
    return image.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()


def master(fill):
    """The icon, cropped to its visible bounds and centred on a square canvas at `fill` of its width."""
    source = Image.open(ICON).convert("RGBA")
    art = source.crop(visible_box(source))
    side = round(MASTER * fill)
    scale = side / max(art.size)
    art = art.resize((max(1, round(art.width * scale)), max(1, round(art.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    canvas.paste(art, ((MASTER - art.width) // 2, (MASTER - art.height) // 2), art)
    return canvas


def sized(image, px):
    return image if image.width == px else image.resize((px, px), Image.LANCZOS)


def png_bytes(image):
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()


def icns_rle(chan):
    """ICNS run-length coding: 0..127 = copy n+1 literals, 128..255 = repeat next byte n-125 times."""
    out, i, n = bytearray(), 0, len(chan)
    while i < n:
        run = 1
        while i + run < n and chan[i + run] == chan[i] and run < 130:
            run += 1
        if run >= 3:
            out += bytes([125 + run, chan[i]])
            i += run
            continue
        j = i
        while j < n and j - i < 128 and not (j + 2 < n and chan[j] == chan[j + 1] == chan[j + 2]):
            j += 1
        out += bytes([j - i - 1]) + chan[i:j]
        i = j
    return bytes(out)


def argb_entry(image):
    rgba = image.convert("RGBA").tobytes()
    return b"ARGB" + b"".join(icns_rle(rgba[c::4]) for c in (3, 0, 1, 2))


def build_icns(dock):
    entries = [(kind, argb_entry(sized(dock, px))) for kind, px in ICNS_ARGB]
    entries += [(kind, png_bytes(sized(dock, px))) for kind, px in ICNS]
    body = b"".join(t + struct.pack(">I", len(data) + 8) + data for t, data in entries)
    return b"icns" + struct.pack(">I", len(body) + 8) + body


def recolour(image, page, tide, new_page, new_tide):
    """Map the two ink colours (and everything between them, i.e. anti-aliasing) onto new ones; alpha is kept."""
    span = [t - p for p, t in zip(page, tide)]
    norm = sum(d * d for d in span)
    out = []
    for r, g, bl, alpha in image.convert("RGBA").getdata():
        t = sum((c - p) * d for c, p, d in zip((r, g, bl), page, span)) / norm
        t = min(1.0, max(0.0, t))
        out.append(tuple(round(n * (1 - t) + m * t) for n, m in zip(new_page, new_tide)) + (alpha,))
    result = Image.new("RGBA", image.size)
    result.putdata(out)
    return result


def wordmarks():
    source = Image.open(WORDMARK).convert("RGBA")
    art = source.crop(visible_box(source))
    art = art.resize((round(art.width * WORDMARK_HEIGHT / art.height), WORDMARK_HEIGHT), Image.LANCZOS)
    return art, recolour(art, LIGHT_PAGE, LIGHT_TIDE, DARK_PAGE, DARK_TIDE)


def main():
    TAURI.mkdir(parents=True, exist_ok=True)
    dock, wide = master(DOCK_FILL), master(WIDE_FILL)
    (TAURI / "icon.icns").write_bytes(build_icns(dock))
    for name, px in TAURI_PNGS.items():
        (TAURI / name).write_bytes(png_bytes(sized(dock, px)))
    wide.save(TAURI / "icon.ico", format="ICO", sizes=ICO_SIZES)
    (STATIC / "favicon.png").write_bytes(png_bytes(sized(wide, 64)))
    light, dark = wordmarks()
    (STATIC / "wordmark.png").write_bytes(png_bytes(light))
    (STATIC / "wordmark-dark.png").write_bytes(png_bytes(dark))
    print("wrote icons ->", TAURI.relative_to(ROOT), "and favicon.png, wordmark.png, wordmark-dark.png ->", STATIC.relative_to(ROOT))


if __name__ == "__main__":
    sys.exit(main())
