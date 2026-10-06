"""Exploration that points at a direction that is forming: the papers of a potential new direction get the
exploration slots first, and the card says so. The reader's explicit feedback on such a paper is the evidence
that makes the direction grow; being shown a paper is not evidence of anything."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
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
        self.addCleanup(self.app.store.close)
        self.pid = self.app.create_project("Crystals", "manual", ["epitaxy"])["project_id"]
        self.app.route_save(self.pid, plan=PLAN)
        for i in range(8):   # papers of the readable concept: the route has plenty to show
            self.add(f"cb{i}", f"Crystal growth and lattice basics {i}", "crystal growth lattice", f"journal-{i % 3}")
        # four papers of a direction the map does not cover; two of them the reader has already marked useful
        for i, source in enumerate(("journal-a", "journal-b", "journal-a", "journal-b"), start=1):
            self.add(f"s{i}", f"Strain relaxation by misfit dislocation glide {i}",
                     "strain relaxation by misfit dislocation glide in thin films", source)
        # a paper outside the map that the profile will like better than the direction's papers
        self.add("decoy", "A decoy about quantum dots", "quantum dots")
        self.app.record_feedback("s1", "useful", project_id=self.pid)
        self.app.record_feedback("s2", "useful", project_id=self.pid)

    def add(self, key, title, abstract, source="arXiv"):
        self.app.store.upsert_papers([{"key": key, "title": title, "abstract": abstract, "source": source, "published": "2026-02-01"}], project_id=self.pid)

    def kinds(self, cards):
        return {c["key"]: (c["route"] or {}).get("kind") for c in cards}


class ExploreNewTests(Fixture):
    def test_the_exploration_slot_goes_to_a_paper_of_a_forming_direction(self):
        cards = self.app.build_batch(limit=5, project_id=self.pid)["cards"]
        kinds = self.kinds(cards)
        explored = [k for k, v in kinds.items() if v in ("explore", "explore_new")]
        self.assertEqual(len(explored), 1)
        self.assertIn(explored[0], ("s3", "s4"))   # a paper of the direction, not the decoy the profile likes better
        card = next(c for c in cards if c["route"]["kind"] == "explore_new")
        self.assertEqual(card["route"]["name"], "strain relaxation")
        self.assertIsNone(card["route"]["node"])

    def test_it_is_chosen_over_a_paper_the_profile_likes_more(self):
        route = self.app._route_state(self.pid)
        pool = [dict(self.app.store.paper(k)) for k in ("decoy", "s3", "cb0", "cb1", "cb2", "cb3", "cb4")]
        scored = [("decoy", 0.9), ("s3", 0.4)] + [(f"cb{i}", 0.3) for i in range(5)]
        _, _, _, found, _ = self.app._route_candidates(self.pid)
        plain = self.app._route_pick(route, pool, scored, {}, 5, 0, ())
        steered = self.app._route_pick(route, pool, scored, {}, 5, 0, found)
        self.assertIn(("decoy", None, "explore", None), plain)
        self.assertEqual([p for p in steered if p[2].startswith("explore")], [("s3", None, "explore_new", "strain relaxation")])

    def test_directions_are_computed_once_while_nothing_they_depend_on_changes(self):
        real = self.app._route_candidates
        calls = []
        self.app._route_candidates = lambda *a, **k: (calls.append(1), real(*a, **k))[1]
        self.app.build_batch(limit=5, project_id=self.pid)
        self.app.build_batch(limit=5, project_id=self.pid)
        self.assertEqual(len(calls), 1)
        self.app.record_feedback("s3", "useful", project_id=self.pid)    # new evidence: recomputed
        self.app.build_batch(limit=5, project_id=self.pid)
        self.assertEqual(len(calls), 2)

    def test_without_any_forming_direction_the_exploration_slot_is_the_ordinary_one(self):
        self.app.route_candidate_reject(self.pid, next(c["id"] for c in self.app.route_candidates(self.pid)["candidates"]))
        kinds = self.kinds(self.app.build_batch(limit=5, project_id=self.pid)["cards"])
        self.assertNotIn("explore_new", kinds.values())
        self.assertIn("explore", kinds.values())

    def test_every_batch_has_an_exploration_slot_when_the_pool_has_something_to_explore(self):
        first = self.kinds(self.app.build_batch(limit=5, project_id=self.pid)["cards"])
        self.assertEqual(sum(1 for v in first.values() if v in ("explore", "explore_new")), 1)   # not "from the second batch on"

    def test_the_label_is_stored_so_it_does_not_change_when_the_map_does(self):
        out = self.app.build_batch(limit=5, project_id=self.pid)
        key = next(c["key"] for c in out["cards"] if c["route"]["kind"] == "explore_new")
        self.app.route_candidate_reject(self.pid, next(c["id"] for c in self.app.route_candidates(self.pid)["candidates"]))
        again = next(c for c in self.app.cards(out["batch_id"], self.pid) if c["key"] == key)
        self.assertEqual(again["route"]["name"], "strain relaxation")

    def test_being_shown_is_not_evidence_only_the_readers_own_response_is(self):
        self.app.build_batch(limit=5, project_id=self.pid)
        before = self.app.route_candidates(self.pid)["candidates"][0]["positive"]
        self.assertEqual(before, 2)   # showing s3 changed nothing
        self.app.record_feedback("s3", "useful", project_id=self.pid)
        self.assertEqual(self.app.route_candidates(self.pid)["candidates"][0]["positive"], 3)

    def test_an_unknown_exploration_kind_does_not_break_the_cards(self):
        out = self.app.build_batch(limit=5, project_id=self.pid)
        self.app.store.conn.execute("UPDATE exposures SET route_kind='from-the-future' WHERE batch_id=? AND route_kind='explore_new'", (out["batch_id"],))
        self.app.store.conn.commit()
        self.assertTrue(self.app.cards(out["batch_id"], self.pid))


if __name__ == "__main__":
    unittest.main()
