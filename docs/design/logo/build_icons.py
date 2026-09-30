#!/usr/bin/env python3
"""Build every PaperDig app icon from sealion.html (bookmark sea lion, chosen 2026-09-30).

Pipeline: export_icons.js (SVG masters + app/static svgs) -> rasterize.swift (AppKit SVG
renderer) -> src-tauri/icons PNGs + a hand-assembled icon.icns. Sizes <= 32 px use the
simplified "small" master (no blush, wider flipper gap, larger eye).

Usage: python3 docs/design/logo/build_icons.py
"""
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FINAL = HERE / "final"
TAURI = ROOT / "src-tauri" / "icons"
FULL, SMALL = FINAL / "paperdig-icon.svg", FINAL / "paperdig-icon-small.svg"

# ICNS PNG entry types: (OSType, pixels, master)
ICNS = [
    (b"icp4", 16, SMALL), (b"ic11", 32, SMALL), (b"icp5", 32, SMALL), (b"ic12", 64, FULL),
    (b"ic07", 128, FULL), (b"ic13", 256, FULL), (b"ic08", 256, FULL), (b"ic14", 512, FULL),
    (b"ic09", 512, FULL), (b"ic10", 1024, FULL),
]
TAURI_PNGS = {"32x32.png": (32, SMALL), "128x128.png": (128, FULL),
              "128x128@2x.png": (256, FULL), "icon.png": (512, FULL)}


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

        body = b"".join(t + struct.pack(">I", len(png(px, s)) + 8) + png(px, s) for t, px, s in ICNS)
        (TAURI / "icon.icns").write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)
        for name, (px, svg) in TAURI_PNGS.items():
            (TAURI / name).write_bytes(png(px, svg))
        (FINAL / "paperdig-icon-1024.png").write_bytes(png(1024, FULL))
    print("wrote", ", ".join(["icon.icns", *TAURI_PNGS]), "->", TAURI.relative_to(ROOT))


if __name__ == "__main__":
    sys.exit(main())
