"""CORE-01 / PROFILE-01: replayable feedback, freeze/restore, isolation and safe deletion.

Everything here is local and zero-token; no test performs a network request.
"""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import ranking
from app.db import Store
from app.migrations import MIGRATIONS, get_schema_version
from app.service import App
from app.sources import SourceError
from app.weekly_report import generate_weekly_report

ROOT = Path(__file__).resolve().parents[1]

PAPERS = [
    ("p1", "Latent world model planning", "planning with a learned latent dynamics model"),
    ("p2", "World model for robot manipulation", "latent imagination for robot control"),
    ("p3", "Protein folding with transformers", "biology structure prediction"),
    ("p4", "Graph neural networks for chemistry", "molecule property prediction"),
    ("p5", "Video prediction world model", "predict future frames for planning"),
    ("p6", "Dreamer style model based RL", "world model reinforcement learning in latent space"),
    ("p7", "Speech recognition at scale", "audio transcription with transformers"),
]


class CoreChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "PDH_DEV": "0"})
        env.start()
        self.addCleanup(env.stop)
        self.app = App(root=ROOT, data_dir=Path(self.tmp.name) / "app")
        self.a = self.app.create_project("A", "manual", ["world model", "planning"])["project_id"]
        self.b = self.app.create_project("B", "manual", ["protein"])["project_id"]
        for pid in (self.a, self.b):
            self.app.store.upsert_papers([{"key": k, "title": t, "abstract": ab, "published": f"2026-08-0{i + 1}",
                                           "project_id": pid} for i, (k, t, ab) in enumerate(PAPERS)])

    # ------------------------------------------------------------ helpers
    def _vector(self, pid):
        rows = [dict(r) for r in self.app.store.conn.execute(
            "SELECT p.* FROM project_papers pp JOIN papers p ON p.key=pp.paper_key WHERE pp.project_id=?", (pid,))]
        idf = ranking.build_idf([ranking.tokenize(f"{p['title']} {p['abstract']}") for p in rows])
        return self.app.profile_vector({p["key"]: p for p in rows}, idf, pid)

    def _snapshot(self, pid):
        insights = self.app.profile_insights(pid)
        return {"profile": self.app.profile(pid), "vector": self._vector(pid), "stats": self.app.stats(pid),
                "signals": insights["signals"], "weekly": generate_weekly_report(pid, self.app)["stats"]}

    # ------------------------------------------------------------ CORE-01
    def test_ranking_is_replayable_and_needs_no_pdf_or_model(self):
        with mock.patch("app.gateway.urllib.request.urlopen") as urlopen:
            first = self.app.build_batch(project_id=self.a, exclude_seen=False)
            second = self.app.build_batch(project_id=self.a, exclude_seen=False)
        urlopen.assert_not_called()
        self.assertEqual([c["key"] for c in first["cards"]], [c["key"] for c in second["cards"]])
        self.assertEqual(self.app.store.conn.execute("SELECT COUNT(*) FROM pdfs").fetchone()[0], 0)

    def test_repeat_exposure_and_feedback_exclusion(self):
        first = [c["key"] for c in self.app.build_batch(limit=3, project_id=self.a)["cards"]]
        self.app.record_feedback(first[0], "useful", project_id=self.a)
        second = self.app.build_batch(limit=3, project_id=self.a)
        keys = [c["key"] for c in second["cards"]]
        self.assertFalse(set(first) & set(keys), "seen papers must not be shown again")
        self.assertIsNone(second["shortfall"])
        third = self.app.build_batch(limit=5, project_id=self.a)
        self.assertEqual(len(third["cards"]), 1)
        self.assertEqual(third["shortfall"]["available"], 1)
        self.assertEqual(third["shortfall"]["excluded_seen"], 6)
        empty = self.app.build_batch(limit=5, project_id=self.a)
        self.assertEqual(empty["cards"], [])
        self.assertEqual(empty["shortfall"]["available"], 0)
        self.assertIn("reason", empty["shortfall"])

    def test_labels_are_distinct_and_too_hard_is_not_disinterest(self):
        base = self._vector(self.a)
        self.app.record_feedback("p3", "too_hard", project_id=self.a)
        profile = self.app.profile(self.a)
        self.assertEqual(profile["too_hard_feedback"], ["p3"])
        self.assertEqual(profile["explicit_negatives"], [])
        self.assertEqual(self._vector(self.a), base, "difficulty must not change interest")
        self.app.record_feedback("p2", "irrelevant", project_id=self.a)
        self.assertNotEqual(self._vector(self.a), base, "explicit irrelevance does change interest")
        self.assertNotIn("hard", self.app.profile(self.a)["weights"])

    def test_no_action_changes_nothing(self):
        before = self._snapshot(self.a)
        self.app.build_batch(project_id=self.a)  # shown but not labelled
        after = self._snapshot(self.a)
        self.assertEqual(before["profile"], after["profile"])
        self.assertEqual(before["vector"], after["vector"])

    # --------------------------------------------------------- PROFILE-01
    def test_feedback_is_idempotent(self):
        first = self.app.record_feedback("p1", "useful", project_id=self.a)
        again = self.app.record_feedback("p1", "useful", project_id=self.a)
        self.assertEqual(again["feedback_id"], first["feedback_id"])
        self.assertTrue(again["duplicate"])
        self.assertEqual(self.app.store.conn.execute(
            "SELECT COUNT(*) FROM feedback WHERE project_id=?", (self.a,)).fetchone()[0], 1)

    def test_undo_replays_to_the_pre_feedback_state_everywhere(self):
        self.app.build_batch(project_id=self.a)
        self.app.record_feedback("p2", "irrelevant", project_id=self.a)
        before = self._snapshot(self.a)
        event = self.app.record_feedback("p1", "useful", project_id=self.a)
        changed = self._snapshot(self.a)
        self.assertNotEqual(before["vector"], changed["vector"])
        self.app.undo_feedback(event["feedback_id"], self.a)
        after = self._snapshot(self.a)
        self.assertEqual(after["vector"], before["vector"])
        self.assertEqual(after["profile"], before["profile"])
        for key in ("positive", "negative", "too_hard", "shown"):
            self.assertEqual(after["stats"][key], before["stats"][key], key)
        self.assertEqual(after["signals"]["positive"], before["signals"]["positive"])
        self.assertEqual(after["weekly"]["positive"], before["weekly"]["positive"])
        # The save is a separate user fact and stays (documented profile-redesign rule).
        self.assertEqual(after["stats"]["saved"], 1)

    def test_undo_restores_an_earlier_label_and_is_project_checked(self):
        first = self.app.record_feedback("p1", "useful", project_id=self.a)
        second = self.app.record_feedback("p1", "irrelevant", project_id=self.a)
        self.assertEqual(self.app.profile(self.a)["explicit_negatives"], ["p1"])
        with self.assertRaises(ValueError):
            self.app.undo_feedback(second["feedback_id"], self.b)
        self.app.undo_feedback(second["feedback_id"], self.a)
        profile = self.app.profile(self.a)
        self.assertEqual(profile["positive_feedback"], ["p1"])
        self.assertEqual(profile["explicit_negatives"], [])
        self.assertEqual(self.app.latest_feedback(self.a)["p1"]["id"], first["feedback_id"])

    def test_freeze_keeps_learning_still_and_matches_snapshot_after_undo(self):
        self.app.record_feedback("p1", "useful", project_id=self.a)
        frozen = self.app.set_profile_frozen(True, self.a)["profile"]
        self.assertTrue(frozen["frozen"])
        snapshot = self._vector(self.a)
        event = self.app.record_feedback("p4", "irrelevant", project_id=self.a)
        self.assertEqual(self._vector(self.a), snapshot, "frozen profile must not learn")
        self.assertIn("p4", self.app.latest_feedback(self.a), "events are still recorded while frozen")
        self.app.undo_feedback(event["feedback_id"], self.a)
        self.assertEqual(self._vector(self.a), snapshot)
        # Manual long-term pins remain editable while frozen and are not overwritten by feedback.
        self.app.pin_terms(["latent dynamics"], self.a)
        self.assertEqual(self.app.profile(self.a)["pinned_terms"], ["latent dynamics"])
        self.app.record_feedback("p5", "useful", project_id=self.a)
        self.assertEqual(self.app.profile(self.a)["pinned_terms"], ["latent dynamics"])
        resumed = self.app.set_profile_frozen(False, self.a)["profile"]
        self.assertFalse(resumed["frozen"])
        self.assertEqual(resumed["positive_feedback"], ["p1", "p5"])

    def test_undo_of_feedback_inside_the_frozen_snapshot_takes_effect_now(self):
        event = self.app.record_feedback("p4", "irrelevant", project_id=self.a)
        self.app.record_feedback("p1", "useful", project_id=self.a)
        before_event = self.app.set_profile_frozen(True, self.a)["profile"]
        self.assertEqual(before_event["explicit_negatives"], ["p4"])
        later = self.app.record_feedback("p1", "irrelevant", project_id=self.a)
        self.app.undo_feedback(event["feedback_id"], self.a)
        profile = self.app.profile(self.a)
        self.assertTrue(profile["frozen"])
        # Undo reaches the snapshot; feedback recorded after the freeze still does not.
        self.assertEqual(profile["explicit_negatives"], [])
        self.assertEqual(profile["positive_feedback"], ["p1"])
        self.app.undo_feedback(later["feedback_id"], self.a)
        self.assertEqual(self.app.profile(self.a)["positive_feedback"], ["p1"])

    def test_repeated_useful_after_unsave_saves_again(self):
        self.app.record_feedback("p1", "useful", project_id=self.a)
        self.app.unsave("p1", project_id=self.a)
        self.assertEqual(self.app.stats(self.a)["saved"], 0)
        again = self.app.record_feedback("p1", "useful", project_id=self.a)
        self.assertTrue(again["duplicate"])
        self.assertTrue(again["saved"])
        self.assertEqual(self.app.stats(self.a)["saved"], 1)
        self.assertEqual(len(self.app.latest_feedback(self.a)), 1)

    def test_restore_default_is_safe_and_reversible(self):
        self.app.pin_terms(["custom term"], self.a)
        self.app.set_profile_frozen(True, self.a)
        self.app.record_feedback("p1", "useful", project_id=self.a)
        result = self.app.restore_default_profile(self.a)
        self.assertEqual(result["previous_pinned_terms"], ["custom term"])
        profile = result["profile"]
        self.assertEqual(profile["pinned_terms"], ["world model", "planning"])
        self.assertFalse(profile["frozen"])
        self.assertEqual(profile["positive_feedback"], ["p1"], "restore never deletes feedback")
        versions = self.app.profile_versions(self.a)
        self.assertIn(["custom term"], [v["data"]["pinned_terms"] for v in versions])
        with self.assertRaises(ValueError):
            self.app.restore_default_profile("missing")

    def test_two_projects_are_isolated(self):
        self.app.record_feedback("p1", "useful", project_id=self.a)
        self.app.set_profile_frozen(True, self.a)
        self.app.build_batch(limit=2, project_id=self.a)
        self.app.store.add_qa("p1", "user", "question", project_id=self.a)
        profile_b = self.app.profile(self.b)
        self.assertEqual(profile_b["positive_feedback"], [])
        self.assertFalse(profile_b["frozen"])
        self.assertEqual(self.app.stats(self.b)["shown"], 0)
        self.assertEqual(self.app.stats(self.b)["saved"], 0)
        self.assertEqual(self.app.qa_history("p1", project_id=self.b), [])
        self.assertEqual(len(self.app.build_batch(limit=5, project_id=self.b)["cards"]), 5)

    def test_delete_project_removes_its_state_and_keeps_canonical_facts(self):
        pdf = Path(self.tmp.name) / "p1.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        self.app.store.record_pdf("p1", pdf, "local")
        self.app.store.save_fulltext("p1", [{"page": 1, "text": "full text"}])
        self.app.store.save_summary("p1", "one", "why", "caution", "test")
        self.app.build_batch(limit=2, project_id=self.a)
        self.app.record_feedback("p1", "useful", project_id=self.a)
        self.app.record_feedback("p1", "irrelevant", project_id=self.b)
        self.app.set_profile_frozen(True, self.a)
        self.app.store.add_qa("p1", "user", "private question", project_id=self.a)
        self.app.projects.delete_project(self.a)
        conn = self.app.store.conn
        count = lambda sql, *args: conn.execute(sql, args).fetchone()[0]
        self.assertEqual(count("SELECT COUNT(*) FROM feedback WHERE project_id=?", self.a), 0)
        self.assertEqual(count("SELECT COUNT(*) FROM qa_history WHERE project_id=?", self.a), 0)
        self.assertEqual(count("SELECT COUNT(*) FROM exposures e LEFT JOIN batches b ON b.id=e.batch_id "
                               "WHERE b.id IS NULL"), 0)
        self.assertEqual(count("SELECT COUNT(*) FROM settings WHERE key LIKE ?", f"%{self.a}"), 0)
        # Canonical facts and the other project are untouched.
        self.assertEqual(count("SELECT COUNT(*) FROM papers WHERE key='p1'"), 1)
        self.assertEqual(count("SELECT COUNT(*) FROM pdfs WHERE paper_key='p1'"), 1)
        self.assertTrue(pdf.exists())
        self.assertEqual(count("SELECT COUNT(*) FROM fulltext WHERE paper_key='p1'"), 1)
        self.assertEqual(count("SELECT COUNT(*) FROM summaries WHERE paper_key='p1'"), 1)
        self.assertEqual(self.app.profile(self.b)["explicit_negatives"], ["p1"])


class SeedResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = App(root=ROOT, data_dir=Path(self.tmp.name) / "app")

    def test_each_seed_reports_its_own_status(self):
        def work(identifier):
            if identifier.endswith("2601.00001"):
                return {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.48550/arxiv.2601.00001",
                        "title": "Resolved Seed", "publication_date": "2026-01-01"}
            if identifier.endswith("2601.00002"):
                raise SourceError("missing", "not_found")
            raise SourceError("offline", "network_error")

        with mock.patch.object(self.app.source, "work", side_effect=work):
            result = self.app.create_project("Seeds", "manual", ["x"],
                                             seeds=["2601.00001", "arxiv:2601.00001", "2601.00002", "2601.00003", 7])
        statuses = [r["status"] for r in result["seed_results"]]
        self.assertEqual(statuses, ["resolved", "duplicate", "not_found", "network_error", "failed"])
        self.assertEqual(self.app.stats(result["project_id"])["seeds"], 1)

    def test_unusable_seed_input_never_escapes_after_project_creation(self):
        import http.client
        calls = []

        def work(identifier):
            calls.append(identifier)
            if "W2" in identifier:
                raise http.client.InvalidURL("bad url")
            raise ValueError("Expecting value")

        with mock.patch.object(self.app.source, "work", side_effect=work):
            result = self.app.create_project("Odd seeds", "manual", ["x"],
                                             seeds=["World Models", "W1?select=x#y", "W2", "10.1234/abc"])
        statuses = [r["status"] for r in result["seed_results"]]
        self.assertEqual(statuses, ["invalid_input", "invalid_input", "failed", "failed"])
        # Free text is rejected locally; nothing that is not an identifier leaves the machine.
        self.assertEqual(calls, ["W2", "https://doi.org/10.1234/abc"])
        self.assertEqual(len([p for p in self.app.projects.list_projects() if p["name"] == "Odd seeds"]), 1)

    def test_openalex_bad_url_and_bad_body_become_source_errors(self):
        import http.client
        import io
        from app.sources import OpenAlex
        client = OpenAlex(Path(self.tmp.name) / "cache")
        with mock.patch("app.sources.urllib.request.urlopen", side_effect=http.client.InvalidURL("x")), \
                mock.patch("app.sources.time.sleep"):
            with self.assertRaises(SourceError) as caught:
                client.work("W1")
        self.assertEqual(caught.exception.kind, "invalid_input")

        class Body(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        with mock.patch("app.sources.urllib.request.urlopen", return_value=Body(b"<html>busy</html>")), \
                mock.patch("app.sources.time.sleep"):
            with self.assertRaises(SourceError) as caught:
                client.work("W3")
        self.assertEqual(caught.exception.kind, "bad_response")
        # A bad body is not cached, so a later retry by the user can succeed.
        self.assertEqual(list((Path(self.tmp.name) / "cache").glob("*.json")), [])

    def test_openalex_404_is_not_retried(self):
        import io
        import urllib.error
        from app.sources import OpenAlex
        client = OpenAlex(Path(self.tmp.name) / "cache")
        error = urllib.error.HTTPError("u", 404, "missing", {}, io.BytesIO(b""))
        with mock.patch("app.sources.urllib.request.urlopen", side_effect=error) as urlopen, \
                mock.patch("app.sources.time.sleep"):
            with self.assertRaises(SourceError) as caught:
                client.work("https://doi.org/10.0000/none")
        self.assertEqual(caught.exception.kind, "not_found")
        self.assertEqual(urlopen.call_count, 1)


class MigrationBackupTests(unittest.TestCase):
    def test_pending_migration_backs_up_and_backup_restores(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paperdighelper.sqlite"
            app = App(root=ROOT, data_dir=Path(tmp))
            pid = app.create_project("Keep", "manual", ["kept"])["project_id"]
            app.store.upsert_papers([{"key": "k1", "title": "Kept paper", "abstract": "", "published": "2026-01-01",
                                      "project_id": pid}])
            app.record_feedback("k1", "useful", project_id=pid)
            # Simulate a database written by an older build that still has the last migration pending.
            app.store.conn.execute("DELETE FROM schema_version WHERE version=?", (len(MIGRATIONS),))
            app.store.conn.commit()
            app.store.conn.close()

            reopened = Store(path)
            reopened.init()
            backup = path.with_name(f"{path.name}.pre-v{len(MIGRATIONS) - 1}.bak")
            self.assertTrue(backup.exists())
            self.assertEqual(get_schema_version(reopened.conn), len(MIGRATIONS))
            reopened.conn.close()

            restored = sqlite3.connect(str(backup))
            self.assertEqual(restored.execute("SELECT COUNT(*) FROM feedback").fetchone()[0], 1)
            self.assertEqual(restored.execute("SELECT name FROM projects WHERE id=?", (pid,)).fetchone()[0], "Keep")
            restored.close()
            # A restored copy can be opened and upgraded again by the current build.
            copy = Path(tmp) / "restored.sqlite"
            copy.write_bytes(backup.read_bytes())
            store = Store(copy)
            store.init()
            self.assertEqual(store.conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0], 1)
            store.conn.close()

    def test_fresh_database_makes_no_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            App(root=ROOT, data_dir=Path(tmp))
            self.assertEqual(list(Path(tmp).glob("*.bak")), [])


if __name__ == "__main__":
    unittest.main()
