"""Route Mode slice 4: the map is stored per project in the knowledge-base record and its progress comes from feedback.

Reuses Organization's revision check, undo log and backups; the map block rides along in the same JSON.
"""
import json
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
from app import pathgraph as pg
from app import server
from app.organization import Conflict, Organization
from app.service import App

PLAN = {"concepts": [
    {"id": "a", "name": "Crystal basics", "terms": ["crystal growth", "lattice"], "hint": 1, "needs": []},
    {"id": "b", "name": "Epitaxy", "terms": ["epitaxy", "epitaxial"], "hint": 2, "needs": ["a"]},
    {"id": "c", "name": "MBE", "terms": ["molecular beam epitaxy"], "hint": 3, "needs": ["b"]}], "targets": ["c"]}


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "harness").mkdir()
        (self.root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (self.root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        self.app = App(root=str(self.root), data_dir=str(self.root / "data"))
        self.addCleanup(self.app.store.close)
        self.pid = self.app.create_project("Crystals", "manual", ["epitaxy"])["project_id"]
        self.other = self.app.create_project("Poetry", "manual", ["poetry"])["project_id"]

    def add(self, key, title, abstract="", pid=None, published="2026-01-01"):
        self.app.store.upsert_papers([{"key": key, "title": title, "abstract": abstract, "published": published}], project_id=pid or self.pid)

    def ids(self, route=None):
        route = route or self.app.route_get(self.pid)
        return {c["name"]: c["id"] for c in route["graph"]["concepts"]}


class StoreTests(Fixture):
    def test_a_project_has_no_route_until_one_is_saved(self):
        empty = self.app.route_get(self.pid)
        self.assertEqual((empty["enabled"], empty["mode"], empty["graph"]), (False, "off", None))
        self.assertEqual(empty["revision"], 0)   # a first save can be guarded against another window saving first

    def test_saving_a_plan_normalises_stores_and_survives_a_restart(self):
        saved = self.app.route_save(self.pid, plan=PLAN)
        self.assertTrue(saved["enabled"])
        self.assertEqual(sorted(self.ids(saved)), ["Crystal basics", "Epitaxy", "MBE"])
        again = App(root=str(self.root), data_dir=str(self.root / "data"))
        self.addCleanup(again.store.close)
        self.assertEqual(again.route_get(self.pid)["graph"], saved["graph"])

    def test_a_broken_structured_graph_is_refused_and_nothing_changes(self):
        saved = self.app.route_save(self.pid, plan=PLAN)
        bad = json.loads(json.dumps(saved["graph"]))
        bad["prereqs"].append({"from": bad["concepts"][2]["id"], "to": bad["concepts"][0]["id"]})
        with self.assertRaises(ValueError):
            self.app.route_save(self.pid, graph=bad)
        self.assertEqual(self.app.route_get(self.pid)["graph"], saved["graph"])
        self.assertEqual(self.app.route_get(self.pid)["revision"], saved["revision"])

    def test_a_stale_revision_is_a_conflict(self):
        first = self.app.route_save(self.pid, plan=PLAN)
        self.app.route_manual(self.pid, self.ids(first)["Epitaxy"], "demoted")
        with self.assertRaises(Conflict):
            self.app.route_save(self.pid, graph=first["graph"], revision=first["revision"])

    def test_manual_marks_are_stored_cleared_and_checked(self):
        route = self.app.route_save(self.pid, plan=PLAN)
        cid = self.ids(route)["Epitaxy"]
        self.assertEqual(self.app.route_manual(self.pid, cid, "mastered")["manual"], {cid: "mastered"})
        self.assertEqual(self.app.route_manual(self.pid, cid, None)["manual"], {})
        with self.assertRaises(ValueError):
            self.app.route_manual(self.pid, "nope", "mastered")
        with self.assertRaises(ValueError):
            self.app.route_manual(self.pid, cid, "disliked")

    def test_start_nodes_and_mode_are_validated(self):
        route = self.app.route_save(self.pid, plan=PLAN)
        cid = self.ids(route)["Epitaxy"]
        self.assertEqual(self.app.route_start(self.pid, [cid])["start"], [cid])
        with self.assertRaises(ValueError):
            self.app.route_start(self.pid, ["nope"])
        self.assertFalse(self.app.route_mode(self.pid, "off")["enabled"])
        self.assertTrue(self.app.route_mode(self.pid, "route")["enabled"])
        with self.assertRaises(ValueError):
            self.app.route_mode(self.pid, "diverged")

    def test_the_change_can_be_undone_by_name(self):
        route = self.app.route_save(self.pid, plan=PLAN)
        org = Organization(self.app.store, project=self.pid)
        undo = org.snapshot()["undo"]
        self.assertEqual(undo["label"], "保存学习路径")
        org.action({"action": "undo", "event": undo["id"]})
        self.assertEqual(self.app.route_get(self.pid)["graph"], None)
        self.assertIsNotNone(route)

    def test_projects_are_isolated_and_the_default_knowledge_base_is_untouched(self):
        self.app.route_save(self.pid, plan=PLAN)
        self.assertEqual(self.app.route_get(self.other)["graph"], None)
        self.assertNotIn("route", Organization(self.app.store, project="default").snapshot())

    def test_resaving_a_plan_keeps_marks_on_the_same_concepts_by_name_and_drops_the_rest(self):
        route = self.app.route_save(self.pid, plan=PLAN)
        mbe = self.ids(route)["MBE"]
        self.app.route_manual(self.pid, mbe, "mastered")
        self.app.route_start(self.pid, [self.ids(route)["Epitaxy"]])
        reordered = {"concepts": list(reversed(PLAN["concepts"])), "targets": ["c"]}
        again = self.app.route_save(self.pid, plan=reordered)
        names = {v: k for k, v in self.ids(again).items()}
        self.assertEqual({names[i]: m for i, m in again["manual"].items()}, {"MBE": "mastered"})
        self.assertEqual([names[i] for i in again["start"]], ["Epitaxy"])
        unrelated = self.app.route_save(self.pid, plan={"concepts": [{"id": "x", "name": "Poetry forms", "terms": ["poetry"], "needs": []}]})
        self.assertEqual((unrelated["manual"], unrelated["start"]), ({}, []))

    def test_a_structured_save_drops_a_mark_when_the_concept_behind_its_id_changed(self):
        route = self.app.route_save(self.pid, plan=PLAN)
        mbe = self.ids(route)["MBE"]
        self.app.route_manual(self.pid, mbe, "mastered")
        self.app.route_start(self.pid, [mbe])
        graph = json.loads(json.dumps(route["graph"]))
        graph["concepts"] = [c for c in graph["concepts"] if c["id"] != mbe]
        graph["prereqs"] = [e for e in graph["prereqs"] if mbe not in (e["from"], e["to"])]
        graph["targets"] = [graph["concepts"][-1]["id"]]
        graph["concepts"].append({"id": mbe, "name": "A brand new topic", "terms": ["brand new"], "hint": 3, "origin": "user", "state": "active", "side": False})
        saved = self.app.route_save(self.pid, graph=graph)
        self.assertEqual((saved["manual"], saved["start"]), ({}, []))   # the id was reused by a different concept

    def test_a_structured_save_keeps_marks_by_id(self):
        route = self.app.route_save(self.pid, plan=PLAN)
        cid = self.ids(route)["Epitaxy"]
        self.app.route_manual(self.pid, cid, "demoted")
        self.assertEqual(self.app.route_save(self.pid, graph=route["graph"])["manual"], {cid: "demoted"})

    def test_a_save_must_choose_between_plan_and_graph_and_refuses_oversized_or_empty_plans(self):
        route = self.app.route_save(self.pid, plan=PLAN)
        org = Organization(self.app.store, project=self.pid)
        with self.assertRaises(ValueError):
            org.action({"action": "route-save", "plan": PLAN, "graph": route["graph"]})
        with self.assertRaises(ValueError):
            org.action({"action": "route-save", "plan": {"concepts": [{"id": str(i), "name": f"C{i}", "terms": [f"t{i}"]} for i in range(500)]}})
        with self.assertRaises(ValueError):
            self.app.route_save(self.pid, plan={"concepts": []})

    def test_clearing_a_mark_that_is_not_set_or_repeating_the_mode_changes_nothing(self):
        route = self.app.route_save(self.pid, plan=PLAN)
        org = Organization(self.app.store, project=self.pid)
        before = (org.snapshot()["revision"], org.snapshot()["undo"])
        self.app.route_manual(self.pid, self.ids(route)["Epitaxy"], None)
        self.app.route_mode(self.pid, "route")
        after = (org.snapshot()["revision"], org.snapshot()["undo"])
        self.assertEqual(before, after)

    def test_reading_a_route_never_creates_knowledge_base_rows_or_backups(self):
        before = self.app.store.conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='org_projects'").fetchone()[0]
        self.assertEqual(self.app.route_get(self.pid)["graph"], None)
        self.assertEqual(self.app.store.conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='org_projects'").fetchone()[0], before)
        if before:
            self.assertEqual(self.app.store.conn.execute("SELECT COUNT(*) FROM org_projects WHERE project=?", (self.pid,)).fetchone()[0], 0)
        self.assertEqual([p.name for p in self.app.data.glob(".paperdighelper.sqlite.pre-organization-*")], [])

    def test_non_string_project_ids_are_value_errors(self):
        for bad in (["x"], {"a": 1}, 5.5):
            with self.assertRaises(ValueError):
                self.app.route_get(bad)

    def test_a_proposed_concept_never_absorbs_a_papers_feedback(self):
        plan = {"concepts": [{"id": "p", "name": "Maybe topic", "terms": ["shared term", "alpha topic"], "hint": 1},
                             {"id": "q", "name": "Real topic", "terms": ["shared term", "beta topic"], "hint": 1}]}
        graph = json.loads(json.dumps(self.app.route_save(self.pid, plan=plan)["graph"]))
        self.assertEqual(len(graph["concepts"]), 2)
        graph["concepts"][0]["state"] = "proposed"   # listed first, so it would win the tie
        self.app.route_save(self.pid, graph=graph)
        self.add("sh0", "A shared term study", "shared term")
        self.app.record_feedback("sh0", "useful", project_id=self.pid)
        prog = self.app.route_get(self.pid)["progress"]
        self.assertEqual([v["useful"] for v in prog.values() if v["status"] != "proposed"], [1])
        self.assertEqual([v["useful"] for v in prog.values() if v["status"] == "proposed"], [0])

    def test_two_concepts_cannot_share_a_name(self):
        route = self.app.route_save(self.pid, plan=PLAN)
        graph = json.loads(json.dumps(route["graph"]))
        graph["concepts"][1]["name"] = graph["concepts"][0]["name"].upper()
        with self.assertRaises(ValueError):
            self.app.route_save(self.pid, graph=graph)

    def test_the_knowledge_base_snapshot_includes_the_map_only_when_there_is_one(self):
        org = Organization(self.app.store, project=self.pid)
        self.assertNotIn("route", org.snapshot())
        self.app.route_save(self.pid, plan=PLAN)
        snapshot = org.snapshot()
        self.assertEqual(len(snapshot["route"]["graph"]["concepts"]), 3)
        self.assertEqual(snapshot["route"]["mode"], "route")

    def test_the_export_carries_the_map(self):
        self.app.route_save(self.pid, plan=PLAN)
        exported = Organization(self.app.store, project=self.pid).action({"action": "export"})
        self.assertIn("route", exported["organization"])

    def test_deleting_a_project_removes_its_map_history_and_nothing_else(self):
        self.app.route_save(self.pid, plan=PLAN)
        self.app.route_save(self.other, plan=PLAN)
        Organization(self.app.store, project="default").snapshot()   # the shared knowledge-base row must survive
        conn = self.app.store.conn
        conn.execute("INSERT INTO org_notes(project, paper_key, version, text, created_at) VALUES (?,?,?,?,?)", (self.pid, "k", 1, "n", "now"))
        conn.execute("INSERT INTO org_drafts(project, paper_key, client, version, text, updated_at) VALUES (?,?,?,?,?,?)", (self.pid, "k", "c", 1, "x", "now"))
        conn.commit()
        self.app.projects.delete_project(self.pid)
        for table in ("org_projects", "org_notes", "org_events", "org_drafts"):
            self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE project=?", (self.pid,)).fetchone()[0], 0, table)
        rows = {r[0] for r in conn.execute("SELECT project FROM org_projects")}
        self.assertIn(self.other, rows)
        self.assertIn("default", rows)

    def test_deleting_a_project_works_when_the_knowledge_base_tables_do_not_exist(self):
        lonely = self.app.create_project("Lonely", "manual", ["x"])["project_id"]
        for table in ("org_events", "org_notes", "org_drafts", "org_projects"):
            self.app.store.conn.execute(f"DROP TABLE IF EXISTS {table}")
        self.app.store.conn.commit()
        self.app.projects.delete_project(lonely)
        self.assertFalse(self.app.projects.get_project(lonely))


class ProgressFromFeedbackTests(Fixture):
    def setUp(self):
        super().setUp()
        self.route = self.app.route_save(self.pid, plan=PLAN)
        self.cid = self.ids(self.route)
        for i in range(3):
            self.add(f"cb{i}", f"Crystal growth and lattice basics {i}", "crystal growth lattice")
            self.add(f"ep{i}", f"Epitaxial growth of films {i}", "epitaxy epitaxial layers")
        self.add("misc", "Classical poetry", "Tang dynasty")

    def status(self):
        prog = self.app.route_get(self.pid)["progress"]
        return {name: prog[cid]["status"] for name, cid in self.cid.items()}

    def feedback(self, *pairs):
        for key, action in pairs:
            self.app.record_feedback(key, action, project_id=self.pid)

    def test_the_start_of_the_map(self):
        self.assertEqual(self.status(), {"Crystal basics": "unlocked", "Epitaxy": "locked", "MBE": "locked"})
        self.assertEqual(self.app.route_get(self.pid)["frontier"], [self.cid["Crystal basics"]])

    def test_two_saved_papers_unlock_the_next_concept_only(self):
        self.feedback(("cb0", "useful"), ("cb1", "useful"))
        self.assertEqual(self.status(), {"Crystal basics": "satisfied", "Epitaxy": "unlocked", "MBE": "locked"})

    def test_undoing_feedback_takes_the_progress_back(self):
        self.feedback(("cb0", "useful"), ("cb1", "useful"))
        self.app.undo_feedback(self.app.latest_feedback(self.pid)["cb1"]["id"])
        self.assertEqual(self.status()["Crystal basics"], "unlocked")

    def test_a_too_hard_paper_lowers_progress_and_is_not_interest(self):
        self.feedback(("cb0", "useful"), ("cb1", "useful"), ("cb2", "too_hard"))
        prog = self.app.route_get(self.pid)["progress"][self.cid["Crystal basics"]]
        self.assertEqual(prog["status"], "unlocked")
        self.assertEqual((prog["too_hard"], prog["rated"]), (1, 2))

    def test_papers_outside_every_concept_and_silence_change_nothing(self):
        before = self.status()
        self.feedback(("misc", "useful"))
        self.assertEqual(self.status(), before)

    def test_a_paper_counts_for_its_best_concept_only(self):
        self.add("both", "Epitaxial growth from crystal growth lattice", "epitaxy epitaxial crystal growth lattice")
        self.feedback(("both", "useful"))
        prog = self.app.route_get(self.pid)["progress"]
        self.assertEqual(sum(v["useful"] for v in prog.values()), 1)
        from app import pathgrowth
        best = pathgrowth.assign(self.app.route_get(self.pid)["graph"], [dict(self.app.store.paper("both"))])["both"][0]
        self.assertEqual(prog[best]["useful"], 1)   # it counted for the concept it fits best, not just for some concept

    def test_a_seed_counts_as_explicit_positive_evidence(self):
        self.app.store.add_project_paper(self.pid, "cb0", "seed")
        self.app.store.add_project_paper(self.pid, "cb1", "seed")
        self.app.store.set_setting(f"seed_keys_{self.pid}", ["cb0", "cb1"])
        self.assertEqual(self.status()["Crystal basics"], "satisfied")

    def test_freezing_stops_new_feedback_from_moving_the_map(self):
        self.feedback(("cb0", "useful"))
        self.app.set_profile_frozen(True, self.pid)
        self.feedback(("cb1", "useful"))
        self.assertEqual(self.status()["Crystal basics"], "unlocked")

    def test_shown_counts_come_from_the_batches(self):
        with mock.patch.object(self.app.gateway, "call", side_effect=AssertionError("no model")):
            self.app.build_batch(limit=5, project_id=self.pid)
        prog = self.app.route_get(self.pid)["progress"]
        self.assertGreater(sum(v["shown"] for v in prog.values()), 0)

    def test_manual_mastery_unlocks_the_next_concept(self):
        self.app.route_manual(self.pid, self.cid["Crystal basics"], "mastered")
        self.assertEqual(self.status()["Epitaxy"], "unlocked")

    def test_a_route_that_is_off_reports_disabled_but_keeps_the_map(self):
        self.app.route_mode(self.pid, "off")
        state = self.app.route_get(self.pid)
        self.assertFalse(state["enabled"])
        self.assertEqual(len(state["graph"]["concepts"]), 3)

    def test_the_same_inputs_give_the_same_progress(self):
        self.feedback(("cb0", "useful"), ("ep0", "irrelevant"))
        self.assertEqual(self.app.route_get(self.pid), self.app.route_get(self.pid))


class RouteTests(Fixture):
    def serve(self):
        httpd = server.build_server(port=0, root=str(self.root))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd.server_address[1]

    def call(self, port, path, body=None, origin=None):
        headers = {"Content-Type": "application/json", **({"Origin": origin} if origin else {})}
        request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_save_read_mark_and_errors_over_http(self):
        port = self.serve()
        with mock.patch.dict("os.environ", {"PAPERDIGHELPER_DATA": str(self.app.data)}):
            self.assertEqual(self.call(port, f"/api/route?project_id={self.pid}")[1]["enabled"], False)
            status, saved = self.call(port, "/api/route", {"action": "save", "project_id": self.pid, "plan": PLAN})
            self.assertEqual(status, 200)
            cid = {c["name"]: c["id"] for c in saved["graph"]["concepts"]}["Epitaxy"]
            status, marked = self.call(port, "/api/route", {"action": "manual", "project_id": self.pid, "concept": cid, "value": "mastered", "revision": saved["revision"]})
            self.assertEqual((status, marked["manual"]), (200, {cid: "mastered"}))
            status, body = self.call(port, "/api/route", {"action": "manual", "project_id": self.pid, "concept": cid, "value": "x"})
            self.assertEqual(status, 400)
            status, body = self.call(port, "/api/route", {"action": "manual", "project_id": self.pid, "concept": cid, "value": None, "revision": saved["revision"]})
            self.assertEqual(status, 409)   # the revision moved on
            self.assertEqual(self.call(port, "/api/route", {"action": "bogus", "project_id": self.pid})[0], 400)
            self.assertEqual(self.call(port, "/api/route", {"action": "save", "project_id": "no-such-project", "plan": PLAN})[0], 400)

    def test_a_foreign_origin_is_refused(self):
        port = self.serve()
        self.assertEqual(self.call(port, "/api/route", {"action": "save", "project_id": self.pid, "plan": PLAN}, origin="http://evil.example")[0], 403)


if __name__ == "__main__":
    unittest.main()
