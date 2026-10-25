"""Route Mode slice 2: new papers should arrive without pressing 抓取, without creating reading debt.

Rules under test (R-NODEBT, E-NO-DEBT, E-OFFLINE): at most one refresh per interval and one batch per day,
no catch-up for missed days, no unread count, failures visible and bounded, and never an AI call.
"""
import datetime
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import maintenance, server, sources
from app.service import App
from recommendation_fixtures import english_papers

UTC = datetime.timezone.utc


def at(day, hour=9, minute=0):
    return datetime.datetime(2026, 10, day, hour, minute, tzinfo=UTC)


class DueTests(unittest.TestCase):
    def test_never_refreshed_is_due_unless_manual(self):
        self.assertTrue(maintenance.refresh_due(None, "daily", at(5)))
        self.assertTrue(maintenance.refresh_due(None, "weekly", at(5)))
        self.assertFalse(maintenance.refresh_due(None, "manual", at(5)))

    def test_daily_means_once_per_local_calendar_day(self):
        last = at(5, 8).isoformat()
        self.assertFalse(maintenance.refresh_due(last, "daily", at(5, 23), tz=UTC))
        self.assertTrue(maintenance.refresh_due(last, "daily", at(6, 0, 1), tz=UTC))

    def test_weekly_means_seven_days(self):
        last = at(5, 8).isoformat()
        self.assertFalse(maintenance.refresh_due(last, "weekly", at(11, 23), tz=UTC))
        self.assertTrue(maintenance.refresh_due(last, "weekly", at(12, 8), tz=UTC))

    def test_a_garbled_or_future_timestamp_counts_as_due_not_as_a_crash(self):
        self.assertTrue(maintenance.refresh_due("not a date", "daily", at(5)))
        self.assertTrue(maintenance.refresh_due(at(20).isoformat(), "daily", at(5), tz=UTC))  # clock moved back

    def test_unknown_frequency_falls_back_to_daily(self):
        self.assertEqual(maintenance.normalize_frequency("hourly"), "daily")
        self.assertEqual(maintenance.normalize_frequency(None), "daily")
        self.assertEqual(maintenance.normalize_frequency("manual"), "manual")


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "harness").mkdir()
        (self.root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (self.root / "app").mkdir(exist_ok=True)
        (self.root / "app" / "budget.json").write_text((ROOT / "app" / "budget.json").read_text())
        self.app = App(root=str(self.root), data_dir=str(self.root / "data"))
        from recommendation_fixtures import legacy_recommendation_settings
        legacy_recommendation_settings(self.app, route_beta=False)
        self.addCleanup(self.app.store.close)
        self.pid = self.app.create_project("P", "manual", ["epitaxy"])["project_id"]
        self.add_papers(6)
        english_papers(self.app,self.pid)
        tz = mock.patch.object(maintenance, "LOCAL_TZ", UTC)   # the tests reason in UTC days
        tz.start()
        self.addCleanup(tz.stop)
        # nothing in this slice may ever reach a model
        patcher = mock.patch.object(self.app.gateway, "call", side_effect=AssertionError("maintenance must not call a model"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def add_papers(self, n, start=0):
        self.app.store.upsert_papers([
            {"key": f"p{start + i}", "title": f"epitaxy growth study {start + i}", "abstract": "epitaxy growth", "published": "2026-01-01", 'language':'en'}
            for i in range(n)], project_id=self.pid)

    def set_frequency(self, value):
        (self.app.data / "settings.json").write_text(json.dumps({"updateFrequency": value}))

    def refresher(self, added=3, errors=None, fetched=None):
        return mock.patch.object(self.app, "refresh_candidates",
                                 return_value={"fetched": added if fetched is None else fetched, "added": added, "field": added, "errors": errors or []})

    def batches(self):
        return self.app.store.conn.execute("SELECT COUNT(*) FROM batches WHERE project_id=?", (self.pid,)).fetchone()[0]


class RunTests(Fixture):
    def test_first_open_refreshes_and_builds_one_batch(self):
        with self.refresher() as refresh:
            result = maintenance.run(self.app, self.pid, at(5))
        refresh.assert_called_once()
        self.assertTrue(result["refreshed"] and result["batch"])
        self.assertEqual(self.batches(), 1)

    def test_opening_again_the_same_day_does_nothing(self):
        with self.refresher() as refresh:
            maintenance.run(self.app, self.pid, at(5, 8))
            again = maintenance.run(self.app, self.pid, at(5, 20))
        self.assertEqual(refresh.call_count, 1)
        self.assertFalse(again["refreshed"] or again["batch"])
        self.assertEqual(self.batches(), 1)

    def test_a_long_absence_gives_one_refresh_and_one_batch_not_a_backlog(self):
        with self.refresher() as refresh:
            maintenance.run(self.app, self.pid, at(1))
            maintenance.run(self.app, self.pid, at(5))   # four days later
        self.assertEqual(refresh.call_count, 2)
        self.assertEqual(self.batches(), 2)               # day 1 and day 5; the days between are not made up

    def test_manual_frequency_does_nothing_at_all(self):
        self.set_frequency("manual")
        with self.refresher() as refresh:
            result = maintenance.run(self.app, self.pid, at(5))
        refresh.assert_not_called()
        self.assertEqual((result["refreshed"], result["batch"], self.batches()), (False, False, 0))

    def test_no_unseen_papers_means_no_empty_batch(self):
        self.app.store.conn.execute("DELETE FROM project_papers WHERE project_id=?", (self.pid,))
        self.app.store.conn.commit()
        with self.refresher(added=0):
            result = maintenance.run(self.app, self.pid, at(5))
        self.assertFalse(result["batch"])
        self.assertEqual(self.batches(), 0)

    def test_a_failed_refresh_is_visible_not_recorded_as_done_and_does_not_block_the_batch(self):
        with self.refresher(added=0, fetched=0, errors=[{"query": "epitaxy", "kind": "unavailable", "error": "OpenAlex busy"}]):
            result = maintenance.run(self.app, self.pid, at(5, 8))
        status = maintenance.status(self.app, self.pid, at(5, 8))
        self.assertFalse(result["refreshed"])
        self.assertIsNone(status["last_refresh"])
        self.assertEqual(status["last_error"], "unavailable")   # the kind only: the provider's words and the URL go to the log
        self.assertTrue(result["batch"])  # the papers already in the project are still delivered

    def test_a_failed_refresh_is_not_hammered(self):
        with self.refresher(added=0, fetched=0, errors=[{"query": "q", "kind": "unavailable", "error": "busy"}]) as refresh:
            maintenance.run(self.app, self.pid, at(5, 8, 0))
            maintenance.run(self.app, self.pid, at(5, 8, 10))   # ten minutes later
            maintenance.run(self.app, self.pid, at(5, 9, 0))    # an hour later: allowed again
        self.assertEqual(refresh.call_count, 2)

    def test_a_refresh_that_raises_is_caught(self):
        with mock.patch.object(self.app, "refresh_candidates", side_effect=RuntimeError("boom")):
            result = maintenance.run(self.app, self.pid, at(5))
        self.assertFalse(result["refreshed"])
        self.assertEqual(maintenance.status(self.app, self.pid, at(5))["last_error"], "failed")

    def test_a_second_run_while_one_is_running_is_skipped(self):
        gate = threading.Event()
        release = threading.Event()

        def slow(**kw):
            gate.set()
            release.wait(5)
            return {"fetched": 1, "added": 1, "field": 1, "errors": []}
        results = []
        with mock.patch.object(self.app, "refresh_candidates", side_effect=slow):
            worker = threading.Thread(target=lambda: results.append(maintenance.run(self.app, self.pid, at(5))))
            worker.start()
            self.assertTrue(gate.wait(5))
            second = maintenance.run(self.app, self.pid, at(5))
            release.set()
            worker.join(5)
        self.assertEqual(second.get("skipped"), "already running")
        self.assertTrue(results[0]["refreshed"])

    def test_deleting_a_project_removes_its_maintenance_state(self):
        with self.refresher():
            maintenance.run(self.app, self.pid, at(5))
        self.app.projects.delete_project(self.pid)
        left = self.app.store.conn.execute("SELECT key FROM settings WHERE key LIKE ?", (f"%{self.pid}",)).fetchall()
        self.assertEqual([r["key"] for r in left], [])

    def test_projects_are_independent(self):
        other = self.app.create_project("Q", "manual", ["glass"])["project_id"]
        self.app.store.upsert_papers([{"key": "q0", "title": "glass study", "abstract": "glass", "published": "2026-01-01"}], project_id=other)
        english_papers(self.app,other)
        with self.refresher() as refresh:
            maintenance.run(self.app, self.pid, at(5))
            maintenance.run(self.app, other, at(5))
        self.assertEqual(refresh.call_count, 2)


class StatusTests(Fixture):
    def test_status_has_times_and_frequency_but_no_unread_or_backlog_counts(self):
        with self.refresher():
            maintenance.run(self.app, self.pid, at(5, 8))
        status = maintenance.status(self.app, self.pid, at(5, 9))
        self.assertEqual(status["frequency"], "daily")
        self.assertEqual(status["last_refresh"], at(5, 8).isoformat())
        for forbidden in ("unread", "backlog", "pending", "behind", "missed", "pool", "unseen"):
            self.assertFalse(any(forbidden in key for key in status), forbidden)

    def test_plan_is_computed_without_any_network(self):
        with mock.patch.object(self.app, "refresh_candidates", side_effect=AssertionError("planning must not fetch")):
            plan = maintenance.plan(self.app, self.pid, at(5))
        self.assertEqual((plan["refresh"], plan["batch"]), (True, True))

    def test_home_payload_includes_the_status(self):
        self.assertIn("maintenance", self.app.home_maintenance(self.pid))


class RouteAndPageTests(Fixture):
    def serve(self):
        httpd = server.build_server(port=0, root=str(self.root))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd.server_address[1]

    def post(self, port, body, origin=None):
        headers = {"Content-Type": "application/json", **({"Origin": origin} if origin else {})}
        request = urllib.request.Request(f"http://127.0.0.1:{port}/api/maintain", data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_route_reports_nothing_due_without_starting_a_job(self):
        self.set_frequency("manual")
        port = self.serve()
        # the server builds its own App on the same data directory
        with mock.patch.dict("os.environ", {"PAGETIDE_DATA": str(self.app.data)}):
            status, body = self.post(port, {"project_id": self.pid})
        self.assertEqual((status, body["due"]), (200, False))

    def test_route_starts_a_job_when_due(self):
        port = self.serve()
        with mock.patch.dict("os.environ", {"PAGETIDE_DATA": str(self.app.data)}), \
                mock.patch.object(maintenance, "run", return_value={"refreshed": True, "batch": True}):
            status, body = self.post(port, {"project_id": self.pid})
        self.assertEqual((status, body["due"]), (200, True))
        self.assertTrue(body["job"]["id"].startswith("job-"))

    def test_foreign_origin_is_refused(self):
        port = self.serve()
        status, _ = self.post(port, {"project_id": self.pid}, origin="http://evil.example")
        self.assertEqual(status, 403)

    def test_page_calls_maintain_at_start_and_never_triages(self):
        index = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
        self.assertIn("/api/maintain", index)
        body = index[index.index("async function autoMaintain"):]
        body = body[:body.index("\n}\n")]
        self.assertIn("r.status", body)   # a not-due answer still refreshes a stale page
        self.assertNotIn("triage", body.lower())
        self.assertNotIn("autoAi", body)


if __name__ == "__main__":
    unittest.main()
