"""The suggestion review: look at what is saved, propose only changes, never redo what was reviewed.

Everything here is deterministic and offline; no model is involved.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import Store
from app.organization import Conflict, Organization, _dump
from app.organization_facets import paper_signature, review
from app.project import ProjectManager

PAPERS = [
    {"key": "w1", "title": "World model learning for planning", "abstract": "world model latent dynamics"},
    {"key": "w2", "title": "Video world model prediction", "abstract": "world model video prediction"},
    {"key": "r1", "title": "Robot manipulation with imitation", "abstract": "robot manipulation imitation learning"},
    {"key": "r2", "title": "Robot grasping from demonstrations", "abstract": "robot grasping demonstrations"},
    {"key": "x1", "title": "Quantum error correction codes", "abstract": "quantum codes"},
]


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = Store(Path(tmp.name) / "t.sqlite")
        self.store.init()
        self.addCleanup(self.store.close)
        self.store.upsert_papers(PAPERS)
        for paper in PAPERS:
            self.store.save_to_library(paper["key"])
        self.org = Organization(self.store)

    def direction(self, name, parent=None, color="#123456"):
        body = {"action": "direction-save", "name": name, "color": color}
        if parent:
            body["parent_id"] = parent
        return self.org.action(body)["directions"][-1]["id"]

    def place(self, keys, *ids):
        self.org.action({"action": "membership", "keys": keys, "add": list(ids)})

    def suggest(self, **extra):
        return self.org.action({"action": "suggest", **extra})["suggestions"]

    def apply(self, preview, groups=True, merges=(), moves=(), finish=False, dismissed=()):
        body = {"dismissed": [m["id"] for m in preview["moves"]] if dismissed is True else list(dismissed),
                "action": "apply-suggestions", "apply_mode": "add", "fingerprint": preview["fingerprint"],
                "suggestions": [{k: g[k] for k in ("id", "name", "color", "keys")} for g in preview["groups"]] if groups else [],
                "merges": [m["id"] for m in preview["merges"]] if merges is True else list(merges),
                "moves": [m["id"] for m in preview["moves"]] if moves is True else list(moves)}
        if finish:
            body["finish"] = True
        return self.org.action(body)

    def memberships(self):
        return {p["key"]: p["directions"] for p in self.org.snapshot()["items"]}

    def directions(self):
        return self.org.snapshot()["directions"]


class UnplacedTests(Fixture):
    def test_pending_reasons_identify_missing_metadata_and_single_paper_local_limit(self):
        blank = review([{'key':'missing','title':'','abstract':''}], [], {}, {})
        self.assertEqual(blank['pending_details'], [{'key':'missing','code':'metadata_missing'}])
        single = review([{'key':'single','title':'World models for planning','abstract':''}], [], {}, {})
        self.assertEqual(single['pending_details'], [{'key':'single','code':'insufficient_group'}])
        unknown = review([{'key':'one','title':'Novel chemistry','abstract':''},
                          {'key':'two','title':'Unknown mineral','abstract':''}], [], {}, {})
        self.assertEqual({p['code'] for p in unknown['pending_details']}, {'no_matching_terms'})

    def test_first_review_proposes_new_categories_and_a_second_review_after_applying_proposes_nothing(self):
        first = self.suggest()
        self.assertTrue(first["groups"])
        self.assertTrue(all(g["kind"] == "create" and g["target"] is None for g in first["groups"]))
        self.apply(first)
        placed = {k for k, ids in self.memberships().items() if ids}
        self.assertTrue({"w1", "w2"} <= placed or {"r1", "r2"} <= placed)
        second = self.suggest()
        self.assertEqual((second["groups"], second["merges"], second["moves"]), ([], [], []))   # nothing to say about what was done

    def test_a_paper_that_mentions_an_existing_category_is_added_to_it_not_to_a_new_duplicate(self):
        world = self.direction("World model")
        self.place(["w1"], world)
        preview = self.suggest()
        adds = [g for g in preview["groups"] if g["kind"] == "add"]
        self.assertTrue(any(g["target"] == world and "w2" in g["keys"] for g in adds))
        before = len(self.directions())
        self.apply(preview)
        self.assertIn(world, self.memberships()["w2"])
        names = [d["name"].lower() for d in self.directions()]
        self.assertEqual(names.count("world model"), 1)                      # never a second category of the same name
        self.assertGreaterEqual(len(self.directions()), before)

    def test_a_category_made_by_hand_after_a_review_makes_it_stale_and_the_next_review_offers_it_instead_of_a_copy(self):
        preview = self.suggest()
        create = next(g for g in preview["groups"] if g["kind"] == "create")
        existing = self.direction(create["name"])                            # created by hand after the preview
        with self.assertRaises(Conflict):
            self.apply(preview)
        again = self.suggest()
        mine = [g for g in again["groups"] if g["name"].lower() == create["name"].lower()]
        self.assertTrue(mine and all(g["kind"] == "add" and g["target"] == existing for g in mine))
        self.apply(again)
        same = [d for d in self.directions() if d["name"].lower() == create["name"].lower() and d.get("parent_id") is None]
        self.assertEqual([d["id"] for d in same], [existing])

    def test_unplaced_papers_are_always_looked_at(self):
        first = self.suggest()
        again = self.suggest()
        self.assertTrue(again["groups"])
        self.assertEqual([(g["name"], g["keys"]) for g in first["groups"]], [(g["name"], g["keys"]) for g in again["groups"]])   # nothing was applied, so the same proposals stand


class MergeTests(Fixture):
    def duplicates(self):
        a, b, c = self.direction("Robotics"), self.direction("robotics"), self.direction("Robotics")
        self.place(["r1"], a)
        self.place(["r2"], b)
        self.place(["x1"], c)
        return a, b, c

    def test_same_name_at_the_same_level_is_offered_as_one_merge_that_keeps_the_biggest(self):
        a, b, c = self.duplicates()
        self.place(["w1"], a)
        preview = self.suggest()
        self.assertEqual(len(preview["merges"]), 1)
        merge = preview["merges"][0]
        self.assertEqual(merge["keep"], a)                                   # two papers beat one
        self.assertEqual(sorted(merge["drop"]), sorted([b, c]))
        self.assertIn("3", merge["reason"])
        self.assertEqual([(c_["id"], c_["papers"]) for c_ in merge["copies"]][0], (a, 2))   # each copy with its paper count, the kept one first
        self.assertEqual(len(merge["copies"]), 3)

    def test_applying_a_merge_moves_papers_reparents_children_removes_the_extras_and_can_be_undone(self):
        a, b, c = self.duplicates()
        child = self.direction("Grasping", parent=b)
        self.place(["r2"], child)
        preview = self.suggest()
        before = self.org.snapshot()
        self.apply(preview, groups=False, merges=True)
        after = self.org.snapshot()
        ids = {d["id"] for d in after["directions"]}
        self.assertIn(a, ids)
        self.assertFalse({b, c} & ids)
        self.assertEqual(next(d for d in after["directions"] if d["id"] == child)["parent_id"], a)
        members = self.memberships()
        self.assertIn(a, members["r2"])
        self.assertIn(a, members["x1"])
        self.assertEqual(self.suggest()["merges"], [])                       # done: nothing more to merge
        undone = self.org.action({"action": "undo"})
        self.assertEqual(sorted(d["id"] for d in undone["directions"]), sorted(d["id"] for d in before["directions"]))
        self.assertEqual({p["key"]: p["directions"] for p in undone["items"]}, {p["key"]: p["directions"] for p in before["items"]})

    def test_same_name_under_different_parents_is_not_a_duplicate(self):
        top = self.direction("Robotics")
        parent = self.direction("Embodied")
        self.direction("Robotics", parent=parent)
        self.place(["r1"], top)
        self.assertEqual(self.suggest()["merges"], [])

    def test_a_merge_the_person_leaves_unticked_is_not_applied(self):
        self.duplicates()
        preview = self.suggest()
        count = len(self.directions())
        self.apply(preview, groups=False, merges=[], finish=True)
        self.assertEqual(len(self.directions()), count)


class MoveTests(Fixture):
    def test_a_paper_whose_category_is_not_in_its_text_but_another_is_gets_a_move_proposal(self):
        world, robot = self.direction("World model"), self.direction("Robot manipulation")
        self.place(["r1"], world)                                           # r1 is about robots, filed under world models
        self.place(["w1"], world)
        preview = self.suggest()
        moves = [m for m in preview["moves"] if m["key"] == "r1"]
        self.assertEqual(len(moves), 1)
        self.assertEqual((moves[0]["from"], moves[0]["to"]), ([world], robot))
        self.assertIn("World model", moves[0]["reason"])
        self.assertFalse([m for m in preview["moves"] if m["key"] == "w1"])   # w1 fits where it is: not mentioned at all

    def test_applying_a_move_changes_the_membership_protects_the_paper_and_can_be_undone(self):
        world, robot = self.direction("World model"), self.direction("Robot manipulation")
        self.place(["r1", "w1"], world)
        preview = self.suggest()
        self.apply(preview, groups=False, moves=True)
        self.assertEqual(self.memberships()["r1"], [robot])
        self.assertEqual(self.memberships()["w1"], [world])
        self.assertEqual(self.suggest()["moves"], [])
        undone = self.org.action({"action": "undo"})
        self.assertEqual({p["key"]: p["directions"] for p in undone["items"]}["r1"], [world])

    def test_a_category_the_matcher_cannot_read_is_never_judged(self):
        from app.organization_facets import _variants
        name = "某个自定义方向"                                              # a Chinese name with no glossary entry: unknown, not wrong
        self.assertEqual(_variants(name), [])
        chinese = self.direction(name)
        self.direction("Robot manipulation")
        self.place(["r1"], chinese)
        self.assertEqual(self.suggest()["moves"], [])

    def test_a_paper_with_some_fitting_category_is_left_alone(self):
        world, robot, imitation = self.direction("World model"), self.direction("Robot manipulation"), self.direction("Imitation learning")
        self.place(["r1"], world, robot)                                    # robot fits; imitation also fits but r1 is already well placed
        self.assertEqual([m for m in self.suggest()["moves"] if m["key"] == "r1"], [])

    def test_a_move_that_empties_a_category_removes_it_like_any_membership_edit(self):
        world, robot = self.direction("World model"), self.direction("Robot manipulation")
        self.place(["r1"], world)
        self.apply(self.suggest(), groups=False, moves=True)
        self.assertNotIn(world, {d["id"] for d in self.directions()})


class ReviewedMemoryTests(Fixture):
    def setUp(self):
        super().setUp()
        self.world, self.robot = self.direction("World model"), self.direction("Robot manipulation")
        self.place(["r1"], self.world)
        self.place(["r2", "w1", "w2"], self.world)

    def test_a_declined_proposal_is_not_proposed_again_until_the_paper_changes(self):
        first = self.suggest()
        self.assertTrue([m for m in first["moves"] if m["key"] == "r1"])
        self.apply(first, groups=False, moves=[], dismissed=True, finish=True)   # the person says: leave r1 where it is
        again = self.suggest()
        self.assertEqual(again["moves"], [])
        self.assertNotIn("r1", again["evaluated"])
        self.store.conn.execute("UPDATE papers SET abstract='robot manipulation changed' WHERE key='r1'")
        self.store.conn.commit()
        changed = self.suggest()
        self.assertIn("r1", changed["evaluated"])                            # its text changed, so it is looked at again

    def test_a_change_of_categories_makes_a_paper_due_again(self):
        self.apply(self.suggest(), groups=False, moves=[], dismissed=True, finish=True)
        self.assertNotIn("w1", self.suggest()["evaluated"])
        self.place(["w1"], self.robot)
        self.assertIn("w1", self.suggest()["evaluated"])

    def test_nothing_to_change_marks_the_organised_papers_reviewed_without_asking(self):
        for key in ("r1", "r2"):
            self.org.action({"action": "membership", "keys": [key], "remove": [self.world]})
        self.place(["r1", "r2"], self.robot)
        first = self.suggest()
        self.assertEqual((first["groups"], first["merges"], first["moves"]), ([], [], []))
        self.assertTrue(first["evaluated"])
        self.assertEqual(self.suggest()["evaluated"], [])                    # not looked at twice

    def test_the_marks_live_in_the_organization_data_are_exported_and_undone_with_the_change(self):
        first = self.suggest()
        self.apply(first, groups=False, moves=True)
        exported = self.org.action({"action": "export"})["organization"]
        self.assertTrue(exported["reviewed"])
        self.org.action({"action": "undo"})
        self.assertEqual(self.org.action({"action": "export"})["organization"].get("reviewed", {}), {})

    def test_the_signature_depends_on_text_and_categories_only(self):
        row = {"title": "T", "abstract": "A", "topic": ""}
        base = paper_signature(row, ["d1"])
        self.assertEqual(base, paper_signature(dict(row), ["d1"]))
        self.assertEqual(base, paper_signature(dict(row), [1 and "d1"]))
        self.assertNotEqual(base, paper_signature(dict(row, abstract="B"), ["d1"]))
        self.assertNotEqual(base, paper_signature(row, ["d1", "d2"]))

    def test_an_unticked_move_is_not_a_no_it_comes_back_until_it_is_applied_or_dismissed_on_purpose(self):
        first = self.suggest()
        self.assertTrue([m for m in first["moves"] if m["key"] == "r1"])
        self.apply(first, groups=False, moves=[], finish=True)               # clicked apply with the move left unticked
        again = self.suggest()
        self.assertTrue([m for m in again["moves"] if m["key"] == "r1"])    # silence is not an answer
        self.assertIn("r1", again["evaluated"])
        self.assertNotIn("r2", again["evaluated"])                           # papers with nothing to say were marked

    def test_merges_and_additions_are_not_remembered_only_move_dismissals_are(self):
        a, b = self.direction("Alpha"), self.direction("alpha")
        self.place(["x1"], a)
        first = self.suggest()
        self.assertTrue(first["merges"])
        self.apply(first, groups=False, merges=[], finish=True)
        self.assertTrue(self.suggest()["merges"])                            # still offered: unticking a merge does not hide it


class SafetyTests(Fixture):
    def test_merge_and_move_ids_must_come_from_the_stored_preview(self):
        world, robot = self.direction("World model"), self.direction("Robot manipulation")
        self.place(["r1"], world)
        preview = self.suggest()
        base = {"action": "apply-suggestions", "apply_mode": "add", "fingerprint": preview["fingerprint"], "suggestions": []}
        with self.assertRaises(ValueError):
            self.org.action({**base, "moves": ["move-forged"]})
        with self.assertRaises(ValueError):
            self.org.action({**base, "merges": ["merge-forged"]})
        with self.assertRaises(ValueError):
            self.org.action({**base, "moves": [preview["moves"][0]["id"]] * 2})
        self.assertEqual(self.memberships()["r1"], [world])

    def test_a_stale_corpus_is_refused_for_merges_and_moves_too(self):
        world, robot = self.direction("World model"), self.direction("Robot manipulation")
        self.place(["r1"], world)
        preview = self.suggest()
        self.store.conn.execute("UPDATE papers SET abstract='edited' WHERE key='r1'")
        self.store.conn.commit()
        with self.assertRaises(Conflict):
            self.apply(preview, groups=False, moves=True)

    def test_an_empty_choice_without_finish_is_refused(self):
        self.direction("World model")
        preview = self.suggest()
        with self.assertRaises(ValueError):
            self.apply(preview, groups=False)

    def test_a_dropped_category_in_a_move_follows_the_merge(self):
        a, b = self.direction("Robot manipulation"), self.direction("robot manipulation")
        world = self.direction("World model")
        self.place(["r1"], world)
        self.place(["r2"], b)
        preview = self.suggest()
        self.assertTrue(preview["merges"])
        moves = [m for m in preview["moves"] if m["key"] == "r1"]
        self.assertTrue(moves)
        keep = preview["merges"][0]["keep"]
        self.assertIn(keep, (a, b))
        self.apply(preview, groups=False, merges=True, moves=True)
        self.assertEqual(self.memberships()["r1"], [keep])                   # whichever copy the move named, it ends in the one the merge kept
        self.assertEqual(len([d for d in self.directions() if d["name"].lower() == "robot manipulation"]), 1)


class ScopeTests(Fixture):
    def setUp(self):
        super().setUp()
        manager = ProjectManager(self.store)
        self.one, self.two = manager.create_project("One"), manager.create_project("Two")
        for key in ("w1", "w2"):
            self.store.add_project_paper(self.one, key)
            self.store.save_to_library(key, project_id=self.one)
        for key in ("r1", "r2"):
            self.store.add_project_paper(self.two, key)
            self.store.save_to_library(key, project_id=self.two)

    def test_a_review_for_a_project_only_looks_at_that_projects_papers(self):
        preview = self.suggest(scope_project=self.one)
        keys = {k for g in preview["groups"] for k in g["keys"]}
        self.assertTrue(keys and keys <= {"w1", "w2"})
        self.assertEqual(preview["scope"], self.one)
        self.assertEqual(preview["scope_size"], 2)

    def test_a_paper_saved_by_another_project_does_not_make_the_preview_stale_or_unappliable(self):
        preview = self.suggest(scope_project=self.one)
        self.store.add_project_paper(self.two, "x1")
        self.store.save_to_library("x1", project_id=self.two)
        self.assertFalse(self.org.snapshot()["suggestions"]["stale"])
        self.apply(preview)                                                  # still applies: its own papers did not change

    def test_a_paper_saved_by_the_same_project_makes_it_stale(self):
        preview = self.suggest(scope_project=self.one)
        self.store.add_project_paper(self.one, "x1")
        self.store.save_to_library("x1", project_id=self.one)                # this project's own paper: stale
        self.assertTrue(self.org.snapshot()["suggestions"]["stale"])
        with self.assertRaises(Conflict):
            self.apply(preview)


class StructureTests(Fixture):
    """A preview rests on the shape of the shared categories; if that shape changes it is refused, and what it would
    still do with a shape that changed unnoticed is skipped, not guessed."""

    def test_a_category_edit_after_the_review_refuses_the_apply(self):
        a, b = self.direction("Robotics"), self.direction("robotics")
        self.place(["r1"], a)
        preview = self.suggest()
        self.direction("Another")
        self.assertTrue(self.org.snapshot()["suggestions"]["stale"])
        with self.assertRaises(Conflict):
            self.apply(preview, groups=False, merges=True)

    def test_a_merge_never_makes_a_category_its_own_parent_even_if_the_shape_changed_unnoticed(self):
        a, b = self.direction("Robotics"), self.direction("robotics")
        self.place(["r1"], a)
        self.place(["r2"], b)
        with patch("app.organization.structure_hash", return_value="same"), patch("app.organization_facets.structure_hash", return_value="same"):
            preview = self.suggest()
            merge = preview["merges"][0]
            keep, drop = merge["keep"], merge["drop"][0]
            self.org.action({"action": "direction-save", "id": keep, "name": "Robotics", "color": "#123456", "parent_id": drop})   # the kept one moved under the other
            self.apply(preview, groups=False, merges=True)
        after = {d["id"]: d for d in self.directions()}
        self.assertTrue(all(d.get("parent_id") != d["id"] for d in after.values()))
        self.assertIn(keep, after)
        self.assertIn(drop, after)                                          # different levels now: the merge was skipped, not forced

    def test_an_addition_for_a_category_that_vanished_is_skipped_not_recreated(self):
        world = self.direction("World model")
        self.place(["w1"], world)
        with patch("app.organization.structure_hash", return_value="same"), patch("app.organization_facets.structure_hash", return_value="same"):
            preview = self.suggest()
            self.assertTrue(any(g["kind"] == "add" and g["target"] == world for g in preview["groups"]))
            self.org.action({"action": "direction-delete", "id": world})
            before = len(self.directions())
            self.apply(preview)
        self.assertEqual([d["name"].lower() for d in self.directions()].count("world model"), 0)
        self.assertGreaterEqual(len(self.directions()), before)             # (other proposals may still create their own categories)

    def test_a_move_keeps_a_category_that_still_holds_an_archived_paper(self):
        world, robot = self.direction("World model"), self.direction("Robot manipulation")
        self.place(["r1"], world)
        with self.org._transaction():                                       # an archived paper (not saved) still holds the category
            revision, data = self.org._load()
            data["memberships"]["z9"] = [world]
            self.org.conn.execute("UPDATE org_projects SET revision=?,data=? WHERE project=?", (revision + 1, _dump(data), self.org.project))
        self.apply(self.suggest(), groups=False, moves=True)
        self.assertEqual(self.memberships()["r1"], [robot])
        self.assertIn(world, {d["id"] for d in self.directions()})          # not deleted: z9 is still in it

    def test_finishing_with_nothing_to_write_adds_no_undo_step(self):
        for key in ("w1", "w2", "r1", "r2", "x1"):
            self.store.conn.execute("DELETE FROM library WHERE paper_key=?", (key,))
        self.store.conn.commit()
        preview = self.suggest()
        before = self.org.snapshot()
        result = self.apply(preview, groups=False, finish=True)
        self.assertEqual(result["revision"], before["revision"])
        self.assertEqual(result["undo"], before["undo"])


class PendingTests(Fixture):
    def test_an_unplaced_paper_nothing_can_be_proposed_for_is_listed_so_the_owner_can_place_it(self):
        preview = self.suggest()
        self.assertIn("x1", preview["pending_keys"])                         # "Quantum error correction": no category, no partner

    def test_a_category_that_shares_part_of_its_name_is_offered_as_a_possible_match_not_ticked_by_default(self):
        self.direction("Quantum Computing")
        preview = self.suggest()
        weak = [g for g in preview["groups"] if g.get("weak")]
        self.assertEqual([(g["name"], g["keys"]) for g in weak], [("Quantum Computing", ["x1"])])
        self.assertEqual(weak[0]["kind"], "add")
        self.assertIn("quantum", weak[0]["reason"].lower())
        self.assertNotIn("x1", preview["pending_keys"])                      # it has a suggestion, so it is not "nothing found"

    def test_only_the_best_fitting_partial_matches_are_offered(self):
        self.direction("Quantum Computing")                                  # 1 of 2 words
        self.direction("Quantum Error Correction Hardware")                  # 3 of 4 words: the best fit
        self.direction("Quantum Annealing Sampling Systems Group")           # 1 of 5 words
        names = {g["name"] for g in self.suggest()["groups"] if g.get("weak")}
        self.assertEqual(names, {"Quantum Error Correction Hardware"})

    def test_same_named_categories_at_different_levels_are_offered_once(self):
        top = self.direction("Quantum Computing")
        parent = self.direction("Physics")
        self.direction("Quantum Computing", parent=parent)
        self.place(["w1"], top)                                              # the top-level copy is the more used one
        weak = [g for g in self.suggest()["groups"] if g.get("weak")]
        self.assertEqual([(g["name"], g["target"]) for g in weak], [("Quantum Computing", top)])

    def test_a_possible_match_is_applied_only_if_chosen_like_any_other_addition(self):
        target = self.direction("Quantum Computing")
        preview = self.suggest()
        self.apply(preview, groups=False, finish=True)
        self.assertEqual(self.memberships()["x1"], [])
        self.apply(self.suggest())
        self.assertIn(target, self.memberships()["x1"])

    def test_generic_category_names_are_not_evidence(self):
        self.direction("Learning")
        self.direction("Model")
        preview = self.suggest()
        self.assertFalse([g for g in preview["groups"] if g["name"] in ("Learning", "Model")])


class MergeScopeTests(ScopeTests):
    def test_a_duplicate_pair_with_no_paper_in_the_reviewed_project_is_not_that_projects_business(self):
        a, b = self.direction("Robotics"), self.direction("robotics")
        self.place(["r1", "r2"], a)
        self.place(["x1"], b)
        self.assertEqual(len(self.suggest(scope_project=self.two)["merges"]), 1)    # r1, r2 are project two's
        self.assertEqual(self.suggest(scope_project=self.one)["merges"], [])        # project one has none of these papers
        self.assertEqual(len(self.suggest()["merges"]), 1)


class DuplicateAdditionTests(Fixture):
    def test_a_paper_is_offered_to_one_copy_of_a_duplicated_category_not_to_both(self):
        a, b = self.direction("World model"), self.direction("world model")
        self.place(["w1"], a)
        preview = self.suggest()
        adds = [g for g in preview["groups"] if g["kind"] == "add" and "w2" in g["keys"]]
        self.assertEqual(len(adds), 1)
        self.assertEqual(adds[0]["target"], preview["merges"][0]["keep"])


class PureReviewTests(unittest.TestCase):
    def test_review_is_deterministic_and_does_not_touch_its_inputs(self):
        directions = [{"id": "d1", "name": "World model", "parent_id": None, "rank": 0, "color": "#111111"}]
        memberships = {"w1": ["d1"]}
        reviewed = {}
        snapshot = (repr(directions), repr(memberships), repr(reviewed))
        one = review(PAPERS, directions, memberships, reviewed, {})
        two = review(PAPERS, directions, memberships, reviewed, {})
        self.assertEqual(one, two)
        self.assertEqual(snapshot, (repr(directions), repr(memberships), repr(reviewed)))

    def test_no_papers_no_directions_is_an_empty_review(self):
        out = review([], [], {}, {}, {})
        self.assertEqual((out["groups"], out["merges"], out["moves"], out["evaluated"]), ([], [], [], []))

    def test_the_reasons_follow_the_interface_language(self):
        directions = [{"id": "d1", "name": "World model", "parent_id": None, "rank": 0}, {"id": "d2", "name": "world model", "parent_id": None, "rank": 1}]
        zh = review(PAPERS, directions, {"w1": ["d1"]}, {}, {})["merges"][0]["reason"]
        en = review(PAPERS, directions, {"w1": ["d1"]}, {}, {"language": "en-US"})["merges"][0]["reason"]
        self.assertIn("同义", zh)
        self.assertIn("equivalent", en)


if __name__ == "__main__":
    unittest.main()


class PageContractTests(unittest.TestCase):
    """The page asks for a review of the selected tab and applies only what is ticked, then finishes the review."""

    def test_the_request_and_the_apply_body(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "static" / "organization.js").read_text(encoding="utf-8")
        self.assertTrue("const asked = S.scope !== 'all' ? S.scope : window.PDH.state?.currentProject;" in source, "asked project")
        self.assertTrue("...(S.scope === 'all' ? { scope: 'all' } : {})" in source, "all tab")
        self.assertTrue("apply_mode:'add', fingerprint:preview.fingerprint, suggestions, merges, moves, dismissed, finish: true" in source, "the apply body")
        self.assertTrue("data-move-dismiss" in source and "保持现状，不再提示" in source, "a move is dismissed only on purpose")
        self.assertTrue("data-move-enabled aria-label" in source, "moves are not ticked by default")
        self.assertFalse("data-move-enabled checked" in source)
