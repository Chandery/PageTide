import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import legacy_cleanup as lc
from app.db import Store


def seed_old_first_start(store, extra_projects=False):
    """What an older desktop build left after its first launch: default project, 10 seed papers, fetched papers, a batch,
    summaries, the auto profile version and settings; nobody did anything."""
    c = store.conn
    c.execute("INSERT INTO projects (id,name,creation_mode,creation_timestamp,keywords) VALUES (?,?,?,?,?)",
              ("default_project", "默认项目", "manual", "2026-01-01T00:00:00+00:00", "[]"))
    for i in range(15):   # 10 seeds + 5 fetched
        key = f"paper-{i}"
        c.execute("INSERT INTO papers(key,title,abstract,published,source,created_at,project_id) VALUES (?,?,?,?,?,?,?)",
                  (key, f"World model {i}", "abstract", "2025-01-01", "openalex", "2026-01-01", "default_project"))
        c.execute("INSERT INTO project_papers(project_id,paper_key,relation_kind,added_at) VALUES (?,?,?,?)",
                  ("default_project", key, "seed" if i < 10 else "discovered", "2026-01-01"))
    cursor = c.execute("INSERT INTO batches(run_date,created_at,source,project_id) VALUES (?,?,?,?)",
                       ("2026-01-02", "2026-01-02", "sparse", "default_project"))
    for rank in range(5):
        c.execute("INSERT INTO exposures(batch_id,paper_key,rank,shown_at) VALUES (?,?,?,?)", (cursor.lastrowid, f"paper-{10 + rank}", rank, "2026-01-02"))
    c.execute("INSERT INTO profile_snapshots(project_id,snapshot_timestamp,top_keywords,interest_distribution) VALUES (?,?,?,?)",
              ("default_project", "2026-01-02", "[]", "{}"))
    c.execute("INSERT INTO weekly_reports(project_id,week_start,week_end,stats,generated_timestamp) VALUES (?,?,?,?,?)",
              ("default_project", "2026-01-01", "2026-01-07", "{}", "2026-01-08"))
    c.execute("INSERT INTO profile_versions(created_at,note,data) VALUES (?,?,?)",
              ("2026-01-01", "initial", json.dumps({"project": "world-models", "pinned_terms": [], "weights": {"pos": 1.0, "neg": 0.5}})))
    store.set_setting("seed_keys_default_project", [f"paper-{i}" for i in range(10)])
    store.set_setting("last_refresh_default_project", "2026-01-01T00:00:00")
    store.set_setting("last_refresh_result_default_project", {"fetched": 5})
    c.commit()


def count(store, sql, *args):
    return store.conn.execute(sql, args).fetchone()[0]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "paperdighelper.sqlite")
        self.store.init()
        self.addCleanup(self.store.close)
        self.dir = Path(self.tmp.name)

    def backups(self):
        return sorted(self.dir.glob("paperdighelper.sqlite" + lc.BACKUP_PREFIX + "-*.bak"))

    def leftovers(self):
        return sorted(self.dir.glob("*.tmp"))

    def marker(self):
        return self.store.get_setting(lc.KEY)

    def assertUntouched(self, reason):
        out = lc.run(self.store)
        self.assertEqual(out["result"], "kept: " + reason)
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM projects"), 1)
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM papers"), 15)
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM batches"), 1)
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM profile_versions"), 1)
        self.assertEqual(self.backups(), [])
        self.assertEqual(self.marker()["result"], "kept: " + reason)


class CleansTheUntouchedDefaultProject(Base):
    def test_old_first_start_is_removed_with_a_backup_and_a_marker(self):
        seed_old_first_start(self.store)
        out = lc.run(self.store)
        cleaned = out["result"]["cleaned"]
        self.assertEqual((cleaned["projects"], cleaned["papers"], cleaned["batches"], cleaned["exposures"]), (1, 15, 1, 5))
        for table in ("projects", "papers", "project_papers", "batches", "exposures", "profile_snapshots",
                      "weekly_reports", "profile_versions"):
            self.assertEqual(count(self.store, f"SELECT COUNT(*) FROM {table}"), 0, table)
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM settings WHERE key LIKE '%default_project%'"), 0)
        (backup,) = self.backups()
        self.assertEqual(self.leftovers(), [])
        copy = sqlite3.connect(str(backup))
        self.assertEqual(copy.execute("SELECT COUNT(*) FROM papers").fetchone()[0], 15)   # the backup still has the old state
        # ...and carries the marker, so a restored backup is never cleaned a second time
        self.assertEqual(json.loads(copy.execute("SELECT value FROM settings WHERE key=?", (lc.KEY,)).fetchone()[0])["result"], "in_progress")
        copy.close()
        self.assertEqual(self.marker()["result"]["cleaned"]["papers"], 15)
        self.assertIn("done_at", self.marker())

    def test_a_second_start_does_nothing(self):
        seed_old_first_start(self.store)
        lc.run(self.store)
        before = self.marker()
        seed_old_first_start(self.store)   # even if the same state reappeared, the one-time check is spent
        self.assertIsNone(lc.run(self.store))
        self.assertEqual(self.marker(), before)
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM projects"), 1)

    def test_a_new_library_without_the_default_project_is_not_an_error(self):
        out = lc.run(self.store)
        self.assertEqual(out["result"], "kept")
        self.assertIsNone(lc.run(self.store))
        self.assertEqual(self.backups(), [])

    def test_another_projects_papers_and_settings_survive(self):
        seed_old_first_start(self.store)
        c = self.store.conn
        c.execute("INSERT INTO projects (id,name,creation_mode,creation_timestamp,keywords) VALUES ('p2','Mine','manual','2026-02-01','[\"x\"]')")
        c.execute("INSERT INTO papers(key,title,created_at,project_id) VALUES ('mine','Mine','2026-02-01','p2')")
        c.execute("INSERT INTO project_papers(project_id,paper_key,relation_kind,added_at) VALUES ('p2','mine','discovered','2026-02-01')")
        self.store.set_setting("seed_keys_p2", ["mine"])
        c.commit()
        lc.run(self.store)
        self.assertEqual([r[0] for r in c.execute("SELECT id FROM projects")], ["p2"])
        self.assertEqual([r[0] for r in c.execute("SELECT key FROM papers")], ["mine"])
        self.assertEqual(self.store.get_setting("seed_keys_p2"), ["mine"])
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM profile_versions"), 1)   # the global profile stays while a project remains

    def test_a_seed_paper_linked_by_another_project_stays_and_only_the_link_goes(self):
        seed_old_first_start(self.store)
        c = self.store.conn
        c.execute("INSERT INTO projects (id,name,creation_mode,creation_timestamp,keywords) VALUES ('p2','Mine','manual','2026-02-01','[\"x\"]')")
        c.execute("INSERT INTO project_papers(project_id,paper_key,relation_kind,added_at) VALUES ('p2','paper-3','shared','2026-02-01')")
        c.execute("INSERT INTO summaries(paper_key,one_liner,why_relevant,caution,model,created_at) VALUES ('paper-3','x','y','','demo','2026-01-01')")
        c.commit()
        lc.run(self.store)
        self.assertEqual([r[0] for r in c.execute("SELECT key FROM papers")], ["paper-3"])
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM summaries WHERE paper_key='paper-3'"), 1)
        self.assertEqual([tuple(r) for r in c.execute("SELECT project_id,paper_key FROM project_papers")], [("p2", "paper-3")])
        self.assertIsNone(c.execute("SELECT project_id FROM papers WHERE key='paper-3'").fetchone()[0])

    def test_exploration_evidence_and_other_projects_category_entries_for_removed_papers_go(self):
        from app.organization import Organization
        seed_old_first_start(self.store)
        c = self.store.conn
        batch = c.execute("SELECT id FROM batches").fetchone()[0]
        self.store.set_setting(f"route_exploration_evidence_{batch}", {"paper-10": "x"})
        c.execute("INSERT INTO projects (id,name,creation_mode,creation_timestamp,keywords) VALUES ('p2','Mine','manual','2026-02-01','[\"x\"]')")
        c.commit()
        Organization(self.store, project="p2")
        c.execute("UPDATE org_projects SET data=? WHERE project='p2'", (json.dumps(
            {"directions": [], "memberships": {"paper-1": ["d"], "keep": ["d"]}, "positions": {"paper-1": {"x": 1}}, "protected": ["paper-1"]}),))
        c.commit()
        lc.run(self.store)
        self.assertIsNone(self.store.get_setting(f"route_exploration_evidence_{batch}"))
        data = json.loads(c.execute("SELECT data FROM org_projects WHERE project='p2'").fetchone()[0])
        self.assertEqual((data["memberships"], data["positions"], data["protected"]), ({"keep": ["d"]}, {}, []))

    def test_a_failure_rolls_everything_back_and_is_recorded(self):
        seed_old_first_start(self.store)
        original = lc._delete_everything

        def broken(conn):
            conn.execute("DELETE FROM papers")
            raise RuntimeError("boom")
        lc._delete_everything = broken
        try:
            out = lc.run(self.store)
        finally:
            lc._delete_everything = original
        self.assertIn("failed", out["result"])
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM papers"), 15)
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM projects"), 1)
        self.assertEqual(len(self.backups()), 1)
        self.assertIn("failed", self.marker()["result"])


class BackupSafety(Base):
    def test_an_old_backup_file_is_never_trusted_or_overwritten(self):
        seed_old_first_start(self.store)
        stale = self.dir / ("paperdighelper.sqlite" + lc.BACKUP_PREFIX + "-20200101T000000Z-deadbeef.bak")
        stale.write_bytes(b"not a database")
        legacy_name = self.dir / "paperdighelper.sqlite.pre-legacy-cleanup.bak"
        legacy_name.write_bytes(b"also junk")
        out = lc.run(self.store)
        self.assertIn("cleaned", out["result"])
        self.assertEqual(stale.read_bytes(), b"not a database")
        self.assertEqual(legacy_name.read_bytes(), b"also junk")
        new = [b for b in self.backups() if b != stale]
        self.assertEqual(len(new), 1)
        copy = sqlite3.connect(str(new[0]))
        self.assertEqual(copy.execute("PRAGMA quick_check").fetchone()[0], "ok")
        copy.close()

    def test_a_backup_that_does_not_verify_deletes_nothing_and_leaves_no_fragment(self):
        seed_old_first_start(self.store)
        original = self.store.backup

        def bad(target):
            Path(target).write_bytes(b"garbage")
            return target
        self.store.backup = bad
        try:
            out = lc.run(self.store)
        finally:
            self.store.backup = original
        self.assertIn("failed: backup", out["result"])
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM papers"), 15)
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM projects"), 1)
        self.assertEqual(self.backups(), [])
        self.assertEqual(self.leftovers(), [])
        self.assertIn("failed: backup", self.marker()["result"])
        self.assertIsNone(lc.run(self.store))

    def test_a_backup_with_different_counts_is_refused(self):
        seed_old_first_start(self.store)
        original = self.store.backup

        def thin(target):
            original(target)
            copy = sqlite3.connect(str(target))
            copy.execute("DELETE FROM papers WHERE key='paper-1'")
            copy.commit()
            copy.close()
            return target
        self.store.backup = thin
        try:
            out = lc.run(self.store)
        finally:
            self.store.backup = original
        self.assertIn("failed: backup", out["result"])
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM papers"), 15)
        self.assertEqual(self.backups(), [])

    def test_a_restored_backup_is_not_cleaned_again(self):
        seed_old_first_start(self.store)
        lc.run(self.store)
        (backup,) = self.backups()
        restored = Store(self.dir / "restored.sqlite")
        restored.close()
        import shutil
        shutil.copyfile(backup, self.dir / "restored.sqlite")
        again = Store(self.dir / "restored.sqlite")
        self.addCleanup(again.close)
        self.assertEqual(count(again, "SELECT COUNT(*) FROM papers"), 15)
        self.assertIsNone(lc.run(again))
        self.assertEqual(count(again, "SELECT COUNT(*) FROM papers"), 15)
        self.assertEqual(count(again, "SELECT COUNT(*) FROM projects"), 1)


class AnythingTheUserDidKeepsEverything(Base):
    def setUp(self):
        super().setUp()
        seed_old_first_start(self.store)

    def test_a_feedback_row(self):
        self.store.conn.execute("INSERT INTO feedback(paper_key,action,created_at,project_id) VALUES ('paper-1','useful','2026-01-03','default_project')")
        self.store.conn.commit()
        self.assertUntouched("feedback")

    def test_an_undone_feedback_row_still_counts(self):
        self.store.conn.execute("INSERT INTO feedback(paper_key,action,created_at,undone,project_id) VALUES ('paper-1','irrelevant','2026-01-03',1,'default_project')")
        self.store.conn.commit()
        self.assertUntouched("feedback")

    def test_a_saved_paper(self):
        self.store.save_to_library("paper-2", project_id="default_project")
        self.assertUntouched("library")

    def test_a_legacy_library_row(self):
        self.store.conn.execute("INSERT OR IGNORE INTO library(paper_key,saved_at,note) VALUES ('paper-2','2026-01-03','n')")
        self.store.conn.commit()
        self.assertUntouched("library")

    def test_a_question_asked_about_a_paper(self):
        self.store.conn.execute("INSERT INTO qa_history(paper_key,role,content,created_at,project_id) VALUES ('paper-1','user','q','2026-01-03','default_project')")
        self.store.conn.commit()
        self.assertUntouched("qa_history")

    def test_a_note(self):
        from app.organization import Organization
        Organization(self.store, project="default_project")
        self.store.conn.execute("INSERT INTO org_notes VALUES ('default_project','paper-1',1,'my note','2026-01-03')")
        self.store.conn.commit()
        self.assertUntouched("notes")

    def test_a_category(self):
        from app.organization import Organization
        Organization(self.store, project="default_project")
        self.store.conn.execute("UPDATE org_projects SET data=? WHERE project='default_project'",
                                (json.dumps({"directions": [{"id": "d1", "name": "A"}], "memberships": {}, "positions": {}, "protected": []}),))
        self.store.conn.commit()
        self.assertUntouched("organization")

    def test_a_stored_pdf(self):
        self.store.conn.execute("INSERT INTO pdfs(paper_key,path,fetched_at) VALUES ('paper-1','/x.pdf','2026-01-03')")
        self.store.conn.commit()
        self.assertUntouched("reading")

    def test_an_import_batch(self):
        from app import library_import
        self.store.conn.executescript(library_import.SCHEMA)
        self.store.conn.execute("INSERT INTO import_batches(id,project_id,source,options,status,created_at,updated_at) VALUES ('b','default_project','files','{}','review','t','t')")
        self.store.conn.commit()
        self.assertUntouched("import")

    def test_a_learning_goal_setting(self):
        self.store.set_setting("project_goal_default_project", {"goal": "x"})
        self.assertUntouched("setting:project_goal")

    def test_an_unknown_setting_that_names_the_project(self):
        self.store.set_setting("something_new_default_project", 1)
        self.assertUntouched("setting:something_new")

    def test_a_pinned_term_history(self):
        self.store.conn.execute("INSERT INTO profile_versions(created_at,note,data) VALUES ('2026-01-04','pin',?)",
                                (json.dumps({"project_id": "default_project", "pinned_terms": ["a"]}),))
        self.store.conn.commit()
        out = lc.run(self.store)
        self.assertEqual(out["result"], "kept: profile_versions")
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM papers"), 15)

    def test_other_profile_version_kinds_of_this_project_or_of_no_project(self):
        for note, data in (("freeze", {"project_id": "default_project"}), ("unfreeze", {}), ("restore", {"pinned_terms": []})):
            with self.subTest(note):
                self.store.conn.execute("INSERT INTO profile_versions(created_at,note,data) VALUES ('2026-01-04',?,?)", (note, json.dumps(data)))
                self.store.conn.commit()
                out = lc.run(self.store)
                self.assertEqual(out["result"], "kept: profile_versions")
                self.store.conn.execute("DELETE FROM settings WHERE key=?", (lc.KEY,))
                self.store.conn.execute("DELETE FROM profile_versions WHERE note=?", (note,))
                self.store.conn.commit()
        self.store.conn.execute("INSERT INTO profile_versions(created_at,note,data) VALUES ('2026-01-04','pin',?)", (json.dumps({"project_id": "other"}),))
        self.store.conn.commit()
        self.assertIn("cleaned", lc.run(self.store)["result"])   # another project's pin history is not this project's

    def test_a_language_policy(self):
        self.store.conn.execute("UPDATE projects SET language_policy_revision=1 WHERE id='default_project'")
        self.store.conn.commit()
        self.assertUntouched("language_policy")

    def test_allowed_languages(self):
        self.store.conn.execute("""UPDATE projects SET allowed_languages='["en"]' WHERE id='default_project'""")
        self.store.conn.commit()
        self.assertUntouched("language_policy")

    def test_an_ai_preview_on_a_linked_paper(self):
        self.store.conn.execute("INSERT INTO summaries(paper_key,one_liner,why_relevant,caution,model,created_at) VALUES ('paper-2','x','y','','deepseek-chat','2026-01-03')")
        self.store.conn.commit()
        self.assertUntouched("summaries")

    def test_a_weekly_report_with_ai_analysis(self):
        self.store.conn.execute("UPDATE weekly_reports SET ai_analysis='some analysis' WHERE project_id='default_project'")
        self.store.conn.commit()
        self.assertUntouched("ai_analysis")

    def test_batches_on_more_than_one_day(self):
        self.store.conn.execute("INSERT INTO batches(run_date,created_at,source,project_id) VALUES ('2026-02-02','2026-02-02','sparse','default_project')")
        self.store.conn.commit()
        out = lc.run(self.store)
        self.assertEqual(out["result"], "kept: used_over_days")
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM papers"), 15)

    def test_a_paper_shared_on_from_this_project(self):
        c = self.store.conn
        c.execute("INSERT INTO projects (id,name,creation_mode,creation_timestamp,keywords) VALUES ('p2','Mine','manual','2026-02-01','[\"x\"]')")
        c.execute("INSERT INTO project_papers(project_id,paper_key,relation_kind,added_at,source_project_id) VALUES ('p2','paper-3','shared','2026-02-01','default_project')")
        c.commit()
        out = lc.run(self.store)
        self.assertEqual(out["result"], "kept: shared")
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM projects"), 2)

    def test_a_renamed_project(self):
        self.store.conn.execute("UPDATE projects SET name='My topic' WHERE id='default_project'")
        self.store.conn.commit()
        self.assertUntouched("renamed")

    def test_keywords(self):
        self.store.conn.execute("""UPDATE projects SET keywords='["transformer"]' WHERE id='default_project'""")
        self.store.conn.commit()
        self.assertUntouched("project_keywords")

    def test_a_guidance_transcript(self):
        self.store.conn.execute("UPDATE projects SET guidance_transcript='[{\"role\":\"user\"}]' WHERE id='default_project'")
        self.store.conn.commit()
        self.assertUntouched("project_guidance_transcript")

    def test_a_project_with_another_id_is_never_touched(self):
        self.store.conn.execute("PRAGMA foreign_keys=OFF")
        self.store.conn.execute("UPDATE projects SET id='other' WHERE id='default_project'")
        self.store.conn.commit()
        out = lc.run(self.store)
        self.assertEqual(out["result"], "kept")
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM projects"), 1)


class StartupHook(Base):
    def _root(self):
        root = Path(self.tmp.name) / "root"
        (root / "harness").mkdir(parents=True)
        (root / "harness" / "budget.json").write_text((Path(__file__).resolve().parents[1] / "harness" / "budget.json").read_text())
        return root

    def test_building_the_server_never_opens_the_library_and_the_cleanup_runs_once(self):
        import os
        from unittest import mock
        from app import server
        seed_old_first_start(self.store)
        self.store.close()
        root = self._root()
        db_path = Path(self.tmp.name) / "paperdighelper.sqlite"
        with mock.patch.dict(os.environ, {"PAPERDIGHELPER_DATA": self.tmp.name}):
            before = db_path.read_bytes()
            server.build_server(port=0, root=str(root)).server_close()
            self.assertEqual(db_path.read_bytes(), before)   # build_server did not open or touch the database
            server.clean_legacy_default_project(str(root))
            db = sqlite3.connect(str(db_path))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 0)
            first = db.execute("SELECT value FROM settings WHERE key=?", (lc.KEY,)).fetchone()[0]
            db.close()
            server.clean_legacy_default_project(str(root))
            db = sqlite3.connect(str(db_path))
            self.assertEqual(db.execute("SELECT value FROM settings WHERE key=?", (lc.KEY,)).fetchone()[0], first)
            db.close()
        self.store = Store(db_path)

    def test_only_the_desktop_start_up_and_an_explicit_source_run_call_it(self):
        root = Path(__file__).resolve().parents[1] / "app"
        desktop, srv = (root / "desktop.py").read_text(encoding="utf-8"), (root / "server.py").read_text(encoding="utf-8")
        gate = desktop.index('os.environ.get("PDH_APP_VERSION") or os.environ.get("PDH_LEGACY_CLEANUP") == "1"')
        self.assertLess(desktop.index("platform_compat.lock_exclusive"), gate)           # after the instance lock
        self.assertLess(gate, desktop.index("httpd = build_server("))                  # before any request is served
        self.assertIn("clean_legacy_default_project(resources)", desktop)
        build = srv[srv.index("def build_server("):srv.index("def serve(")]
        self.assertNotIn("clean_legacy", build)
        self.assertNotIn("make_app", build)
        serve = srv[srv.index("def serve("):srv.index('if __name__ == "__main__":')]
        self.assertIn('os.environ.get("PDH_LEGACY_CLEANUP") == "1"', serve)


if __name__ == "__main__":
    unittest.main()
