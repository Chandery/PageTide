"""One disposable project traverses the complete local Route lifecycle; no native or AI quality claim."""
from collections import Counter
from datetime import date
from unittest import mock

from test_route_detail import Fixture
from recommendation_fixtures import SYNTHETIC_OA
from app.organization import Conflict
from app.service import App


class FullLocalFlowTests(Fixture):
    def test_single_project_language_batch_feedback_undo_watch_revision_restart_restore(self):
        self.app.set_project_language(self.pid, "stem", ["en"])
        public={f'x{i}':[{'query':'photonic calibration','kinds':['explore'],'observed_at':date.today().isoformat()}] for i in range(6)}
        with mock.patch.object(self.app.gateway, "call", side_effect=AssertionError("no model calls")), \
                mock.patch.object(self.app.source, "_fetch", side_effect=AssertionError("no source calls")), \
                mock.patch.object(self.app, 'route_recall_sources', return_value=public):
            route = self.app.route_save(self.pid, plan={"concepts": [
                {"id": "a", "name": "Lattice basis", "terms": ["crystal lattice"], "hint": 1, "needs": []},
                {"id": "b", "name": "Epitaxy goal", "terms": ["epitaxy"], "hint": 2, "needs": ["a"]}], "targets": ["b"]})
            ids = {c["name"]: c["id"] for c in route["graph"]["concepts"]}
            self.app.store.upsert_papers([
                {"key": kind + str(i), "title": term + " study " + str(i), "abstract": term + " methods and measurements",
                 "language": "en", "published": date.today().isoformat(), "oa": SYNTHETIC_OA}
                for kind, term in [("p", "epitaxy"), ("w", "crystal lattice"), ("x", "photonic calibration")]
                for i in range(6)], project_id=self.pid)
            route = self.app.route_manual(self.pid, ids["Lattice basis"], "mastered", route["revision"])
            route = self.app.route_watch(self.pid, ids["Lattice basis"], True, route["revision"])
            batch = self.app.build_batch(project_id=self.pid)
            self.assertEqual(Counter(c["route"]["kind"] for c in batch["cards"]), {"route": 3, "explore": 1, "watch": 1})
            key = next(c["key"] for c in batch["cards"] if c["route"]["kind"] == "explore")
            exploration=next(c for c in batch['cards'] if c['key']==key)['route']['exploration_evidence']
            self.assertEqual(exploration['query'],'photonic calibration')
            self.assertIn(exploration['quote'],self.app.store.paper(key)['title']+' '+self.app.store.paper(key)['abstract'])
            feedback = self.app.record_feedback(key, "useful", project_id=self.pid)
            self.assertTrue(self.app.store.in_library(key, self.pid))
            self.app.undo_feedback(feedback["feedback_id"], self.pid)
            self.assertNotIn(key, self.app.latest_feedback(self.pid))
            self.assertTrue(self.app.store.in_library(key, self.pid))
            ctx = self.app.paper_detail(key, self.pid)["context"]
            self.assertEqual(ctx["units"], [])
            self.assertEqual(ctx["recommendation"]["kind"], "explore")
            self.assertIn(key, self.app.route_detail(self.pid, focus_key=key)["unmatched"])
            route = self.app.route_manual(self.pid, ids["Epitaxy goal"], "mastered", route["revision"])
            self.assertEqual(route["goal_status"], "completed")
            discovery = self.app.build_batch(project_id=self.pid)
            self.assertEqual(len(discovery["cards"]), 1)
            self.assertEqual(discovery["cards"][0]["route"]["kind"], "explore")
            self.assertEqual(self.app.build_batch(project_id=self.pid)["batch_id"], discovery["batch_id"])
            patch = {"operations": [{"op": "update_node", "ref": "c1", "changes": {"name": "Revised lattice basis"}}]}
            draft = self.app.route_revision_preview(self.pid, {"goal": "Teacher corrected route"}, patch, route["revision"])
            route = self.app.route_watch(self.pid, ids["Lattice basis"], False, route["revision"])
            with self.assertRaises(Conflict):
                self.app.route_revision_confirm(self.pid, draft["draft_id"])
            retained = self.app.route_revision_draft(self.pid)
            self.assertEqual(retained["draft_id"], draft["draft_id"])
            before = self.app.route_get(self.pid)
            draft = self.app.route_revision_preview(self.pid, {"goal": "Teacher corrected route"}, patch, before["revision"])
            confirmed = self.app.route_revision_confirm(self.pid, draft["draft_id"])
            self.assertEqual(confirmed["graph"], draft["after"]["graph"])
            self.assertEqual(confirmed["goal_status"], "learning")
            self.assertNotIn(ids["Lattice basis"], confirmed["manual"])
        self.app.store.close()
        self.app = App(root=str(self.root), data_dir=str(self.root / "data"))
        from recommendation_fixtures import legacy_recommendation_settings
        legacy_recommendation_settings(self.app, route_beta=True)
        self.addCleanup(self.app.store.close)
        with mock.patch.object(self.app.gateway, "call", side_effect=AssertionError("no model calls")), \
                mock.patch.object(self.app.source, "_fetch", side_effect=AssertionError("no source calls")):
            resumed = self.app.route_get(self.pid)
            self.assertEqual(resumed["graph"], confirmed["graph"])
            self.assertEqual(resumed["brief"], confirmed["brief"])
            restored = self.app.route_undo(self.pid, resumed["revision"])
            for field in ["graph", "manual", "watch", "brief"]:
                self.assertEqual(restored.get(field), before.get(field))
            self.assertEqual(restored["goal_status"], "completed")
            self.assertEqual(self.app.build_batch(project_id=self.pid)["batch_id"], discovery["batch_id"])
            off = self.app.route_mode(self.pid, "off", restored["revision"])
            self.assertFalse(off["enabled"])
            self.assertTrue(self.app.paper_detail(key, self.pid)["context"]["map_available"])
            # Ordinary mode shares the same language/readable-content gate.
            self.app.store.upsert_papers([{"key": "zh-rejected", "title": "epitaxy",
                "abstract": "Useful abstract", "language": "zh", "published": date.today().isoformat()}], self.pid)
            ordinary = self.app.build_batch(project_id=self.pid)
            self.assertNotIn("zh-rejected", {c["key"] for c in ordinary["cards"]})
            self.assertTrue(all(c["route"] is None for c in ordinary["cards"]))
