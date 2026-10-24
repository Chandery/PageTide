"""A fresh install has no project, no papers and no seeds; nothing creates one behind the person's back."""
import http.client
import http.cookiejar
import json
import os
import select
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from app import migrations, server
from app.db import Store
from app.service import App, NoProject

ROOT = Path(__file__).resolve().parents[1]


class FreshDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_a_new_database_has_no_project(self):
        store = Store(self.dir / "fresh.sqlite")
        store.init()
        try:
            self.assertEqual(store.conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 0)
            self.assertEqual(migrations.get_schema_version(store.conn), 9)
        finally:
            store.close()

    def test_a_database_that_already_held_data_still_gets_its_default_project(self):
        path = self.dir / "legacy.sqlite"
        with mock.patch.object(migrations, "MIGRATIONS", []):   # the schema as it was before multi-project
            old = Store(path)
            old.init()
            old.conn.execute("INSERT INTO papers(key,title,created_at) VALUES ('k','Old paper','2026-01-01')")
            old.conn.commit()
            old.close()
        upgraded = Store(path)
        upgraded.init()
        try:
            self.assertEqual([r["id"] for r in upgraded.conn.execute("SELECT id FROM projects")], ["default_project"])
            self.assertEqual(upgraded.conn.execute("SELECT project_id FROM papers WHERE key='k'").fetchone()[0], "default_project")
        finally:
            upgraded.close()

    def test_any_legacy_table_with_rows_counts_as_data(self):
        for table, sql in (("feedback", "INSERT INTO feedback(paper_key,action,created_at) VALUES ('k','useful','2026-01-01')"),
                           ("profile_versions", "INSERT INTO profile_versions(created_at,note,data) VALUES ('2026-01-01','n','{}')")):
            path = self.dir / f"{table}.sqlite"
            with mock.patch.object(migrations, "MIGRATIONS", []):
                old = Store(path)
                old.init()
                old.conn.execute(sql)
                old.conn.commit()
                old.close()
            store = Store(path)
            store.init()
            try:
                self.assertEqual(store.conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 1, table)
            finally:
                store.close()


class NoProjectServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = App(root=str(ROOT), data_dir=Path(self.tmp.name) / "app")
        self.addCleanup(self.app.store.close)

    def assertStillEmpty(self):
        self.assertEqual(self.app.projects.list_projects(), [])
        self.assertIsNone(self.app.get_default_project_id())

    def test_the_default_project_is_never_created(self):
        self.assertIsNone(self.app.get_default_project_id())
        self.assertStillEmpty()

    def test_calls_that_need_a_project_say_so_and_create_nothing(self):
        calls = [lambda: self.app.profile(), lambda: self.app.pin_terms(["x"]), lambda: self.app.build_batch(),
                 lambda: self.app.cards(), lambda: self.app.explain({"title": "t"}),
                 lambda: self.app.refresh_candidates(), lambda: self.app.profile_insights(),
                 lambda: self.app._require_project(None)]
        for call in calls:
            with self.assertRaises(NoProject):
                call()
            self.assertStillEmpty()

    def test_feedback_has_no_project_to_land_in(self):
        self.app.store.upsert_papers([{"key": "p", "title": "T"}])
        with self.assertRaises(ValueError):
            self.app.record_feedback("p", "useful")
        with self.assertRaises(ValueError):
            self.app.retract_feedback("p", "understood")
        self.assertStillEmpty()

    def test_the_no_project_error_is_a_value_error_in_both_languages(self):
        with self.assertRaisesRegex(ValueError, "请先创建项目"):
            self.app.profile()

    def test_maintenance_has_nothing_to_do(self):
        from app import maintenance
        with mock.patch.object(self.app, "refresh_candidates", side_effect=AssertionError("must not fetch")):
            result = maintenance.manual_refresh(self.app)
        self.assertEqual((result["fetched"], result["reason_code"]), (0, "no_project"))
        self.assertEqual(self.app.home_maintenance(), {"maintenance": None, "recommendation_eligibility": None})
        self.assertStillEmpty()

    def test_a_project_without_keywords_asks_no_source(self):
        pid = self.app.projects.create_project("No keywords", "manual", [])
        with mock.patch.object(self.app.source, "discover", side_effect=AssertionError("no network")), \
                mock.patch.object(self.app.source, "discover_topic", side_effect=AssertionError("no network")):
            result = self.app.refresh_candidates(project_id=pid)
        self.assertEqual(result["reason_code"], "no_keywords")

    def test_a_missing_seed_file_means_no_seeds(self):
        (Path(self.tmp.name) / "harness").mkdir()   # the budget, but no seed list, as in the packaged app
        (Path(self.tmp.name) / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        bare = App(root=self.tmp.name, data_dir=Path(self.tmp.name) / "bare")
        self.addCleanup(bare.store.close)
        self.assertEqual(bare.seeds(), [])   # the packaged app ships none
        with self.assertRaises(ValueError):
            self.app.ensure_seed_papers()   # seeding always names its project

    def test_the_dev_cli_seeds_into_a_project_it_makes_explicitly(self):
        from app import cli
        self.assertEqual(cli._dev_project(self.app), self.app.get_default_project_id())
        names = [p["name"] for p in self.app.projects.list_projects()]
        self.assertEqual(names, ["Seeds (dev)"])
        self.assertEqual(cli._dev_project(self.app), self.app.get_default_project_id())   # and then reuses it

    def test_legacy_pins_do_not_follow_the_newest_project(self):
        self.app.store.save_profile({"project": "default", "pinned_terms": ["old-global-pin"], "weights": {"pos": 1.0, "neg": 0.5}}, note="pin")
        pid = self.app.projects.create_project("New", "manual", [])
        self.assertEqual(self.app.profile(pid)["pinned_terms"], [])


class NoProjectHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "harness").mkdir()
        (root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        env = mock.patch.dict(os.environ, {"PAGETIDE_DATA": str(root / "data")})
        env.start()
        self.addCleanup(env.stop)
        server.make_app(str(root)).store.close()
        self.httpd = server.build_server(port=0, root=str(root))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.port = self.httpd.server_address[1]

    def call(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=None if body is None else json.dumps(body).encode(),
                         headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, json.loads(response.read() or b"{}")
        finally:
            conn.close()

    def projects(self):
        return self.call("GET", "/api/projects")[1]["projects"]

    def test_home_and_state_answer_200_with_no_project_flag(self):
        for path in ("/api/home", "/api/state"):
            status, payload = self.call("GET", path)
            self.assertEqual(status, 200, path)
            self.assertIs(payload["no_project"], True)
            self.assertEqual(payload["cards"], [])
            self.assertIsNone(payload["profile"])
        status, payload = self.call("GET", "/api/home")
        self.assertIn("usage", payload)
        self.assertIn("provider", payload)
        self.assertEqual(self.projects(), [])

    def test_maintain_reports_no_project(self):
        status, payload = self.call("POST", "/api/maintain", {})
        self.assertEqual((status, payload["due"], payload["reason_code"]), (200, False, "no_project"))
        self.assertEqual(self.projects(), [])

    def test_routes_that_need_a_project_answer_400_not_500_and_create_nothing(self):
        for method, path, body in (("POST", "/api/daily", {}), ("POST", "/api/triage", {}), ("POST", "/api/pin", {"terms": "a"}),
                                   ("GET", "/api/profile", None), ("GET", "/api/profile/insights", None),
                                   ("GET", "/api/library", None)):
            status, payload = self.call(method, path, body)
            self.assertIn(status, (200, 400), path)
            self.assertNotEqual(status, 500, path)
            self.assertEqual(self.projects(), [], path)
        self.assertEqual(self.call("POST", "/api/daily", {})[0], 400)
        self.assertEqual(self.call("POST", "/api/pin", {"terms": "a"})[1]["reason_code"], "no_project")

    def test_the_first_project_the_person_makes_is_the_only_one(self):
        status, made = self.call("POST", "/api/projects", {"name": "Mine"})
        self.assertEqual(status, 200)
        self.assertEqual([p["id"] for p in self.projects()], [made["project_id"]])
        status, payload = self.call("GET", "/api/home")
        self.assertNotIn("no_project", payload)


class StaticGuardTests(unittest.TestCase):
    def test_the_desktop_backend_does_not_seed_or_fetch(self):
        source = (ROOT / "app" / "desktop.py").read_text(encoding="utf-8")
        for needle in ("ensure_seed_papers", "manual_refresh", "bootstrap", "seeds.json"):
            self.assertNotIn(needle, source)

    def test_the_build_does_not_package_the_seed_list(self):
        self.assertNotIn("seeds.json", (ROOT / "scripts" / "build_desktop.py").read_text(encoding="utf-8"))


@unittest.skipIf(sys.platform == "win32", "uses select.select on pipes; the Windows backend start is covered by tests/test_platform_compat.py")
class EmptyDirectoryStartTests(unittest.TestCase):
    def test_a_backend_started_on_an_empty_directory_stays_empty_and_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "fresh"
            env = dict(os.environ, HOME=tmp, DEEPSEEK_API_KEY="", PAGETIDE_DEV="0", PAGETIDE_DATA=str(data))
            code = ("import socket; "
                    "socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('Test prohibits outbound network')); "
                    "from app.desktop import main; main()")
            with tempfile.TemporaryFile(mode="w+") as errors:
                process = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, env=env, stdin=subprocess.PIPE,
                                           stdout=subprocess.PIPE, stderr=errors, text=True)
                try:
                    self.assertTrue(select.select([process.stdout], [], [], 20)[0], "backend did not announce readiness")
                    url = process.stdout.readline().strip().split(" ", 1)[1]
                    base = url.split("/_desktop/", 1)[0]
                    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                    opener.open(url, timeout=10).close()
                    with opener.open(base + "/api/projects", timeout=10) as response:
                        self.assertEqual(json.load(response)["projects"], [])
                    with opener.open(base + "/api/home", timeout=10) as response:
                        self.assertIs(json.load(response)["no_project"], True)
                    # Give a would-be bootstrap thread time to act before looking at the database.
                    threading.Event().wait(1.5)
                    process.stdin.close()
                    self.assertEqual(process.wait(timeout=15), 0)
                    errors.seek(0)
                    stderr = errors.read()
                    self.assertNotIn("Test prohibits outbound network", stderr)
                    self.assertNotIn("PAGETIDE_BOOTSTRAP_FAILED", stderr)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
                    process.stdout.close()
            db = sqlite3.connect(str(data / "pagetide.sqlite"))
            try:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM papers").fetchone()[0], 0)
            finally:
                db.close()
            self.assertFalse((data / "harness" / "seeds.json").exists())


if __name__ == "__main__":
    unittest.main()
