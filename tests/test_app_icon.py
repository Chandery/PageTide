"""Regression: the 1x 16/32 px icns slots must be ic04/ic05 ARGB entries (what iconutil writes).

macOS decodes PNG data stored under icp4/icp5 as noise, so the app icon looked garbled on
non-Retina external displays (Retina uses the @2x PNG slots). See docs/design/logo/build_icons.py.
"""
import importlib.util
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICNS = ROOT / "src-tauri" / "icons" / "icon.icns"

spec = importlib.util.spec_from_file_location("build_icons", ROOT / "docs/design/logo/build_icons.py")
build_icons = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_icons)


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
        w, h, rgba = build_icons.decode_png_rgba(self.entries[b"ic11"])
        self.assertEqual((w, h), (32, 32))
        a, r, g, b = self.argb(b"ic05", 32)
        for plane, c in ((r, 0), (g, 1), (b, 2), (a, 3)):
            self.assertEqual(plane, rgba[c::4], f"channel {c}")

    def test_argb_16px_has_alpha_and_ink(self):
        a, r, g, b = self.argb(b"ic04", 16)
        self.assertEqual(a[0], 0, "corner pixel is transparent")
        self.assertEqual(a[8 * 16 + 8], 255, "centre is opaque")
        self.assertLess(min(r), 60, "dark seal ink is present")
        self.assertGreater(max(r) - min(g), 100, "red bookmark is present")


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
