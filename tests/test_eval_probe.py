import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import eval_probe


class EvalProbeTests(unittest.TestCase):
    def test_tokenize_drops_stopwords_and_short_tokens(self):
        tokens = eval_probe.tokenize("The World-Model is a JEPA for planning of models")
        self.assertIn("world-model", tokens)
        self.assertIn("jepa", tokens)
        self.assertIn("planning", tokens)
        self.assertNotIn("the", tokens)
        self.assertNotIn("of", tokens)
        self.assertNotIn("is", tokens)

    def test_idf_downweights_common_terms(self):
        docs = [eval_probe.tokenize("world model planning"), eval_probe.tokenize("world model biology")]
        idf = eval_probe.build_idf(docs)
        self.assertLess(idf["world"], idf["planning"])

    def test_vectorize_and_cosine_rank_similar_docs_higher(self):
        docs = [eval_probe.tokenize("world model planning jepa"),
                eval_probe.tokenize("world model planning robotics"),
                eval_probe.tokenize("cancer biomarker clinical trial")]
        idf = eval_probe.build_idf(docs)
        vectors = [eval_probe.l2_normalize(eval_probe.vectorize(d, idf)) for d in docs]
        self.assertGreater(eval_probe.cosine(vectors[0], vectors[1]),
                           eval_probe.cosine(vectors[0], vectors[2]))

    def test_centroid_normalized_and_orders_top_terms(self):
        docs = [eval_probe.tokenize("world model planning"), eval_probe.tokenize("world model prediction")]
        idf = eval_probe.build_idf(docs)
        vectors = [eval_probe.l2_normalize(eval_probe.vectorize(d, idf)) for d in docs]
        center = eval_probe.centroid(vectors)
        self.assertAlmostEqual(sum(v * v for v in center.values()), 1.0, places=6)
        self.assertEqual(max(center, key=center.get), "world")

    def test_precision_at_k_returns_none_for_unjudged_top_k(self):
        labels = {"a": {"relevance": 3}, "b": {"relevance": 1}, "c": {"relevance": 2}}
        self.assertEqual(eval_probe.precision_at_k(["a", "c", "b"], labels, 2, 2), 1.0)
        self.assertEqual(eval_probe.precision_at_k(["a", "c", "b"], labels, 3, 2), 2 / 3)
        self.assertEqual(eval_probe.precision_at_k(["a", "c", "b"], labels, 3, 3), 1 / 3)
        self.assertIsNone(eval_probe.precision_at_k(["a", "zzz", "b"], labels, 3, 2))

    def test_mean_relevance_at_k(self):
        labels = {"a": {"relevance": 3}, "b": {"relevance": 0}, "c": {"relevance": 2}}
        self.assertEqual(eval_probe.mean_relevance_at_k(["a", "c", "b"], labels, 3), 5 / 3)
        self.assertEqual(eval_probe.mean_relevance_at_k(["a"], labels, 1), 3.0)
        self.assertIsNone(eval_probe.mean_relevance_at_k(["a", "zzz"], labels, 2))

    def test_cosine_handles_empty_vectors(self):
        self.assertEqual(eval_probe.cosine({}, {}), 0.0)
        self.assertEqual(eval_probe.l2_normalize({}), {})

    def test_parse_spotcheck_sheet_reads_levels_and_keys(self):
        import tempfile
        sheet = """# t

## 1. relevance = _3_
- Title A
- 2026-08-01 · https://doi.org/10.1/a

abstract

## 2. relevance = _0_
- Title B
- 2026-08-02 · https://doi.org/10.1/b
"""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'sheet.md'
            path.write_text(sheet)
            items = eval_probe.parse_spotcheck_sheet(path)
        self.assertEqual(items, [('https://doi.org/10.1/a', 3), ('https://doi.org/10.1/b', 0)])

    def test_spotcheck_agreement_counts_exact_within1_and_binary(self):
        items = [('a', 0), ('b', 1), ('c', 2), ('d', 3)]
        labels = {'a': {'relevance': 1}, 'b': {'relevance': 3}, 'c': {'relevance': 3}, 'd': {'relevance': 3}}
        stats = eval_probe.spotcheck_agreement(items, labels)
        self.assertEqual(stats['n'], 4)
        self.assertEqual(stats['exact'], 0.25)          # only d matches exactly
        self.assertEqual(stats['within1'], 0.75)        # a and c are within 1, b (1 vs 3) is not
        self.assertEqual(stats['binary'], 0.75)         # b disagrees on useful>=2

    def test_spotcheck_agreement_ignores_unmatched_keys(self):
        stats = eval_probe.spotcheck_agreement([('zzz', 2)], {})
        self.assertEqual(stats['n'], 0)

    def test_rocchio_profile_adds_positives_and_subtracts_negatives(self):
        seed = [{"world": 1.0, "model": 1.0}]
        positive = [{"planning": 1.0, "latent": 1.0}]
        negative = [{"cancer": 1.0}]
        frozen = eval_probe.build_rocchio_profile(seed, [], [])
        updated = eval_probe.build_rocchio_profile(seed, positive, negative, 1.0, 1.0)
        self.assertIn("planning", updated)
        self.assertGreater(updated.get("planning", 0), frozen.get("planning", 0))
        # A term only present in the negative centroid must not survive.
        self.assertNotIn("cancer", updated)

    def test_rocchio_profile_is_l2_normalized(self):
        profile = eval_probe.build_rocchio_profile([{"a": 2.0, "b": 1.0}], [{"c": 3.0}], [], 1.0, 0.0)
        self.assertAlmostEqual(sum(v * v for v in profile.values()), 1.0, places=6)

    def test_feedback_split_is_chronological_and_disjoint(self):
        candidates = [
            {"key": "a", "publication_date": "2026-07-01"},
            {"key": "b", "publication_date": "2026-08-01"},
            {"key": "c", "publication_date": "2026-09-01"},
            {"key": "d", "publication_date": "2026-09-15"},
        ]
        labels = {c["key"]: {"relevance": 3} for c in candidates}
        a, b, split = eval_probe.feedback_split(candidates, labels)
        self.assertEqual([c["key"] for c in a], ["a", "b"])
        self.assertEqual([c["key"] for c in b], ["c", "d"])
        self.assertEqual(split, "2026-09-01")

    def test_feedback_split_honours_explicit_date(self):
        candidates = [{"key": "a", "publication_date": "2026-07-01"},
                      {"key": "b", "publication_date": "2026-08-01"}]
        labels = {c["key"]: {"relevance": 2} for c in candidates}
        a, b, split = eval_probe.feedback_split(candidates, labels, "2026-08-01")
        self.assertEqual([c["key"] for c in a], ["a"])
        self.assertEqual([c["key"] for c in b], ["b"])
        self.assertEqual(split, "2026-08-01")

    def test_ranking_auc_rewards_useful_items_on_top(self):
        labels = {"u1": {"relevance": 3}, "u2": {"relevance": 2}, "n1": {"relevance": 1}, "n2": {"relevance": 0}}
        perfect = eval_probe.ranking_auc(["u1", "u2", "n1", "n2"], labels, 2)
        worst = eval_probe.ranking_auc(["n1", "n2", "u1", "u2"], labels, 2)
        self.assertEqual(perfect, 1.0)
        self.assertEqual(worst, 0.0)
        self.assertIsNone(eval_probe.ranking_auc(["u1", "u2"], labels, 2))

    def test_mean_rank_of_useful(self):
        labels = {"u1": {"relevance": 3}, "u2": {"relevance": 2}, "n1": {"relevance": 1}}
        self.assertEqual(eval_probe.mean_rank_of_useful(["n1", "u1", "u2"], labels, 2), 2.5)
        self.assertIsNone(eval_probe.mean_rank_of_useful(["n1"], labels, 2))


if __name__ == "__main__":
    unittest.main()
