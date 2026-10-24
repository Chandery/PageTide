import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.service import App
from app.weekly_report import generate_weekly_report


class ProfileInsightsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(root=".", data_dir=Path(self.tmp.name) / "app")
        self.project = self.app.projects.create_project("Test project", "manual", [])   # a fresh app has no project
        self.app.store.upsert_papers([
            {"key": "p1", "title": "Latent world model planning", "abstract": "planning with temporal memory", "published": "2025", "source": "test", "project_id": self.project},
            {"key": "p2", "title": "Visual representation learning", "abstract": "contrastive representation for agents", "published": "2025", "source": "test", "project_id": self.project},
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_keywords_are_deterministic_and_evidence_backed(self):
        self.app.record_feedback("p1", "useful", project_id=self.project)
        first = self.app.profile_insights(self.project)
        second = self.app.profile_insights(self.project)
        self.assertEqual(first, second)
        terms = {item["term"] for item in first["keyword_distribution"]}
        self.assertIn("planning", terms)
        self.assertEqual(first["keyword_evidence"]["papers"], 1)

    def test_timeline_only_counts_real_events(self):
        before = self.app.profile_insights(self.project)
        self.assertFalse(before["timeline"]["has_activity"])
        self.app.record_feedback("p2", "irrelevant", project_id=self.project)
        after = self.app.profile_insights(self.project)
        self.assertTrue(after["timeline"]["has_activity"])
        self.assertEqual(sum(item["negative"] for item in after["timeline"]["weeks"]), 1)
        self.assertEqual(sum(item["activity"] for item in after["timeline"]["weeks"]), 1)

    def test_understood_is_counted_apart_and_keeps_the_interest_label(self):
        self.app.record_feedback("p1", "useful", project_id=self.project)
        self.app.record_feedback("p1", "understood", project_id=self.project)
        self.app.record_feedback("p2", "too_hard", project_id=self.project)
        result = self.app.profile_insights(self.project)
        self.assertEqual((result["signals"]["positive"], result["signals"]["too_hard"]), (1, 1))
        weeks = result["timeline"]["weeks"]
        self.assertEqual((sum(w["positive"] for w in weeks), sum(w["understood"] for w in weeks)), (1, 1))
        self.assertEqual(sum(w["interest_score"] for w in weeks), 1)   # understanding is not interest
        self.assertEqual([i["key"] for i in self.app.profile_evidence(self.project, "positive")["items"]], ["p1"])
        self.assertEqual([i["key"] for i in self.app.profile_evidence(self.project, "understood")["items"]], ["p1"])

    def test_weekly_keyword_changes_compare_two_real_periods(self):
        now = datetime.now(timezone.utc)
        self.app.record_feedback("p1", "useful", project_id=self.project)
        self.app.store.conn.execute(
            "UPDATE feedback SET created_at=? WHERE paper_key='p1'",
            ((now - timedelta(days=8)).isoformat(),),
        )
        self.app.store.conn.execute(
            "UPDATE library SET saved_at=? WHERE paper_key='p1'",
            ((now - timedelta(days=8)).isoformat(),),
        )
        self.app.store.conn.commit()
        self.app.record_feedback("p2", "useful", project_id=self.project)
        report = generate_weekly_report(self.project, self.app)
        rising = {item["term"] for item in report["keyword_changes"]["rising"]}
        self.assertIn("representation", rising)
        self.assertTrue(report["has_activity"])


if __name__ == "__main__":
    unittest.main()
