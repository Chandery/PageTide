import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from app.clustering import ClusteringUnavailable, cluster, corpus_fingerprint


PAPERS = [
    {"key": "a", "title": "Robotics motion planning", "abstract": "robotics motion control"},
    {"key": "b", "title": "Robotics motion planning", "abstract": "robotics motion control"},
    {"key": "c", "title": "Cancer clinical trial", "abstract": "cancer clinical medicine"},
    {"key": "d", "title": "Cancer clinical trial", "abstract": "cancer clinical medicine"},
    {"key": "empty", "title": "", "abstract": ""},
]
HAS_NETWORKX = importlib.util.find_spec("networkx") is not None


class FingerprintTests(unittest.TestCase):
    def test_order_independent_and_excludes_private_notes(self):
        changed = [dict(paper, note="private", saved_at="later") for paper in reversed(PAPERS)]
        self.assertEqual(corpus_fingerprint(PAPERS), corpus_fingerprint(changed))
        changed[0]["abstract"] = "changed content"
        self.assertNotEqual(corpus_fingerprint(PAPERS), corpus_fingerprint(changed))
        self.assertNotEqual(corpus_fingerprint(PAPERS), corpus_fingerprint(PAPERS[:-1]))

    def test_bad_corpus_rejected(self):
        for papers in ([PAPERS[0], PAPERS[0]], [{"key": ""}], [{"key": "x", "title": 7}]):
            with self.subTest(papers=papers), self.assertRaises(ValueError):
                corpus_fingerprint(papers)

    def test_missing_dependency_explicit_even_for_empty_corpus(self):
        with patch.dict(sys.modules, {"networkx": None}):
            with self.assertRaisesRegex(ClusteringUnavailable, "NetworkX"):
                cluster([])

    def test_resource_limits_do_not_silently_sample(self):
        with patch("app.clustering.MAX_PAPERS", 1), self.assertRaises(ValueError):
            cluster(PAPERS)
        with patch("app.clustering.MAX_TEXT", 1), self.assertRaises(ValueError):
            cluster(PAPERS)


@unittest.skipUnless(HAS_NETWORKX, "NetworkX optional dependency not installed")
class ClusteringTests(unittest.TestCase):
    def test_groups_separate_topics_and_keep_isolated_papers(self):
        result = cluster(PAPERS)
        self.assertEqual([g["keys"] for g in result["groups"]], [["a", "b"], ["c", "d"], ["empty"]])
        self.assertTrue(all(e["kind"] == "similarity" for e in result["edges"]))
        self.assertEqual(result["algorithm"], "tfidf-louvain-v1")

    def test_determinism_and_stable_ids(self):
        first = cluster(PAPERS)
        self.assertEqual(first, cluster(list(reversed(PAPERS))))
        changed = [dict(p) for p in PAPERS]
        changed[0]["title"] += " robotics"
        self.assertEqual([g["id"] for g in first["groups"]],
                         [g["id"] for g in cluster(changed)["groups"]])

    def test_determinism_across_hash_seeds(self):
        code = "from app.clustering import cluster; import json; print(json.dumps(cluster(%r),sort_keys=True))" % PAPERS
        outputs = []
        for seed in ("1", "42"):
            outputs.append(subprocess.check_output([sys.executable, "-c", code],
                           cwd=str(Path(__file__).resolve().parents[1]),
                           env=dict(os.environ, PYTHONHASHSEED=seed), text=True, timeout=30))
        self.assertEqual(json.loads(outputs[0]), json.loads(outputs[1]))

    def test_empty_singleton_and_no_vocabulary(self):
        self.assertEqual(cluster([])["groups"], [])
        self.assertEqual(cluster([PAPERS[-1]])["groups"][0]["name"], "Unclassified")
        result = cluster([{"key": "a"}, {"key": "b"}])
        self.assertEqual([g["keys"] for g in result["groups"]], [["a"], ["b"]])


if __name__ == "__main__":
    unittest.main()
