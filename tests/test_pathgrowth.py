"""Route Mode slice 3b: attaching papers to concepts, checking edges against the corpus, and letting the map grow.

All deterministic and local. The point of these tests is the rules in the plan: a new branch needs several
distinct papers, explicit positive evidence and more than one source before it is even proposed; it is
only ever proposed (never merged by itself); and nothing depends on input order or the clock.
"""
import random
import sys
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


# ----------------------------------------------------------- branch growth
def corpus():
    """Eight perovskite-solar papers (three sources, four positive), plus unrelated ones and an epitaxy paper."""
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


def pv(found):
    """Candidates whose members are exactly perovskite-solar papers (names are only proposals, so tests look at members)."""
    return [c for c in found if c["papers"] and all(k.startswith("pv") for k in c["papers"])]


def positives(*keys, days=None):
    days = days or {}
    return {k: days.get(k, "2026-09-01") for k in keys}


class BranchTests(unittest.TestCase):
    def setUp(self):
        self.graph = graph_of(("Epitaxy", ["epitaxy", "epitaxial growth"], []), ("GaN", ["gan"], [0]))
        self.papers = corpus()

    def candidates(self, pos, papers=None, graph=None, **kw):
        return pgr.branch_candidates(graph or self.graph, papers or self.papers, pos, **kw)

    def test_a_strong_new_cluster_is_proposed_as_ready(self):
        found = self.candidates(positives("pv0", "pv1", "pv2", "pv3"))
        top = pv(found)[0]
        self.assertEqual(top["status"], "ready")
        self.assertTrue(all(top["gates"].values()))
        self.assertGreaterEqual(top["strength"], pgr.MIN_STRENGTH)
        self.assertTrue(set(top["positive"]) <= {"pv0", "pv1", "pv2", "pv3"})
        self.assertGreaterEqual(len(top["papers"]), 3)

    def test_the_name_is_the_leading_title_phrase_and_terms_are_phrases_not_stray_words(self):
        top = pv(self.candidates(positives("pv0", "pv1", "pv2", "pv3")))[0]
        self.assertEqual(top["name"], "perovskite solar")
        self.assertLessEqual(len(top["terms"]), 2)
        self.assertEqual(top["terms"][0], "perovskite solar")
        self.assertTrue(all(" " in t for t in top["terms"]), top["terms"])

    def test_a_loose_cluster_is_less_coherent_and_weaker_than_a_tight_one(self):
        tight = self.candidates(positives("pv0", "pv1", "pv2", "pv3"))
        loose_papers = [paper(f"lo{i}", f"Perovskite solar topic {i}", f"{w} unrelated words about {w2} and {w3}", source=("Nature", "Joule")[i % 2])
                        for i, (w, w2, w3) in enumerate([("quantum", "tunnelling", "spectra"), ("ocean", "currents", "salinity"),
                                                         ("graph", "theory", "colouring"), ("medieval", "trade", "routes")])]
        loose = pgr.branch_candidates(self.graph, loose_papers, positives("lo0", "lo1", "lo2", "lo3"))
        a = pv(tight)[0]
        b = [c for c in loose if all(k.startswith("lo") for k in c["papers"])][0]
        self.assertGreater(a["parts"]["C"], b["parts"]["C"])
        self.assertGreater(a["strength"], b["strength"])

    def test_clusters_already_on_the_map_are_not_proposed_again(self):
        found = self.candidates(positives("ep0", "ep1", "ep2", "ep3"))
        self.assertEqual(found, [])   # covered by the map: not even listed as "watching"

    def test_one_positive_paper_is_only_watched_if_at_all(self):
        found = self.candidates(positives("pv0"))
        self.assertEqual([c for c in found if c["status"] == "ready"], [])

    def test_two_positive_papers_from_one_source_are_not_enough(self):
        papers = [dict(p, source="Joule") if p["key"].startswith("pv") else p for p in self.papers]
        found = self.candidates(positives("pv0", "pv1", "pv2"), papers=papers)
        self.assertEqual([c for c in found if c["status"] == "ready"], [])
        top = pv(found)
        self.assertTrue(top and top[0]["status"] == "watch" and top[0]["gates"]["sources"] is False)

    def test_a_cluster_of_fewer_than_three_papers_is_not_a_candidate(self):
        papers = [p for p in self.papers if p["key"] not in ("pv2", "pv3", "pv4", "pv5", "pv6", "pv7")]
        self.assertEqual(pv(self.candidates(positives("pv0", "pv1"), papers=papers)), [])

    def test_nothing_is_proposed_without_positive_evidence(self):
        self.assertEqual(self.candidates({}), [])

    def test_recent_positives_outrank_old_ones(self):
        all_days = {f"d{i}": f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(80)}   # eighty active days of other evidence
        extra = [paper(k, f"Filler {k}", "plain words only", source="Other") for k in all_days]
        recent = positives("pv0", "pv1", "pv2", "pv3", days={k: "2026-09-02" for k in ("pv0", "pv1", "pv2", "pv3")})
        old = positives("pv0", "pv1", "pv2", "pv3", days={k: "2025-01-02" for k in ("pv0", "pv1", "pv2", "pv3")})
        recent.update(all_days)
        old.update(all_days)
        a = pv(self.candidates(recent, papers=self.papers + extra))[0]
        b = pv(self.candidates(old, papers=self.papers + extra))[0]
        self.assertGreater(a["parts"]["R"], b["parts"]["R"])
        self.assertGreater(a["strength"], b["strength"])

    def test_the_result_does_not_depend_on_input_order(self):
        pos = positives("pv0", "pv1", "pv2", "pv3", "ep0", "ep1")
        shuffled = list(self.papers)
        random.Random(7).shuffle(shuffled)
        self.assertEqual(self.candidates(pos), self.candidates(dict(reversed(list(pos.items()))), papers=shuffled))

    def test_a_cluster_that_sits_inside_an_existing_concept_gets_that_concept_as_parent(self):
        graph = graph_of(("Solar cells", ["solar cell"], []))
        wider = self.papers + [paper(f"sc{i}", f"Silicon solar cell design {i}", "solar cell silicon wafer", source="Solar Energy") for i in range(6)]
        found = self.candidates(positives("pv0", "pv1", "pv2", "pv3", "pv4", "pv5"), papers=wider, graph=graph)
        top = pv(found)[0]
        self.assertEqual(top["parent"], graph["concepts"][0]["id"])
        self.assertEqual(top["status"], "ready")   # a specialisation of a broader concept is still a new branch

    def test_a_prerequisite_is_proposed_when_the_new_branch_mentions_an_existing_concept_more(self):
        graph = graph_of(("Halide chemistry", ["halide"], []))
        papers = [paper(f"h{i}", f"Halide salts overview {i}", "halide ionic crystals basic chemistry", source="Chem") for i in range(4)] + self.papers
        found = self.candidates(positives("pv0", "pv1", "pv2", "pv3"), papers=papers, graph=graph)
        top = pv(found)[0]
        self.assertEqual([p["from"] for p in top["prereqs"]], [graph["concepts"][0]["id"]])
        self.assertGreaterEqual(top["prereqs"][0]["support"], 0.15)
        self.assertEqual(top["layer"], 2)

    def test_merging_adds_a_proposed_grown_concept_without_touching_the_original(self):
        graph = graph_of(("Halide chemistry", ["halide"], []))
        papers = [paper(f"h{i}", f"Halide salts overview {i}", "halide ionic crystals basic chemistry", source="Chem") for i in range(4)] + self.papers
        top = [c for c in pv(self.candidates(positives("pv0", "pv1", "pv2", "pv3"), papers=papers, graph=graph)) if c["status"] == "ready"][0]
        merged = pgr.merge_candidate(graph, top)
        self.assertEqual(len(graph["concepts"]), 1)
        added = merged["concepts"][-1]
        self.assertEqual((added["origin"], added["state"]), ("grown", "proposed"))
        self.assertTrue(pg.is_acyclic(merged))
        self.assertEqual(len(merged["prereqs"]), 1)
        self.assertEqual(merged["prereqs"][0]["state"], "proposed")

    def test_near_duplicate_phrases_collapse_into_one_candidate(self):
        found = self.candidates(positives("pv0", "pv1", "pv2", "pv3"))
        sets = [frozenset(c["papers"]) for c in found]
        self.assertEqual(len(sets), len(set(sets)))

    def test_the_list_is_bounded(self):
        many = []
        for t in range(12):
            for i in range(4):
                many.append(paper(f"t{t}_{i}", f"Topic{t}word Topic{t}term study {i}", f"topic{t}word topic{t}term material", source=("S1", "S2")[i % 2]))
        pos = positives(*[p["key"] for p in many])
        self.assertLessEqual(len(pgr.branch_candidates(self.graph, many, pos)), pgr.MAX_CANDIDATES)

    def test_a_display_threshold_of_two_cannot_crowd_a_ready_direction_out_of_the_phrase_cap(self):
        papers = []
        for i in range(pgr.MAX_PHRASES + 10):    # many two-paper phrases that sort before the real one
            for j in range(2):
                papers.append(paper(f"pair{i}_{j}", f"alpha{i:02d} beta{i:02d} note {j}", f"alpha{i:02d} beta{i:02d} detail", source=("S1", "S2")[j]))
        for j in range(3):
            papers.append(paper(f"real{j}", f"zzzz yyyy method {j}", "zzzz yyyy yyyy method material", source=("Nature", "Joule", "Nature")[j]))
        pos = positives(*[p["key"] for p in papers if p["key"].startswith("pair")], "real0", "real1")
        strict = pgr.branch_candidates(self.graph, papers, pos, limit=200)
        loose = pgr.branch_candidates(self.graph, papers, pos, min_members=2, limit=200)
        is_real = lambda c: all(k.startswith("real") for k in c["papers"])
        self.assertEqual([c["status"] for c in strict if is_real(c)], ["ready"])
        self.assertEqual([c["status"] for c in loose if is_real(c)], ["ready"])

    def test_a_large_corpus_is_handled(self):
        many = [paper(f"k{i}", f"Paper {i} about topic{i % 40} widgets", f"topic{i % 40} widgets analysis", source=f"S{i % 5}") for i in range(600)]
        found = pgr.branch_candidates(self.graph, many, positives(*[p["key"] for p in many[:120]]))
        self.assertLessEqual(len(found), pgr.MAX_CANDIDATES)

    def test_random_corpora_never_break_the_rules(self):
        rng = random.Random(20261005)
        vocab = [f"w{i}x" for i in range(30)] + ["epitaxy", "gan", "perovskite", "solar", "cell", "growth", "quantum", "dot"]
        for round_ in range(60):
            papers = [paper(f"r{i}", " ".join(rng.choices(vocab, k=rng.randint(2, 6))), " ".join(rng.choices(vocab, k=rng.randint(0, 15))),
                            source=rng.choice(["A", "B", "C", None])) for i in range(rng.randint(0, 80))]
            pos = {p["key"]: rng.choice([None, "2026-09-0%d" % rng.randint(1, 9)]) for p in papers if rng.random() < 0.3}
            graph = rng.choice([pg.empty_graph(), self.graph])
            first = pgr.branch_candidates(graph, papers, pos)
            self.assertEqual(first, pgr.branch_candidates(graph, list(reversed(papers)), pos), round_)
            self.assertLessEqual(len(first), pgr.MAX_CANDIDATES)
            for cand in first:
                self.assertIn(cand["status"], ("ready", "watch"))
                self.assertTrue(0.0 <= cand["strength"] <= 1.0, cand)
                self.assertGreaterEqual(len(cand["papers"]), pgr.MIN_MEMBERS)
                self.assertGreaterEqual(len(cand["positive"]), pgr.MIN_POSITIVE)
                if cand["status"] == "ready":
                    self.assertTrue(all(cand["gates"].values()) and cand["strength"] >= pgr.MIN_STRENGTH)
                self.assertTrue(all(p["from"] in {c["id"] for c in graph["concepts"]} for p in cand["prereqs"]))
                if graph["concepts"]:
                    self.assertTrue(pg.is_acyclic(pgr.merge_candidate(graph, cand)))

    def test_phrases_are_adjacent_in_the_text_so_every_search_term_can_actually_match(self):
        papers = [paper(f"po{i}", f"Policy for robot learning study {i}", "policy for robot learning with sparse reward signals", source=("A", "B")[i % 2])
                  for i in range(5)]
        found = pgr.branch_candidates(self.graph, papers, positives("po0", "po1", "po2"))
        self.assertTrue(found)
        for cand in found:
            self.assertNotIn("policy robot", cand["terms"])   # "for" sits between them
            for term in cand["terms"]:
                self.assertTrue(any(pgr.term_in_text(f"{p['title']} {p['abstract']}", term) for p in papers if p["key"] in cand["papers"]), term)

    def test_every_term_of_every_candidate_matches_some_member_on_random_corpora(self):
        rng = random.Random(99)
        vocab = [f"w{i}x" for i in range(12)] + ["for", "the", "with", "and", "of"]
        for round_ in range(40):
            papers = [paper(f"r{i}", " ".join(rng.choices(vocab, k=rng.randint(2, 7))), " ".join(rng.choices(vocab, k=rng.randint(0, 20))),
                            source=rng.choice(["A", "B", "C"])) for i in range(rng.randint(5, 40))]
            pos = {p["key"]: None for p in papers if rng.random() < 0.5}
            for cand in pgr.branch_candidates(pg.empty_graph(), papers, pos):
                for term in cand["terms"]:
                    self.assertTrue(any(pgr.term_in_text(f"{p['title']} {p['abstract']}", term) for p in papers if p["key"] in cand["papers"]), (round_, term))

    def test_the_same_paper_under_two_keys_counts_once(self):
        twin = [paper("k1", "Perovskite solar cell stability study", "perovskite solar cell efficiency stability", source="arXiv"),
                paper("k2", "Perovskite solar cell stability study", "perovskite solar cell efficiency stability", source="Joule"),
                paper("k3", "Perovskite solar cell outlook", "perovskite solar cell efficiency stability", source="Nature")]
        found = pgr.branch_candidates(self.graph, twin, positives("k1", "k2"))
        self.assertEqual([c for c in found if c["status"] == "ready"], [])
        self.assertTrue(all(c["gates"]["positive"] is False for c in found))

    def test_a_doi_identifies_the_same_paper_even_when_titles_differ(self):
        a, b = paper("k1", "Perovskite solar cells", "perovskite solar", source="A"), paper("k2", "Perovskite photovoltaics", "perovskite solar", source="B")
        a["doi"] = b["doi"] = "https://doi.org/10.1/SAME"
        c = paper("k3", "Perovskite solar outlook", "perovskite solar", source="C")
        found = pgr.branch_candidates(self.graph, [a, b, c], positives("k1", "k2"))
        self.assertTrue(all(cand["gates"]["positive"] is False for cand in found))

    def test_sources_are_compared_after_trimming_and_lowercasing(self):
        papers = [dict(p, source=("arXiv", " arxiv ", "ARXIV")[int(p["key"][2:]) % 3]) if p["key"].startswith("pv") else p for p in self.papers]
        found = self.candidates(positives("pv0", "pv1", "pv2", "pv3"), papers=papers)
        self.assertEqual([c for c in found if c["status"] == "ready"], [])
        self.assertTrue(pv(found) and pv(found)[0]["gates"]["sources"] is False)

    def test_mixed_date_types_and_unknown_positive_keys_are_tolerated(self):
        pos = {"pv0": "2026-09-01", "pv1": 20260902, "pv2": None, "pv3": "2026-09-03", "ghost": "2026-09-04"}
        self.assertTrue(pv(self.candidates(pos)))

    def test_merging_twice_adds_the_concept_once_and_never_a_redundant_edge(self):
        graph = graph_of(("A", ["aterm"], []), ("B", ["bterm"], [0]))
        a, b = [c["id"] for c in graph["concepts"]]
        cand = {"id": "g-1", "name": "new topic", "terms": ["new topic"], "papers": ["x"], "parent": None, "prereqs": [{"from": a, "support": 0.5}, {"from": b, "support": 0.4}]}
        once = pgr.merge_candidate(graph, cand)
        twice = pgr.merge_candidate(once, cand)
        self.assertEqual(once, twice)
        new_id = once["concepts"][-1]["id"]
        self.assertEqual([(e["from"], e["to"]) for e in once["prereqs"] if e["to"] == new_id], [(b, new_id)])   # a -> new is implied by a -> b -> new

    def test_a_big_corpus_stays_fast_enough(self):
        import time
        many = [paper(f"k{i}", f"Paper {i} about topic{i % 50} widgets", f"topic{i % 50} widgets analysis of kind{i % 7}", source=f"S{i % 5}") for i in range(1500)]
        graph = graph_of(*[(f"Concept {j}", [f"kind{j}", f"topic{j}"], []) for j in range(8)])
        started = time.time()
        pgr.branch_candidates(graph, many, positives(*[p["key"] for p in many[:150]]))
        self.assertLess(time.time() - started, 3.0)

    def test_proposals_never_mutate_the_inputs(self):
        before = (repr(self.graph), repr(self.papers))
        self.candidates(positives("pv0", "pv1", "pv2", "pv3"))
        self.assertEqual((repr(self.graph), repr(self.papers)), before)


if __name__ == "__main__":
    unittest.main()
