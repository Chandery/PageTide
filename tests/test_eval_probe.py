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


if __name__ == "__main__":
    unittest.main()
