"""Goal scope and explicit watching are local state, independent of interest/mastery."""
import copy
import json
import unittest

from app import pathgraph as pg
from app.organization import Conflict, Organization
from app.service import App
from test_route_store import Fixture, PLAN


def graph():
    return {"concepts": [{"id": i, "state": "active"} for i in "abcd"],
            "prereqs": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"},
                        {"from": "a", "to": "d"}], "targets": ["c"]}


class ScopeTests(unittest.TestCase):
    def goal(self, g=None, mastered=()):
        g = g or graph()
        p = pg.progress(g, {}, manual={i: "mastered" for i in mastered})
        return pg.goal_state(g, p)

    def test_side_branch_is_outside_goal_and_does_not_block_completion(self):
        result = self.goal(mastered="abc")
        self.assertEqual(result["goal_scope"], list("abc"))
        self.assertEqual((result["goal_status"], result["goal_done"], result["goal_total"]), ("completed", 3, 3))
        self.assertEqual(result["frontier"], [])

    def test_multiple_targets_union_shared_prerequisites_once(self):
        g = graph(); g["targets"] = ["c", "d", "c"]
        r = self.goal(g, "abc")
        self.assertEqual(r["goal_scope"], list("abcd"))
        self.assertEqual((r["goal_status"], r["frontier"]), ("learning", ["d"]))

    def test_manually_mastered_target_still_requires_its_prerequisites(self):
        r = self.goal(mastered="c")
        self.assertEqual((r["goal_status"], r["goal_done"], r["frontier"]), ("learning", 1, ["a"]))

    def test_proposed_edges_and_nonactive_nodes_do_not_expand_scope(self):
        g = graph(); g["prereqs"].append({"from": "d", "to": "c", "state": "proposed"})
        self.assertEqual(self.goal(g)["goal_scope"], list("abc"))
        g["prereqs"][-1]["state"] = "active"; g["concepts"][-1]["state"] = "archived"
        self.assertEqual(self.goal(g)["goal_scope"], list("abc"))

    def test_missing_or_nonactive_targets_need_review_without_inventing_targets(self):
        for targets in ([], ["missing"], ["c", "missing"], ["d"]):
            g = graph(); g["targets"] = targets; g["concepts"][-1]["state"] = "archived"
            self.assertEqual(self.goal(g, "abc")["goal_status"], "needs_review")

    def test_cycle_has_no_frontier_but_is_not_completed_even_with_manual_marks(self):
        g = graph(); g["prereqs"].append({"from": "c", "to": "a"})
        for marks in ((), "abc"):
            r = self.goal(g, marks)
            self.assertEqual((r["goal_status"], r["frontier"]), ("needs_review", []))

    def test_dangling_active_prerequisite_needs_review(self):
        g = graph(); g["prereqs"].append({"from": "missing", "to": "c"})
        self.assertEqual(self.goal(g)["goal_status"], "needs_review")

    def test_off_scope_cycle_does_not_block_goal(self):
        g = graph(); g["prereqs"].append({"from": "d", "to": "d"})
        self.assertEqual(self.goal(g, "abc")["goal_status"], "completed")

    def test_nonactive_reverse_edge_cannot_change_unlock_evaluation_order(self):
        g = graph(); g["prereqs"].append({"from": "c", "to": "a", "state": "proposed"})
        p = pg.progress(g, {}, manual={"a": "mastered", "b": "mastered"})
        self.assertEqual(p["c"]["status"], "unlocked")
        self.assertEqual(pg.goal_state(g, p)["frontier"], ["c"])


class WatchTests(Fixture):
    def setUp(self):
        super().setUp()
        self.route = self.app.route_save(self.pid, plan=PLAN)
        self.cid = self.ids(self.route)["MBE"]

    def test_watch_is_independent_of_mastery_and_new_updates_require_satisfaction(self):
        before = self.app.route_get(self.pid)
        watched = self.app.route_watch(self.pid, self.cid, True, revision=before["revision"])
        self.assertEqual(watched["progress"], before["progress"])
        self.assertEqual((watched["watch"], watched["watched_satisfied"]), ([self.cid], []))
        mastered = self.app.route_manual(self.pid, self.cid, "mastered")
        self.assertEqual(mastered["watched_satisfied"], [self.cid])
        cleared = self.app.route_manual(self.pid, self.cid, None)
        self.assertEqual((cleared["watch"], cleared["watched_satisfied"]), ([self.cid], []))

    def test_watch_survives_mode_off_restart_save_and_undo(self):
        watched = self.app.route_watch(self.pid, self.cid, True)
        self.app.route_mode(self.pid, "off")
        again = App(root=str(self.root), data_dir=str(self.root / "data")); self.addCleanup(again.store.close)
        self.assertEqual(again.route_get(self.pid)["watch"], [self.cid])
        self.assertEqual(again.home_route(self.pid)["goal_status"], "off")
        self.app.route_mode(self.pid, "route")
        self.app.route_save(self.pid, graph=watched["graph"])
        self.app.route_watch(self.pid, self.cid, False)
        restored = self.app.route_undo(self.pid)
        self.assertEqual(restored["watch"], [self.cid])

    def test_watch_follows_plan_names_then_stable_graph_identity(self):
        self.app.route_watch(self.pid, self.cid, True)
        plan = copy.deepcopy(PLAN); plan["concepts"].reverse()
        saved = self.app.route_save(self.pid, plan=plan)
        new_id = self.ids(saved)["MBE"]
        self.assertEqual(saved["watch"], [new_id])
        g = copy.deepcopy(saved["graph"])
        next(c for c in g["concepts"] if c["id"] == new_id)["name"] = "Brand new subject"
        self.assertEqual(self.app.route_save(self.pid, graph=g)["watch"], [new_id])
        # A different learning task has a fresh identity, instead of reusing one.
        for node in g['concepts']:
            if node['id'] == new_id: node['id'] = 'new-task-identity'
        for edge in g['prereqs']:
            for field in ('from','to'):
                if edge[field] == new_id: edge[field] = 'new-task-identity'
        g['targets'] = ['new-task-identity' if i == new_id else i for i in g['targets']]
        self.assertEqual(self.app.route_save(self.pid, graph=g)['watch'], [])

    def test_stale_revision_and_invalid_watch_leave_state_unchanged(self):
        watched = self.app.route_watch(self.pid, self.cid, True)
        with self.assertRaises(Conflict):
            self.app.route_watch(self.pid, self.cid, False, revision=self.route["revision"])
        for concept, value in (("missing", True), (self.cid, 1), (self.cid, "false"), (self.cid, None)):
            with self.assertRaises(ValueError): self.app.route_watch(self.pid, concept, value)
        self.assertEqual(self.app.route_get(self.pid), watched)

    def test_watch_noop_creates_no_revision_or_event_and_is_project_local(self):
        watched = self.app.route_watch(self.pid, self.cid, True)
        event = Organization(self.app.store, project=self.pid).snapshot()["undo"]
        self.assertEqual(self.app.route_watch(self.pid, self.cid, True), watched)
        self.assertEqual(Organization(self.app.store, project=self.pid).snapshot()["undo"], event)
        self.assertIsNone(self.app.route_get(self.other)["graph"])

    def test_deleted_watch_is_restored_only_by_undo(self):
        watched = self.app.route_watch(self.pid, self.cid, True)
        reduced = pg.remove_concept(watched["graph"], self.cid)
        reduced["targets"] = [self.ids(watched)["Epitaxy"]]   # target deletion requires explicit replacement
        self.assertEqual(self.app.route_save(self.pid, graph=reduced)["watch"], [])
        self.assertEqual(self.app.route_undo(self.pid)["watch"], [self.cid])

    def test_home_cache_detects_changed_paper_matching_not_only_count(self):
        for key in ("one", "two"):
            self.add(key, "Crystal growth lattice", "crystal growth lattice")
            self.app.store.save_to_library(key, project_id=self.pid)
            self.app.record_feedback(key, "understood", project_id=self.pid)
        before = self.app.home_route(self.pid)
        self.app.store.conn.execute("UPDATE papers SET title='Nothing matches',abstract='Unrelated' WHERE key='one'")
        self.app.store.conn.commit()
        after = self.app.home_route(self.pid)
        self.assertEqual((before["goal_done"], after["goal_done"]), (1, 0))
        self.assertEqual(after["goal_status"], "learning")
        self.assertEqual(after["goal_total"], before["goal_total"])

    def test_legacy_route_reads_without_writes_and_normalizes_on_save(self):
        conn = self.app.store.conn
        row = conn.execute("SELECT data FROM org_projects WHERE project=?", (self.pid,)).fetchone()
        data = json.loads(row[0]); data["route"].pop("watch", None)
        conn.execute("UPDATE org_projects SET data=? WHERE project=?", (json.dumps(data), self.pid)); conn.commit()
        before = conn.execute("SELECT data,revision FROM org_projects WHERE project=?", (self.pid,)).fetchone()
        self.assertEqual(self.app.route_get(self.pid)["watch"], [])
        self.assertEqual(tuple(conn.execute("SELECT data,revision FROM org_projects WHERE project=?", (self.pid,)).fetchone()), tuple(before))
        self.app.route_watch(self.pid, self.cid, True)
        self.assertEqual(self.app.route_get(self.pid)["watch"], [self.cid])

    def test_home_completion_recomputes_after_undo_of_earlier_feedback(self):
        g = copy.deepcopy(self.route["graph"])
        next(c for c in g["concepts"] if c["id"] == self.cid)["terms"] = ["beam deposition"]
        self.app.route_save(self.pid, graph=g)
        self.add("mbe1", "Beam deposition", "beam deposition")
        self.add("mbe2", "Beam deposition studies", "beam deposition")
        for key in ("mbe1", "mbe2"):
            self.app.store.save_to_library(key, project_id=self.pid)
            self.app.record_feedback(key, "understood", project_id=self.pid)
        for name, cid in self.ids().items():
            if name != "MBE": self.app.route_manual(self.pid, cid, "mastered")
        self.assertEqual(self.app.home_route(self.pid)["goal_status"], "completed")
        ids = [r[0] for r in self.app.store.conn.execute("SELECT id FROM feedback WHERE action='understood' ORDER BY id")]
        self.app.undo_feedback(ids[0], project_id=self.pid)
        self.assertEqual(self.app.home_route(self.pid)["goal_status"], "learning")

    def test_frozen_progress_undo_invalidates_cache_even_when_later_label_masks_it(self):
        for key in ("cb1", "cb2"):
            self.add(key, "Crystal growth lattice", "crystal growth lattice")
            self.app.store.save_to_library(key, project_id=self.pid)
            self.app.record_feedback(key, "understood", project_id=self.pid)
        rows = [r[0] for r in self.app.store.conn.execute("SELECT id FROM feedback ORDER BY id")]
        self.app.store.set_setting(f"profile_freeze_{self.pid}", {"through_feedback_id": rows[-1]})
        self.app.record_feedback("cb1", "too_hard", project_id=self.pid)
        before = self.app.home_route(self.pid)
        self.app.undo_feedback(rows[0], project_id=self.pid)
        after = self.app.home_route(self.pid)
        self.assertEqual((before["goal_done"], after["goal_done"]), (1, 0))


if __name__ == "__main__": unittest.main()
