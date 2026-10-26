"""The app's own files are served with fixed content types, whatever the system says.

A Windows user's reader failed with "Failed to fetch dynamically imported module .../vendor/pdfjs/pdf.min.mjs"
(2026-10-26): on Windows, mimetypes reads the registry, where an installed program can map .js/.mjs to text/plain or
leave .mjs unknown, and WebView2 refuses a JavaScript module served with any other type. Here the registry's answer is
simulated by making mimetypes say text/plain for everything.
"""
import sys
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from app import server  # noqa: E402
import test_app_server  # noqa: E402  (module import: its tests are not collected again here)

STATIC = ROOT / "app" / "static"


class StaticTypeTests(unittest.TestCase):
    setUp = test_app_server.ServerSmokeTests.setUp

    def served_type(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as response:
            response.read()
            return response.headers.get("Content-Type")

    def test_pdfjs_modules_are_javascript_even_when_the_system_says_text_plain(self):
        with mock.patch.object(server.mimetypes, "guess_type", return_value=("text/plain", None)):
            for path in ("/vendor/pdfjs/pdf.min.mjs", "/vendor/pdfjs/pdf.worker.min.mjs", "/app.js" if (STATIC / "app.js").exists()
                         else "/cnki.js"):
                self.assertEqual(self.served_type(path), "text/javascript; charset=utf-8", path)
            self.assertEqual(self.served_type("/theme.css"), "text/css; charset=utf-8")

    def test_every_kind_of_file_the_app_ships_has_a_fixed_type(self):
        suffixes = {p.suffix.lower() for p in STATIC.rglob("*") if p.is_file() and p.suffix}
        self.assertEqual(sorted(suffixes - set(server.STATIC_TYPES)), [])

    def test_an_unknown_kind_still_falls_back_to_mimetypes(self):
        with mock.patch.object(server.mimetypes, "guess_type", return_value=("image/webp", None)):
            self.assertEqual(server.static_type("x.webp"), "image/webp")
        self.assertEqual(server.static_type("X.MJS"), "text/javascript; charset=utf-8")


if __name__ == "__main__":
    unittest.main()
