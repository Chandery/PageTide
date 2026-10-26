"""The 功能介绍 page: it exists, is served, links home, is linked from home, its table of contents resolves."""
import http.client
import os
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import server

STATIC = ROOT / "app" / "static"


class GuidePageTests(unittest.TestCase):
    def setUp(self):
        self.html = (STATIC / "guide.html").read_text(encoding="utf-8")

    def test_page_and_style_exist(self):
        self.assertTrue((STATIC / "guide.css").is_file())
        self.assertIn('href="/theme.css"', self.html)

    def test_links_back_home(self):
        self.assertRegex(self.html, r'<a class="back" href="/">')

    def test_home_links_to_it(self):
        home = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/guide.html">功能介绍</a>', home)

    def test_every_toc_anchor_has_a_section(self):
        toc = re.search(r'<ul class="toc">(.*?)</ul>', self.html, re.S).group(1)
        anchors = re.findall(r'href="#([^"]+)"', toc)
        self.assertGreaterEqual(len(anchors), 8)
        ids = re.findall(r'<section id="([^"]+)"', self.html)
        self.assertEqual(sorted(anchors), sorted(ids))

    def test_no_baidu(self):
        self.assertNotIn("百度", self.html)

    def test_extractor_covers_the_page(self):
        text = (ROOT / "scripts" / "i18n_extract.py").read_text(encoding="utf-8")
        self.assertIn('"guide.html"', text)


class GuideServedTests(unittest.TestCase):
    def test_server_serves_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "harness").mkdir()
            (root / "app").mkdir()
            (root / "app" / "budget.json").write_text((ROOT / "app" / "budget.json").read_text())
            with mock.patch.dict(os.environ, {"PAGETIDE_DATA": str(root / "data")}):
                server.make_app(str(root)).store.close()
                httpd = server.build_server(port=0, root=str(root))
                threading.Thread(target=httpd.serve_forever, daemon=True).start()
                try:
                    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
                    conn.request("GET", "/guide.html")
                    r = conn.getresponse()
                    body = r.read().decode("utf-8")
                    conn.close()
                finally:
                    httpd.shutdown()
                    httpd.server_close()
        self.assertEqual(r.status, 200)
        self.assertIn("功能介绍", body)
        self.assertIn('id="privacy"', body)


if __name__ == "__main__":
    unittest.main()
