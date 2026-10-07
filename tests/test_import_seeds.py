"""Setting imported papers as seeds: they shape the profile, but never the learning map.

A seed from an import says "start from these", not "the map should grow here": it counts for ranking and the profile, and
is NOT growth evidence and NOT a progress event on the learning map (ROUTE-V2-06: an import is not evidence).
A seed chosen at project creation, or any paper the reader marks useful, still counts as before."""
import io
from pathlib import Path

from test_route_growth import Fixture, NEAR
from tests.library_import_fixtures import pdf


class ImportSeedTests(Fixture):
    def setUp(self):
        super().setUp()
        self.add(*NEAR)
        for key in ("s1", "s2", "n1"):
            self.app.store.save_to_library(key, project_id=self.pid)   # an import saves what it brings in

    def positive(self):
        return set(self.app._positive_evidence(self.pid)[0])

    def pending(self):
        return {p["key"] for p in self.app._pending_growth(self.pid)}

    def events(self):
        graph = self.app.route_get(self.pid)["graph"]
        return self.app._route_inputs(self.pid, graph)[0]

    def test_an_imported_seed_is_a_seed_of_the_project_and_is_recorded_as_import_origin(self):
        result = self.app.add_import_seeds(self.pid, ["s1", "s2"])
        self.assertEqual((result["added"], result["seeds"]), (2, 2))
        self.assertEqual(sorted(self.app.seed_keys(self.pid)), ["s1", "s2"])
        self.assertEqual(self.app.store.get_setting(f"import_seed_keys_{self.pid}"), ["s1", "s2"])
        kind = self.app.store.conn.execute("SELECT relation_kind FROM project_papers WHERE project_id=? AND paper_key='s1'", (self.pid,)).fetchone()[0]
        self.assertEqual(kind, "seed")

    def test_an_imported_seed_is_not_growth_evidence(self):
        self.app.add_import_seeds(self.pid, ["s1"])
        self.assertEqual(self.positive(), set())
        self.assertEqual(self.pending(), set())

    def test_a_seed_chosen_at_creation_still_is(self):
        self.app.store.add_project_paper(self.pid, "s1", "seed")
        self.app.store.set_setting(f"seed_keys_{self.pid}", ["s1"])
        self.assertEqual(self.positive(), {"s1"})

    def test_a_creation_seed_stays_evidence_even_when_it_is_also_imported(self):
        self.app.store.add_project_paper(self.pid, "s1", "seed")
        self.app.store.set_setting(f"seed_keys_{self.pid}", ["s1"])
        result = self.app.add_import_seeds(self.pid, ["s1"])
        self.assertEqual((result["added"], result["already"]), (0, 1))
        self.assertEqual(self.positive(), {"s1"})
        self.assertEqual(self.app.store.get_setting(f"import_seed_keys_{self.pid}", []), [])

    def test_the_readers_own_useful_label_makes_an_imported_seed_evidence(self):
        self.app.add_import_seeds(self.pid, ["s1"])
        self.app.record_feedback("s1", "useful", project_id=self.pid)
        self.assertEqual(self.positive(), {"s1"})

    def test_an_imported_seed_does_not_move_the_learning_map_but_a_creation_seed_does(self):
        self.app.add_import_seeds(self.pid, ["n1"])
        self.assertEqual(self.events(), {})
        self.app.store.set_setting(f"import_seed_keys_{self.pid}", [])
        self.assertEqual(list(self.events().values()), [["useful"]])

    def test_the_profile_still_counts_imported_seeds(self):
        self.app.add_import_seeds(self.pid, ["s1"])
        self.assertIn("s1", self.app.seed_keys(self.pid))
        self.assertIn("s1", self.app.profile(self.pid)["positive_seeds"])

    def test_at_most_twenty_at_a_time_and_forty_in_a_project(self):
        for i in range(45):
            self.add(f"x{i}", f"Paper {i}", "an abstract about something", "journal-a")
            self.app.store.save_to_library(f"x{i}", project_id=self.pid)
        with self.assertRaises(ValueError):
            self.app.add_import_seeds(self.pid, [f"x{i}" for i in range(21)])
        self.app.add_import_seeds(self.pid, [f"x{i}" for i in range(20)])
        self.app.add_import_seeds(self.pid, [f"x{i}" for i in range(20, 40)])
        with self.assertRaises(ValueError) as caught:
            self.app.add_import_seeds(self.pid, ["x40"])
        self.assertIn("40", str(caught.exception))
        self.assertEqual(len(self.app.seed_keys(self.pid)), 40)

    def test_only_papers_in_this_projects_library_with_real_metadata_can_be_seeds(self):
        self.add("loose", "Not saved", "abstract", "journal-a")
        self.app.store.upsert_papers([{"key": "pdf:" + "a" * 64, "title": "scan"}], project_id=self.pid)
        self.app.store.save_to_library("pdf:" + "a" * 64, project_id=self.pid)
        for keys in (["loose"], ["pdf:" + "a" * 64], ["missing"], [], "s1", [5]):
            with self.assertRaises(ValueError, msg=str(keys)):
                self.app.add_import_seeds(self.pid, keys)
        self.assertEqual(self.app.seed_keys(self.pid), [])

    def test_adding_twice_is_harmless(self):
        self.app.add_import_seeds(self.pid, ["s1"])
        again = self.app.add_import_seeds(self.pid, ["s1"])
        self.assertEqual((again["added"], again["already"], again["seeds"]), (0, 1, 1))

    def test_a_batch_only_seeds_what_it_imported(self):
        imp = self.app.library_import
        batch = imp.create_batch(self.pid, "folder", "r", {})["id"]
        data = pdf(1)
        item = imp.add_pdf(batch, "r/a.pdf", io.BytesIO(data), len(data), 1, None)
        imp._set(item["id"], "matched", match_source="title", paper={"key": "https://doi.org/10.1000/z", "title": "Z", "abstract": "an abstract of Z"})
        imp.commit(batch)
        with self.assertRaises(ValueError):
            self.app.add_import_seeds(self.pid, ["s1"], batch_id=batch)   # in the library, but not from this import
        self.assertEqual(self.app.add_import_seeds(self.pid, ["https://doi.org/10.1000/z"], batch_id=batch)["added"], 1)

    def test_taking_a_seed_back_demotes_only_import_seeds(self):
        self.app.store.add_project_paper(self.pid, "s2", "seed")
        self.app.store.set_setting(f"seed_keys_{self.pid}", ["s2"])
        self.app.add_import_seeds(self.pid, ["s1"])
        self.app.remove_import_seeds(self.pid, ["s1", "s2"])
        self.assertEqual(self.app.seed_keys(self.pid), ["s2"])
        kinds = dict(self.app.store.conn.execute("SELECT paper_key, relation_kind FROM project_papers WHERE project_id=? AND paper_key IN ('s1','s2')", (self.pid,)))
        self.assertEqual(kinds, {"s1": "imported", "s2": "seed"})
        self.assertEqual(self.app.store.get_setting(f"import_seed_keys_{self.pid}"), [])
        self.assertIn("s1", self.app.saved_keys(self.pid))

    def test_another_projects_seeds_are_separate(self):
        self.app.add_import_seeds(self.pid, ["s1"])
        self.assertEqual(self.app.seed_keys(self.other), [])
        self.assertIsNone(self.app.store.get_setting(f"import_seed_keys_{self.other}"))


if __name__ == "__main__":
    import unittest
    unittest.main()
