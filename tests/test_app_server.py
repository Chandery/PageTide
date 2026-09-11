import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import server


class ServerSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "harness").mkdir()
        (self.root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (self.root / "harness" / "budget.json").write_text(
            (Path(__file__).resolve().parents[1] / "harness" / "budget.json").read_text())
        self.httpd = server.build_server(port=0, root=str(self.root))
        self.port = self.httpd.server_address[1]
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def _get(self, path):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def test_index_and_state_are_served(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"PaperDigHelper", body)
        status, body = self._get("/api/state")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertIn("profile", payload)
        self.assertIsInstance(payload["cards"], list)
        status, body = self._get("/api/home")
        payload = json.loads(body)
        self.assertIn("stats", payload)
        self.assertIn("summaries", payload)

    def test_paper_detail_endpoint(self):
        app = server.make_app(str(self.root))
        # A realistic key contains '://' and '/', which is why the API takes ?key=.
        url_key = "https://doi.org/10.48550/arxiv.2609.00001"
        app.store.upsert_papers([{"key": url_key, "title": "World Model Detail",
                                  "abstract": "full abstract text", "published": "2026-08-01",
                                  "group_name": "field"}])
        from urllib.parse import quote
        status, body = self._get(f"/api/paper?key={quote(url_key, safe='')}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["abstract"], "full abstract text")
        status, body = self._get(f"/api/paper/{quote(url_key, safe='')}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["key"], url_key)
        status, _ = self._get("/api/paper?key=missing")
        self.assertEqual(status, 404)

    def test_feedback_round_trip_over_http(self):
        # Seed one paper directly so the UI has something to show.
        app = server.make_app(str(self.root))
        app.store.upsert_papers([
            {"key": "p1", "title": "World Model Paper", "abstract": "latent planning",
             "published": "2026-08-01", "group_name": "field"}])
        app.build_batch(limit=1)
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/feedback",
            data=json.dumps({"key": "p1", "action": "useful"}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read())
        self.assertTrue(payload["interest_changed"])


if __name__ == "__main__":
    unittest.main()
