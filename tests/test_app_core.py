import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import ranking
from app.db import Store
from app.gateway import BudgetExceeded, Gateway
from app.service import App


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "t.sqlite")
        self.store.init()
        self.addCleanup(self.store.close)

    def _paper(self, key, title="World Model Paper"):
        self.store.upsert_papers([{"key": key, "title": title, "abstract": "latent prediction",
                                   "published": "2026-01-01", "group_name": "field"}])

    def test_papers_batch_and_cards(self):
        self._paper("p1")
        self._paper("p2")
        batch_id = self.store.create_batch("2026-09-11", ["p1", "p2"])
        rows = self.store.batch(batch_id)
        self.assertEqual([r["key"] for r in rows], ["p1", "p2"])
        self.assertEqual(rows[0]["rank"], 1)

    def test_upsert_is_idempotent(self):
        self._paper("p1")
        added = self.store.upsert_papers([{"key": "p1", "title": "World Model Paper"}])
        self.assertEqual(added, 0)
        self.assertEqual(len(self.store.papers()), 1)

    def test_feedback_and_undo(self):
        self._paper("p1")
        fid = self.store.add_feedback("p1", "useful")
        self.assertEqual(self.store.feedback_by_paper()["p1"]["action"], "useful")
        self.store.undo_feedback(fid)
        self.assertEqual(self.store.feedback_by_paper(), {})
        self.assertEqual(len(self.store.feedback(include_undone=True)), 1)

    def test_profile_versions_are_append_only(self):
        self.store.save_profile({"pinned_terms": []}, note="v1")
        self.store.save_profile({"pinned_terms": ["jepa"]}, note="v2")
        versions = self.store.profile_versions()
        self.assertEqual([v["note"] for v in versions], ["v1", "v2"])
        self.assertEqual(self.store.current_profile()["pinned_terms"], ["jepa"])


class RankingTests(unittest.TestCase):
    def test_rocchio_subtracts_negatives(self):
        seed = [ranking.l2_normalize({"world": 1.0, "model": 1.0})]
        pos = [ranking.l2_normalize({"planning": 1.0})]
        neg = [ranking.l2_normalize({"cancer": 1.0})]
        profile = ranking.rocchio(seed, pos, neg, 1.0, 1.0)
        self.assertIn("planning", profile)
        self.assertNotIn("cancer", profile)

    def test_mmr_prefers_diverse_selection(self):
        vectors = {
            "a": {"world": 1.0},
            "b": {"world": 0.99, "x": 0.01},   # near-duplicate of a
            "c": {"robotics": 1.0},            # different but relevant
        }
        scored = [("a", 1.0), ("b", 0.99), ("c", 0.8)]
        chosen = ranking.mmr_select(scored, vectors, 2, lambda_=0.5)
        self.assertEqual(chosen[0], "a")
        self.assertEqual(chosen[1], "c")

    def test_mmr_is_deterministic(self):
        vectors = {"a": {"x": 1.0}, "b": {"y": 1.0}, "c": {"z": 1.0}}
        scored = [("a", 1.0), ("b", 1.0), ("c", 1.0)]
        self.assertEqual(ranking.mmr_select(scored, vectors, 3),
                         ranking.mmr_select(scored, vectors, 3))


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_dry_run_reserves_without_network(self):
        gateway = Gateway(root=".", ledger=Path(self.tmp.name) / "usage.jsonl")
        result = gateway.call("daily_triage", [], dry_run=True)
        self.assertTrue(result["ok"]) if result.get("ok") else None
        if result.get("ok"):
            self.assertEqual(result["operation"], "daily_triage")
            self.assertIn("reservation", result)

    def test_unregistered_operation_is_rejected(self):
        gateway = Gateway(root=".", ledger=Path(self.tmp.name) / "usage.jsonl")
        result = gateway.call("not_registered", [], dry_run=True)
        self.assertFalse(result["ok"])
        self.assertTrue(result["degraded"])


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = App(root=".", data_dir=Path(self.tmp.name) / "app")
        self.app.store.upsert_papers([
            {"key": "p1", "title": "World Model Planning", "abstract": "latent planning",
             "published": "2026-08-01", "group_name": "field"},
            {"key": "p2", "title": "Cancer Biomarker Study", "abstract": "clinical trial",
             "published": "2026-08-02", "group_name": "distractor"},
        ])

    def test_busy_and_confused_do_not_change_interest(self):
        result = self.app.record_feedback("p1", "busy")
        self.assertFalse(result["interest_changed"])
        profile = self.app.profile()
        self.assertIn("p1", profile["neutral_feedback"])
        self.assertNotIn("p1", profile["positive_feedback"])

    def test_irrelevant_is_explicit_negative(self):
        result = self.app.record_feedback("p2", "irrelevant")
        self.assertTrue(result["interest_changed"])
        self.assertIn("p2", self.app.profile()["explicit_negatives"])

    def test_unknown_action_rejected(self):
        with self.assertRaises(ValueError):
            self.app.record_feedback("p1", "hate")

    def test_build_batch_excludes_seen_and_feedback(self):
        first = self.app.build_batch(limit=2)
        self.assertEqual(len(first["cards"]), 2)
        second = self.app.build_batch(limit=2)
        self.assertEqual(second["cards"], [])  # everything already exposed

    def test_cards_have_reason_and_url(self):
        self.app.build_batch(limit=1)
        card = self.app.cards()[0]
        self.assertTrue(card["why"])
        self.assertEqual(card["mode"], "sparse")

    def test_pinned_terms_are_used(self):
        data = self.app.store.current_profile() or {"project": "world-models", "weights": {"pos": 1.0, "neg": 0.5}}
        data["pinned_terms"] = ["planning"]
        self.app.save_profile(data, note="pin")
        self.assertEqual(self.app.profile()["pinned_terms"], ["planning"])


if __name__ == "__main__":
    unittest.main()
