"""Runtime provider key provisioning: data-dir resolution, private storage, HTTP wiring.

These cover the desktop regression where the packaged app could never load the
runtime provider key (it lives under the user data directory, not the CWD or the
frozen bundle), so every AI feature silently degraded to local mode.
"""
import json
import os
import stat
import tempfile
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from tests import test_app_server
from app import server
from app.gateway import Gateway

REPO = Path(__file__).resolve().parents[1]


def _budget_root(tmp):
    root = Path(tmp) / "app"
    (root / "harness").mkdir(parents=True)
    (root / "app").mkdir(exist_ok=True)
    (root / "app" / "budget.json").write_text((REPO / "app" / "budget.json").read_text())
    return root


class GatewayKeyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = _budget_root(self.tmp.name)
        self.data = Path(self.tmp.name) / "data"
        self.data.mkdir()
        # Never let a developer's ambient key change the result.
        patch = mock.patch.dict(os.environ, {}, clear=False)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("DEEPSEEK_API_KEY", None)
        os.environ.pop("PAGETIDE_KEY_FILE", None)

    def test_key_is_loaded_from_the_data_directory(self):
        gateway = Gateway(root=self.root, data_dir=self.data)
        self.assertFalse(gateway.provider_status()["configured"])
        (self.data / "deepseek.env").write_text("DEEPSEEK_API_KEY=sk-data-dir\n")
        status = gateway.provider_status()
        self.assertTrue(status["configured"])
        self.assertEqual(status["source"], str(self.data / "deepseek.env"))

    def test_legacy_checkout_env_file_still_works(self):
        legacy = self.root / ".local" / "deepseek.env"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("DEEPSEEK_API_KEY=sk-legacy\n")
        gateway = Gateway(root=self.root, data_dir=self.data)
        self.assertTrue(gateway.provider_status()["configured"])

    def test_save_key_is_private_and_clearable(self):
        gateway = Gateway(root=self.root, data_dir=self.data)
        status = gateway.save_key("  sk-saved-secret  ")
        self.assertTrue(status["configured"])
        target = gateway.key_file()
        if sys.platform != "win32":  # 0600 file modes are POSIX-only; on Windows the per-user profile ACL is the protection.
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        # The wrapper value is trimmed, not echoed back through status.
        self.assertNotIn("sk-saved-secret", json.dumps(status))
        gateway.clear_key()
        self.assertFalse(gateway.provider_status()["configured"])
        self.assertFalse(target.exists())

    def test_save_key_rejects_empty_and_multiline(self):
        gateway = Gateway(root=self.root, data_dir=self.data)
        for bad in ("", "   ", "sk-a\nsk-b"):
            with self.assertRaises(ValueError):
                gateway.save_key(bad)
        self.assertFalse(gateway.provider_status()["configured"])

    def test_configured_key_reaches_the_provider_and_records_usage_locally(self):
        gateway = Gateway(root=self.root, data_dir=self.data, dev=False)
        payload = {"model": "deepseek-flash", "choices": [{"message": {"content": "你好"}}],
                   "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(payload).encode()

        # No provider request is made: this proves the key now traverses the one
        # gateway, and that reconciled usage lands in the user data directory.
        gateway.save_key("sk-fake-desktop")
        with mock.patch("app.gateway.urllib.request.urlopen", return_value=FakeResponse()) as opener:
            result = gateway.call("selection_translate", [{"role": "user", "content": "hi"}])
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["content"], "你好")
        request = opener.call_args[0][0]
        self.assertEqual(request.get_header("Authorization"), "Bearer sk-fake-desktop")
        self.assertEqual(gateway.ledger, self.data / "usage.jsonl")
        self.assertTrue(gateway.ledger.exists())

    def test_missing_key_degrades_without_calling_out(self):
        gateway = Gateway(root=self.root, data_dir=self.data, dev=False)
        with mock.patch("app.gateway.urllib.request.urlopen") as opener:
            result = gateway.call("selection_translate", [{"role": "user", "content": "hi"}])
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "no API key")
        opener.assert_not_called()

    def test_usage_ledger_and_dev_marker_live_in_the_data_directory(self):
        gateway = Gateway(root=self.root, data_dir=self.data, dev=False)
        self.assertEqual(gateway.ledger, self.data / "usage.jsonl")
        self.assertFalse(str(gateway.ledger).startswith(str(self.root)))
        (self.data / "DEV_MODE").write_text("")
        self.assertTrue(Gateway(root=self.root, data_dir=self.data).dev)


class SettingsHTTPTests(unittest.TestCase):
    def setUp(self):  # noqa: N802 - unittest hook
        test_app_server.ServerSmokeTests.setUp(self)
        patch = mock.patch.dict(os.environ, {}, clear=False)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("DEEPSEEK_API_KEY", None)
        os.environ.pop("PAGETIDE_KEY_FILE", None)

    def _request(self, method, path, body=None, origin=None):
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=None if body is None else json.dumps(body).encode(),
            headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def test_settings_round_trip_never_returns_the_key(self):
        status, body = self._request("GET", "/api/settings")
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["provider"]["configured"])
        secret = "sk-http-secret-value"
        status, body = self._request("POST", "/api/settings", {"api_key": secret})
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["provider"]["configured"])
        self.assertNotIn(secret, body.decode())
        status, body = self._request("GET", "/api/settings")
        self.assertNotIn(secret, body.decode())
        self.assertTrue(json.loads(body)["provider"]["configured"])
        # /api/home advertises readiness without the secret.
        status, body = self._request("GET", "/api/home")
        self.assertTrue(json.loads(body)["provider"]["configured"])
        self.assertNotIn(secret, body.decode())
        status, body = self._request("POST", "/api/settings", {"clear": True})
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["provider"]["configured"])

    def test_settings_rejects_bad_input_and_cross_origin(self):
        status, body = self._request("POST", "/api/settings", {"api_key": ""})
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(body))
        status, body = self._request("POST", "/api/settings", {"api_key": "x" * 600})
        self.assertEqual(status, 400)
        status, body = self._request("POST", "/api/settings", {"api_key": "sk-x"},
                                     origin="http://evil.example")
        self.assertEqual(status, 403)

    def test_ai_switch_and_user_settings_never_store_the_key(self):
        status, body = self._request("POST", "/api/settings", {"ai_enabled": False})
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertFalse(payload["ai_enabled"])
        self.assertIn("daily_total_tokens", payload["limits"])
        status, body = self._request("POST", "/api/settings", {"ai_enabled": "no"})
        self.assertEqual(status, 400)
        status, _ = self._request("POST", "/api/user_settings",
                                  {"settings": {"theme": "dark", "apiKey": "sk-leak", "dailyLimit": 0}})
        self.assertEqual(status, 200)
        status, body = self._request("GET", "/api/user_settings")
        self.assertNotIn("sk-leak", body.decode())
        self.assertNotIn("dailyLimit", json.loads(body)["settings"])
        status, body = self._request("POST", "/api/settings", {"ai_enabled": True})
        self.assertTrue(json.loads(body)["ai_enabled"])


class SettingsPageTests(unittest.TestCase):
    def test_settings_page_keeps_usage_and_explicit_test_without_budget_controls(self):
        html = (Path(__file__).resolve().parents[1] / "app/static/settings.html").read_text()
        for removed in ("dailyLimit", "aiRerank", "settings.apiKey", "apiKey:"):
            self.assertNotIn(removed, html)
        self.assertIn('id="aiEnabled"', html)
        self.assertIn("ai_enabled", html)
        self.assertIn('id="budgetLimits"', html)
        self.assertIn('id="testAiBtn"', html)
        self.assertIn('/api/ai-test', html)
        self.assertNotIn('不设用量上限，仍记录消耗', html)
        self.assertNotIn('预算上限（', html)


if __name__ == "__main__":
    unittest.main()
