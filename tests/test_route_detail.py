"""The second knowledge-graph view: a project's learning units with the papers it saved, joined by what the text
says. Read-only and derived: nothing here is stored, so nothing can drift from the map or the library."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import server
from app.organization import Organization
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

    def save(self, key, title, abstract="", pid=None):
        pid = pid or self.pid
        self.app.store.upsert_papers([{"key": key, "title": title, "abstract": abstract, "published": "2026-01-01"}], project_id=pid)
        self.app.store.save_to_library(key, project_id=pid)

    def unit(self, detail, name):
        return next(u for u in detail["units"] if u["name"] == name)

    def detail(self, pid=None):
        return self.app.route_detail(pid or self.pid)


class AvailabilityTests(Fixture):
    def test_without_a_learning_map_the_view_is_not_available(self):
        out = self.detail()
        self.assertEqual((out["available"], out["reason"]), (False, "no_route"))
        self.assertNotIn("units", out)

    def test_an_unknown_project_is_an_error(self):
        with self.assertRaises(ValueError):
            self.app.route_detail("no-such")

    def test_only_projects_with_a_map_are_listed_in_the_snapshot(self):
        snapshot = lambda: Organization(self.app.store).snapshot()
        self.assertEqual(snapshot()["route_projects"], [])
        self.app.route_save(self.pid, plan=PLAN)
        self.assertEqual(snapshot()["route_projects"], [self.pid])

    def test_a_map_with_no_active_unit_is_not_available(self):
        self.app.route_save(self.pid, plan=PLAN)
        graph = self.app.route_get(self.pid)["graph"]
        for concept in graph["concepts"]:
            concept["state"] = "archived"
        # a saved map must keep one active unit, so emulate an old record by writing the block directly
        revision, data = self.app._route_org(self.pid)._load()
        data["route"]["graph"] = graph
        self.app.store.conn.execute("UPDATE org_projects SET data=? WHERE project=?", (json.dumps(data), self.pid))
        self.app.store.conn.commit()
        self.assertEqual(self.detail()["available"], False)


class ContentTests(Fixture):
    def setUp(self):
        super().setUp()
        self.app.route_save(self.pid, plan=PLAN)
        self.save("cb", "Crystal growth and lattice defects", "lattice mismatch")
        self.save("ep", "Epitaxial layers", "epitaxy of thin films")
        self.save("mbe", "Molecular beam epitaxy of oxides", "molecular beam epitaxy chambers")
        self.save("poem", "Classical poetry", "Tang dynasty")

    def test_units_carry_their_level_type_and_prerequisites(self):
        out = self.detail()
        self.assertTrue(out["available"])
        self.assertEqual([(u["name"], u["level"]) for u in sorted(out["units"], key=lambda u: u["level"])],
                         [("Crystal basics", 1), ("Epitaxy", 2), ("MBE", 3)])
        names = {u["id"]: u["name"] for u in out["units"]}
        self.assertEqual(sorted((names[e["from"]], names[e["to"]]) for e in out["prereqs"]), [("Crystal basics", "Epitaxy"), ("Epitaxy", "MBE")])

    def test_a_paper_matches_a_unit_by_the_terms_it_uses_and_says_which(self):
        out = self.detail()
        by_paper = {}
        for m in out["matches"]:
            by_paper.setdefault(m["paper"], []).append(m)
        unit = {u["id"]: u["name"] for u in out["units"]}
        self.assertEqual([(unit[m["unit"]], m["terms"]) for m in by_paper["cb"]], [("Crystal basics", ["crystal growth", "lattice"])])
        self.assertIn("Epitaxy", [unit[m["unit"]] for m in by_paper["ep"]])
        self.assertTrue(all(len(v) <= 2 for v in by_paper.values()))

    def test_a_paper_that_fits_no_unit_is_listed_as_unmatched_not_dropped(self):
        out = self.detail()
        self.assertEqual({p["key"] for p in out["papers"]}, {"cb", "ep", "mbe", "poem"})
        self.assertEqual(out["unmatched"], ["poem"])

    def test_only_the_papers_this_project_saved_appear(self):
        self.save("other-ep", "Epitaxy for other people", "epitaxy", pid=self.other)
        self.app.store.upsert_papers([{"key": "unsaved", "title": "Epitaxy but never saved", "abstract": "epitaxy", "published": "2026-01-01"}], project_id=self.pid)
        keys = {p["key"] for p in self.detail()["papers"]}
        self.assertNotIn("other-ep", keys)
        self.assertNotIn("unsaved", keys)

    def test_a_paper_both_projects_saved_appears_for_each_with_its_own_map(self):
        self.save("shared", "Epitaxial growth", "epitaxy", pid=self.pid)
        self.app.store.save_to_library("shared", project_id=self.other)
        self.assertIn("shared", {p["key"] for p in self.detail()["papers"]})
        self.assertEqual(self.detail(self.other), {"available": False, "reason": "no_route", "project_id": self.other})

    def test_a_proposed_unit_is_shown_as_proposed_and_an_archived_one_is_not(self):
        graph = self.app.route_get(self.pid)["graph"]
        graph["concepts"].append({"id": "c9", "name": "Strain relaxation", "terms": ["strain relaxation"], "hint": 3, "origin": "grown", "state": "proposed", "side": False})
        graph["concepts"].append({"id": "c10", "name": "Old idea", "terms": ["old idea"], "hint": 1, "origin": "user", "state": "archived", "side": False})
        self.app.route_save(self.pid, graph=graph)
        out = self.detail()
        self.assertEqual(self.unit(out, "Strain relaxation")["state"], "proposed")
        self.assertNotIn("Old idea", [u["name"] for u in out["units"]])

    def test_a_unit_reports_its_progress_status_for_colouring(self):
        out = self.detail()
        self.assertEqual({u["name"]: u["status"] for u in out["units"]},
                         {"Crystal basics": "unlocked", "Epitaxy": "locked", "MBE": "locked"})

    def test_reading_the_view_writes_nothing_even_on_a_database_without_the_knowledge_base_tables(self):
        for table in ("org_events", "org_notes", "org_drafts", "org_projects"):
            self.app.store.conn.execute(f"DROP TABLE IF EXISTS {table}")
        self.app.store.conn.commit()
        before = sorted(p.name for p in self.app.data.iterdir())
        self.assertEqual(self.detail()["available"], False)   # no map: nothing to draw, and nothing created
        tables = {r[0] for r in self.app.store.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertFalse(tables & {"org_projects", "org_events", "org_notes", "org_drafts"})
        self.assertEqual(sorted(p.name for p in self.app.data.iterdir()), before)   # and no backup file

    def test_it_is_read_only_and_repeatable(self):
        before = self.app.route_get(self.pid)["revision"]
        first, second = self.detail(), self.detail()
        self.assertEqual(first, second)
        self.assertEqual(self.app.route_get(self.pid)["revision"], before)
        events = self.app.store.conn.execute("SELECT COUNT(*) FROM org_events").fetchone()[0]
        self.detail()
        self.assertEqual(self.app.store.conn.execute("SELECT COUNT(*) FROM org_events").fetchone()[0], events)

    def test_titles_are_data_only_never_markup_the_server_changes(self):
        self.save("xss", '<img src=x onerror=alert(1)> epitaxy', "epitaxy")
        titles = [p["title"] for p in self.detail()["papers"] if p["key"] == "xss"]
        self.assertEqual(titles, ['<img src=x onerror=alert(1)> epitaxy'])   # escaped by the page, not rewritten here

    def test_a_very_large_library_is_bounded(self):
        for i in range(250):
            self.save(f"bulk{i}", f"Epitaxy study {i}", "epitaxy")
        out = self.detail()
        self.assertLessEqual(len(out["papers"]), 120)
        self.assertGreater(out["omitted"], 0)
        self.assertEqual(len(out["papers"]) + out["omitted"], 254)

    def test_selected_saved_paper_survives_graph_cap_and_unmatched_count_is_complete(self):
        for i in range(130):
            self.save(f"bulk{i}", f"Epitaxy study {i}", "epitaxy")
        out = self.app.route_detail(self.pid, focus_key="poem")
        self.assertEqual(len(out["papers"]), 120)
        self.assertIn("poem", out["unmatched"])
        self.assertEqual(out["unmatched_total"], 1)
        self.save("foreign", "Other poem", pid=self.other)
        self.assertNotIn("foreign", {p["key"] for p in self.app.route_detail(self.pid, focus_key="foreign")["papers"]})

    def test_paper_context_separates_categories_units_and_current_batch_purpose(self):
        org = Organization(self.app.store)
        org.action({"action": "direction-save", "name": "Materials", "color": "#64748b"})
        second = org.action({"action": "direction-save", "name": "Methods", "color": "#64748b"})
        ids = [d["id"] for d in second["directions"]]
        org.action({"action": "membership", "keys": ["ep"], "add": ids, "remove": []})
        unit = self.unit(self.detail(), "Epitaxy")["id"]
        batch = self.app.store.create_batch("2026-10-07", ["ep"], project_id=self.pid,
                                            route={"ep": (unit, "route", "Historical epitaxy", 2)})
        context = self.app.paper_detail("ep", self.pid)["context"]
        self.assertEqual({c["name"] for c in context["categories"]}, {"Materials", "Methods"})
        self.assertEqual([u["name"] for u in context["units"]], ["Epitaxy"])
        self.assertEqual(context["recommendation"], {"batch_id": batch, "kind": "route", "name": "Historical epitaxy"})
        self.app.route_mode(self.pid, "off")
        off = self.app.paper_detail("ep", self.pid)["context"]
        self.assertFalse(off["route_enabled"])
        self.assertTrue(off["map_available"])
        self.assertEqual(off["units"], context["units"])
        self.app.store.create_batch("2026-10-07", ["cb"], project_id=self.pid)
        self.assertIsNone(self.app.paper_detail("ep", self.pid)["context"]["recommendation"])

    def test_unsaved_and_other_project_context_cannot_navigate_to_current_library_graph(self):
        self.app.store.upsert_papers([{"key": "unsaved", "title": "epitaxy", "abstract": "epitaxy"}], self.pid)
        ctx = self.app.paper_detail("unsaved", self.pid)["context"]
        self.assertTrue(ctx["units"])
        self.assertFalse(ctx["saved_in_project"])
        other = self.app.paper_detail("ep", self.other)["context"]
        self.assertFalse(other["map_available"])
        self.assertEqual(other["units"], [])
        self.assertFalse(other["saved_in_project"])

    def test_multiple_learning_matches_do_not_create_or_change_categories(self):
        self.save("multi", "Crystal lattice and epitaxy", "crystal growth epitaxial")
        before = Organization(self.app.store).snapshot()
        ctx = self.app.paper_detail("multi", self.pid)["context"]
        self.assertEqual(len(ctx["units"]), 2)
        self.assertEqual(ctx["categories"], [])
        after = Organization(self.app.store).snapshot()
        self.assertEqual(after["revision"], before["revision"])
        self.assertEqual(after["directions"], before["directions"])


class LifecycleTests(Fixture):
    def test_deleting_the_project_removes_the_view(self):
        self.app.route_save(self.pid, plan=PLAN)
        self.save("ep", "Epitaxial layers", "epitaxy")
        self.app.delete_project(self.pid)
        with self.assertRaises(ValueError):
            self.app.route_detail(self.pid)
        self.assertEqual(self.app.store.conn.execute("SELECT COUNT(*) FROM org_projects WHERE project=?", (self.pid,)).fetchone()[0], 0)


class HttpTests(Fixture):
    def serve(self):
        httpd = server.build_server(port=0, root=str(self.root))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd.server_address[1]

    def post(self, port, body):
        request = urllib.request.Request(f"http://127.0.0.1:{port}/api/organization", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_the_view_is_served_over_the_organization_route(self):
        self.app.route_save(self.pid, plan=PLAN)
        self.save("ep", "Epitaxial layers", "epitaxy")
        port = self.serve()
        from unittest import mock
        with mock.patch.dict("os.environ", {"PAPERDIGHELPER_DATA": str(self.app.data)}):
            status, body = self.post(port, {"action": "route-detail", "project_id": self.pid})
            self.assertEqual(status, 200)
            self.assertTrue(body["available"])
            self.assertEqual([p["key"] for p in body["papers"]], ["ep"])
            self.assertEqual(self.post(port, {"action": "route-detail"})[0], 400)
            self.assertEqual(self.post(port, {"action": "route-detail", "project_id": "no-such"})[0], 400)
            self.assertEqual(self.post(port, {"action": "route-detail", "project_id": self.pid, "focus_key": []})[0], 400)


if __name__ == "__main__":
    unittest.main()
