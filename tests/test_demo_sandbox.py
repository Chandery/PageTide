"""The onboarding tour's demo project: a disposable offline sandbox that never touches the person's data."""
import http.client
import json
import os
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from app import demo, demo_fixture as fixture, server
from app.gateway import Gateway

ROOT = Path(__file__).resolve().parents[1]
REAL_TABLES = ("projects", "papers", "feedback", "summaries", "batches", "exposures", "settings", "profile_versions",
               "library", "project_library", "project_papers", "org_events", "org_projects")
_REAL_CONNECT = socket.socket.connect


def _loopback_only(self, address, *args, **kwargs):
    host = address[0] if isinstance(address, tuple) else address
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise RuntimeError("Test prohibits outbound network: %r" % (address,))
    return _REAL_CONNECT(self, address, *args, **kwargs)


class DemoCase(unittest.TestCase):
    """A server over a data directory that already holds one real project, with the network and the model shut."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "harness").mkdir()
        (self.root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        self.data = self.root / "data"
        for patcher in (mock.patch.dict(os.environ, {"PAGETIDE_DATA": str(self.data), "DEEPSEEK_API_KEY": "x"}),
                        mock.patch.object(socket.socket, "connect", _loopback_only),
                        mock.patch.object(Gateway, "call", side_effect=AssertionError("the demo must not call a model")),
                        mock.patch.object(Gateway, "_call", side_effect=AssertionError("the demo must not call a model"))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.real = server.make_app(str(self.root))
        self.real_pid = self.real.projects.create_project("My real project", "manual", ["epitaxy"],
                                                          language_policy={"allowed_languages": ["en"]})
        self.real.store.upsert_papers([{"key": "real-paper", "title": "Epitaxy study", "abstract": "epitaxy growth",
                                        "published": "2026-01-01"}], self.real_pid)
        self.real.store.save_to_library("real-paper", project_id=self.real_pid)
        self.real.store.conn.commit()
        self.real.store.close()
        (self.data / "settings.json").write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
        self.httpd = server.build_server(port=0, root=str(self.root))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.port = self.httpd.server_address[1]
        demo._PROCESS_RESET["done"] = False

    # ------------------------------------------------------------------ helpers
    def call(self, method, path, body=None, header=True, conn=None):
        own = conn is None
        conn = conn or http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        headers = {"Content-Type": "application/json"}
        if header:
            headers[demo.HEADER] = "1"
        try:
            conn.request(method, path, body=None if body is None else json.dumps(body).encode(), headers=headers)
            response = conn.getresponse()
            raw = response.read()
            try:
                return response.status, json.loads(raw)
            except ValueError:
                return response.status, raw
        finally:
            if own:
                conn.close()

    def real_counts(self):
        db = sqlite3.connect(str(self.data / "pagetide.sqlite"))
        try:
            return {t: db.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0] for t in REAL_TABLES
                    if db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone()}
        finally:
            db.close()

    def start(self):
        status, payload = self.call("POST", "/api/onboarding", {"action": "start"}, header=False)
        self.assertEqual(status, 200, payload)
        return payload

    def wait_job(self, job_id):
        for _ in range(200):
            status, job = self.call("GET", "/api/jobs/" + job_id)
            if job.get("state") != "running":
                return job
            time.sleep(0.15)
        self.fail("job did not finish")


class DemoFlowTests(DemoCase):
    def test_the_whole_tour_flow_works_offline_and_leaves_the_real_data_alone(self):
        before_counts, before_settings = self.real_counts(), (self.data / "settings.json").read_bytes()
        self.start()
        # recommendations: today's five, ranked locally
        status, daily = self.call("POST", "/api/daily", {"project_id": demo.PROJECT_ID})
        self.assertEqual(status, 200, daily)
        self.assertEqual(len(daily["cards"]), 5)
        self.assertEqual({c["title"] for c in daily["cards"]},
                         {p["title"] for p in fixture.candidates()})
        # previews: pre-written, model="demo", in the person's interface language
        status, tri = self.call("POST", "/api/triage", {"project_id": demo.PROJECT_ID})
        self.assertEqual((status, tri["ok"], tri["mode"]), (200, True, "demo"), tri)
        self.assertEqual(len(tri["items"]), 5)
        self.assertEqual(set(tri["items"][0]), {"paper_id", "one_liner", "why_relevant", "caution"})
        status, home = self.call("GET", "/api/home?project_id=" + demo.PROJECT_ID)
        self.assertEqual({s["model"] for k, s in home["summaries"].items() if k in {i["paper_id"] for i in tri["items"]}}, {"demo"})
        self.assertTrue(all(i["caution"].strip() for i in tri["items"]))
        # rate the first card
        first = daily["cards"][0]["key"]
        status, fb = self.call("POST", "/api/feedback", {"key": first, "action": "useful", "project_id": demo.PROJECT_ID})
        self.assertEqual((status, fb["saved"]), (200, True), fb)
        # the library holds only demo papers: 22 pre-saved + the one just saved
        status, org = self.call("GET", "/api/organization")
        self.assertEqual(status, 200)
        keys = {item["key"] for item in org["items"]}
        self.assertEqual(len(keys), 23)
        self.assertTrue(keys <= {fixture.key_of(p) for p in fixture.PAPERS})
        self.assertNotIn("real-paper", keys)
        self.assertEqual(len(org["directions"]), 4)
        # the graph is built by the real offline worker on the sandbox library and has edges
        status, started = self.call("POST", "/api/organization", {"op": "graph"})
        self.assertEqual(status, 200, started)
        job = self.wait_job(started["job"]["id"])
        self.assertEqual(job["state"], "done", job.get("error"))
        relations = job["result"]["relations"]
        self.assertGreaterEqual(len(relations["edges"]), 20)   # the demo paraphrases are written to keep the directions connected
        self.assertGreaterEqual(len([g for g in relations["groups"] if len(g["keys"]) > 1]), 4)
        # profile, insights, weekly
        status, insights = self.call("GET", "/api/profile/insights?project_id=" + demo.PROJECT_ID)
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(insights["keyword_distribution"]), 10)
        weekly = insights["weekly_change"]
        self.assertTrue(weekly["comparable"])
        self.assertGreater(weekly["stats"]["activity"], 0)
        self.assertGreater(weekly["previous_stats"]["activity"], 0)
        self.assertTrue(any(weekly["keyword_changes"].values()))
        self.assertGreaterEqual(len(insights["versions"]), 3)
        status, report = self.call("GET", "/api/weekly_report?project_id=" + demo.PROJECT_ID)
        self.assertEqual(status, 200)
        self.assertTrue(report["has_activity"])
        self.assertGreaterEqual(len(report["directions"]), 3)
        status, profile = self.call("GET", "/api/profile?project_id=" + demo.PROJECT_ID)
        self.assertEqual(profile["profile"]["pinned_terms"], fixture.KEYWORDS)
        # undo and unsave work inside the sandbox
        self.assertEqual(self.call("POST", "/api/undo", {"feedback_id": fb["feedback_id"], "project_id": demo.PROJECT_ID})[0], 200)
        self.assertEqual(self.call("POST", "/api/unsave", {"key": first, "project_id": demo.PROJECT_ID})[0], 200)
        # nothing of it reached the person's data
        self.assertEqual(self.real_counts(), before_counts)
        self.assertEqual((self.data / "settings.json").read_bytes(), before_settings)
        status, real_org = self.call("GET", "/api/organization", header=False)
        self.assertEqual([i["key"] for i in real_org["items"]], ["real-paper"])
        status, projects = self.call("GET", "/api/projects", header=False)
        self.assertEqual([p["id"] for p in projects["projects"]], [self.real_pid])
        self.assertEqual(projects["demo"]["id"], demo.PROJECT_ID)

    def test_saved_demo_library_numbers_meet_the_floor(self):
        self.start()
        status, lib = self.call("GET", "/api/library?project_id=" + demo.PROJECT_ID)
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(lib["items"]), 20)
        self.assertGreaterEqual(lib["stats"]["negative"], 1)
        self.assertGreaterEqual(lib["stats"]["too_hard"], 1)
        self.assertGreaterEqual(lib["stats"]["understood"], 1)

    def test_previews_follow_the_real_interface_language(self):
        (self.data / "settings.json").write_text(json.dumps({"language": "en-US"}), encoding="utf-8")
        self.start()
        self.call("POST", "/api/daily", {"project_id": demo.PROJECT_ID})
        status, tri = self.call("POST", "/api/triage", {})
        text = " ".join(i["one_liner"] + i["why_relevant"] + i["caution"] for i in tri["items"])
        self.assertFalse(any("一" <= ch <= "鿿" for ch in text))
        status, projects = self.call("GET", "/api/projects", header=False)
        self.assertEqual(projects["demo"]["name"], "Demo project")
        status, blocked = self.call("POST", "/api/refresh", {})
        self.assertEqual(status, 403)
        self.assertIn("demo project", blocked["error"])

    def test_welcome_card_saves_language_without_wiping_other_settings_and_the_sandbox_follows_it(self):
        (self.data / "settings.json").write_text(json.dumps({"theme": "dark", "recommendCount": 7}), encoding="utf-8")
        status, _ = self.call("POST", "/api/user_settings", {"settings": {"language": "en-US"}, "merge": True}, header=False)
        self.assertEqual(status, 200)
        saved = json.loads((self.data / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual((saved["language"], saved["theme"], saved["recommendCount"]), ("en-US", "dark", 7))
        status, _ = self.call("POST", "/api/user_settings", {"settings": {"theme": "light"}, "merge": True}, header=False)
        saved = json.loads((self.data / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual((saved["language"], saved["theme"], saved["recommendCount"]), ("en-US", "light", 7))
        self.start()   # the tour's start comes after the save, so the sandbox is built in English
        status, projects = self.call("GET", "/api/projects", header=False)
        self.assertEqual(projects["demo"]["name"], "Demo project")
        generation = demo.current_generation(str(self.data))[0]
        dump = "\n".join(sqlite3.connect(str(demo.sandbox_root(self.data) / generation / "pagetide.sqlite")).iterdump())
        name = fixture.DIRECTIONS[0]["name"]
        self.assertIn(name["en"], dump)
        self.assertNotIn(name["zh"], dump)

    def test_marks_survive_a_reload_and_pressing_again_takes_them_back_in_the_demo(self):
        self.start()
        pid = demo.PROJECT_ID
        status, daily = self.call("POST", "/api/daily", {"project_id": pid})
        key = daily["cards"][0]["key"]
        other = daily["cards"][1]["key"]
        self.assertTrue(all({"feedback", "feedback_id", "familiarity"} <= set(c) for c in daily["cards"]))
        status, home = self.call("GET", "/api/home?project_id=" + pid)
        card = next(c for c in home["cards"] if c["key"] == key)
        self.assertEqual((card["feedback"], card["feedback_id"], card["familiarity"]), (None, None, None))
        before = self.call("GET", "/api/library?project_id=" + pid)[1]["stats"]

        status, marked = self.call("POST", "/api/feedback", {"key": key, "action": "irrelevant", "project_id": pid})
        self.assertEqual(status, 200)
        self.assertEqual(marked["state"]["feedback"], "irrelevant")
        self.assertEqual(marked["state"]["feedback_id"], marked["feedback_id"])
        status, _ = self.call("POST", "/api/feedback", {"key": key, "action": "too_hard", "project_id": pid})
        self.assertEqual(status, 200)
        # a reload (a fresh /api/home) carries both marks, each on its own
        for payload in (self.call("GET", "/api/home?project_id=" + pid)[1],):
            card = next(c for c in payload["cards"] if c["key"] == key)
            self.assertEqual((card["feedback"], card["familiarity"]), ("irrelevant", "too_hard"), payload.get("batch_id"))
            self.assertEqual(card["feedback_id"], marked["feedback_id"])
            untouched = next(c for c in payload["cards"] if c["key"] == other)
            self.assertEqual((untouched["feedback"], untouched["familiarity"]), (None, None))
        after = self.call("GET", "/api/library?project_id=" + pid)[1]["stats"]
        self.assertEqual((after["negative"], after["too_hard"]), (before["negative"] + 1, before["too_hard"] + 1))

        # pressing "not interested" again: undo that record (the route is on the demo allow list); the profile follows
        status, undone = self.call("POST", "/api/undo", {"feedback_id": marked["feedback_id"], "project_id": pid})
        self.assertEqual(status, 200, undone)
        self.assertEqual((undone["state"]["feedback"], undone["state"]["familiarity"]), (None, "too_hard"))
        status, retracted = self.call("POST", "/api/feedback", {"key": key, "action": "too_hard", "retract": True, "project_id": pid})
        self.assertEqual(status, 200, retracted)
        self.assertEqual((retracted["state"]["feedback"], retracted["state"]["familiarity"]), (None, None))
        card = next(c for c in self.call("GET", "/api/home?project_id=" + pid)[1]["cards"] if c["key"] == key)
        self.assertEqual((card["feedback"], card["feedback_id"], card["familiarity"]), (None, None, None))
        final = self.call("GET", "/api/library?project_id=" + pid)[1]["stats"]
        self.assertEqual((final["negative"], final["too_hard"]), (before["negative"], before["too_hard"]))

    def test_an_undo_brings_back_the_older_interest_label_and_reports_it(self):
        self.start()
        pid = demo.PROJECT_ID
        key = self.call("POST", "/api/daily", {"project_id": pid})[1]["cards"][0]["key"]
        _, useful = self.call("POST", "/api/feedback", {"key": key, "action": "useful", "project_id": pid})
        self.assertEqual((useful["state"]["feedback"], useful["state"]["saved"]), ("useful", True))
        _, no = self.call("POST", "/api/feedback", {"key": key, "action": "irrelevant", "project_id": pid})
        self.assertEqual(no["state"]["feedback"], "irrelevant")
        _, back = self.call("POST", "/api/undo", {"feedback_id": no["feedback_id"], "project_id": pid})
        self.assertEqual((back["state"]["feedback"], back["state"]["feedback_id"]), ("useful", useful["feedback_id"]))
        status, bad = self.call("POST", "/api/undo", {"feedback_id": 10**9, "project_id": pid})
        self.assertEqual(status, 400)

    def _saved_keys(self, pid, header):
        return {i["key"] for i in self.call("GET", "/api/library?project_id=" + pid, header=header)[1]["items"]}

    def _round_trip(self, pid, key, header):
        """Saved, then not interested (leaves the library in the same call), then undone (back as saved, same time and note)."""
        self.assertIn(key, self._saved_keys(pid, header))
        saved_at = [i for i in self.call("GET", "/api/library?project_id=" + pid, header=header)[1]["items"] if i["key"] == key][0].get("saved_at")
        status, no = self.call("POST", "/api/feedback", {"key": key, "action": "irrelevant", "project_id": pid}, header=header)
        self.assertEqual(status, 200, no)
        self.assertTrue(no["unsaved"])
        self.assertEqual((no["state"]["feedback"], no["state"]["saved"]), ("irrelevant", False))
        self.assertNotIn(key, self._saved_keys(pid, header))
        status, back = self.call("POST", "/api/undo", {"feedback_id": no["feedback_id"], "project_id": pid}, header=header)
        self.assertEqual(status, 200, back)
        self.assertTrue(back["restored_saved"])
        self.assertEqual(back["state"]["saved"], True)
        self.assertIn(key, self._saved_keys(pid, header))
        items = self.call("GET", "/api/library?project_id=" + pid, header=header)[1]["items"]
        self.assertEqual([i for i in items if i["key"] == key][0].get("saved_at"), saved_at)
        # undoing twice or a label that took nothing out changes nothing
        status, again = self.call("POST", "/api/undo", {"feedback_id": no["feedback_id"], "project_id": pid}, header=header)
        self.assertFalse(again["restored_saved"])
        _, plain = self.call("POST", "/api/feedback", {"key": key, "action": "too_hard", "project_id": pid}, header=header)
        self.assertNotIn("unsaved", plain)

    def test_undoing_not_interested_puts_a_saved_paper_back_in_the_real_library(self):
        self._round_trip(self.real_pid, "real-paper", header=False)

    def test_undoing_not_interested_puts_a_saved_paper_back_in_the_demo_library(self):
        self.start()
        pid = demo.PROJECT_ID
        key = sorted(self._saved_keys(pid, True))[0]
        self._round_trip(pid, key, header=True)

    def test_triage_of_selected_keys_rejects_others(self):
        self.start()
        self.call("POST", "/api/daily", {"project_id": demo.PROJECT_ID})
        status, out = self.call("POST", "/api/triage", {"keys": ["https://doi.org/10.48550/arxiv.1907.11692"]})
        self.assertEqual(status, 400)
        status, out = self.call("POST", "/api/triage", {"keys": []})
        self.assertEqual(status, 400)

    def test_descriptor_matches_the_sandbox_project_row(self):
        self.start()
        app = demo.open_app(str(self.root), str(self.data))
        try:
            row = app.projects.get_project(demo.PROJECT_ID)
        finally:
            app.store.close()
        described = demo.descriptor(False)
        for field in ("id", "name", "keywords", "language_policy", "creation_mode", "decay_window_days", "goal_confirmation"):
            self.assertEqual(described[field], row[field], field)
        self.assertIs(described["demo"], True)

    def test_the_demo_project_is_ready_for_recommendations_and_unrated_candidates_are_exactly_five(self):
        self.start()
        app = demo.open_app(str(self.root), str(self.data))
        try:
            self.assertEqual(app.projects.get_project(demo.PROJECT_ID)["language_policy"]["status"], "ready")
            self.assertEqual(len(fixture.candidates()), 5)
            self.assertGreaterEqual(len(fixture.history()), 20)
            for paper in fixture.PAPERS:
                self.assertIn(paper["arxiv_id"], fixture.PREVIEWS)
                for lang in ("zh", "en"):
                    preview = fixture.PREVIEWS[paper["arxiv_id"]][lang]
                    self.assertTrue(all(preview[f].strip() for f in ("one_liner", "why_relevant", "caution")))
            self.assertEqual(app.stats(demo.PROJECT_ID)["saved"], 22)
        finally:
            app.store.close()


class DemoBlockedTests(DemoCase):
    def test_every_action_outside_the_allow_list_is_403_with_the_demo_reason(self):
        self.start()
        before = self.real_counts()
        key = fixture.key_of(fixture.candidates()[0])
        blocked = [
            ("POST", "/api/refresh", {}), ("POST", "/api/pdf/prepare", {"key": key}), ("POST", "/api/pdf", {"key": key}),
            ("POST", "/api/qa", {"key": key, "question": "q"}), ("POST", "/api/qa/session", {"key": key}),
            ("POST", "/api/translate", {"text": "x"}), ("POST", "/api/pin", {"terms": "x"}),
            ("POST", "/api/profile/freeze", {"frozen": True}), ("POST", "/api/profile/restore", {}),
            ("POST", "/api/projects", {"name": "x"}), ("POST", "/api/projects/" + demo.PROJECT_ID, {"action": "rename", "name": "x"}),
            ("DELETE", "/api/projects/" + demo.PROJECT_ID, None), ("DELETE", "/api/project-papers", {"project_id": demo.PROJECT_ID, "paper_key": key}),
            ("POST", "/api/project-papers", {"project_id": demo.PROJECT_ID, "paper_key": key}),
            ("POST", "/api/route", {"action": "save", "project_id": demo.PROJECT_ID}),
            ("POST", "/api/weekly_report/analysis", {"project_id": demo.PROJECT_ID}),
            ("POST", "/api/organization", {"op": "export"}), ("POST", "/api/organization", {"op": "note", "key": key, "text": "x"}),
            ("POST", "/api/organization", {"op": "review-categories"}), ("POST", "/api/organization", {"op": "suggest"}),
            ("POST", "/api/organization", {"op": "direction-save", "name": "x", "color": "#112233"}),
            ("POST", "/api/organization", {"op": "membership", "keys": [key], "add": []}),
            ("POST", "/api/import/batches", {"project_id": demo.PROJECT_ID, "source": "files"}),
            ("POST", "/api/seeds/pdf", None), ("POST", "/api/seeds/resolve", {"input": "x"}), ("POST", "/api/seeds/search", {"query": "x"}),
            ("POST", "/api/project-guidance/sessions", {"name": "x", "goal": "y"}), ("POST", "/api/fulltext", {"key": key, "pages": []}),
            ("GET", "/api/pdf/view?key=" + key, None), ("GET", "/api/figure-page?key=" + key, None),
        ]
        for method, path, body in blocked:
            status, payload = self.call(method, path, body)
            self.assertEqual(status, 403, (method, path, payload))
            self.assertEqual(payload["reason_code"], "demo_readonly", (method, path))
            self.assertIn("演示项目里不能这样做", payload["error"])
        self.assertEqual(self.real_counts(), before)

    def test_the_project_id_alone_also_routes_to_the_demo_and_is_checked(self):
        self.start()
        status, payload = self.call("POST", "/api/pin", {"terms": "x", "project_id": demo.PROJECT_ID}, header=False)
        self.assertEqual((status, payload["reason_code"]), (403, "demo_readonly"))
        status, payload = self.call("GET", "/api/library?project_id=" + demo.PROJECT_ID, header=False)
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(payload["items"]), 20)
        # the real database has no such project
        status, payload = self.call("GET", "/api/library?project_id=nope", header=False)
        self.assertEqual(status, 404)

    def test_settings_class_routes_ignore_the_demo_header_and_use_the_real_directory(self):
        self.start()
        status, out = self.call("POST", "/api/user_settings", {"settings": {"theme": "light"}, "merge": True})
        self.assertEqual((status, out), (200, {"status": "saved"}))
        self.assertEqual(json.loads((self.data / "settings.json").read_text())["theme"], "light")
        self.assertEqual(self.call("GET", "/api/settings")[0], 200)
        self.assertEqual(self.call("GET", "/api/data-location")[0], 200)
        self.assertEqual(self.call("GET", "/api/onboarding")[1]["project_count"], 1)
        self.assertEqual(self.call("GET", "/i18n/current.js")[0], 200)
        self.assertEqual(self.call("GET", "/")[0], 200)

    def test_the_demo_cannot_use_the_model_or_the_network(self):
        self.start()
        app = demo.open_app(str(self.root), str(self.data))
        try:
            with self.assertRaises(demo.DemoBlocked):
                app.gateway.call("daily_triage", [])
            with self.assertRaises(demo.DemoBlocked):
                app.gateway.save_key("k")
            with self.assertRaises(demo.DemoBlocked):
                app.gateway.set_enabled(True)
            self.assertIn("configured", app.gateway.provider_status())   # read-only status still works
            from app.sources import SourceError
            with self.assertRaises(SourceError):
                app.source.discover_topic("x")
            with self.assertRaises(SourceError):
                app.pdf_fetcher.fetch("https://example.org/a.pdf", "a")
            with self.assertRaises(RuntimeError):
                socket.create_connection(("93.184.216.34", 80), timeout=1)
        finally:
            app.store.close()

    def test_maintain_in_the_demo_never_fetches(self):
        self.start()
        status, out = self.call("POST", "/api/maintain", {"project_id": demo.PROJECT_ID})
        self.assertEqual((status, out["due"]), (200, False))

    def test_project_creation_ids_are_reserved(self):
        from app.project import ProjectManager
        app = server.make_app(str(self.root))
        try:
            with self.assertRaises(ValueError):
                app.projects.create_project("x", project_id=demo.PROJECT_ID)
            with self.assertRaises(ValueError):
                app.projects.create_project("x", project_id="anything", _demo=True)
            self.assertEqual(len(app.projects.list_projects()), 1)
            status, made = self.call("POST", "/api/projects", {"name": "Mine", "project_id": demo.PROJECT_ID}, header=False)
            self.assertNotEqual(made.get("project_id"), demo.PROJECT_ID)
        finally:
            app.store.close()


class SandboxLifecycleTests(DemoCase):
    def test_start_builds_a_new_generation_and_removes_the_old_one(self):
        self.start()
        first = demo.current_generation(str(self.data))[0]
        self.start()
        second = demo.current_generation(str(self.data))[0]
        self.assertNotEqual(first, second)
        names = {p.name for p in demo.sandbox_root(self.data).iterdir()}
        self.assertEqual(names, {second, demo.POINTER})

    def test_a_reset_discards_what_the_person_did_in_the_demo(self):
        self.start()
        self.call("POST", "/api/daily", {"project_id": demo.PROJECT_ID})
        status, home = self.call("GET", "/api/home?project_id=" + demo.PROJECT_ID)
        self.assertEqual(len(home["cards"]), 5)
        self.start()
        status, home = self.call("GET", "/api/home?project_id=" + demo.PROJECT_ID)
        self.assertEqual(home["cards"], [])

    def test_an_old_generation_that_cannot_be_deleted_is_left_and_not_an_error(self):
        self.start()
        first = demo.current_generation(str(self.data))[0]
        with mock.patch.object(demo.shutil, "rmtree", lambda *a, **k: None):
            self.start()
        self.assertTrue((demo.sandbox_root(self.data) / first).is_dir())
        self.start()   # the next reset cleans up what was left
        self.assertFalse((demo.sandbox_root(self.data) / first).exists())

    def test_the_first_use_in_a_process_resets_and_a_changed_fixture_rebuilds(self):
        self.start()
        first = demo.current_generation(str(self.data))[0]
        app = demo.open_app(str(self.root), str(self.data)); app.store.close()
        self.assertEqual(demo.current_generation(str(self.data))[0], first)   # reused within the process
        demo._PROCESS_RESET["done"] = False   # a new process
        app = demo.open_app(str(self.root), str(self.data)); app.store.close()
        second = demo.current_generation(str(self.data))[0]
        self.assertNotEqual(first, second)
        with mock.patch.object(fixture, "DIGEST", "changed"):
            app = demo.open_app(str(self.root), str(self.data)); app.store.close()
        self.assertNotEqual(demo.current_generation(str(self.data))[0], second)

    def test_reads_stay_safe_while_the_sandbox_is_reset(self):
        self.start()
        errors, stop = [], threading.Event()

        def reader():
            while not stop.is_set():
                try:
                    status, out = self.call("GET", "/api/library?project_id=" + demo.PROJECT_ID)
                    if status != 200:
                        errors.append((status, out))
                except Exception as exc:   # a reader must never see a half-built sandbox
                    errors.append(repr(exc))
        threads = [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        try:
            for _ in range(3):
                self.start()
        finally:
            stop.set()
            for t in threads:
                t.join(timeout=30)
        self.assertEqual(errors, [])

    def test_the_demo_flag_does_not_survive_on_a_kept_alive_connection(self):
        self.start()
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            status, demo_home = self.call("GET", "/api/home", conn=conn)
            self.assertEqual(demo_home["profile"]["project_id"], demo.PROJECT_ID)
            status, blocked = self.call("POST", "/api/pin", {"terms": "x"}, conn=conn)
            self.assertEqual(status, 403)
            status, real_home = self.call("GET", "/api/home", header=False, conn=conn)
            self.assertEqual(real_home["profile"]["project_id"], self.real_pid)
            status, projects = self.call("GET", "/api/projects", header=False, conn=conn)
            self.assertEqual([p["id"] for p in projects["projects"]], [self.real_pid])
            status, dropped = self.call("POST", "/api/refresh", {"x": "y" * 5000}, conn=conn)   # a refused body is drained
            self.assertEqual(status, 403)
            status, real_home = self.call("GET", "/api/home", header=False, conn=conn)
            self.assertEqual(real_home["profile"]["project_id"], self.real_pid)
        finally:
            conn.close()

    def test_cross_origin_onboarding_writes_are_refused(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/api/onboarding", body=b'{"action":"start"}',
                         headers={"Content-Type": "application/json", "Origin": "http://evil.example"})
            response = conn.getresponse()
            response.read()
            self.assertEqual(response.status, 403)
        finally:
            conn.close()
        self.assertIsNone(demo.current_generation(str(self.data)))


if __name__ == "__main__":
    unittest.main()
