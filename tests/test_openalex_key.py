"""OpenAlex API key: stored locally with 0600, sent only as a header to api.openalex.org, never echoed.

Every key in these tests is a dummy value.
"""
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from app import openalex_key, server, sources
from app.service import App

DUMMY = "dummy-openalex-key-0000"


class KeyStorageTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name)
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        os.environ.pop("OPENALEX_API_KEY", None)
        self.addCleanup(env.stop)

    def test_save_load_clear_round_trip_with_private_permissions(self):
        self.assertEqual(openalex_key.status(self.data), {"configured": False, "source": None})
        status = openalex_key.save(self.data, DUMMY)
        self.assertTrue(status["configured"])
        self.assertNotIn(DUMMY, json.dumps(status))
        path = openalex_key.key_file(self.data)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(openalex_key.load(self.data), DUMMY)
        openalex_key.clear(self.data)
        self.assertIsNone(openalex_key.load(self.data))
        self.assertFalse(path.exists())

    def test_clear_when_nothing_saved_is_fine(self):
        self.assertFalse(openalex_key.clear(self.data)["configured"])

    def test_environment_variable_wins_and_is_reported_as_such(self):
        openalex_key.save(self.data, DUMMY)
        with mock.patch.dict(os.environ, {"OPENALEX_API_KEY": "from-env-key-1111"}):
            self.assertEqual(openalex_key.load(self.data), "from-env-key-1111")
            self.assertEqual(openalex_key.status(self.data)["source"], "environment")

    def test_invalid_keys_are_rejected_and_not_written(self):
        for bad in ("", "   ", "short", "has space inside-key", "line\nbreak-key-12345", "x" * 300, None):
            with self.assertRaises(ValueError):
                openalex_key.save(self.data, bad)
        self.assertFalse(openalex_key.key_file(self.data).exists())

    def test_surrounding_whitespace_is_trimmed(self):
        openalex_key.save(self.data, f"  {DUMMY}\n")
        self.assertEqual(openalex_key.load(self.data), DUMMY)


class RequestTests(unittest.TestCase):
    def test_key_is_a_header_on_the_openalex_host_and_not_in_the_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = sources.OpenAlex(tmp, api_key=DUMMY)
            request = client._request("https://api.openalex.org/works?search=x&mailto=a%40b.co")
            self.assertEqual(request.get_header("Authorization"), f"Bearer {DUMMY}")
            self.assertNotIn(DUMMY, request.full_url)
            # An unredirected header is not copied to the target of a redirect.
            self.assertNotIn("Authorization", request.headers)

    def test_key_is_never_attached_to_another_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = sources.OpenAlex(tmp, api_key=DUMMY)
            for url in ("https://example.org/works", "http://api.openalex.org.evil.example/works",
                        "https://evil.example/api.openalex.org"):
                self.assertIsNone(client._request(url).get_header("Authorization"), url)

    def test_no_key_means_no_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(sources.OpenAlex(tmp)._request("https://api.openalex.org/works").get_header("Authorization"))

    def test_cache_key_and_error_text_do_not_contain_the_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            keyed, plain = sources.OpenAlex(tmp, api_key=DUMMY), sources.OpenAlex(tmp)
            url = "https://api.openalex.org/works?search=x"
            self.assertEqual(keyed._cache_key(url), plain._cache_key(url))  # adding a key keeps the cache valid
            error = urllib.error.HTTPError(url, 500, "boom", {}, None)
            with mock.patch.object(sources.urllib.request, "urlopen", side_effect=error), \
                    mock.patch.object(sources.time, "sleep"):
                with self.assertRaises(sources.SourceError) as caught:
                    keyed._fetch(url)
            self.assertNotIn(DUMMY, str(caught.exception))

    def test_probe_sends_the_key_only_to_openalex(self):
        import data_probe
        with mock.patch.dict(os.environ, {"OPENALEX_API_KEY": DUMMY}):
            self.assertEqual(data_probe.openalex_auth_headers("https://api.openalex.org/works")["Authorization"],
                             f"Bearer {DUMMY}")
            self.assertEqual(data_probe.openalex_auth_headers("https://export.arxiv.org/api/query"), {})


class ServiceAndServerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "harness").mkdir()
        (self.root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (self.root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        os.environ.pop("OPENALEX_API_KEY", None)
        self.addCleanup(env.stop)

    def test_app_loads_a_saved_key_into_its_client(self):
        data = self.root / "data"
        openalex_key.save(data, DUMMY)
        app = App(root=str(self.root), data_dir=str(data))
        self.addCleanup(app.store.close)
        self.assertEqual(app.source.api_key, DUMMY)

    def _serve(self):
        httpd = server.build_server(port=0, root=str(self.root))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd.server_address[1]

    def _call(self, port, path, payload=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}", data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json"}, method="POST" if payload is not None else "GET")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()

    def test_settings_endpoint_saves_reports_and_clears_without_echoing_the_key(self):
        port = self._serve()
        status, body = self._call(port, "/api/settings", {"openalex_key": DUMMY})
        self.assertEqual(status, 200)
        self.assertNotIn(DUMMY, body)
        self.assertTrue(json.loads(body)["openalex"]["configured"])
        status, body = self._call(port, "/api/settings")
        self.assertNotIn(DUMMY, body)
        self.assertTrue(json.loads(body)["openalex"]["configured"])
        status, body = self._call(port, "/api/settings", {"clear_openalex_key": True})
        self.assertFalse(json.loads(body)["openalex"]["configured"])

    def test_invalid_key_is_a_400_and_nothing_is_stored(self):
        port = self._serve()
        status, body = self._call(port, "/api/settings", {"openalex_key": "bad key"})
        self.assertEqual(status, 400)
        self.assertFalse(json.loads(self._call(port, "/api/settings")[1])["openalex"]["configured"])

    def test_key_never_lands_in_the_user_settings_file(self):
        port = self._serve()
        self._call(port, "/api/settings", {"openalex_key": DUMMY})
        self._call(port, "/api/user_settings", {"settings": {"contactEmail": "me@lab.example"}})
        for path in self.root.rglob("settings.json"):
            self.assertNotIn(DUMMY, path.read_text())


if __name__ == "__main__":
    unittest.main()
