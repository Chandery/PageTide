import json
import sys
import tempfile
import threading
import unittest
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
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as response:
            return response.status, response.read()

    def test_index_and_state_are_served(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"PaperDigHelper", body)
        status, body = self._get("/api/state")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertIn("profile", payload)
        self.assertIsInstance(payload["cards"], list)

    def test_feedback_round_trip_over_http(self):
        # Seed one paper directly so /api/state has something to show.
        server.Handler.app.store.upsert_papers([
            {"key": "p1", "title": "World Model Paper", "abstract": "latent planning",
             "published": "2026-08-01", "group_name": "field"}])
        server.Handler.app.build_batch(limit=1)
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/feedback",
            data=json.dumps({"key": "p1", "action": "useful"}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read())
        self.assertTrue(payload["interest_changed"])


if __name__ == "__main__":
    unittest.main()
