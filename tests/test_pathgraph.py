"""Route Mode slice 3a: the prerequisite graph. Pure functions, no network, no model.

The graph is what an AI proposes and a person edits, so the first job is to make any input safe:
acyclic, bounded, readable. The second job is per-branch progress: each concept unlocks when its own
prerequisites are understood, so branches advance at different speeds.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import pathgraph as pg


def concept(id_, name, needs=(), hint=2, terms=None):
    return {"id": id_, "name": name, "needs": list(needs), "hint": hint,
            "terms": terms if terms is not None else [name.lower(), f"{name.lower()} theory"]}


def raw(*concepts, targets=()):
    return {"concepts": list(concepts), "targets": list(targets)}


def names(graph):
    return [c["name"] for c in graph["concepts"]]


def edge_names(graph):
    by_id = {c["id"]: c["name"] for c in graph["concepts"]}
    return sorted((by_id[e["from"]], by_id[e["to"]]) for e in graph["prereqs"])


class NormalizeTests(unittest.TestCase):
    def test_a_clean_chain_keeps_its_shape_and_gets_layers(self):
        graph, report = pg.normalize(raw(concept("a", "Crystal basics", hint=1), concept("b", "Epitaxy", ["a"], hint=2),
                                         concept("c", "MBE growth", ["b"], hint=3), targets=["c"]))
        self.assertEqual(edge_names(graph), [("Crystal basics", "Epitaxy"), ("Epitaxy", "MBE growth")])
        self.assertEqual(sorted(pg.layers(graph).values()), [1, 2, 3])
        self.assertEqual(report["dropped_edges"], [])
        self.assertEqual([c["name"] for c in graph["concepts"] if c["id"] in graph["targets"]], ["MBE growth"])

    def test_ids_are_canonical_so_garbage_ids_cannot_leak(self):
        graph, _ = pg.normalize(raw(concept("../x\n", "One"), concept("<b>", "Two", ["../x\n"])))
        self.assertTrue(all(c["id"].startswith("c") and c["id"][1:].isdigit() for c in graph["concepts"]))
        self.assertEqual(len(graph["prereqs"]), 1)

    def test_dangling_self_and_duplicate_needs_are_dropped_and_reported(self):
        graph, report = pg.normalize(raw(concept("a", "Alpha"), concept("b", "Beta", ["a", "a", "b", "zzz"])))
        self.assertEqual(edge_names(graph), [("Alpha", "Beta")])
        self.assertEqual(sorted(d["why"] for d in report["dropped_edges"]), ["dangling", "self"])

    def test_an_edge_from_a_harder_prerequisite_is_dropped_by_hint_order(self):
        graph, report = pg.normalize(raw(concept("a", "Advanced", hint=4), concept("b", "Basic", ["a"], hint=1)))
        self.assertEqual(graph["prereqs"], [])
        self.assertEqual([d["why"] for d in report["dropped_edges"]], ["hint_order"])

    def test_a_cycle_between_equal_hints_is_broken_deterministically(self):
        data = raw(concept("a", "A", ["c"]), concept("b", "B", ["a"]), concept("c", "C", ["b"]))
        one, report = pg.normalize(data)
        two, _ = pg.normalize(data)
        self.assertTrue(pg.is_acyclic(one))
        self.assertEqual(len(one["prereqs"]), 2)
        self.assertEqual([d["why"] for d in report["dropped_edges"]], ["cycle"])
        self.assertEqual(edge_names(one), edge_names(two))

    def test_a_two_node_cycle_loses_exactly_one_edge(self):
        graph, _ = pg.normalize(raw(concept("a", "A", ["b"]), concept("b", "B", ["a"])))
        self.assertTrue(pg.is_acyclic(graph))
        self.assertEqual(len(graph["prereqs"]), 1)

    def test_redundant_shortcuts_are_removed(self):
        graph, report = pg.normalize(raw(concept("a", "A", hint=1), concept("b", "B", ["a"]), concept("c", "C", ["a", "b"], hint=3)))
        self.assertEqual(edge_names(graph), [("A", "B"), ("B", "C")])
        self.assertEqual([d["why"] for d in report["dropped_edges"]], ["redundant"])

    def test_too_many_prerequisites_are_capped(self):
        feeders = [concept(f"p{i}", f"P{i}", hint=1) for i in range(5)]
        graph, report = pg.normalize(raw(*feeders, concept("t", "Target", [f.__getitem__("id") for f in feeders], hint=3), targets=["t"]))
        into = [e for e in graph["prereqs"] if e["to"] == [c["id"] for c in graph["concepts"] if c["name"] == "Target"][0]]
        self.assertEqual(len(into), pg.MAX_FAN_IN)
        self.assertEqual(sum(1 for d in report["dropped_edges"] if d["why"] == "fan_in"), 2)

    def test_duplicate_concepts_are_merged_and_their_needs_united(self):
        graph, report = pg.normalize(raw(
            concept("a", "Epitaxy", terms=["epitaxial growth", "epitaxy"]),
            concept("b", "epitaxy", terms=["Epitaxial Growth"]),
            concept("c", "Base", hint=1), concept("d", "Dependent", ["b"], hint=3)))
        self.assertEqual(len(graph["concepts"]), 3)
        self.assertEqual(len(report["merged"]), 1)
        self.assertIn(("Epitaxy", "Dependent"), edge_names(graph))

    def test_identical_term_sets_merge_but_a_shared_generic_term_does_not(self):
        same, _ = pg.normalize(raw(concept("a", "MBE", terms=["molecular beam epitaxy"]), concept("b", "Molecular beam epitaxy", terms=["molecular beam epitaxy"])))
        self.assertEqual(len(same["concepts"]), 1)
        apart, report = pg.normalize(raw(concept("a", "Transformer", terms=["transformer"]), concept("b", "Vision Transformer", terms=["transformer"]),
                                         concept("c", "Reinforcement learning", terms=["learning"]), concept("d", "Supervised learning", terms=["learning"]),
                                         targets=["b"]))
        self.assertEqual(len(apart["concepts"]), 4)
        self.assertEqual(report["merged"], [])
        self.assertEqual([c["name"] for c in apart["concepts"] if c["id"] in apart["targets"]], ["Vision Transformer"])

    def test_names_made_only_of_punctuation_are_dropped_not_merged(self):
        graph, report = pg.normalize(raw({"id": "a", "name": "@", "terms": ["@"]}, {"id": "b", "name": "#", "terms": ["#"]}, concept("c", "Real")))
        self.assertEqual(names(graph), ["Real"])
        self.assertEqual(len(report["dropped_concepts"]), 2)

    def test_concepts_without_a_name_are_dropped_and_terms_are_cleaned(self):
        graph, report = pg.normalize(raw({"id": "a", "name": "  ", "terms": ["x"]},
                                         {"id": "b", "name": "Real", "terms": ["Alpha, beta", "", "alpha, beta", "gamma", "delta"]}))
        self.assertEqual(names(graph), ["Real"])
        self.assertEqual(graph["concepts"][0]["terms"], ["Alpha beta", "gamma"])   # two terms, no commas, no duplicates
        self.assertEqual(len(report["dropped_concepts"]), 1)

    def test_a_concept_without_terms_gets_terms_from_an_english_name_and_is_reported_otherwise(self):
        graph, report = pg.normalize(raw({"id": "a", "name": "Quantum well", "terms": []}, {"id": "b", "name": "量子阱", "terms": []}))
        self.assertEqual(graph["concepts"][0]["terms"], ["quantum well"])
        self.assertEqual(graph["concepts"][1]["terms"], [])
        self.assertEqual(report["terms_missing"], ["量子阱"])

    def test_the_graph_is_bounded_and_keeps_targets_and_their_ancestors_first(self):
        chain = [concept("a0", "Root", hint=1)] + [concept(f"a{i}", f"Step{i}", [f"a{i - 1}"], hint=1 + min(i, 3)) for i in range(1, 4)]
        filler = [concept(f"f{i}", f"Filler{i}", hint=1) for i in range(15)]
        graph, report = pg.normalize(raw(*filler, *chain, targets=["a3"]))
        self.assertEqual(len(graph["concepts"]), pg.MAX_NODES)
        self.assertTrue({"Root", "Step1", "Step2", "Step3"} <= set(names(graph)))
        self.assertGreater(len(report["dropped_concepts"]), 0)

    def test_without_targets_the_leaves_become_the_targets_and_unrelated_nodes_are_side_branches(self):
        graph, _ = pg.normalize(raw(concept("a", "A", hint=1), concept("b", "B", ["a"]), concept("x", "Lonely", hint=1)))
        target_names = sorted(c["name"] for c in graph["concepts"] if c["id"] in graph["targets"])
        self.assertEqual(target_names, ["B", "Lonely"])
        graph2, _ = pg.normalize(raw(concept("a", "A", hint=1), concept("b", "B", ["a"]), concept("x", "Lonely", hint=1), targets=["b"]))
        side = {c["name"]: c["side"] for c in graph2["concepts"]}
        self.assertEqual(side, {"A": False, "B": False, "Lonely": True})

    def test_concepts_without_ids_or_with_repeated_ids_still_get_distinct_ids(self):
        graph, _ = pg.normalize({"concepts": [{"name": "Alpha", "terms": ["alpha"]}, {"name": "Beta", "terms": ["beta"]}, {"name": "Gamma", "terms": ["gamma"]}]})
        self.assertEqual(sorted(c["id"] for c in graph["concepts"]), ["c1", "c2", "c3"])
        self.assertEqual(len(graph["targets"]), 3)
        twins, _ = pg.normalize({"concepts": [{"id": "x", "name": "One", "terms": ["one"]}, {"id": "x", "name": "Two", "terms": ["two"], "needs": ["x"]}]})
        self.assertEqual(len(twins["concepts"]), 2)
        self.assertEqual(len(set(c["id"] for c in twins["concepts"])), 2)

    def test_a_need_can_name_the_concept_instead_of_its_id(self):
        graph, _ = pg.normalize({"concepts": [{"id": "1", "name": "Crystal basics", "terms": ["crystal"], "hint": 1},
                                              {"id": "2", "name": "Epitaxy", "terms": ["epitaxy"], "needs": ["crystal basics"]}]})
        self.assertEqual(edge_names(graph), [("Crystal basics", "Epitaxy")])

    def test_truncation_keeps_the_targets_and_their_nearest_ancestors(self):
        chain = [concept(f"n{i}", f"N{i}", [f"n{i - 1}"] if i else [], hint=1 + min(i // 5, 3)) for i in range(20)]
        graph, report = pg.normalize(raw(*chain, targets=["n19"]))
        self.assertEqual(len(graph["concepts"]), pg.MAX_NODES)
        kept = set(names(graph))
        self.assertIn("N19", kept)
        self.assertEqual(kept, {f"N{i}" for i in range(8, 20)})   # the target and the eleven nearest steps before it
        self.assertEqual([c["name"] for c in graph["concepts"] if c["id"] in graph["targets"]], ["N19"])
        self.assertEqual(sum(d["why"] == "too_many" for d in report["dropped_concepts"]), 8)

    def test_odd_types_never_raise(self):
        weird = [{"concepts": [{"id": "a", "name": "A", "terms": ["a"]}], "targets": 5},
                 {"concepts": [{"id": "a", "name": "A", "terms": ["a"], "needs": 5}]},
                 {"concepts": [{"id": "a", "name": "A", "terms": ["a"], "needs": "abc"}, {"id": "b", "name": "A", "terms": ["a"], "needs": 5}]},
                 {"concepts": [{"id": ["x"], "name": "A", "terms": "oops", "hint": [1], "needs": [None, {"k": 1}, 3.5]}], "targets": [["a"], None]},
                 {"concepts": [{"id": 1, "name": 12345, "terms": [5, None, "x"]}]}]
        for data in weird:
            graph, _ = pg.normalize(data)
            self.assertTrue(pg.is_acyclic(graph))

    def test_garbage_input_gives_an_empty_graph_not_an_exception(self):
        for bad in (None, 5, "x", [], {}, {"concepts": "no"}, {"concepts": [None, 3, "x"]}):
            graph, report = pg.normalize(bad)
            self.assertEqual((graph["concepts"], graph["prereqs"]), ([], []), repr(bad))
            self.assertIn("dropped_edges", report)

    def test_hint_is_clamped_and_defaults(self):
        graph, _ = pg.normalize(raw({"id": "a", "name": "A", "terms": ["a"], "hint": 99}, {"id": "b", "name": "B", "terms": ["b"], "hint": "x"}))
        self.assertEqual([c["hint"] for c in graph["concepts"]], [4, 2])

    def test_new_concepts_start_active_with_plan_origin(self):
        graph, _ = pg.normalize(raw(concept("a", "A")))
        self.assertEqual((graph["concepts"][0]["origin"], graph["concepts"][0]["state"]), ("plan", "active"))

    def test_normalizing_twice_changes_nothing(self):
        graph, _ = pg.normalize(raw(concept("a", "A", hint=1), concept("b", "B", ["a"]), concept("c", "C", ["a", "b"], hint=3), targets=["c"]))
        again, report = pg.normalize({"concepts": [dict(c, needs=[e["from"] for e in graph["prereqs"] if e["to"] == c["id"]]) for c in graph["concepts"]],
                                      "targets": graph["targets"]})
        self.assertEqual(edge_names(again), edge_names(graph))
        self.assertEqual(report["dropped_edges"], [])


class InvariantTests(unittest.TestCase):
    def test_random_inputs_with_missing_ids_and_odd_types_still_come_out_valid(self):
        import random
        rng = random.Random(4242)
        odd = [None, 5, 2.5, "x", ["a"], {"k": 1}, True]
        for round_ in range(300):
            concepts = []
            for i in range(rng.randint(0, 20)):
                item = {"name": rng.choice([f"Concept {i}", f"Concept {i % 4}", None, "  ", "@", 12]),
                        "terms": rng.choice([[f"t{i}"], [], "oops", None, [None, 5, f"t{i % 3}"]]),
                        "hint": rng.choice([1, 2, 3, 4, None, "x", 99]),
                        "needs": rng.choice([[], [f"c{rng.randint(0, 20)}"], "abc", 5, None, [rng.choice(odd)], [f"Concept {rng.randint(0, 4)}"]])}
                if rng.random() < 0.7:
                    item["id"] = rng.choice([f"c{i}", f"c{i % 5}", None, "", 7, ["z"]])
                concepts.append(item if rng.random() > 0.05 else rng.choice(odd))
            graph, _ = pg.normalize({"concepts": concepts, "targets": rng.choice([[], ["c1"], [f"Concept {rng.randint(0, 4)}"], 5, None, odd])})
            ids = [c["id"] for c in graph["concepts"]]
            self.assertEqual(len(ids), len(set(ids)), round_)
            self.assertLessEqual(len(ids), pg.MAX_NODES)
            self.assertTrue(pg.is_acyclic(graph), round_)
            self.assertTrue(set(graph["targets"]) <= set(ids), round_)
            if ids:
                self.assertTrue(graph["targets"], round_)

    def test_random_graphs_always_come_out_valid_and_stay_valid(self):
        import random
        rng = random.Random(20261005)
        for round_ in range(400):
            n = rng.randint(0, 18)
            ids = [f"n{i}" for i in range(n)]
            concepts = []
            for i, id_ in enumerate(ids):
                needs = [rng.choice(ids + ["ghost"]) for _ in range(rng.randint(0, 6))] if ids else []
                concepts.append({"id": id_, "name": rng.choice([f"Concept {i}", f"Concept {i % 5}", "  ", f"概念{i}"]),
                                 "terms": [f"term {rng.randint(0, 8)}", f"t{i}"][:rng.randint(0, 2)],
                                 "hint": rng.choice([1, 2, 3, 4, 9, None, "x"]), "needs": needs})
            graph, report = pg.normalize({"concepts": concepts, "targets": [rng.choice(ids + ["ghost"]) for _ in range(rng.randint(0, 3))] if ids else []})
            got = [c["id"] for c in graph["concepts"]]
            self.assertEqual(len(got), len(set(got)), round_)
            self.assertLessEqual(len(got), pg.MAX_NODES, round_)
            self.assertTrue(pg.is_acyclic(graph), round_)
            hints = {c["id"]: c["hint"] for c in graph["concepts"]}
            into = {}
            for edge in graph["prereqs"]:
                self.assertIn(edge["from"], hints)
                self.assertIn(edge["to"], hints)
                self.assertNotEqual(edge["from"], edge["to"])
                self.assertLessEqual(hints[edge["from"]], hints[edge["to"]], round_)
                into[edge["to"]] = into.get(edge["to"], 0) + 1
            self.assertTrue(all(count <= pg.MAX_FAN_IN for count in into.values()), round_)
            for edge in graph["prereqs"]:   # reduced: no edge is implied by a longer path
                others = [e for e in graph["prereqs"] if e is not edge]
                self.assertFalse(pg._reachable(others, edge["from"], edge["to"], skip=None), round_)
            self.assertTrue(set(graph["targets"]) <= set(got), round_)
            if graph["concepts"]:
                self.assertTrue(graph["targets"], round_)
            levels = pg.layers(graph)
            for edge in graph["prereqs"]:
                self.assertLess(levels[edge["from"]], levels[edge["to"]], round_)
            # a graph that came out valid goes in again unchanged
            again, again_report = pg.normalize({"concepts": [dict(c, needs=[e["from"] for e in graph["prereqs"] if e["to"] == c["id"]])
                                                             for c in graph["concepts"]], "targets": graph["targets"]})
            self.assertEqual(sorted((e["from"], e["to"]) for e in again["prereqs"]), sorted((e["from"], e["to"]) for e in graph["prereqs"]), round_)
            self.assertEqual(again_report["dropped_edges"], [], round_)


class ValidateTests(unittest.TestCase):
    def good(self):
        graph, _ = pg.normalize(raw(concept("a", "A", hint=1), concept("b", "B", ["a"]), concept("c", "C", ["b"], hint=3), targets=["c"]))
        return graph

    def test_a_graph_that_normalize_produced_is_accepted_unchanged(self):
        graph = self.good()
        self.assertEqual(pg.validate(graph), graph)

    def test_validate_returns_a_clean_copy_and_keeps_growth_fields(self):
        graph = self.good()
        graph["concepts"][0]["unknown"] = "dropped"
        graph["concepts"][1].update(origin="grown", state="proposed", parent="c1", evidence=["p1"], candidate="g-1")
        clean = pg.validate(graph)
        self.assertNotIn("unknown", clean["concepts"][0])
        self.assertEqual((clean["concepts"][1]["origin"], clean["concepts"][1]["state"], clean["concepts"][1]["parent"]), ("grown", "proposed", "c1"))
        clean["concepts"][0]["name"] = "changed"
        self.assertEqual(graph["concepts"][0]["name"], "A")

    def test_each_broken_rule_is_refused(self):
        def broken(change):
            graph = self.good()
            change(graph)
            with self.assertRaises(ValueError):
                pg.validate(graph)
        broken(lambda g: g["prereqs"].append({"from": "c3", "to": "c1"}))                       # cycle
        broken(lambda g: g["prereqs"].append({"from": "c1", "to": "zzz"}))                       # dangling
        broken(lambda g: g["prereqs"].append({"from": "c1", "to": "c1"}))                        # self edge
        broken(lambda g: g["concepts"].append(dict(g["concepts"][0])))                           # duplicate id
        broken(lambda g: g["concepts"][0].update(hint=4))                                        # prerequisite harder than its dependent
        broken(lambda g: g["targets"].append("zzz"))                                             # unknown target
        broken(lambda g: g["concepts"][0].update(name="  "))                                     # no name
        broken(lambda g: g["prereqs"].append(dict(g["prereqs"][0])))                             # duplicate edge
        broken(lambda g: g.update(concepts=[dict(g["concepts"][0], id=f"c{i}") for i in range(pg.MAX_MAP_NODES + 1)], prereqs=[], targets=[]))

    def test_non_graphs_are_refused(self):
        for bad in (None, 5, "x", [], {}, {"concepts": "x", "prereqs": []}, {"concepts": [], "prereqs": "x"}):
            with self.assertRaises(ValueError):
                pg.validate(bad)

    def test_proposed_or_archived_paths_never_remove_an_active_prerequisite(self):
        def graph_with(middle_state):
            return {"concepts": [{"id": "a", "name": "A", "terms": ["a"], "hint": 1}, {"id": "b", "name": "B", "terms": ["b"], "hint": 2, "state": middle_state},
                                 {"id": "c", "name": "C", "terms": ["c"], "hint": 3}],
                    "prereqs": [{"from": "a", "to": "c"}, {"from": "a", "to": "b", "state": "proposed" if middle_state == "proposed" else "active"},
                                {"from": "b", "to": "c"}], "targets": ["c"]}
        for state in ("proposed", "archived"):
            clean = pg.validate(graph_with(state))
            self.assertIn(("a", "c"), [(e["from"], e["to"]) for e in clean["prereqs"]], state)
            prog = pg.progress(clean, {}, {}, {})
            self.assertEqual(prog["c"]["status"], "locked", state)   # still waits for a

    def test_a_proposed_edge_between_active_concepts_never_removes_an_active_prerequisite(self):
        graph = {"concepts": [{"id": i, "name": i.upper(), "terms": [i], "hint": h} for i, h in (("a", 1), ("b", 2), ("c", 3))],
                 "prereqs": [{"from": "a", "to": "c"}, {"from": "a", "to": "b", "state": "proposed"}, {"from": "b", "to": "c"}], "targets": ["c"]}
        clean = pg.validate(graph)
        self.assertIn(("a", "c"), [(e["from"], e["to"]) for e in clean["prereqs"]])
        self.assertEqual(pg.progress(clean, {}, {}, {})["c"]["status"], "locked")

    def test_adding_beside_a_proposed_concept_keeps_the_active_edges(self):
        graph = pg.validate(self.good())
        graph = pg.add_concept(graph, {"name": "Maybe", "terms": ["maybe"], "hint": 2, "origin": "grown", "state": "proposed"}, needs=["c1"], dependents=["c3"])
        self.assertIn(("c2", "c3"), [(e["from"], e["to"]) for e in graph["prereqs"]])
        self.assertIn(("c1", "c2"), [(e["from"], e["to"]) for e in graph["prereqs"]])

    def test_extras_are_bounded_and_numbers_must_be_finite(self):
        graph = self.good()
        graph["concepts"][0]["evidence"] = ["p" * 5000] * 3
        with self.assertRaises(ValueError):
            pg.validate(graph)
        graph = self.good()
        graph["concepts"][0]["parent"] = "x" * 500
        with self.assertRaises(ValueError):
            pg.validate(graph)
        graph = self.good()
        graph["prereqs"][0]["support"] = float("inf")
        self.assertIsNone(pg.validate(graph)["prereqs"][0]["support"])
        graph["prereqs"][0]["support"] = float("nan")
        self.assertIsNone(pg.validate(graph)["prereqs"][0]["support"])

    def test_unhashable_ids_and_targets_are_value_errors_not_type_errors(self):
        for change in (lambda g: g["targets"].append(["a"]), lambda g: g["prereqs"].append({"from": ["a"], "to": "c1"}),
                       lambda g: g["concepts"].append({"id": ["x"], "name": "X"}), lambda g: g["prereqs"].append({"from": {}, "to": {}})):
            graph = self.good()
            change(graph)
            with self.assertRaises(ValueError):
                pg.validate(graph)

    def test_an_empty_or_fully_archived_map_is_refused_and_missing_targets_become_the_sinks(self):
        for graph in ({"concepts": [], "prereqs": [], "targets": []},):
            with self.assertRaises(ValueError):
                pg.validate(graph)
        graph = self.good()
        graph["targets"] = []
        clean = pg.validate(graph)
        self.assertEqual(clean["targets"], ["c3"])
        self.assertFalse(any(c["side"] for c in clean["concepts"]))
        for c in graph["concepts"]:
            c["state"] = "archived"
        with self.assertRaises(ValueError):
            pg.validate(graph)

    def test_a_redundant_edge_is_dropped_rather_than_refused(self):
        graph = self.good()
        graph["prereqs"].append({"from": "c1", "to": "c3", "support": None, "origin": "user", "state": "active"})
        self.assertEqual(len(pg.validate(graph)["prereqs"]), 2)


class StructureTests(unittest.TestCase):
    def build(self):
        graph, _ = pg.normalize(raw(concept("a", "A", hint=1), concept("b", "B", ["a"]), concept("c", "C", ["a"]),
                                    concept("d", "D", ["b", "c"], hint=3), targets=["d"]))
        return graph, {c["name"]: c["id"] for c in graph["concepts"]}

    def test_layers_are_longest_path_depth(self):
        graph, ids = self.build()
        self.assertEqual(pg.layers(graph), {ids["A"]: 1, ids["B"]: 2, ids["C"]: 2, ids["D"]: 3})

    def test_ancestors_and_descendants(self):
        graph, ids = self.build()
        self.assertEqual(pg.ancestors(graph, [ids["D"]]), {ids["A"], ids["B"], ids["C"]})
        self.assertEqual(pg.descendants(graph, [ids["A"]]), {ids["B"], ids["C"], ids["D"]})

    def test_adding_a_concept_checks_for_cycles_and_does_not_modify_the_input(self):
        graph, ids = self.build()
        grown = pg.add_concept(graph, {"name": "New", "terms": ["new"], "hint": 3, "origin": "grown", "state": "proposed"}, needs=[ids["C"]])
        self.assertEqual(len(graph["concepts"]), 4)
        self.assertEqual(len(grown["concepts"]), 5)
        new_id = [c["id"] for c in grown["concepts"] if c["name"] == "New"][0]
        self.assertEqual(pg.layers(grown)[new_id], 3)
        with self.assertRaises(ValueError):
            pg.add_concept(grown, {"name": "Loop", "terms": ["loop"], "hint": 2}, needs=[new_id], dependents=[ids["C"]])

    def test_adding_respects_the_same_rules_as_normalize(self):
        graph, ids = self.build()
        # a prerequisite that is harder than the new concept
        with self.assertRaises(ValueError):
            pg.add_concept(graph, {"name": "Easy", "terms": ["easy"], "hint": 1}, needs=[ids["D"]])
        # D already has two prerequisites (B and C): a third fits, a fourth does not
        third = pg.add_concept(graph, {"name": "F1", "terms": ["f1"], "hint": 1}, dependents=[ids["D"]])
        with self.assertRaises(ValueError):
            pg.add_concept(third, {"name": "F2", "terms": ["f2"], "hint": 1}, dependents=[ids["D"]])

    def test_adding_never_leaves_an_edge_that_a_longer_path_implies(self):
        graph, ids = self.build()
        grown = pg.add_concept(graph, {"name": "X", "terms": ["x"], "hint": 4}, needs=[ids["A"], ids["B"]])   # A already leads to B
        into = [(e["from"], e["to"]) for e in grown["prereqs"] if e["to"] == [c["id"] for c in grown["concepts"] if c["name"] == "X"][0]]
        self.assertEqual(into, [(ids["B"], grown["concepts"][-1]["id"])])
        between = pg.add_concept(graph, {"name": "Mid", "terms": ["mid"], "hint": 2}, needs=[ids["A"]], dependents=[ids["B"]])   # A -> Mid -> B replaces A -> B
        self.assertNotIn((ids["A"], ids["B"]), [(e["from"], e["to"]) for e in between["prereqs"]])
        self.assertTrue(pg.is_acyclic(between))

    def test_the_map_may_grow_past_the_size_of_a_plan_but_not_without_limit(self):
        graph, _ = self.build()
        for i in range(pg.MAX_MAP_NODES - len(graph["concepts"])):
            graph = pg.add_concept(graph, {"name": f"Grown {i}", "terms": [f"grown{i}"], "hint": 2})
        self.assertGreater(len(graph["concepts"]), pg.MAX_NODES)
        with self.assertRaises(ValueError):
            pg.add_concept(graph, {"name": "One too many", "terms": ["many"], "hint": 2})

    def test_removing_a_concept_also_removes_its_edges(self):
        graph, ids = self.build()
        smaller = pg.remove_concept(graph, ids["B"])
        self.assertNotIn(ids["B"], [c["id"] for c in smaller["concepts"]])
        self.assertTrue(all(ids["B"] not in (e["from"], e["to"]) for e in smaller["prereqs"]))
        self.assertTrue(pg.is_acyclic(smaller))


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.graph, _ = pg.normalize(raw(
            concept("a", "Basics", hint=1), concept("b", "Left", ["a"]), concept("c", "Right", ["a"]),
            concept("d", "Joint", ["b", "c"], hint=3), targets=["d"]))
        self.ids = {c["name"]: c["id"] for c in self.graph["concepts"]}

    def prog(self, events=None, manual=None, shown=None):
        mapped = {self.ids[k]: v for k, v in (events or {}).items()}
        return {c["name"]: pg.progress(self.graph, mapped, {self.ids[k]: v for k, v in (manual or {}).items()},
                                       {self.ids[k]: n for k, n in (shown or {}).items()})[c["id"]] for c in self.graph["concepts"]}

    def test_at_the_start_only_roots_are_unlocked_and_nothing_is_satisfied(self):
        prog = self.prog()
        self.assertEqual({k: v["status"] for k, v in prog.items()}, {"Basics": "unlocked", "Left": "locked", "Right": "locked", "Joint": "locked"})
        self.assertAlmostEqual(prog["Basics"]["m"], 0.3)
        self.assertAlmostEqual(prog["Left"]["m"], 0.1)

    def test_two_saved_papers_satisfy_a_node_and_unlock_its_dependents(self):
        prog = self.prog({"Basics": ["useful", "useful"]})
        self.assertEqual(prog["Basics"]["status"], "satisfied")
        self.assertGreaterEqual(prog["Basics"]["m"], 0.6)
        self.assertEqual((prog["Left"]["status"], prog["Right"]["status"], prog["Joint"]["status"]), ("unlocked", "unlocked", "locked"))

    def test_one_saved_paper_is_not_enough(self):
        self.assertEqual(self.prog({"Basics": ["useful"]})["Basics"]["status"], "unlocked")

    def test_a_too_hard_paper_lowers_mastery_and_can_undo_satisfaction(self):
        prog = self.prog({"Basics": ["useful", "useful", "too_hard"]})
        self.assertEqual(prog["Basics"]["status"], "unlocked")
        self.assertEqual(prog["Left"]["status"], "locked")
        self.assertLess(prog["Basics"]["m"], 0.6)

    def test_branches_advance_independently(self):
        prog = self.prog({"Basics": ["useful", "useful"], "Left": ["useful", "useful"]})
        self.assertEqual((prog["Left"]["status"], prog["Right"]["status"], prog["Joint"]["status"]), ("satisfied", "unlocked", "locked"))

    def test_a_node_with_every_prerequisite_satisfied_is_unlocked(self):
        prog = self.prog({"Basics": ["useful"] * 2, "Left": ["useful"] * 2, "Right": ["useful"] * 2})
        self.assertEqual(prog["Joint"]["status"], "unlocked")

    def test_irrelevant_and_silence_never_change_mastery(self):
        quiet = self.prog()
        noisy = self.prog({"Basics": ["irrelevant", "irrelevant", "irrelevant"]}, shown={"Basics": 6})
        self.assertAlmostEqual(quiet["Basics"]["m"], noisy["Basics"]["m"])
        self.assertEqual(noisy["Basics"]["shown"], 6)

    def test_interest_comes_only_from_explicit_ratings(self):
        prog = self.prog({"Basics": ["useful", "irrelevant", "irrelevant", "irrelevant"]})
        self.assertAlmostEqual(prog["Basics"]["p"], (1 + 1) / (4 + 2))
        self.assertTrue(prog["Basics"]["low_interest"])
        self.assertFalse(self.prog({"Basics": ["irrelevant", "irrelevant"]})["Basics"]["low_interest"])  # fewer than three ratings
        self.assertFalse(self.prog()["Basics"]["low_interest"])   # nothing rated is not low interest

    def test_too_hard_is_not_a_rating_of_interest(self):
        prog = self.prog({"Basics": ["too_hard", "too_hard", "too_hard", "too_hard"]})
        self.assertEqual(prog["Basics"]["rated"], 0)
        self.assertFalse(prog["Basics"]["low_interest"])
        self.assertEqual(prog["Basics"]["too_hard"], 4)

    def test_manual_mastered_satisfies_and_stays_satisfied(self):
        prog = self.prog({"Basics": ["too_hard", "too_hard"]}, manual={"Basics": "mastered"})
        self.assertEqual(prog["Basics"]["status"], "satisfied")
        self.assertEqual(prog["Left"]["status"], "unlocked")

    def test_manual_unlock_opens_a_locked_node_without_satisfying_it(self):
        prog = self.prog(manual={"Joint": "unlocked"})
        self.assertEqual(prog["Joint"]["status"], "unlocked")
        self.assertLess(prog["Joint"]["m"], 0.6)

    def test_manual_demote_marks_low_interest_without_blocking(self):
        prog = self.prog(manual={"Right": "demoted"})
        self.assertTrue(prog["Right"]["low_interest"])
        self.assertEqual(prog["Right"]["status"], "locked")

    def test_start_nodes_can_be_chosen(self):
        mapped = pg.progress(self.graph, {}, {}, {}, start=[self.ids["Left"]])
        self.assertAlmostEqual(mapped[self.ids["Left"]]["m"], 0.3)
        self.assertAlmostEqual(mapped[self.ids["Basics"]]["m"], 0.1)

    def test_unknown_event_names_and_unknown_nodes_are_ignored(self):
        prog = pg.progress(self.graph, {self.ids["Basics"]: ["useful", "bogus"], "nope": ["useful"]}, {"nope": "mastered"}, {})
        self.assertEqual(len(prog), 4)
        self.assertEqual(prog[self.ids["Basics"]]["useful"], 1)

    def test_unmet_prerequisites_are_listed_for_the_page(self):
        prog = self.prog({"Basics": ["useful"] * 2})
        self.assertEqual(prog["Joint"]["unmet"], [self.ids["Left"], self.ids["Right"]])

    def test_same_events_give_the_same_progress(self):
        events = {"Basics": ["useful", "useful", "too_hard", "useful"]}
        self.assertEqual(self.prog(events), self.prog(events))


class StateAndCycleTests(unittest.TestCase):
    def graph(self):
        graph, _ = pg.normalize(raw(concept("a", "Basics", hint=1), concept("b", "Next", ["a"]), concept("c", "Other", hint=1)))
        return graph, {c["name"]: c["id"] for c in graph["concepts"]}

    def test_a_proposed_concept_is_not_on_the_frontier_and_blocks_nothing(self):
        graph, ids = self.graph()
        graph = pg.add_concept(graph, {"name": "Suggested", "terms": ["suggested"], "hint": 1, "origin": "grown", "state": "proposed"})
        prog = pg.progress(graph, {}, {}, {})
        new = graph["concepts"][-1]["id"]
        self.assertEqual(prog[new]["status"], "proposed")
        self.assertNotIn(new, pg.frontier(graph, prog))

    def test_an_archived_prerequisite_neither_blocks_nor_appears(self):
        graph, ids = self.graph()
        graph["concepts"][0]["state"] = "archived"
        prog = pg.progress(graph, {}, {}, {})
        self.assertEqual(prog[ids["Basics"]]["status"], "archived")
        self.assertEqual(prog[ids["Next"]]["status"], "unlocked")   # it no longer waits for an archived concept
        self.assertNotIn(ids["Basics"], pg.frontier(graph, prog))

    def test_a_proposed_edge_does_not_lock_anything(self):
        graph, ids = self.graph()
        graph["prereqs"].append({"from": ids["Other"], "to": ids["Next"], "support": None, "origin": "grown", "state": "proposed"})
        self.assertEqual(pg.progress(graph, {}, {}, {})[ids["Next"]]["unmet"], [ids["Basics"]])

    def test_a_cycle_that_got_into_stored_data_does_not_crash_progress(self):
        graph = {"concepts": [{"id": i, "name": i, "terms": [i], "hint": 2, "state": "active"} for i in "abc"],
                 "prereqs": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}, {"from": "c", "to": "a"}], "targets": ["c"]}
        prog = pg.progress(graph, {}, {}, {})
        self.assertEqual(set(prog), {"a", "b", "c"})
        self.assertTrue(all(v["status"] == "locked" for v in prog.values()))   # nothing unlocks itself: the reader must break the cycle


class FrontierAndRemedialTests(unittest.TestCase):
    def setUp(self):
        self.graph, _ = pg.normalize(raw(
            concept("a", "Basics", hint=1), concept("b", "Left", ["a"]), concept("c", "Right", ["a"]),
            concept("d", "Joint", ["b", "c"], hint=3), targets=["d"]))
        self.ids = {c["name"]: c["id"] for c in self.graph["concepts"]}

    def test_the_frontier_is_unlocked_and_unsatisfied_ordered_by_layer_then_interest(self):
        events = {self.ids["Basics"]: ["useful", "useful"], self.ids["Right"]: ["useful", "irrelevant"], self.ids["Left"]: ["irrelevant"]}
        prog = pg.progress(self.graph, events, {}, {})
        front = pg.frontier(self.graph, prog)
        self.assertEqual(front, [self.ids["Right"], self.ids["Left"]])   # same layer: the one with higher interest first

    def test_remedial_lists_the_unmet_prerequisites_most_basic_first(self):
        prog = pg.progress(self.graph, {self.ids["Basics"]: ["useful", "useful"]}, {}, {})
        self.assertEqual(pg.remedial(self.graph, prog, self.ids["Joint"]), [self.ids["Left"], self.ids["Right"]])
        self.assertEqual(pg.remedial(self.graph, prog, self.ids["Basics"]), [])

    def test_a_branch_stuck_on_a_hard_node_does_not_block_the_other_branch(self):
        events = {self.ids["Basics"]: ["useful", "useful"], self.ids["Left"]: ["too_hard", "too_hard"]}
        prog = pg.progress(self.graph, events, {}, {})
        self.assertIn(self.ids["Right"], pg.frontier(self.graph, prog))
        self.assertIn(self.ids["Left"], pg.frontier(self.graph, prog))


class ExplorationTests(unittest.TestCase):
    def test_the_share_rises_smoothly_with_progress(self):
        self.assertAlmostEqual(pg.exploration_share(0, 10), 0.10)
        self.assertAlmostEqual(pg.exploration_share(5, 10), 0.30)
        self.assertAlmostEqual(pg.exploration_share(10, 10), 0.50)
        self.assertAlmostEqual(pg.exploration_share(0, 0), 0.10)
        self.assertAlmostEqual(pg.exploration_share(99, 10), 0.50)   # clamped

    def test_slots_follow_the_share_on_average_and_are_replayable(self):
        counts = [pg.exploration_slots(5, 0, 10, n) for n in range(20)]
        self.assertEqual(sum(counts), 10)            # 0.10 of 100 slots over twenty batches
        self.assertTrue(all(0 <= c <= 1 for c in counts))
        self.assertEqual(counts, [pg.exploration_slots(5, 0, 10, n) for n in range(20)])
        half = [pg.exploration_slots(5, 10, 10, n) for n in range(20)]
        self.assertEqual(sum(half), 50)

    def test_a_batch_always_keeps_at_least_one_route_slot(self):
        self.assertTrue(all(pg.exploration_slots(5, 10, 10, n) <= 4 for n in range(10)))
        self.assertEqual(pg.exploration_slots(1, 10, 10, 0), 0)

    def test_odd_arguments_are_safe(self):
        self.assertEqual(pg.exploration_slots(10, 5, 10, -3), pg.exploration_slots(10, 5, 10, 0))
        self.assertEqual(pg.exploration_slots(0, 5, 10, 1), 0)
        self.assertEqual(pg.allocate(3, [float("nan"), 1, float("inf")]), [0, 3, 0])
        self.assertEqual(pg.allocate(3, ["x", None, 2]), [0, 0, 3])

    def test_allocation_uses_largest_remainders_and_is_stable(self):
        self.assertEqual(pg.allocate(5, [1, 1, 1]), [2, 2, 1])
        self.assertEqual(pg.allocate(4, [3, 1]), [3, 1])
        self.assertEqual(pg.allocate(3, [0, 0]), [0, 0])
        self.assertEqual(pg.allocate(0, [1, 1]), [0, 0])
        self.assertEqual(pg.allocate(5, []), [])
        self.assertEqual(sum(pg.allocate(7, [0.2, 5, 1.3])), 7)


if __name__ == "__main__":
    unittest.main()
