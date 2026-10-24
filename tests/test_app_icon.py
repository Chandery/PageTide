"""The app icon comes from one source (assets/brand/PageTide-icon.png) and every file is the right size.

Regression kept from the previous icon: the 1x 16/32 px icns slots must be ic04/ic05 ARGB entries (what
iconutil writes). macOS decodes PNG data stored under icp4/icp5 as noise, so the app icon looked garbled on
non-Retina external displays (Retina uses the @2x PNG slots). See assets/brand/build_icons.py.
"""
import struct as _struct
import zlib
import importlib.util
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "src-tauri" / "icons"
ICNS = ICONS / "icon.icns"
SOURCE = ROOT / "assets" / "brand" / "PageTide-icon.png"

spec = importlib.util.spec_from_file_location("build_icons", ROOT / "assets/brand/build_icons.py")
build_icons = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_icons)


def decode_png_rgba(data):
    """Decode an 8-bit RGBA, non-interlaced PNG (what the build writes) -> (w, h, bytes)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, idat = 8, b""
    while pos < len(data):
        n, kind = _struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, interlace = _struct.unpack(">IIBBBBB", body)
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


def entries(data):
    assert data[:4] == b"icns" and struct.unpack(">I", data[4:8])[0] == len(data)
    pos, out = 8, {}
    while pos < len(data):
        kind, n = struct.unpack(">4sI", data[pos:pos + 8])
        out[kind] = data[pos + 8:pos + n]
        pos += n
    return out


def rle_decode(data, start, count=None):
    """Decode one RLE plane; with count -> (bytes, next position); without -> whole buffer."""
    if count is None:
        plane, end = rle_decode(data, 0, start)
        assert end == len(data)
        return plane
    out, i = bytearray(), start
    while len(out) < count:
        c = data[i]
        if c < 128:
            out += data[i + 1:i + 2 + c]
            i += 2 + c
        else:
            out += bytes([data[i + 1]]) * (c - 125)
            i += 2
    assert len(out) == count
    return bytes(out), i


class IcnsEntryTests(unittest.TestCase):
    @classmethod
    def entries_cache(cls):
        return entries(ICNS.read_bytes())

    @classmethod
    def setUpClass(cls):
        cls.entries = entries(ICNS.read_bytes())

    def test_no_png_under_legacy_1x_types(self):
        for kind in (b"icp4", b"icp5"):
            self.assertNotIn(kind, self.entries)

    def test_every_slot_is_present(self):
        wanted = [b"ic04", b"ic05", b"ic11", b"ic12", b"ic07", b"ic13", b"ic08", b"ic14",
                  b"ic09", b"ic10"]
        self.assertEqual(sorted(wanted), sorted(self.entries))

    def argb(self, kind, px):
        data = self.entries[kind]
        self.assertEqual(data[:4], b"ARGB")
        planes, pos = [], 4
        for _ in range(4):
            plane, pos = rle_decode(data, pos, px * px)
            planes.append(plane)
        self.assertEqual(pos, len(data), "no trailing bytes")
        return planes  # A, R, G, B

    def test_argb_32px_matches_the_png_of_the_same_master(self):
        w, h, rgba = decode_png_rgba(self.entries[b"ic11"])
        self.assertEqual((w, h), (32, 32))
        a, r, g, b = self.argb(b"ic05", 32)
        for plane, c in ((r, 0), (g, 1), (b, 2), (a, 3)):
            self.assertEqual(plane, rgba[c::4], f"channel {c}")

    def test_argb_16px_has_alpha_and_ink(self):
        a, r, g, b = self.argb(b"ic04", 16)
        self.assertEqual(a[0], 0, "corner pixel is transparent")
        self.assertGreater(a[8 * 16 + 8], 200, "centre is opaque")
        self.assertGreater(max(b) - min(r), 100, "the blue of the bookmark is present")


class SingleSourceTests(unittest.TestCase):
    def test_source_is_the_owner_chosen_png(self):
        w, h, rgba = decode_png_rgba(SOURCE.read_bytes())
        self.assertEqual((w, h), (1254, 1254))
        self.assertEqual(rgba[3], 0, "transparent outside the artwork")

    def test_tauri_pngs_have_the_declared_sizes(self):
        for name, px in (("32x32.png", 32), ("128x128.png", 128), ("128x128@2x.png", 256), ("icon.png", 512)):
            w, h, _ = decode_png_rgba((ICONS / name).read_bytes())
            self.assertEqual((w, h), (px, px), name)

    def test_dock_tile_leaves_the_apple_grid_margin(self):
        w, h, rgba = decode_png_rgba(IcnsEntryTests.entries_cache()[b"ic10"])
        self.assertEqual((w, h), (1024, 1024))
        xs = [i % w for i in range(w * h) if rgba[i * 4 + 3] > 8]
        ys = [i // w for i in range(w * h) if rgba[i * 4 + 3] > 8]
        share = max(max(xs) - min(xs), max(ys) - min(ys)) / 1024
        self.assertTrue(0.78 <= share <= 0.86, share)
        self.assertGreater(min(xs), 90, "the tile does not touch the edge")
        centre_row = rgba[(h // 2) * w * 4:(h // 2 + 1) * w * 4]
        edge = min(xs) + 6   # just inside the tile, left of the artwork: white
        self.assertEqual(tuple(centre_row[edge * 4:edge * 4 + 4]), (255, 255, 255, 255), "the tile is white")

    def test_ico_holds_the_windows_sizes(self):
        data = (ICONS / "icon.ico").read_bytes()
        reserved, kind, count = _struct.unpack("<HHH", data[:6])
        self.assertEqual((reserved, kind), (0, 1))
        sizes = {(data[6 + 16 * i] or 256) for i in range(count)}
        self.assertTrue({16, 32, 48, 256} <= sizes, sizes)


class RleTests(unittest.TestCase):
    def roundtrip(self, chan):
        self.assertEqual(rle_decode(build_icons.icns_rle(chan), len(chan)), chan)

    def test_runs_literals_and_limits(self):
        self.roundtrip(bytes([7]) * 1000)               # runs longer than 130 split
        self.roundtrip(bytes(range(256)) * 3)           # literals longer than 128 split
        self.roundtrip(b"\x01\x01\x02\x02\x03\x03\x03\x04")  # runs of 2 stay literal
        self.roundtrip(b"\x05")
        self.roundtrip(b"\x09\x09\x09")


if __name__ == "__main__":
    unittest.main()
