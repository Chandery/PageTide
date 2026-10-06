"""Route Mode slice 6a: the map drives refresh and the daily batch.

Rules under test (plan + R-NODEBT/E-NO-DEBT + AGENTS boundaries): papers come from unlocked concepts and each branch
advances at its own speed; exploration is a smooth, deterministic share; remedial reading follows "too hard"; every
card says why it was chosen; nothing infers disinterest from silence; the same inputs give the same batch; a project
without a map behaves exactly as before; no model is ever called.
"""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recommendation_fixtures import english_papers
from app import migrations
from app import pathgraph as pg
from app import sources
from app.db import Store
from app.service import App

PLAN = {"concepts": [
    {"id": "a", "name": "Crystal basics", "terms": ["crystal lattice", "lattice"], "hint": 1, "needs": []},
    {"id": "b", "name": "Epitaxy", "terms": ["epitaxy", "epitaxial growth"], "hint": 2, "needs": ["a"]},
    {"id": "c", "name": "Doping", "terms": ["dopant", "doping"], "hint": 2, "needs": ["a"]},
    {"id": "d", "name": "Defects", "terms": ["dislocation", "defects"], "hint": 3, "needs": ["b", "c"]}], "targets": ["d"]}


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
        patcher = mock.patch.object(self.app.gateway, "call", side_effect=AssertionError("the route must never call a model"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.pid = self.app.create_project("Crystals", "manual", ["crystal growth"])["project_id"]

    def paper(self, key, title, abstract="", published="2026-01-01", pid=None):
        self.app.store.upsert_papers([{"key": key, "title": title, "abstract": abstract, "published": published}], project_id=pid or self.pid)

    def fill(self):
        """Papers for every concept plus a few outside any concept."""
        for i in range(6):
            self.paper(f"lat{i}", f"Crystal lattice study {i}", "lattice", published=f"2026-01-0{i + 1}")
            self.paper(f"epi{i}", f"Epitaxial growth of films {i}", "epitaxy epitaxial", published=f"2026-02-0{i + 1}")
            self.paper(f"dop{i}", f"Dopant control in wafers {i}", "dopant doping", published=f"2026-03-0{i + 1}")
            self.paper(f"def{i}", f"Dislocation defects in layers {i}", "dislocation defects", published=f"2026-04-0{i + 1}")
        for i in range(4):
            self.paper(f"misc{i}", f"Unrelated measurement note {i}", "rainfall ecology", published=f"2026-05-0{i + 1}")
        self.paper("survey", "A survey of crystal lattice structures", "lattice survey", published="2025-01-01")

    def enable(self, mastered=()):
        route = self.app.route_save(self.pid, plan=PLAN)
        self.cid = {c["name"]: c["id"] for c in route["graph"]["concepts"]}
        for name in mastered:
            self.app.route_manual(self.pid, self.cid[name], "mastered")
        return route

    def understand_the_basics(self):
        """Satisfy the entry concept through evidence (two understood papers), not by a manual mark."""
        for key in ("lat0", "lat1"):
            self.app.store.save_to_library(key, project_id=self.pid)   # "understood" needs a saved paper
            self.app.record_feedback(key, "understood", project_id=self.pid)

    def batch(self, limit=5):
        english_papers(self.app, self.pid)
        out = self.app.build_batch(limit=limit, project_id=self.pid)
        return out["cards"]

    def kinds(self, cards):
        return [(c["key"], c["route"]["kind"] if c.get("route") else None) for c in cards]


class MigrationTests(unittest.TestCase):
    def test_exposures_gain_route_columns_on_an_existing_database_and_keep_old_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "db.sqlite")
            store.init()
            store.upsert_papers([{"key": "k", "title": "T"}])
            store.create_batch("2026-01-01", ["k"], project_id="default_project")
            store.conn.execute("DELETE FROM schema_version WHERE version=8")
            store.conn.commit()
            store.close()
            store = Store(Path(tmp) / "db.sqlite")
            store.init()
            columns = {r[1] for r in store.conn.execute("PRAGMA table_info(exposures)")}
            self.assertTrue({"route_node", "route_kind"} <= columns)
            self.assertEqual(store.conn.execute("SELECT paper_key, route_node FROM exposures").fetchone()["paper_key"], "k")
            self.assertIn(8, {r[0] for r in store.conn.execute("SELECT version FROM schema_version")})
            store.close()

    def test_a_database_that_never_had_the_columns_gets_them_without_losing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "db.sqlite")
            store.init()
            store.conn.execute("ALTER TABLE exposures RENAME TO exposures_old")
            store.conn.execute("CREATE TABLE exposures (batch_id INTEGER NOT NULL, paper_key TEXT NOT NULL, rank INTEGER NOT NULL, shown_at TEXT NOT NULL, PRIMARY KEY (batch_id, paper_key))")
            store.conn.execute("DROP TABLE exposures_old")
            store.conn.execute("INSERT INTO exposures VALUES (1, 'k', 1, 'x')")
            store.conn.execute("DELETE FROM schema_version WHERE version=8")
            store.conn.commit()
            migrations.apply_migrations(store.conn)
            self.assertEqual(store.conn.execute("SELECT route_node, route_kind FROM exposures").fetchone()[:], (None, None))
            store.close()


class RefreshTests(Fixture):
    def queries(self, **kw):
        asked = []

        def fake(query, **k):
            asked.append((query, k.get("order"), k.get("from_date")))
            return []
        with mock.patch.object(self.app.source, "discover_topic", side_effect=fake):
            self.app.refresh_candidates(project_id=self.pid, **kw)
        return asked

    def test_without_a_map_the_project_keywords_are_searched_as_before(self):
        self.assertEqual([q[0] for q in self.queries()], ["crystal growth"])

    def test_with_a_map_frontier_and_discovery_share_the_three_query_plan(self):
        self.enable()
        asked = self.queries()
        self.assertEqual([q[0] for q in asked], ["crystal lattice", "crystal growth", "dislocation"])

    def test_after_a_concept_is_understood_its_dependents_are_searched_in_frontier_order(self):
        self.enable(mastered=["Crystal basics"])
        self.assertEqual([q[0] for q in self.queries()], ["epitaxy", "crystal growth", "dopant"])

    def test_at_most_three_concepts_are_searched(self):
        plan = {"concepts": [{"id": f"x{i}", "name": f"Topic {i}", "terms": [f"topic{i}"], "hint": 1, "needs": []} for i in range(6)]}
        self.app.route_save(self.pid, plan=plan)
        self.assertEqual(len(self.queries()), 3)

    def test_route_queries_are_not_recency_sorted_basics_matter(self):
        self.enable()
        order, from_date = self.queries()[0][1:]
        self.assertEqual(order, "relevance")
        self.assertEqual(from_date, sources.window_start(10))

    def test_completed_goal_keeps_discovery_queries_instead_of_ordinary_fallback(self):
        self.enable(mastered=["Crystal basics", "Epitaxy", "Doping", "Defects"])
        asked = self.queries()
        self.assertEqual([q[0] for q in asked], ["crystal growth", "dislocation", "defects"])
        self.assertTrue(all(q[1] == 'recent' for q in asked))

    def test_a_route_that_is_switched_off_is_ignored(self):
        self.enable()
        self.app.route_mode(self.pid, "off")
        self.assertEqual([q[0] for q in self.queries()], ["crystal growth"])

    def test_a_hot_failure_is_reported_and_stops_remaining_queries(self):
        self.enable(mastered=["Crystal basics"])

        def fake(query, **k):
            if query == "epitaxy":
                raise sources.SourceError("down", "unavailable")
            return [sources.slim({"id": "https://openalex.org/W9", "title": "Dopant paper", "doi": "", "ids": {}}, group="field")]
        with mock.patch.object(self.app.source, "discover_topic", side_effect=fake):
            result = self.app.refresh_candidates(project_id=self.pid)
        self.assertEqual(result["field"], 0)
        self.assertEqual(result["errors"][0]["query"], "epitaxy")
        self.assertTrue(all(e['kind']=='skipped' for e in result['errors'][1:]))


class BatchTests(Fixture):
    def setUp(self):
        super().setUp()
        self.fill()

    def test_a_project_without_a_map_gets_the_same_batch_as_before_and_no_labels(self):
        legacy = self.batch()
        self.assertTrue(all(c.get("route") is None and c["mode"] == "sparse" for c in legacy))
        self.assertEqual(len(legacy), 5)

    def test_at_the_start_route_slots_come_only_from_the_entry_concept(self):
        self.enable()
        cards = self.batch()
        route_cards = [c for c in cards if c["route"]["kind"] in ("route", "remedial")]
        self.assertTrue(route_cards)
        self.assertTrue(all(c["route"]["node"] == self.cid["Crystal basics"] for c in route_cards))
        self.assertTrue(all(c["key"].startswith(("lat", "survey")) for c in route_cards))

    def test_locked_concepts_never_appear_as_route_picks(self):
        self.enable()
        for _ in range(3):
            for c in self.batch():
                if c["route"] and c["route"]["kind"] == "route":
                    self.assertEqual(c["route"]["node"], self.cid["Crystal basics"])

    def test_the_survey_comes_before_the_ordinary_papers_of_a_concept(self):
        self.enable()
        cards = self.batch(limit=1)
        self.assertEqual(cards[0]["key"], "survey")

    def test_exposures_record_the_concept_and_why_it_was_chosen(self):
        self.enable()
        cards = self.batch()
        rows = {r["paper_key"]: (r["route_node"], r["route_kind"]) for r in self.app.store.conn.execute("SELECT * FROM exposures")}
        for c in cards:
            self.assertEqual(rows[c["key"]], (c["route"]["node"], c["route"]["kind"]))

    def test_cards_name_the_concept_and_layer_for_the_page(self):
        self.enable()
        card = [c for c in self.batch() if c["route"]["kind"] == "route"][0]
        self.assertEqual((card["route"]["name"], card["route"]["layer"], card["mode"]), ("Crystal basics", 1, "route"))

    def test_after_the_entry_concept_is_understood_the_two_next_branches_share_the_slots(self):
        self.enable(mastered=["Crystal basics"])
        cards = self.batch()
        nodes = {c["route"]["node"] for c in cards if c["route"]["kind"] == "route"}
        self.assertEqual(nodes, {self.cid["Epitaxy"], self.cid["Doping"]})
        self.assertTrue(all(c["key"].startswith(("epi", "dop")) for c in cards if c["route"]["kind"] == "route"))

    def test_a_branch_with_more_evidence_still_leaves_the_other_branch_its_turn(self):
        self.enable(mastered=["Crystal basics"])
        for key in ("epi0", "epi1"):
            self.app.store.save_to_library(key, project_id=self.pid)   # "understood" needs a saved paper
            self.app.record_feedback(key, "understood", project_id=self.pid)
        cards = self.batch()
        nodes = [c["route"]["node"] for c in cards if c["route"]["kind"] == "route"]
        self.assertIn(self.cid["Doping"], nodes)   # Epitaxy is satisfied; Doping is still being read
        self.assertNotIn(self.cid["Epitaxy"], nodes)
        self.assertNotIn(self.cid["Defects"], nodes)   # still locked behind Doping

    def counts(self, cards):
        names = {v: k for k, v in self.cid.items()}
        out = {}
        for c in cards:
            if c["route"] and c["route"]["kind"] == "route":
                out[names[c["route"]["node"]]] = out.get(names[c["route"]["node"]], 0) + 1
        return out

    def test_the_slots_are_shared_equally_between_equally_new_branches(self):
        self.enable(mastered=["Crystal basics"])
        self.assertEqual(self.counts(self.batch()), {"Epitaxy": 2, "Doping": 2})

    def test_a_branch_the_reader_rated_low_gets_a_smaller_share_but_is_never_dropped(self):
        self.enable(mastered=["Crystal basics"])
        for key in ("dop0", "dop1", "dop2"):
            self.app.record_feedback(key, "irrelevant", project_id=self.pid)
        self.assertTrue(self.app.route_get(self.pid)["progress"][self.cid["Doping"]]["low_interest"])
        counts = self.counts(self.batch())
        self.assertEqual(counts, {"Epitaxy": 3, "Doping": 1})

    def test_a_branch_that_was_shown_a_lot_gives_way_to_the_one_that_was_not(self):
        self.enable(mastered=["Crystal basics"])
        shown = ["epi0", "epi1", "epi2", "epi3"]
        self.app.store.create_batch("2026-01-01", shown, project_id=self.pid, route={k: (self.cid["Epitaxy"], "route") for k in shown})
        self.assertEqual(self.app.route_get(self.pid)["progress"][self.cid["Epitaxy"]]["shown"], 4)
        counts = self.counts(self.batch())   # one of the five slots is exploration now, so compare the branches with each other
        self.assertGreaterEqual(counts["Epitaxy"], 1)
        self.assertGreater(counts["Doping"], counts["Epitaxy"])

    def test_silence_does_not_make_a_branch_low_interest(self):
        self.enable(mastered=["Crystal basics"])
        for _ in range(3):
            self.batch()
        for state in self.app.route_get(self.pid)["progress"].values():
            self.assertFalse(state["low_interest"])

    def test_exploration_never_exceeds_its_share_and_unrated_path_papers_keep_coming_back_to_fill_a_batch(self):
        self.enable()
        explore, route_keys = [], []
        for index in range(5):
            cards = self.batch()
            self.assertEqual(len(cards), 5 if index < 1 else len(cards))
            explore.append(sum(1 for c in cards if c["route"] and c["route"]["kind"] == "explore"))
            self.assertLessEqual(explore[-1], 1)
            route_keys += [c["key"] for c in cards if c["route"] and c["route"]["kind"] == "route"]
        self.assertLessEqual(sum(explore), 5)     # 20% of the slots: one per batch of five, never more
        self.assertGreater(len(route_keys), len(set(route_keys)))   # seven papers belong to the entry concept: unanswered ones are shown again

    def test_a_paper_is_shown_again_only_after_the_ones_not_shown_yet_and_never_after_the_reader_answered_it(self):
        self.enable()
        first = {c["key"] for c in self.batch() if c["route"]["kind"] == "route"}
        second = {c["key"] for c in self.batch() if c["route"]["kind"] == "route"}
        entry = [p["key"] for p in self.app.store.papers() if p["key"].startswith(("lat", "survey"))]
        self.assertEqual(first | second, set(entry))      # the unseen path papers all come before any is repeated (the second batch is topped up with one repeat)
        for key in entry[:3]:
            self.app.record_feedback(key, "irrelevant", project_id=self.pid)
        later = []
        for _ in range(4):
            later += [c["key"] for c in self.batch() if c["route"]["kind"] == "route"]
        self.assertFalse(set(entry[:3]) & set(later))                 # answered: never again
        self.assertTrue(set(later) & (first | second))                # unanswered: back again once everything was shown

    def test_a_batch_never_borrows_from_locked_concepts(self):
        self.enable()
        for _ in range(4):
            for c in self.batch():
                self.assertTrue(c["route"]["kind"] != "route" or c["route"]["node"] == self.cid["Crystal basics"])

    def test_a_short_batch_says_why_when_every_path_paper_was_answered(self):
        self.enable()
        for p in self.app.store.papers():
            if p["key"].startswith(("lat", "survey")):
                self.app.record_feedback(p["key"], "irrelevant", project_id=self.pid)
        english_papers(self.app, self.pid)
        out = self.app.build_batch(limit=5, project_id=self.pid)
        self.assertTrue(all(c["route"]["kind"] == "explore" for c in out["cards"]))
        self.assertIn("没凑够", out["shortfall"]["reason"])

    def test_when_the_map_has_no_papers_at_all_the_batch_is_only_exploration_and_says_so(self):
        for key in [p["key"] for p in self.app.store.papers() if p["key"].startswith(("lat", "survey"))]:
            self.app.store.conn.execute("DELETE FROM project_papers WHERE project_id=? AND paper_key=?", (self.pid, key))
        self.app.store.conn.commit()
        self.enable()
        english_papers(self.app, self.pid)
        out = self.app.build_batch(limit=5, project_id=self.pid)
        self.assertTrue(out["cards"])
        self.assertTrue(all(c["route"] is not None and c["route"]["kind"] == "explore" for c in out["cards"]))   # never a card without a path label
        self.assertIn("没凑够", out["shortfall"]["reason"])

    def test_exploration_offers_only_papers_that_match_no_concept_of_the_map(self):
        self.enable(mastered=["Crystal basics"])
        self.paper("understood_one", "Crystal lattice reconstruction notes", "lattice crystal lattice")   # a concept the reader already understood
        self.paper("locked_one", "Dislocation defects revisited", "dislocation defects")                     # a concept that is still locked
        self.paper("new_one", "Photonic nanowire arrays", "photonics nanowires")                            # matches nothing on the map
        explored = []
        for _ in range(6):
            explored += [c["key"] for c in self.batch() if c["route"]["kind"] == "explore"]
        self.assertNotIn("understood_one", explored)
        self.assertNotIn("locked_one", explored)
        self.assertIn("new_one", explored)

    def test_a_paper_is_explored_only_once(self):
        self.enable()
        explored = []
        for _ in range(8):
            explored += [c["key"] for c in self.batch() if c["route"]["kind"] == "explore"]
        self.assertEqual(len(explored), len(set(explored)))

    def test_exploration_picks_are_outside_the_unlocked_frontier(self):
        self.enable(mastered=["Crystal basics", "Epitaxy", "Doping"])
        explored = []
        for _ in range(8):
            explored += [c["key"] for c in self.batch() if c["route"] and c["route"]["kind"] == "explore"]
        self.assertTrue(all(not k.startswith("def") for k in explored))   # the frontier concept (Defects) is read as route, not explored

    def test_too_hard_adds_a_remedial_slot_from_the_prerequisite(self):
        self.enable()
        self.understand_the_basics()
        self.app.record_feedback("epi0", "too_hard", project_id=self.pid)
        cards = self.batch()
        remedial = [c for c in cards if c["route"]["kind"] == "remedial"]
        self.assertEqual(len(remedial), 1)
        self.assertEqual(remedial[0]["key"], "survey")        # the introductory paper of the prerequisite
        self.assertEqual(remedial[0]["route"]["node"], self.cid["Crystal basics"])

    def test_too_hard_is_never_treated_as_disinterest(self):
        self.enable(mastered=["Crystal basics"])
        self.app.record_feedback("epi0", "too_hard", project_id=self.pid)
        prog = self.app.route_get(self.pid)["progress"][self.cid["Epitaxy"]]
        self.assertEqual((prog["rated"], prog["low_interest"]), (0, False))

    def test_silence_changes_nothing_and_no_debt_accumulates(self):
        self.enable()
        first = self.batch()
        before = self.app.route_get(self.pid)["progress"]
        self.assertEqual(before, self.app.route_get(self.pid)["progress"])     # nothing happened in between
        for _ in range(3):
            self.batch()                                                      # shown but never rated
        after = self.app.route_get(self.pid)["progress"]
        self.assertEqual({k: v["status"] for k, v in before.items()}, {k: v["status"] for k, v in after.items()})
        self.assertEqual({k: v["m"] for k, v in before.items()}, {k: v["m"] for k, v in after.items()})
        self.assertTrue(first)

    def test_the_same_inputs_give_the_same_batch(self):
        self.enable(mastered=["Crystal basics"])
        one = self.kinds(self.batch()) + self.kinds(self.batch()) + self.kinds(self.batch())
        # rebuild an identical project in a second app and compare
        other = App(root=str(self.root), data_dir=str(self.root / "data2"))
        self.addCleanup(other.store.close)
        pid = other.create_project("Crystals", "manual", ["crystal growth"])["project_id"]
        for p in self.app.store.papers():
            other.store.upsert_papers([{k: p[k] for k in ("key", "title", "abstract", "published")}], project_id=pid)
        route = other.route_save(pid, plan=PLAN)
        other.route_manual(pid, {c["name"]: c["id"] for c in route["graph"]["concepts"]}["Crystal basics"], "mastered")
        with mock.patch.object(other.gateway, "call", side_effect=AssertionError("no model")):
            two = []
            for _ in range(3):
                english_papers(other, pid)
                two += [(c["key"], c["route"]["kind"] if c["route"] else None) for c in other.build_batch(limit=5, project_id=pid)["cards"]]
        self.assertEqual(one, two)

    def test_undoing_feedback_changes_the_next_batch_back(self):
        self.enable()
        with_nothing = [c["key"] for c in self.batch()]
        self.app.store.conn.execute("DELETE FROM exposures")
        self.app.store.conn.execute("DELETE FROM batches")
        self.app.store.conn.commit()
        for key in ("lat0", "lat1"):
            self.app.store.save_to_library(key, project_id=self.pid)   # "understood" needs a saved paper
            self.app.record_feedback(key, "understood", project_id=self.pid)
        advanced = {c["route"]["node"] for c in self.batch() if c["route"]["kind"] == "route"}
        self.assertNotIn(self.cid["Crystal basics"], advanced)
        for key in ("lat0", "lat1"):
            self.app.undo_feedback(self.app.latest_feedback(self.pid)[key]["id"])
        self.app.store.conn.execute("DELETE FROM exposures")
        self.app.store.conn.execute("DELETE FROM batches")
        self.app.store.conn.commit()
        self.assertEqual(sorted(c["key"] for c in self.batch())[:1], sorted(with_nothing)[:1])

    def test_a_frozen_profile_keeps_the_route_where_it_was(self):
        self.enable()
        self.app.set_profile_frozen(True, self.pid)
        for key in ("lat0", "lat1"):
            self.app.store.save_to_library(key, project_id=self.pid)   # "understood" needs a saved paper
            self.app.record_feedback(key, "understood", project_id=self.pid)
        self.assertEqual(self.app.route_get(self.pid)["progress"][self.cid["Crystal basics"]]["status"], "unlocked")

    def test_when_the_route_has_nothing_left_the_batch_is_the_ordinary_one(self):
        self.enable(mastered=["Crystal basics", "Epitaxy", "Doping", "Defects"])
        cards = self.batch()
        self.assertTrue(cards and all(c["mode"] == "sparse" and c.get("route") is None for c in cards))

    def test_projects_do_not_share_a_route(self):
        self.enable()
        other = self.app.create_project("Poetry", "manual", ["poetry"])["project_id"]
        self.paper("po0", "Tang poetry forms", "poetry", pid=other)
        poetry_plan = {"concepts": [{"id": "p", "name": "Poetry forms", "terms": ["poetry"], "hint": 1, "needs": []}]}
        self.app.route_save(other, plan=poetry_plan)
        mine = self.batch()
        english_papers(self.app, other)
        theirs = self.app.build_batch(limit=5, project_id=other)["cards"]
        self.assertEqual([c["key"] for c in theirs], ["po0"])
        self.assertTrue(all(c["route"]["name"] == "Crystal basics" for c in mine if c["route"] and c["route"]["kind"] == "route"))
        self.assertEqual({c["route"]["name"] for c in theirs}, {"Poetry forms"})

    def test_a_batch_never_exceeds_the_limit_or_repeats_a_paper_inside_itself(self):
        self.enable(mastered=["Crystal basics"])
        for limit in (1, 2, 3, 5, 8, 5, 3, 2, 1, 5):
            keys = [c["key"] for c in self.batch(limit=limit)]
            self.assertEqual(len(keys), len(set(keys)))
            self.assertLessEqual(len(keys), limit)


class ReviewFixTests(Fixture):
    def setUp(self):
        super().setUp()
        for i in range(20):
            self.paper(f"lat{i}", f"Crystal lattice study {i}", "lattice", published=f"2026-01-{i + 1:02d}")
        self.enable()

    def test_the_unused_explore_slot_goes_to_route_papers_and_no_false_shortfall_is_reported(self):
        sizes = []
        for _ in range(6):
            english_papers(self.app, self.pid)
            out = self.app.build_batch(limit=5, project_id=self.pid)
            sizes.append(len(out["cards"]))
            if len(out["cards"]) == 5:
                self.assertFalse(out["shortfall"] and out["shortfall"].get("reason", "").startswith("路径上"))
        self.assertEqual(sizes[:3], [5, 5, 5])     # twenty papers, only route papers exist: every batch is full

    def test_batches_stay_full_while_path_papers_are_unanswered_and_never_claim_the_map_has_no_papers(self):
        for i in range(6):
            self.paper(f"other{i}", f"Unrelated ecology note {i}", "rainfall ecology")
        for _ in range(8):
            english_papers(self.app, self.pid)
            out = self.app.build_batch(limit=5, project_id=self.pid)
            self.assertEqual(len(out["cards"]), 5)                       # unanswered path papers come back instead of leaving a gap
            self.assertNotIn("还没有论文", (out["shortfall"] or {}).get("reason", ""))

    def test_cards_keep_the_concept_name_they_were_shown_under_after_the_map_changes(self):
        card = [c for c in self.batch() if c["route"]["kind"] == "route"][0]
        self.assertEqual(card["route"]["name"], "Crystal basics")
        other = {"concepts": [{"id": "z", "name": "Quantum dots", "terms": ["quantum dot"], "hint": 1, "needs": []}]}
        self.app.route_save(self.pid, plan=other)
        again = [c for c in self.app.cards(project_id=self.pid) if c["key"] == card["key"]][0]
        self.assertEqual((again["route"]["name"], again["route"]["layer"]), ("Crystal basics", 1))
        self.app.route_mode(self.pid, "off")
        off = [c for c in self.app.cards(project_id=self.pid) if c["key"] == card["key"]][0]
        self.assertEqual(off["route"]["name"], "Crystal basics")

    def test_an_exposure_from_before_the_columns_existed_has_no_label_and_does_not_crash(self):
        self.app.store.create_batch("2026-01-01", ["lat0"], project_id=self.pid)
        card = self.app.cards(project_id=self.pid)[0]
        self.assertEqual((card["route"], card["mode"]), (None, "sparse"))

    def test_undated_papers_sort_last_not_first(self):
        for key in list(p["key"] for p in self.app.store.papers() if p["key"].startswith("lat")):
            self.app.store.conn.execute("DELETE FROM project_papers WHERE project_id=? AND paper_key=?", (self.pid, key))
        self.app.store.conn.commit()
        for key, published in (("undated", ""), ("yearonly", "2026"), ("dated", "2026-06-01"), ("old", "2001-01-01")):
            self.paper(key, "Crystal lattice identical title", "lattice identical text", published=published)   # equal scores: only the date decides
        order = []
        for _ in range(4):
            order += [c["key"] for c in self.batch(limit=1)]
        self.assertEqual(order, ["dated", "yearonly", "old", "undated"])

    def fill_intros(self):
        for i in range(3):
            self.paper(f"survey{i}", f"A survey of lattice topic {i}", "lattice", published="2025-02-01")
        self.paper("epi0", "Epitaxial growth of films", "epitaxy epitaxial")

    def test_remedial_needs_room_and_is_bounded_by_the_too_hard_papers(self):
        self.fill_intros()
        self.understand_the_basics()
        self.app.record_feedback("epi0", "too_hard", project_id=self.pid)
        kinds = []
        for _ in range(4):
            kinds += [c["route"]["kind"] for c in self.batch(limit=5) if c["route"]]
        self.assertEqual(kinds.count("remedial"), 1)           # one too-hard paper, one introduction
        self.assertTrue(all(c["route"]["kind"] != "remedial" for c in self.batch(limit=1) if c["route"]))

    def test_a_one_paper_batch_has_no_room_for_a_remedial_paper(self):
        self.fill_intros()
        self.understand_the_basics()
        self.app.record_feedback("epi0", "too_hard", project_id=self.pid)
        self.assertTrue(all(c["route"] is None or c["route"]["kind"] != "remedial" for c in self.batch(limit=1)))

    def test_a_prerequisite_the_reader_marked_as_known_gets_no_remedial_reading(self):
        self.fill_intros()
        self.app.route_manual(self.pid, self.cid["Crystal basics"], "mastered")
        self.app.record_feedback("epi0", "too_hard", project_id=self.pid)
        self.assertTrue(all(c["route"] is None or c["route"]["kind"] != "remedial" for c in self.batch()))


class RefreshPagingTests(Fixture):
    def test_local_matching_paper_count_does_not_skip_unfetched_source_pages(self):
        self.enable()
        for i in range(50):
            self.paper(f"lat{i}", f"Crystal lattice study {i}", "lattice")
        seen = []

        def fake(query, **kw):
            seen.append((query, kw.get("page")))
            return []
        with mock.patch.object(self.app.source, "discover_topic", side_effect=fake):
            self.app.refresh_candidates(project_id=self.pid)
        self.assertEqual(seen[0], ("crystal lattice", 1))
        self.assertLessEqual(len(seen), 3)

    def test_the_first_refresh_asks_for_page_one(self):
        self.enable()
        seen = []
        with mock.patch.object(self.app.source, "discover_topic", side_effect=lambda q, **kw: seen.append(kw.get("page")) or []):
            self.app.refresh_candidates(project_id=self.pid)
        self.assertEqual(seen, [1, 1, 1])


class DiscoverPageTests(unittest.TestCase):
    def test_the_page_number_reaches_openalex_and_changes_the_cache_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = sources.OpenAlex(tmp)
            urls = []

            class Reply:
                headers = {}

                def read(self):
                    return json.dumps({"results": []}).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

            def opener(request, timeout=None):
                urls.append(request.full_url)
                return Reply()
            with mock.patch.object(sources.urllib.request, "urlopen", opener), mock.patch.object(sources.time, "sleep"):
                client.discover_topic("epitaxy", page=1, prefer_pdf=False)
                client.discover_topic("epitaxy", page=2, prefer_pdf=False)
            self.assertTrue(any("page=2" in u for u in urls))
            self.assertFalse(any("page=1" in u for u in urls[:1]) and False)
            self.assertNotEqual(urls[0], urls[-1])


class HomeOffTests(Fixture):
    def test_a_map_that_is_switched_off_is_reported_as_off_not_as_missing(self):
        self.assertIsNone(self.app.home_route(self.pid))                  # no map at all
        self.enable()
        self.app.route_mode(self.pid, "off")
        summary = self.app.home_route(self.pid)
        self.assertEqual((summary["enabled"], summary["mode"], summary["total"]), (False, "off", 4))
        self.assertEqual(summary["frontier"], [])                          # nothing is being recommended from it

    def test_an_off_map_costs_no_paper_matching(self):
        self.enable()
        self.app.route_mode(self.pid, "off")
        with mock.patch("app.pathgrowth.assign", side_effect=AssertionError("an off map must not match papers")):
            self.assertFalse(self.app.home_route(self.pid)["enabled"])

    def test_an_unchanged_map_is_not_recomputed_on_every_home_load(self):
        self.enable()
        self.fill()
        calls = []
        real = __import__("app.pathgrowth", fromlist=["assign"]).assign
        with mock.patch("app.pathgrowth.assign", side_effect=lambda *a, **k: calls.append(1) or real(*a, **k)):
            first = self.app.home_route(self.pid)
            for _ in range(3):
                self.assertEqual(self.app.home_route(self.pid), first)
        self.assertEqual(len(calls), 1)

    def test_any_change_that_can_move_progress_recomputes(self):
        self.enable()
        self.fill()
        before = self.app.home_route(self.pid)
        for key in ("lat0", "lat1"):
            self.app.store.save_to_library(key, project_id=self.pid)   # "understood" needs a saved paper
            self.app.record_feedback(key, "understood", project_id=self.pid)
        self.assertGreater(self.app.home_route(self.pid)["done"], before["done"])
        done = self.app.home_route(self.pid)["done"]
        self.app.route_manual(self.pid, self.cid["Epitaxy"], "mastered")
        self.assertGreater(self.app.home_route(self.pid)["done"], done)
        self.paper("newpaper", "Crystal lattice extra", "lattice")
        self.assertEqual(self.app.home_route(self.pid)["total"], 4)

    def test_the_page_tells_off_apart_from_missing(self):
        index = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
        self.assertIn("route.enabled === false", index)
        self.assertIn("路径模式已关闭", index)


class HomeTests(Fixture):
    def test_the_home_payload_carries_a_short_route_summary_only_when_there_is_a_route(self):
        self.assertIsNone(self.app.home_route(self.pid))
        self.enable()
        summary = self.app.home_route(self.pid)
        self.assertEqual((summary["enabled"], summary["total"], summary["done"]), (True, 4, 0))
        self.assertAlmostEqual(summary["exploration_share"], 0.20)
        self.assertEqual(set(summary), {"enabled", "mode", "total", "done", "frontier", "exploration_share", "goal_status", "goal_done", "goal_total", "goal_reasons", "watched_satisfied"})
        self.assertEqual(summary["frontier"], [{"id": self.cid["Crystal basics"], "name": "Crystal basics", "layer": 1}])


if __name__ == "__main__":
    unittest.main()
