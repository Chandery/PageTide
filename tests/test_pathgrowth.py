"""Route Mode slice 3b: attaching papers to concepts, checking edges against the corpus, and letting the map grow.

All deterministic and local. The point of these tests is the rules in the plan: a new branch needs several
distinct papers, explicit positive evidence and more than one source before it is even proposed; it is
only ever proposed (never merged by itself); and nothing depends on input order or the clock.
"""
import random
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import pathgraph as pg
from app import pathgrowth as pgr


def graph_of(*specs, targets=()):
    concepts = [{"id": f"c{i + 1}", "name": name, "terms": terms, "needs": [f"c{n + 1}" for n in needs], "hint": 1 + min(i, 3)}
                for i, (name, terms, needs) in enumerate(specs)]
    graph, _ = pg.normalize({"concepts": concepts, "targets": [f"c{t + 1}" for t in targets]})
    return graph


def paper(key, title, abstract="", source="Journal A", published="2026-01-01"):
    return {"key": key, "title": title, "abstract": abstract, "source": source, "published": published}


class TermMatchTests(unittest.TestCase):
    def test_words_match_on_boundaries_not_inside_other_words(self):
        self.assertTrue(pgr.term_in_text("wide bandgap semiconductors", "bandgap"))
        self.assertFalse(pgr.term_in_text("an organ on a chip", "gan"))
        self.assertTrue(pgr.term_in_text("gan on silicon", "gan"))

    def test_plurals_hyphens_and_case_are_tolerated(self):
        self.assertTrue(pgr.term_in_text("many semiconductors", "semiconductor"))
        self.assertTrue(pgr.term_in_text("wide-bandgap devices", "wide bandgap"))
        self.assertTrue(pgr.term_in_text("wide bandgap devices", "Wide-Bandgap"))

    def test_chinese_terms_match_as_substrings(self):
        self.assertTrue(pgr.term_in_text("介绍半导体晶体生长的方法", "晶体生长"))
        self.assertFalse(pgr.term_in_text("古典诗歌", "晶体生长"))

    def test_empty_terms_never_match(self):
        self.assertFalse(pgr.term_in_text("anything", ""))
        self.assertFalse(pgr.term_in_text("anything", "   "))

    def test_regex_characters_in_terms_are_harmless(self):
        self.assertFalse(pgr.term_in_text("abc", "a.c"))
        self.assertTrue(pgr.term_in_text("the c++ language", "c++"))
        self.assertFalse(pgr.term_in_text("x", "(unclosed"))


class AssignTests(unittest.TestCase):
    def setUp(self):
        self.graph = graph_of(("Epitaxy", ["epitaxial growth", "epitaxy"], []), ("Perovskites", ["perovskite", "halide perovskite"], [0]),
                              ("Solar cells", ["solar cell", "photovoltaic"], [1]))
        self.ids = {c["name"]: c["id"] for c in self.graph["concepts"]}

    def test_a_paper_goes_to_the_concepts_whose_terms_it_uses_best_first(self):
        got = pgr.assign(self.graph, [paper("a", "Halide perovskite solar cell stability", "perovskite photovoltaic devices")])
        self.assertEqual(got["a"][0], self.ids["Perovskites"])  # two terms in text and one in the title
        self.assertEqual(len(got["a"]), 2)                       # at most two concepts per paper

    def test_title_hits_count_more_than_abstract_hits(self):
        got = pgr.assign(self.graph, [paper("t", "Epitaxy of films", "a note on perovskite")])
        self.assertEqual(got["t"][0], self.ids["Epitaxy"])

    def test_a_paper_matching_nothing_is_unassigned(self):
        self.assertEqual(pgr.assign(self.graph, [paper("n", "Classical poetry", "Tang dynasty")]), {})

    def test_result_does_not_depend_on_paper_order(self):
        papers = [paper(f"p{i}", t) for i, t in enumerate(["perovskite films", "epitaxy review", "solar cell design", "perovskite solar cell"])]
        self.assertEqual(pgr.assign(self.graph, papers), pgr.assign(self.graph, list(reversed(papers))))

    def test_concepts_without_terms_match_nothing(self):
        graph, _ = pg.normalize({"concepts": [{"id": "x", "name": "量子阱", "terms": []}]})
        self.assertEqual(pgr.assign(graph, [paper("a", "量子阱结构")]), {})


class MatchingFixTests(unittest.TestCase):
    def test_a_term_made_of_separators_only_matches_nothing(self):
        for term in ("-", " - ", "--", "- -"):
            self.assertFalse(pgr.term_in_text("foo, bar. baz - qux", term), term)

    def test_assign_skips_papers_without_a_key(self):
        graph = graph_of(("Epitaxy", ["epitaxy"], []))
        self.assertEqual(pgr.assign(graph, [{"title": "epitaxy"}, paper("ok", "epitaxy growth")]), {"ok": [graph["concepts"][0]["id"]]})


class RoleTests(unittest.TestCase):
    def test_surveys_tutorials_and_primers_are_intro(self):
        for title in ("A Survey of Epitaxial Growth", "Introduction to MBE", "Perovskite solar cells: a review", "A gentle primer on GaN",
                      "Lecture notes on crystal growth", "半导体晶体生长综述", "晶体生长入门"):
            self.assertEqual(pgr.paper_role({"title": title}), "intro", title)

    def test_other_papers_are_advanced(self):
        for title in ("Strain relaxation in InGaN quantum wells", "Reviewing the reviewers", "半导体生长技术研究"):
            self.assertEqual(pgr.paper_role({"title": title}), "advanced", title)


class SupportTests(unittest.TestCase):
    A = ["epitaxy basics lattice matching and substrates"] * 4
    B_MENTIONS_A = ["mbe growth rate depends on epitaxy and substrate temperature"] * 4
    B_PLAIN = ["mbe growth rate depends on beam flux and shutter timing"] * 4

    def test_positive_when_the_dependent_mentions_the_prerequisite_more_than_the_reverse(self):
        self.assertAlmostEqual(pgr.edge_support(self.A, self.B_MENTIONS_A, ["epitaxy"], ["mbe"]), 1.0 - 0.0)

    def test_negative_when_the_direction_looks_reversed(self):
        self.assertLess(pgr.edge_support(self.B_MENTIONS_A, self.A, ["mbe"], ["epitaxy"]), 0)

    def test_zero_when_neither_mentions_the_other(self):
        self.assertEqual(pgr.edge_support(self.A, self.B_PLAIN, ["epitaxy"], ["mbe"]), 0.0)

    def test_unknown_without_enough_documents(self):
        self.assertIsNone(pgr.edge_support(self.A[:2], self.B_MENTIONS_A, ["epitaxy"], ["mbe"]))
        self.assertIsNone(pgr.edge_support(self.A, [], ["epitaxy"], ["mbe"]))

    def test_labels_use_a_margin(self):
        self.assertEqual(pgr.support_label(None), "unknown")
        self.assertEqual(pgr.support_label(0.4), "supported")
        self.assertEqual(pgr.support_label(-0.4), "contradicted")
        self.assertEqual(pgr.support_label(0.05), "neutral")
        self.assertEqual(pgr.support_label(0.15), "supported")

    def test_annotating_sets_support_on_edges_and_leaves_the_input_alone(self):
        graph = graph_of(("Epitaxy", ["epitaxy"], []), ("MBE", ["mbe"], [0]))
        first, second = [c["id"] for c in graph["concepts"]]
        annotated = pgr.annotate_support(graph, {first: self.A, second: self.B_MENTIONS_A})
        self.assertAlmostEqual(annotated["prereqs"][0]["support"], 1.0)
        self.assertIsNone(graph["prereqs"][0]["support"])
        thin = pgr.annotate_support(graph, {first: self.A[:1], second: self.B_MENTIONS_A})
        self.assertIsNone(thin["prereqs"][0]["support"])


class GapTests(unittest.TestCase):
    def test_terms_the_map_does_not_cover_come_back_rarest_first(self):
        graph = graph_of(("Epitaxy", ["epitaxy"], []))
        idf = {"epitaxy": 1.2, "dislocation": 3.0, "annealing": 2.0, "growth": 1.1, "threading": 2.8}
        got = pgr.gap_terms("Threading dislocation reduction by annealing in epitaxy growth", pgr.covered_tokens(graph), idf)
        self.assertEqual(got, ["dislocation", "threading", "annealing"])

    def test_limit_and_empty_input(self):
        self.assertEqual(pgr.gap_terms("", set(), {}), [])
        self.assertEqual(len(pgr.gap_terms("alpha beta gamma delta", set(), {"alpha": 1, "beta": 2, "gamma": 3, "delta": 4}, limit=2)), 2)

    def test_covered_tokens_come_from_names_and_terms(self):
        graph = graph_of(("Wide bandgap", ["wide bandgap", "gan"], []))
        self.assertTrue({"wide", "bandgap", "gan"} <= pgr.covered_tokens(graph))


# ----------------------------------------------------------- counting the evidence under a direction
def corpus():
    """Eight perovskite-solar papers (three sources), six epitaxy papers and six unrelated ones."""
    papers = []
    for i in range(8):
        papers.append(paper(f"pv{i}", f"Perovskite solar cell stability study {i}",
                            "perovskite solar cell efficiency stability encapsulation halide films", source=("Nature", "Joule", "Adv Mater", "Joule")[i % 4],
                            published=f"2026-0{1 + i % 8}-01"))
    for i in range(6):
        papers.append(paper(f"ep{i}", f"Epitaxial growth of GaN layer {i}", "epitaxy substrate lattice matching gan layer", source="J Cryst Growth"))
    for i in range(6):
        papers.append(paper(f"x{i}", f"Unrelated topic number {i}", "botany ecology rainfall measurement", source="Ecology"))
    return papers


def positives(*keys, days=None):
    days = days or {}
    return {k: days.get(k, "2026-09-01") for k in keys}


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.papers = corpus()
        self.vectors, self.idf = pgr.paper_vectors(self.papers)

    def evidence(self, members, pos, papers=None, **kw):
        papers = papers or self.papers
        vectors = pgr.paper_vectors(papers)[0] if papers is not self.papers else self.vectors
        return pgr.direction_evidence(members, papers, pos, vectors, **kw)

    def test_enough_papers_marked_papers_and_sources_make_it_ready(self):
        e = self.evidence(["pv0", "pv1", "pv2", "pv3"], positives("pv0", "pv1"))
        self.assertEqual(e["status"], "ready")
        self.assertEqual(e["counts"], {"papers": 4, "positive": 2, "sources": 3})
        self.assertTrue(all(e["gates"].values()))
        self.assertGreaterEqual(e["strength"], pgr.MIN_STRENGTH)

    def test_fewer_than_three_papers_is_watched_not_ready(self):
        e = self.evidence(["pv0", "pv1"], positives("pv0", "pv1"))
        self.assertEqual((e["status"], e["gates"]["papers"]), ("watch", False))

    def test_one_marked_paper_is_not_enough(self):
        e = self.evidence(["pv0", "pv1", "pv2"], positives("pv0"))
        self.assertEqual((e["status"], e["gates"]["positive"]), ("watch", False))

    def test_papers_from_one_source_are_not_enough(self):
        e = self.evidence(["ep0", "ep1", "ep2"], positives("ep0", "ep1"))
        self.assertEqual((e["counts"]["sources"], e["gates"]["sources"], e["status"]), (1, False, "watch"))

    def test_sources_are_compared_after_trimming_and_lowercasing(self):
        papers = [paper("a", "Alpha beta study", "alpha beta", source="Nature "), paper("b", "Alpha beta again", "alpha beta", source="nature"),
                  paper("c", "Alpha beta third", "alpha beta", source="NATURE")]
        self.assertEqual(self.evidence(["a", "b", "c"], positives("a", "b"), papers=papers)["counts"]["sources"], 1)

    def test_the_same_paper_under_two_keys_counts_once(self):
        papers = [paper("a", "Alpha beta study", "alpha beta gamma", source="Nature"), paper("a2", "Alpha beta study", "alpha beta gamma", source="Joule"),
                  paper("b", "Alpha beta other", "alpha beta gamma", source="Joule")]
        e = self.evidence(["a", "a2", "b"], positives("a", "a2", "b"), papers=papers)
        self.assertEqual(e["counts"]["papers"], 2)

    def test_a_doi_identifies_the_same_paper_even_when_titles_differ(self):
        one, two = paper("a", "Alpha beta", "alpha beta", source="Nature"), paper("b", "Alpha beta (preprint)", "alpha beta", source="arXiv")
        one["doi"] = two["doi"] = "10.1/x"
        self.assertEqual(self.evidence(["a", "b"], positives("a"), papers=[one, two])["counts"]["papers"], 1)

    def test_papers_that_read_alike_score_higher_than_unrelated_ones(self):
        tight = self.evidence(["pv0", "pv1", "pv2", "pv3"], positives("pv0", "pv1"))
        loose = self.evidence(["pv0", "ep0", "x0", "x1"], positives("pv0", "ep0"))
        self.assertGreater(tight["parts"]["C"], loose["parts"]["C"])
        self.assertGreater(tight["strength"], loose["strength"])

    def test_recent_positive_feedback_outranks_old(self):
        recent = self.evidence(["pv0", "pv1", "pv2"], positives("pv0", "pv1", days={"pv0": "2026-09-30", "pv1": "2026-09-29"}), recent_days=2)
        old = self.evidence(["pv0", "pv1", "pv2"], {"pv0": "2026-01-01", "pv1": "2026-01-02", "pv3": "2026-09-30", "pv4": "2026-09-29"}, recent_days=2)
        self.assertGreater(recent["parts"]["R"], old["parts"]["R"])

    def test_nothing_without_positive_evidence_is_ready(self):
        e = self.evidence(["pv0", "pv1", "pv2"], {})
        self.assertEqual((e["status"], e["counts"]["positive"], e["strength"]), ("watch", 0, 0.0))

    def test_unknown_keys_and_mixed_date_types_are_tolerated(self):
        e = self.evidence(["pv0", "nope", "pv1"], {"pv0": "2026-09-01", "pv1": None, "ghost": "2026-09-02"})
        self.assertEqual(e["papers"], ["pv0", "pv1"])

    def test_the_result_does_not_depend_on_input_order(self):
        papers = corpus()
        pos = positives("pv0", "pv1", "pv5")
        first = self.evidence(["pv0", "pv1", "pv5", "pv6"], pos)
        random.Random(3).shuffle(papers)
        again = pgr.direction_evidence(["pv6", "pv5", "pv1", "pv0"], papers, pos, pgr.paper_vectors(papers)[0])
        self.assertEqual(first["strength"], again["strength"])
        self.assertEqual((first["counts"], first["status"]), (again["counts"], again["status"]))

    def test_it_never_mutates_its_inputs(self):
        before = (repr(self.papers), repr(positives("pv0")))
        self.evidence(["pv0", "pv1", "pv2"], positives("pv0"))
        self.assertEqual((repr(self.papers), repr(positives("pv0"))), before)

    def test_a_large_library_is_counted_fast_enough(self):
        many = [paper(f"k{i}", f"Paper {i} about topic{i % 40} widgets", f"topic{i % 40} widgets analysis", source=f"S{i % 5}") for i in range(600)]
        vectors = pgr.paper_vectors(many)[0]
        started = time.monotonic()
        pgr.direction_evidence([f"k{i}" for i in range(0, 600, 40)], many, positives(*[f"k{i}" for i in range(0, 120, 40)]), vectors)
        self.assertLess(time.monotonic() - started, 2.0)


class NearestConceptTests(unittest.TestCase):
    def setUp(self):
        self.graph = graph_of(("Epitaxy", ["epitaxy", "epitaxial growth"], []), ("GaN", ["gan"], [0]))
        self.papers = corpus()
        self.vectors, self.idf = pgr.paper_vectors(self.papers)

    def test_papers_that_read_like_a_concept_of_the_map_are_near_it(self):
        concept, value = pgr.nearest_concept(self.graph, self.papers, ["ep0", "ep1", "ep2"], self.vectors, self.idf)
        self.assertIn(concept, ("c1", "c2"))
        self.assertGreaterEqual(value, pgr.T_NEAR)

    def test_a_different_topic_is_far_from_every_concept(self):
        concept, value = pgr.nearest_concept(self.graph, self.papers, ["pv0", "pv1", "pv2"], self.vectors, self.idf)
        self.assertLess(value, pgr.T_NEAR)

    def test_no_papers_means_no_answer(self):
        self.assertEqual(pgr.nearest_concept(self.graph, self.papers, ["nope"], self.vectors, self.idf), (None, 0.0))


class TowardTests(unittest.TestCase):
    def test_the_pool_papers_that_read_like_the_directions_papers_come_first_and_others_are_left_out(self):
        papers = corpus()
        vectors = pgr.paper_vectors(papers)[0]
        pool = ["pv5", "pv6", "ep0", "x0"]
        out = pgr.toward_directions([{"name": "perovskite", "papers": ["pv0", "pv1", "pv2"]}], vectors, pool)
        self.assertEqual(out[0]["name"], "perovskite")
        self.assertEqual(set(out[0]["papers"]), {"pv5", "pv6"})
        self.assertNotIn("pv0", out[0]["papers"])    # the direction's own papers are not offered again

    def test_a_direction_without_known_papers_offers_nothing(self):
        vectors = pgr.paper_vectors(corpus())[0]
        self.assertEqual(pgr.toward_directions([{"name": "x", "papers": ["nope"]}], vectors, ["pv0"]), [])


class MergeTests(unittest.TestCase):
    def test_merging_adds_a_proposed_grown_concept_with_the_models_intro_and_without_touching_the_original(self):
        graph = graph_of(("Halide chemistry", ["halide"], []))
        cid = graph["concepts"][0]["id"]
        cand = {"id": "d-1", "name": "钙钛矿太阳能电池", "terms": ["perovskite solar", "halide film"], "papers": ["a", "b"], "intro": "用钙钛矿做吸光层的太阳能电池。",
                "barrier": "要先懂卤化物晶体和能带", "prereqs": [{"from": cid, "support": None}]}
        merged = pgr.merge_candidate(graph, cand)
        self.assertEqual(len(graph["concepts"]), 1)
        added = merged["concepts"][-1]
        self.assertEqual((added["name"], added["origin"], added["state"], added["candidate"]), ("钙钛矿太阳能电池", "grown", "proposed", "d-1"))
        self.assertEqual(added["intro_by"], "ai")
        self.assertIn("用钙钛矿做吸光层", added["intro"])
        self.assertIn("门槛：要先懂卤化物晶体和能带", added["intro"])
        self.assertTrue(pg.is_acyclic(merged))
        self.assertEqual([(e["from"], e["state"]) for e in merged["prereqs"]], [(cid, "proposed")])

    def test_merging_twice_adds_the_concept_once_and_never_a_redundant_edge(self):
        graph = graph_of(("A", ["aterm"], []), ("B", ["bterm"], [0]))
        a, b = [c["id"] for c in graph["concepts"]]
        cand = {"id": "g-1", "name": "new topic", "terms": ["new topic"], "papers": ["x"], "prereqs": [{"from": a, "support": 0.5}, {"from": b, "support": 0.4}]}
        once = pgr.merge_candidate(graph, cand)
        twice = pgr.merge_candidate(once, cand)
        self.assertEqual(once, twice)
        new_id = once["concepts"][-1]["id"]
        self.assertEqual([(e["from"], e["to"]) for e in once["prereqs"] if e["to"] == new_id], [(b, new_id)])   # a -> new is implied by a -> b -> new

    def test_a_direction_with_no_known_prerequisite_becomes_an_entry(self):
        graph = graph_of(("A", ["aterm"], []))
        merged = pgr.merge_candidate(graph, {"id": "d-2", "name": "新入口", "terms": ["entry term"], "papers": [], "prereqs": [{"from": "gone", "support": None}]})
        self.assertEqual(merged["prereqs"], graph["prereqs"])


if __name__ == "__main__":
    unittest.main()
