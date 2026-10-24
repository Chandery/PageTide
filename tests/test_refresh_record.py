"""A successful refresh leaves a record (time, papers fetched, papers new to the project), and the counts are honest.

`added` counts only rows new to the shared papers table; a paper another project (or an earlier refresh) already stored is
linked to this project but is not `added`. Offline: the source is faked, no model is called.
"""
import datetime
import json
import sys
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import maintenance, server
import test_maintenance as tm
from recommendation_fixtures import SYNTHETIC_OA

at = tm.at


def found(*numbers):
    return [{"key": f"r{n}", "title": f"epitaxy refresh paper {n}", "abstract": "epitaxy growth of films", "published": "2026-01-02",
             "language": "en", "source": "openalex", "group_name": "field"} for n in numbers]


class StoreLinkTests(tm.Fixture):
    def test_upsert_reports_how_many_links_are_new_to_the_project(self):
        stats = {}
        added = self.app.store.upsert_papers(found(1, 2), project_id=self.pid, stats=stats)
        self.assertEqual((added, stats["linked"]), (2, 2))
        other = self.app.create_project("Q", "manual", ["glass"])["project_id"]
        stats = {}
        added = self.app.store.upsert_papers(found(1, 2, 3), project_id=other, stats=stats)
        self.assertEqual((added, stats["linked"]), (1, 3))      # r1, r2 already stored: linked to Q, not new to the library
        stats = {}
        added = self.app.store.upsert_papers(found(1, 2, 3), project_id=other, stats=stats)
        self.assertEqual((added, stats["linked"]), (0, 0))      # nothing new anywhere

    def test_add_project_paper_says_whether_the_link_is_new(self):
        self.assertTrue(self.app.store.add_project_paper(self.pid, "p0", "seed") is False)   # fixture papers are linked already
        other = self.app.create_project("Q", "manual", ["glass"])["project_id"]
        self.assertTrue(self.app.store.add_project_paper(other, "p0", "discovered"))
        self.assertFalse(self.app.store.add_project_paper(other, "p0", "discovered"))


class CountTests(tm.Fixture):
    def refresh(self, papers):
        with mock.patch.object(self.app.source, "discover_topic", return_value=papers), \
                mock.patch.object(self.app.source, "discover", side_effect=AssertionError("keywords are used")):
            return self.app.refresh_candidates(project_id=self.pid)

    def test_a_paper_stored_earlier_is_fetched_and_new_to_the_project_but_not_added(self):
        other = self.app.create_project("Q", "manual", ["glass"])["project_id"]
        self.app.store.upsert_papers(found(1), project_id=other)       # another project fetched r1 minutes ago
        first = self.refresh(found(1, 2))
        self.assertEqual((first["fetched"], first["added"], first["new_to_project"]), (2, 1, 2))
        again = self.refresh(found(1, 2))
        self.assertEqual((again["fetched"], again["added"], again["new_to_project"]), (2, 0, 0))

    def test_route_refresh_counts_the_same_way(self):
        route = {"revision": 1}
        stats_papers = found(7, 8)
        planned = {"queries": [{"query": "q", "order": "recent", "from_date": "2020-01-01", "to_date": "2026-10-01", "per_page": 50, "page": 1}],
                   "signature": "s"}
        self.app.store.upsert_papers(found(7), project_id=self.app.create_project("Q", "manual", ["glass"])["project_id"])
        with mock.patch.object(self.app, "_route_recall_plan", return_value=planned), \
                mock.patch.object(self.app, "_route_state", return_value=route), \
                mock.patch.object(self.app.source, "discover_topic", return_value=stats_papers), \
                mock.patch("app.service.route_recall.record", return_value={}):
            out = self.app._refresh_route_candidates(self.pid, route, None, 50)
        self.assertEqual((out["fetched"], out["added"], out["new_to_project"]), (2, 1, 2))


class RecordTests(tm.Fixture):
    def result(self, fetched=33, new=10, errors=None):
        return {"fetched": fetched, "added": new, "new_to_project": new, "field": fetched, "errors": errors or []}

    def run_with(self, result, now):
        with mock.patch.object(self.app, "refresh_candidates", return_value=result):
            return maintenance.run(self.app, self.pid, now)

    def test_an_automatic_refresh_records_time_and_counts(self):
        self.run_with(self.result(), at(5, 8))
        status = maintenance.status(self.app, self.pid)
        self.assertEqual(status["last_refresh"], at(5, 8).isoformat())
        self.assertEqual(status["last_refresh_result"], {"at": at(5, 8).isoformat(), "fetched": 33, "new_to_project": 10})

    def test_a_failed_refresh_keeps_the_last_success(self):
        self.run_with(self.result(), at(5, 8))
        self.run_with(self.result(0, 0, errors=[{"kind": "unavailable", "error": "busy"}]), at(6, 8))
        status = maintenance.status(self.app, self.pid)
        self.assertEqual(status["last_refresh_result"]["fetched"], 33)
        self.assertEqual(status["last_refresh"], at(5, 8).isoformat())

    def test_a_partial_failure_with_papers_counts_as_success(self):
        self.run_with(self.result(4, 1, errors=[{"kind": "unavailable", "error": "busy"}]), at(5, 8))
        self.assertEqual(maintenance.status(self.app, self.pid)["last_refresh_result"]["fetched"], 4)

    def test_no_record_until_the_first_success(self):
        self.assertIsNone(maintenance.status(self.app, self.pid)["last_refresh_result"])

    def test_manual_refresh_records_and_moves_the_next_automatic_refresh(self):
        with mock.patch.object(self.app, "refresh_candidates", return_value=self.result(5, 0)):
            out = maintenance.manual_refresh(self.app, self.pid, now=at(5, 8), pages=1)
        self.assertEqual(out["fetched"], 5)
        status = maintenance.status(self.app, self.pid)
        self.assertEqual(status["last_refresh"], at(5, 8).isoformat())
        self.assertEqual(status["last_refresh_result"], {"at": at(5, 8).isoformat(), "fetched": 5, "new_to_project": 0})
        self.assertFalse(maintenance.plan(self.app, self.pid, at(5, 20))["refresh"])   # a manual fetch counts as the day's fetch

    def test_manual_refresh_failure_does_not_overwrite_the_success(self):
        self.run_with(self.result(), at(5, 8))
        with mock.patch.object(self.app, "refresh_candidates", return_value=self.result(0, 0, errors=[{"kind": "busy", "error": "x"}])):
            maintenance.manual_refresh(self.app, self.pid, now=at(5, 9))
        self.assertEqual(maintenance.status(self.app, self.pid)["last_refresh_result"]["fetched"], 33)

    def test_a_skipped_refresh_with_a_reason_code_is_not_recorded(self):
        with mock.patch.object(self.app, "refresh_candidates", return_value={"fetched": 0, "added": 0, "field": 0, "errors": [], "reason_code": "sources_disabled"}):
            maintenance.manual_refresh(self.app, self.pid, now=at(5, 9))
        self.assertIsNone(maintenance.status(self.app, self.pid)["last_refresh_result"])

    def test_deleting_the_project_clears_the_record(self):
        self.run_with(self.result(), at(5, 8))
        self.app.projects.delete_project(self.pid)
        left = self.app.store.conn.execute("SELECT key FROM settings WHERE key LIKE ?", (f"%{self.pid}",)).fetchall()
        self.assertEqual([r["key"] for r in left], [])


class GuardTests(tm.Fixture):
    ok = {"fetched": 5, "added": 1, "new_to_project": 2, "new_recommendable": 2, "field": 5, "errors": []}

    def test_a_manual_refresh_while_another_runs_is_refused_and_records_nothing(self):
        maintenance._RUNNING.add(self.pid)
        self.addCleanup(maintenance._RUNNING.discard, self.pid)
        with mock.patch.object(self.app, "refresh_candidates", side_effect=AssertionError("must not fetch twice")):
            out = maintenance.manual_refresh(self.app, self.pid, now=at(5, 8))
        self.assertEqual(out["reason_code"], "refresh_running")
        self.assertEqual((out["fetched"], out["new_to_project"]), (0, 0))
        status = maintenance.status(self.app, self.pid)
        self.assertIsNone(status["last_refresh_result"])
        self.assertIsNone(status["last_refresh"])

    def test_an_automatic_run_is_skipped_while_a_manual_refresh_runs_and_the_guard_is_released(self):
        seen = []

        def slow(**kw):
            seen.append(maintenance.run(self.app, self.pid, at(5, 8)))
            return self.ok
        with mock.patch.object(self.app, "refresh_candidates", side_effect=slow):
            maintenance.manual_refresh(self.app, self.pid, now=at(5, 8))
        self.assertEqual(seen[0].get("skipped"), "already running")
        self.assertNotIn(self.pid, maintenance._RUNNING)
        with mock.patch.object(self.app, "refresh_candidates", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                maintenance.manual_refresh(self.app, self.pid)
        self.assertNotIn(self.pid, maintenance._RUNNING)

    def test_the_record_carries_the_completion_time_not_the_start_time(self):
        clock = [at(5, 8)]

        def slow(**kw):
            clock[0] = at(5, 8, 3)      # the fetch takes three minutes
            return self.ok
        with mock.patch.object(maintenance, "_now", side_effect=lambda n: n or clock[0]), \
                mock.patch.object(self.app, "refresh_candidates", side_effect=slow):
            maintenance.run(self.app, self.pid)
        self.assertEqual(maintenance.status(self.app, self.pid)["last_refresh_result"]["at"], at(5, 8, 3).isoformat())

    def test_an_experiment_run_with_distractors_is_not_recorded(self):
        with mock.patch.object(self.app, "refresh_candidates", return_value=self.ok):
            maintenance.manual_refresh(self.app, self.pid, now=at(5, 8), include_distractors=True)
        self.assertIsNone(maintenance.status(self.app, self.pid)["last_refresh_result"])

    def test_the_desktop_backend_fetches_nothing_on_its_own_at_start(self):
        # A first launch has no project to fetch for and no seed papers: no bootstrap refresh, so no unrecorded one either.
        source = (ROOT / "app" / "desktop.py").read_text(encoding="utf-8")
        self.assertNotIn("manual_refresh(", source)
        self.assertNotIn("refresh_candidates(", source)
        self.assertNotIn("ensure_seed_papers", source)


class RecommendableTests(tm.Fixture):
    def refresh(self, papers):
        with mock.patch.object(self.app.source, "discover_topic", return_value=papers), \
                mock.patch.object(self.app.source, "discover", side_effect=AssertionError("keywords are used")):
            return self.app.refresh_candidates(project_id=self.pid)

    def test_only_papers_the_next_batch_could_show_count(self):
        readable = {**found(1)[0], "oa": SYNTHETIC_OA}
        no_pdf = found(2)[0]                                  # new to the project but no PDF source: never recommended
        chinese = {**found(3)[0], "language": "zh", "oa": SYNTHETIC_OA}   # outside the project's paper language
        out = self.refresh([readable, no_pdf, chinese])
        self.assertEqual((out["fetched"], out["new_to_project"]), (3, 3))
        self.assertEqual(out["new_recommendable"], 1)

    def test_a_seed_and_a_paper_already_rated_do_not_count(self):
        self.refresh([{**found(4)[0], "oa": SYNTHETIC_OA}])
        self.app.record_feedback("r4", "useful", None, self.pid)
        self.app.store.conn.execute("DELETE FROM project_papers WHERE project_id=? AND paper_key='r4'", (self.pid,))
        self.app.store.conn.commit()
        out = self.refresh([{**found(4)[0], "oa": SYNTHETIC_OA}])
        self.assertEqual((out["new_to_project"], out["new_recommendable"]), (1, 0))

    def test_nothing_linked_means_zero(self):
        self.refresh([{**found(5)[0], "oa": SYNTHETIC_OA}])
        out = self.refresh([{**found(5)[0], "oa": SYNTHETIC_OA}])
        self.assertEqual((out["new_to_project"], out["new_recommendable"]), (0, 0))

    def test_the_batch_selection_and_the_count_share_one_rule(self):
        out = self.refresh([{**found(6)[0], "oa": SYNTHETIC_OA}])
        self.assertEqual(out["new_recommendable"], 1)
        batch = self.app.build_batch(limit=20, project_id=self.pid)
        self.assertIn("r6", [c["key"] for c in batch["cards"]])


class BatchTodayTests(tm.Fixture):
    def test_status_says_whether_today_already_has_a_batch(self):
        self.assertFalse(maintenance.status(self.app, self.pid, at(5, 8))["batch_today"])
        with mock.patch.object(self.app, "refresh_candidates", return_value={"fetched": 1, "added": 1, "new_to_project": 1, "field": 1, "errors": []}):
            maintenance.run(self.app, self.pid, at(5, 8))
        self.assertTrue(maintenance.status(self.app, self.pid, at(5, 9))["batch_today"])
        self.assertFalse(maintenance.status(self.app, self.pid, at(6, 9))["batch_today"])


class ManualRouteTests(tm.Fixture):
    def test_api_refresh_records_the_success(self):
        httpd = server.build_server(port=0, root=str(self.root))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        port = httpd.server_address[1]

        def call(path, body=None):
            request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode() if body is not None else None,
                                             headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=5) as response:
                return json.loads(response.read())
        fake = {"fetched": 9, "added": 3, "new_to_project": 2, "field": 9, "errors": []}
        with mock.patch.dict("os.environ", {"PAPERDIGHELPER_DATA": str(self.app.data)}), \
                mock.patch("app.service.App.refresh_candidates", return_value=fake):
            job = call("/api/refresh", {"pages": 1, "project_id": self.pid})
            for _ in range(50):
                state = call(f"/api/jobs/{job['id']}")
                if state["state"] != "running":
                    break
                time.sleep(0.1)
            home = call(f"/api/home?project_id={self.pid}")
        self.assertEqual(state["state"], "done")
        record = home["maintenance"]["last_refresh_result"]
        self.assertEqual((record["fetched"], record["new_to_project"]), (9, 2))


if __name__ == "__main__":
    unittest.main()
