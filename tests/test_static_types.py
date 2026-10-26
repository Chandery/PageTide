"""The app's own files are served with fixed content types, whatever the system says.

A Windows user's reader failed with "Failed to fetch dynamically imported module .../vendor/pdfjs/pdf.min.mjs"
(2026-10-26): on Windows, mimetypes reads the registry, where an installed program can map .js/.mjs to text/plain or
leave .mjs unknown, and WebView2 refuses a JavaScript module served with any other type. Here the registry's answer is
simulated by making mimetypes say text/plain for everything.
"""
import sys
import unittest
import urllib.error
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

    def test_a_missing_or_unreadable_file_is_logged_and_answered_plainly(self):
        import io
        from contextlib import redirect_stderr
        log = io.StringIO()
        with redirect_stderr(log):
            with self.assertRaises(urllib.error.HTTPError) as missing:
                self.served_type("/vendor/pdfjs/not-there.mjs")
            with mock.patch.object(server.Path, "read_bytes", side_effect=PermissionError("locked by a scanner")):
                with self.assertRaises(urllib.error.HTTPError) as locked:
                    self.served_type("/vendor/pdfjs/pdf.min.mjs")
        self.assertEqual((missing.exception.code, locked.exception.code), (404, 503))
        self.assertIn("static file missing: /vendor/pdfjs/not-there.mjs", log.getvalue())
        self.assertIn("static file unreadable: /vendor/pdfjs/pdf.min.mjs: locked by a scanner", log.getvalue())

    def test_the_reader_says_what_the_server_answered_when_pdfjs_does_not_load(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        loader = html[html.index("async function lib()"):html.index("const R = {")]
        self.assertIn("fetch('/vendor/pdfjs/pdf.min.mjs', { cache: 'no-store' })", loader)
        self.assertIn("阅读器组件 pdf.js 没能载入（${seen}）", loader)


if __name__ == "__main__":
    unittest.main()


class VersionTests(unittest.TestCase):
    setUp = test_app_server.ServerSmokeTests.setUp

    def version(self, env):
        with mock.patch.dict("os.environ", env, clear=False):
            for name in ("PAGETIDE_APP_VERSION", "PAGETIDE_CHANNEL"):
                if name not in env:
                    __import__("os").environ.pop(name, None)
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/version", timeout=5) as response:
                return __import__("json").loads(response.read())

    def test_the_settings_page_gets_the_packaged_version_and_build_kind(self):
        self.assertEqual(self.version({"PAGETIDE_APP_VERSION": "0.1.2"}), {"version": "0.1.2", "dev": False})
        self.assertEqual(self.version({"PAGETIDE_APP_VERSION": "0.1.2", "PAGETIDE_CHANNEL": "dev"}), {"version": "0.1.2", "dev": True})
        self.assertEqual(self.version({}), {"version": None, "dev": False})

    def test_the_update_section_shows_it(self):
        html = (STATIC / "settings.html").read_text(encoding="utf-8")
        self.assertLess(html.index('id="appVersion"'), html.index('id="checkUpdateBtn"'))
        self.assertIn("fetch('/api/version')", html)


class PdfPageBadgeTests(unittest.TestCase):
    def test_the_badge_states_where_the_pdf_is_and_the_tooltip_says_what_to_do(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("page: ['PDF 在原文页', 'PageTide 拿不到这篇的 PDF 文件，原文页面上有。在那里下载后拖进阅读器即可。']", html)
        self.assertNotIn("仅原文页", html)
        self.assertIn("status === 'page' ? 'external' : 'book'", html)
        self.assertTrue((STATIC / "icons" / "external-link.svg").exists())
        self.assertNotIn("手动下载", html[html.index("const PDF_BADGES"):html.index("const pdfBadge")])
