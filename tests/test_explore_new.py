"""Exploration and potential directions are one loop: a direction on file (the model's opinion about papers the reader
collected from exploration) steers the exploration slots toward papers that read like its own, and the card says so.
The reader's explicit feedback on such a paper is what makes the direction grow; being shown a paper is not evidence."""
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recommendation_fixtures import english_papers
from app.service import App

PLAN = {"concepts": [
    {"id": "a", "name": "Crystal basics", "terms": ["crystal growth", "lattice"], "hint": 1, "needs": []},
    {"id": "b", "name": "Epitaxy", "terms": ["epitaxy", "epitaxial"], "hint": 2, "needs": ["a"]}], "targets": ["b"]}


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "harness").mkdir()
        (self.root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (self.root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        self.app = App(root=str(self.root), data_dir=str(self.root / "data"))
        from recommendation_fixtures import legacy_recommendation_settings
        legacy_recommendation_settings(self.app, route_beta=True)
        self.addCleanup(self.app.store.close)
        self.pid = self.app.create_project("Crystals", "manual", ["epitaxy"])["project_id"]
        self.app.route_save(self.pid, plan=PLAN)
        for i in range(8):   # papers of the readable concept: the route has plenty to show
            self.add(f"cb{i}", f"Crystal growth and lattice basics {i}", "crystal growth lattice", f"journal-{i % 3}")
        # four papers of a direction the map does not cover; two of them the reader collected earlier and the model put under a direction
        for i, source in enumerate(("journal-a", "journal-b", "journal-a", "journal-b"), start=1):
            self.add(f"s{i}", f"Strain relaxation by misfit dislocation glide {i}",
                     "strain relaxation by misfit dislocation glide in thin films", source)
        # a paper outside the map that the profile will like better than the direction's papers
        self.add("decoy", "A decoy about quantum dots", "quantum dots")
        # Ordinary exploration needs an actual public query with visible text
        # evidence. The direction's other papers have explicit positive basis.
        self.public_sources = {"decoy": [{"query": "quantum dots", "kinds": ["explore"], "observed_at": "2026-02-01"}]}
        sources = mock.patch.object(self.app, "route_recall_sources", return_value=self.public_sources)
        sources.start(); self.addCleanup(sources.stop)
        self.app.record_feedback("s1", "useful", project_id=self.pid)
        self.app.record_feedback("s2", "useful", project_id=self.pid)
        self.app.store.create_batch("2026-09-01", ["s1", "s2"], project_id=self.pid, route={k: (None, "explore", None, None) for k in ("s1", "s2")})
        self.app.store.set_setting(f"route_directions_{self.pid}", {"directions": [
            {"id": "d-1", "name": "应变弛豫", "terms": ["strain relaxation", "dislocation glide"], "intro": "位错滑移释放应力。", "barrier": "难在应变与缺陷。",
             "needs": [], "papers": ["s1", "s2"], "created": "2026-09-01", "proposal_type": "new_branch", "context": self.app._growth_context(self.pid, ["s1", "s2"])}], "judged": {"s1": {"verdict": "new"}, "s2": {"verdict": "join"}}})

    def add(self, key, title, abstract, source="arXiv"):
        self.app.store.upsert_papers([{"key": key, "title": title, "abstract": abstract, "source": source, "published": "2026-02-01"}], project_id=self.pid)

    def kinds(self, cards):
        return {c["key"]: (c["route"] or {}).get("kind") for c in cards}


class ExploreNewTests(Fixture):
    def test_rejecting_a_direction_during_selection_invalidates_stale_steering(self):
        english_papers(self.app,self.pid);original=self.app._route_pick
        def changed(*args,**kwargs):
            picks=original(*args,**kwargs);self.app.route_candidate_reject(self.pid,'d-1');return picks
        with mock.patch.object(self.app,'_route_pick',side_effect=changed):
            result=self.app.build_batch(limit=5,project_id=self.pid)
        self.assertEqual(result['reason_code'],'recommendation_changed')

    def test_the_exploration_slot_goes_to_a_paper_that_reads_like_the_directions_papers(self):
        english_papers(self.app, self.pid)
        cards = self.app.build_batch(limit=5, project_id=self.pid)["cards"]
        kinds = self.kinds(cards)
        explored = [k for k, v in kinds.items() if v in ("explore", "explore_new")]
        self.assertEqual(len(explored), 2)
        self.assertIn(explored[0], ("s3", "s4"))   # a paper like the direction's, not the decoy the profile likes better
        card = next(c for c in cards if c["route"]["kind"] == "explore_new")
        self.assertEqual(card["route"]["name"], "应变弛豫")
        self.assertIsNone(card["route"]["node"])

    def test_it_is_chosen_over_a_paper_the_profile_likes_more(self):
        route = self.app._route_state(self.pid)
        pool = [dict(self.app.store.paper(k)) for k in ("decoy", "s3", "cb0", "cb1", "cb2", "cb3", "cb4")]
        scored = [("decoy", 0.9), ("s3", 0.4)] + [(f"cb{i}", 0.3) for i in range(5)]
        plain_evidence={}; route={**route, '_selection_evidence':plain_evidence}
        plain = self.app._route_pick(route, pool, scored, {}, 5, 0, ())
        self.assertIn(("decoy", None, "explore", "quantum dots"), plain)
        self.assertEqual(plain_evidence['decoy']['query'],'quantum dots')
        self.assertIn(plain_evidence['decoy']['quote'], 'A decoy about quantum dots quantum dots')
        steered_evidence={};route={**route, '_selection_evidence':steered_evidence}
        basis=[{'key':'s1','title':self.app.store.paper('s1')['title']}]
        steered = self.app._route_pick(route, pool, scored, {}, 5, 0, [{"name": "应变弛豫", "papers": ["s3"], 'positive_basis':basis}])
        self.assertEqual([p for p in steered if p[2].startswith("explore")], [("s3", None, "explore_new", "应变弛豫"), ("decoy", None, "explore", "quantum dots")])
        self.assertEqual(steered_evidence['s3']['positive_basis'],basis)
        self.assertEqual(steered_evidence['s3']['status'],'pending_user_review')

    def test_the_targets_come_from_the_papers_under_each_direction_and_leave_out_unlike_papers(self):
        papers = self.app._project_papers_for_growth(self.pid)
        vectors, idf = __import__("app.pathgrowth", fromlist=["x"]).paper_vectors(papers)
        pool = [p for p in papers if p["key"] not in ("s1", "s2")]
        targets = self.app._exploration_targets(self.pid, pool, {k: v for k, v in vectors.items() if k not in ("s1", "s2")}, idf)
        self.assertEqual([t["name"] for t in targets], ["应变弛豫"])
        self.assertEqual(set(targets[0]["papers"]), {"s3", "s4"})

    def test_a_direction_already_on_the_map_no_longer_steers(self):
        d = self.app.route_candidates(self.pid)["candidates"]
        self.assertEqual(len(d), 1)
        graph = self.app.route_get(self.pid)["graph"]
        graph["concepts"].append({"id": "c9", "name": "应变弛豫", "terms": ["strain relaxation"], "hint": 2, "origin": "grown", "state": "active", "side": False, "candidate": "d-1"})
        self.app.route_save(self.pid, graph=graph)
        english_papers(self.app, self.pid)
        kinds = self.kinds(self.app.build_batch(limit=5, project_id=self.pid)["cards"])
        self.assertNotIn("explore_new", kinds.values())

    def test_a_direction_the_reader_turned_down_stops_steering_exploration(self):
        self.app.route_candidate_reject(self.pid, self.app.route_candidates(self.pid)["candidates"][0]["id"])
        papers = self.app._project_papers_for_growth(self.pid)
        vectors, idf = __import__("app.pathgrowth", fromlist=["x"]).paper_vectors(papers)
        self.assertEqual(self.app._exploration_targets(self.pid, [p for p in papers if p["key"] in ("s3", "s4")], vectors, idf), [])
        english_papers(self.app, self.pid)
        self.assertNotIn("explore_new", self.kinds(self.app.build_batch(limit=5, project_id=self.pid)["cards"]).values())

    def test_papers_the_reader_turned_down_since_no_longer_steer(self):
        self.app.record_feedback("s1", "irrelevant", project_id=self.pid)
        self.app.record_feedback("s2", "irrelevant", project_id=self.pid)
        self.assertEqual(self.app._visible_directions(self.pid, self.app._route_org(self.pid)._load()[1]["route"], self.app.latest_feedback(self.pid)), [])
        english_papers(self.app, self.pid)
        kinds = self.kinds(self.app.build_batch(limit=5, project_id=self.pid)["cards"])
        self.assertNotIn("explore_new", kinds.values())

    def test_without_any_direction_on_file_the_exploration_slot_is_the_ordinary_one(self):
        self.app.store.set_setting(f"route_directions_{self.pid}", {"directions": [], "judged": {}})
        english_papers(self.app, self.pid)
        kinds = self.kinds(self.app.build_batch(limit=5, project_id=self.pid)["cards"])
        self.assertNotIn("explore_new", kinds.values())
        self.assertIn("explore", kinds.values())

    def test_without_direction_or_public_purpose_unmatched_papers_do_not_fill_exploration(self):
        self.app.store.set_setting(f"route_directions_{self.pid}", {"directions": [], "judged": {}})
        english_papers(self.app, self.pid)
        with mock.patch.object(self.app, 'route_recall_sources', return_value={}):
            cards=self.app.build_batch(limit=5,project_id=self.pid)['cards']
        self.assertTrue(cards)
        self.assertEqual(set(self.kinds(cards).values()),{'route'})
        self.assertFalse({'decoy','s3','s4'} & {c['key'] for c in cards})

    def test_the_path_keeps_its_labels_when_the_readable_concepts_run_out_of_unseen_papers(self):
        for i in range(6):
            self.add(f"o{i}", f"Quantum dots and nanowires {i}", f"quantum dots nanowires photonics {i}", "journal-q")
        for _ in range(4):
            english_papers(self.app, self.pid)
            out = self.app.build_batch(limit=5, project_id=self.pid)
            kinds = self.kinds(out["cards"])
            self.assertNotIn(None, kinds.values())                          # no card without a path label, however many batches
            self.assertTrue(set(kinds.values()) <= {"route", "explore", "explore_new"})
            self.assertEqual(len(out["cards"]), 5)                          # unanswered path papers come back to fill the batch

    def test_a_paper_that_matches_a_concept_of_the_map_is_never_exploration(self):
        for i in range(3):
            self.add(f"e{i}", f"Epitaxial growth study {i}", "epitaxy epitaxial growth", "journal-e")     # a locked concept
        seen = []
        for _ in range(6):
            english_papers(self.app, self.pid)
            seen += [c["key"] for c in self.app.build_batch(limit=5, project_id=self.pid)["cards"] if c["route"]["kind"].startswith("explore")]
        self.assertFalse({"e0", "e1", "e2"} & set(seen))

    def test_every_batch_has_an_exploration_slot_when_the_pool_has_something_to_explore(self):
        english_papers(self.app, self.pid)
        first = self.kinds(self.app.build_batch(limit=5, project_id=self.pid)["cards"])
        self.assertEqual(sum(1 for v in first.values() if v in ("explore", "explore_new")), 2)   # not "from the second batch on"

    def test_the_label_is_stored_so_it_does_not_change_when_the_map_does(self):
        english_papers(self.app, self.pid)
        out = self.app.build_batch(limit=5, project_id=self.pid)
        key = next(c["key"] for c in out["cards"] if c["route"]["kind"] == "explore_new")
        self.app.store.set_setting(f"route_directions_{self.pid}", {"directions": [], "judged": {}})
        again = next(c for c in self.app.cards(out["batch_id"], self.pid) if c["key"] == key)
        self.assertEqual(again["route"]["name"], "应变弛豫")

    def test_being_shown_is_not_evidence_only_the_readers_own_response_is(self):
        english_papers(self.app, self.pid)
        self.app.build_batch(limit=5, project_id=self.pid)
        self.assertEqual(self.app.route_candidates(self.pid)["candidates"][0]["positive"], 2)   # showing s3 changed nothing
        self.assertEqual(self.app.route_candidates(self.pid)["pending"], [])
        self.app.record_feedback("s3", "useful", project_id=self.pid)
        out = self.app.route_candidates(self.pid)
        self.assertEqual(out["candidates"][0]["positive"], 2)       # still under no direction until the model judged it
        self.assertEqual([p["key"] for p in out["pending"]], ["s3"])    # it was shown as exploration and collected: waiting to be judged

    def test_an_unknown_exploration_kind_does_not_break_the_cards(self):
        english_papers(self.app, self.pid)
        out = self.app.build_batch(limit=5, project_id=self.pid)
        self.app.store.conn.execute("UPDATE exposures SET route_kind='from-the-future' WHERE batch_id=? AND route_kind='explore_new'", (out["batch_id"],))
        self.app.store.conn.commit()
        self.assertTrue(self.app.cards(out["batch_id"], self.pid))


if __name__ == "__main__":
    unittest.main()
