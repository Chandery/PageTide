#!/usr/bin/env python3
"""Build every PaperDig app icon from sealion.html (bookmark sea lion, chosen 2026-09-30).

Pipeline: export_icons.js (SVG masters + app/static svgs) -> rasterize.swift (AppKit SVG
renderer) -> src-tauri/icons PNGs + a hand-assembled icon.icns. Sizes <= 32 px use the
simplified "small" master (no blush, wider flipper gap, larger eye). The icns 16 and 32 px
slots (what non-Retina displays show) use the hand-tuned paperdig-icon-16/32.svg masters.

The 1x 16 and 32 px slots are ic04/ic05 ("ARGB" + RLE-coded A,R,G,B planes), exactly what
Apple's iconutil writes, NOT PNG under icp4/icp5: macOS decodes icp4/icp5 PNGs as noise, which
showed up as a garbled icon on non-Retina external displays (Retina uses the @2x PNG slots
ic11/ic12).

Usage: python3 docs/design/logo/build_icons.py
"""
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FINAL = HERE / "final"
TAURI = ROOT / "src-tauri" / "icons"
FULL, SMALL = FINAL / "paperdig-icon.svg", FINAL / "paperdig-icon-small.svg"
TINY16, TINY32 = FINAL / "paperdig-icon-16.svg", FINAL / "paperdig-icon-32.svg"

# ICNS PNG entry types: (OSType, pixels, master)
ICNS = [
    (b"ic11", 32, TINY32), (b"ic12", 64, FULL),
    (b"ic07", 128, FULL), (b"ic13", 256, FULL), (b"ic08", 256, FULL), (b"ic14", 512, FULL),
    (b"ic09", 512, FULL), (b"ic10", 1024, FULL),
]
# 1x ARGB entries: (OSType, pixels, master)
ICNS_ARGB = [(b"ic04", 16, TINY16), (b"ic05", 32, TINY32)]
TAURI_PNGS = {"32x32.png": (32, SMALL), "128x128.png": (128, FULL),
              "128x128@2x.png": (256, FULL), "icon.png": (512, FULL)}


def decode_png_rgba(data):
    """Decode an 8-bit RGBA, non-interlaced PNG (what rasterize.swift writes) -> (w, h, bytes)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, idat, w = 8, b"", None
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            assert (depth, ctype, interlace) == (8, 6, 0), "expected 8-bit RGBA, non-interlaced"
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    raw, stride, rows, prev = zlib.decompress(idat), w * 4, [], bytes(w * 4)
    for y in range(h):
        ft, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - 4] if i >= 4 else 0
            b = prev[i]
            c = prev[i - 4] if i >= 4 else 0
            if ft == 1:
                line[i] = (line[i] + a) & 255
            elif ft == 2:
                line[i] = (line[i] + b) & 255
            elif ft == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(bytes(line))
        prev = line
    return w, h, b"".join(rows)


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


def argb_entry(png_bytes, px):
    w, h, rgba = decode_png_rgba(png_bytes)
    assert w == h == px
    return b"ARGB" + b"".join(icns_rle(rgba[c::4]) for c in (3, 0, 1, 2))


def run(*cmd):
    subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL if cmd[0] == "swift" else None)


def raster(svg, out, px):
    run("swift", str(HERE / "rasterize.swift"), str(svg), str(out), str(px))
    return out.read_bytes()


def main():
    run("node", str(HERE / "export_icons.js"))
    TAURI.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        cache = {}

        def png(px, svg):
            key = (px, svg)
            if key not in cache:
                cache[key] = raster(svg, Path(tmp) / f"{svg.stem}-{px}.png", px)
            return cache[key]

        entries = []
        for kind, px, svg in ICNS_ARGB:
            entries.append((kind, argb_entry(png(px, svg), px)))
        entries += [(t, png(px, svg)) for t, px, svg in ICNS]
        body = b"".join(t + struct.pack(">I", len(data) + 8) + data for t, data in entries)
        (TAURI / "icon.icns").write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)
        for name, (px, svg) in TAURI_PNGS.items():
            (TAURI / name).write_bytes(png(px, svg))
        (FINAL / "paperdig-icon-1024.png").write_bytes(png(1024, FULL))
    print("wrote", ", ".join(["icon.icns", *TAURI_PNGS]), "->", TAURI.relative_to(ROOT))


if __name__ == "__main__":
    sys.exit(main())
