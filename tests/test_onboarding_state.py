"""When the onboarding tour is offered, and where its state is kept."""
import http.client
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from app import app_version, onboarding, server

ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("PAGETIDE_APP_VERSION", None)

    def write_conf(self, value):
        (self.root / "src-tauri").mkdir(exist_ok=True)
        (self.root / "src-tauri" / "tauri.conf.json").write_text(json.dumps(value), encoding="utf-8")

    def test_the_shell_variable_wins(self):
        self.write_conf({"version": "9.9.9"})
        os.environ["PAGETIDE_APP_VERSION"] = "0.1.0"
        self.assertEqual(app_version.current(self.root), "0.1.0")

    def test_prerelease_and_build_suffixes_are_versions(self):
        for value in ("1.2.3-rc.1", "1.2.3+build.5", "10.20.30"):
            os.environ["PAGETIDE_APP_VERSION"] = value
            self.assertEqual(app_version.current(self.root), value)

    def test_a_malformed_variable_is_ignored_and_the_config_is_used(self):
        self.write_conf({"version": "0.1.0"})
        for bad in ("", "v1.0.0", "1.0", "latest", "1.0.0 ", "1.0.0\n9"):
            os.environ["PAGETIDE_APP_VERSION"] = bad
            self.assertEqual(app_version.current(self.root), "0.1.0", repr(bad))

    def test_without_the_variable_the_tauri_config_gives_the_version(self):
        self.write_conf({"version": "0.2.0"})
        self.assertEqual(app_version.current(self.root), "0.2.0")

    def test_nothing_usable_means_unknown(self):
        self.assertEqual(app_version.current(self.root), "unknown")           # no file
        self.write_conf({"version": "not-a-version"})
        self.assertEqual(app_version.current(self.root), "unknown")
        self.write_conf(["not", "an", "object"])
        self.assertEqual(app_version.current(self.root), "unknown")
        (self.root / "src-tauri" / "tauri.conf.json").write_text("{", encoding="utf-8")
        self.assertEqual(app_version.current(self.root), "unknown")

    def test_the_repository_config_has_a_real_version(self):
        self.assertRegex(app_version.current(ROOT), r"^\d+\.\d+\.\d+")


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "data"
        env = mock.patch.dict(os.environ, {"PAGETIDE_APP_VERSION": "0.1.0"})
        env.start()
        self.addCleanup(env.stop)

    def state(self, projects):
        return onboarding.state(self.data, ROOT, projects)

    def test_the_four_combinations(self):
        # no project, never seen: offered because there is no project
        out = self.state(0)
        self.assertEqual((out["show"], out["reason"]), (True, "no_project"))
        # a project, never seen: offered because the version is new to this person
        out = self.state(1)
        self.assertEqual((out["show"], out["reason"], out["seen_version"]), (True, "new_version", None))
        onboarding.mark_done(self.data, ROOT)
        # a project, seen this version: not offered
        out = self.state(2)
        self.assertEqual((out["show"], out["reason"]), (False, "seen"))
        # no project again (all deleted) even though the version was seen: offered again
        out = self.state(0)
        self.assertEqual((out["show"], out["reason"]), (True, "no_project"))
        # a project and a newer app: offered again
        os.environ["PAGETIDE_APP_VERSION"] = "0.2.0"
        out = self.state(1)
        self.assertEqual((out["show"], out["reason"], out["seen_version"], out["version"]), (True, "new_version", "0.1.0", "0.2.0"))

    def test_done_writes_an_atomic_file_with_the_server_chosen_version(self):
        when = datetime(2026, 10, 24, 8, 30, 15, 999, tzinfo=timezone.utc)
        stored = onboarding.mark_done(self.data, ROOT, now=when)
        self.assertEqual(stored, {"seen_version": "0.1.0", "completed_at": "2026-10-24T08:30:15+00:00"})
        self.assertEqual(json.loads((self.data / "onboarding.json").read_text()), stored)
        self.assertEqual([p.name for p in self.data.iterdir()], ["onboarding.json"])   # no staging file left behind

    def test_a_damaged_file_reads_as_never_seen(self):
        self.data.mkdir()
        for text in ("{", "[]", '{"seen_version": 3, "completed_at": []}', ""):
            (self.data / "onboarding.json").write_text(text, encoding="utf-8")
            self.assertEqual(onboarding.read(self.data), {"seen_version": None, "completed_at": None}, text)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "harness").mkdir()
        (root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        self.data = root / "data"
        for patcher in (mock.patch.dict(os.environ, {"PAGETIDE_DATA": str(self.data), "PAGETIDE_APP_VERSION": "0.1.0"}),):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.root = root
        self.httpd = server.build_server(port=0, root=str(root))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def call(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=60)
        try:
            conn.request(method, path, body=None if body is None else json.dumps(body).encode(),
                         headers={"Content-Type": "application/json", **(headers or {})})
            response = conn.getresponse()
            return response.status, json.loads(response.read() or b"{}")
        finally:
            conn.close()

    def test_a_new_install_is_offered_the_tour_and_done_is_remembered(self):
        status, out = self.call("GET", "/api/onboarding")
        self.assertEqual((status, out["show"], out["reason"], out["version"], out["project_count"]), (200, True, "no_project", "0.1.0", 0))
        status, made = self.call("POST", "/api/projects", {"name": "Mine"})
        status, out = self.call("GET", "/api/onboarding")
        self.assertEqual((out["show"], out["reason"]), (True, "new_version"))
        status, out = self.call("POST", "/api/onboarding", {"action": "done"})
        self.assertEqual((status, out["ok"], out["state"]["show"]), (200, True, False))
        status, out = self.call("GET", "/api/onboarding")
        self.assertEqual((out["show"], out["seen_version"]), (False, "0.1.0"))

    def test_saving_settings_without_merge_keeps_the_onboarding_state(self):
        self.call("POST", "/api/projects", {"name": "Mine"})
        self.call("POST", "/api/onboarding", {"action": "done"})
        status, out = self.call("POST", "/api/user_settings", {"settings": {"theme": "dark"}})   # the page saves the whole file
        self.assertEqual(status, 200)
        self.assertEqual(json.loads((self.data / "settings.json").read_text()), {"theme": "dark"})
        status, out = self.call("GET", "/api/onboarding")
        self.assertFalse(out["show"])
        self.assertTrue((self.data / "onboarding.json").is_file())

    def test_an_unknown_action_is_a_400_and_writes_nothing(self):
        for body in ({"action": "reset"}, {"action": 3}, {}, {"action": "done", "version": "9.9.9"}):
            status, out = self.call("POST", "/api/onboarding", body)
            if body.get("action") == "done":
                self.assertEqual(status, 200)       # the version in the body is ignored
                self.assertEqual(out["state"]["seen_version"], "0.1.0")
            else:
                self.assertEqual(status, 400, body)
        self.assertEqual(json.loads((self.data / "onboarding.json").read_text())["seen_version"], "0.1.0")

    def test_start_does_not_mark_the_tour_seen(self):
        status, out = self.call("POST", "/api/onboarding", {"action": "start"})
        self.assertEqual((status, out["ok"]), (200, True))
        self.assertFalse((self.data / "onboarding.json").exists())
        self.assertTrue((self.data / "demo-sandbox").is_dir())

    def test_a_page_from_another_site_cannot_write_it(self):
        for action in ("start", "done"):
            status, out = self.call("POST", "/api/onboarding", {"action": action}, headers={"Origin": "http://evil.example"})
            self.assertEqual(status, 403, action)
        self.assertFalse((self.data / "onboarding.json").exists())
        self.assertFalse((self.data / "demo-sandbox").exists())


if __name__ == "__main__":
    unittest.main()
