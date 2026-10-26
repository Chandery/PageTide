"""A PDF the person attached (dropped, chosen, or handed over by the in-app download window) is part of the library, not
the cache: clearing "已下载的论文信息" keeps it and the reader still opens it (owner's question, 2026-10-26)."""
import json
import sys
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from app import server  # noqa: E402
import test_app_server  # noqa: E402
from pdf_fixture import minimal_pdf  # noqa: E402


class UserPdfKeptTests(unittest.TestCase):
    setUp = test_app_server.ServerSmokeTests.setUp

    def request(self, method, path, body=None, headers=None):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body, method=method, headers=headers or {})
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()

    def test_clearing_the_cache_keeps_an_attached_pdf(self):
        app = server.make_app(str(self.root))
        app.store.upsert_papers([{"key": "https://doi.org/10.1/kept", "title": "Kept", "published": "2026-01-01"}])
        app.store.close()
        pdf = minimal_pdf("kept")
        _, raw = self.request("POST", "/api/seeds/pdf", pdf, {"Content-Type": "application/pdf", "X-Filename": "kept.pdf"})
        pdf_id = json.loads(raw)["pdf_id"]
        self.request("POST", "/api/pdf/attach", json.dumps({"key": "https://doi.org/10.1/kept", "pdf_id": pdf_id}).encode(),
                     {"Content-Type": "application/json"})
        status, raw = self.request("POST", "/api/cache", json.dumps({"_method": "DELETE"}).encode(), {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertIn("pdf-archives", json.loads(raw)["preserved"])
        status, body = self.request("GET", "/api/pdf/view?key=" + urllib.parse.quote("https://doi.org/10.1/kept", safe=""))
        self.assertEqual((status, body), (200, pdf))                          # still there, byte for byte
        app = server.make_app(str(self.root))
        path = Path(app.pdf_path("https://doi.org/10.1/kept"))
        app.store.close()
        self.assertEqual(path.parent.name, "pdfs")                             # the library's own folder, not cache/
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
