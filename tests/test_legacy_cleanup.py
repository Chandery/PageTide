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
        c.execute("INSERT INTO summaries(paper_key,one_liner,why_relevant,caution,model,created_at) VALUES (?,?,?,?,?,?)",
                  (key, "one", "why", "", "m", "2026-01-01"))
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
        self.backup = Path(self.tmp.name) / ("paperdighelper.sqlite" + lc.BACKUP_SUFFIX)

    def marker(self):
        return self.store.get_setting(lc.KEY)

    def assertUntouched(self, reason):
        out = lc.run(self.store)
        self.assertEqual(out["result"], "kept: " + reason)
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM projects"), 1)
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM papers"), 15)
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM summaries"), 15)
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM batches"), 1)
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM profile_versions"), 1)
        self.assertFalse(self.backup.exists())
        self.assertEqual(self.marker()["result"], "kept: " + reason)


class CleansTheUntouchedDefaultProject(Base):
    def test_old_first_start_is_removed_with_a_backup_and_a_marker(self):
        seed_old_first_start(self.store)
        out = lc.run(self.store)
        cleaned = out["result"]["cleaned"]
        self.assertEqual((cleaned["projects"], cleaned["papers"], cleaned["batches"], cleaned["exposures"]), (1, 15, 1, 5))
        for table in ("projects", "papers", "project_papers", "summaries", "batches", "exposures", "profile_snapshots",
                      "weekly_reports", "profile_versions"):
            self.assertEqual(count(self.store, f"SELECT COUNT(*) FROM {table}"), 0, table)
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM settings WHERE key LIKE '%default_project%'"), 0)
        self.assertTrue(self.backup.exists())
        copy = sqlite3.connect(str(self.backup))
        self.assertEqual(copy.execute("SELECT COUNT(*) FROM papers").fetchone()[0], 15)   # the backup still has the old state
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
        self.assertFalse(self.backup.exists())

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
        c.commit()
        lc.run(self.store)
        self.assertEqual([r[0] for r in c.execute("SELECT key FROM papers")], ["paper-3"])
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM summaries WHERE paper_key='paper-3'"), 1)
        self.assertEqual([tuple(r) for r in c.execute("SELECT project_id,paper_key FROM project_papers")], [("p2", "paper-3")])
        self.assertIsNone(c.execute("SELECT project_id FROM papers WHERE key='paper-3'").fetchone()[0])

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
        self.assertTrue(self.backup.exists())
        self.assertIn("failed", self.marker()["result"])


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
        self.assertEqual(out["result"], "kept: pinned_terms")
        self.assertEqual(count(self.store, "SELECT COUNT(*) FROM papers"), 15)

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
    def test_building_the_server_runs_it_once_and_a_restart_does_not(self):
        import os
        from unittest import mock
        from app import server
        seed_old_first_start(self.store)
        self.store.close()
        root = Path(self.tmp.name) / "root"
        (root / "harness").mkdir(parents=True)
        (root / "harness" / "budget.json").write_text((Path(__file__).resolve().parents[1] / "harness" / "budget.json").read_text())
        with mock.patch.dict(os.environ, {"PAPERDIGHELPER_DATA": self.tmp.name}):
            server.build_server(port=0, root=str(root)).server_close()
            db = sqlite3.connect(str(Path(self.tmp.name) / "paperdighelper.sqlite"))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM papers").fetchone()[0], 0)
            first = db.execute("SELECT value FROM settings WHERE key=?", (lc.KEY,)).fetchone()[0]
            db.close()
            server.build_server(port=0, root=str(root)).server_close()
            db = sqlite3.connect(str(Path(self.tmp.name) / "paperdighelper.sqlite"))
            self.assertEqual(db.execute("SELECT value FROM settings WHERE key=?", (lc.KEY,)).fetchone()[0], first)
            db.close()
        self.store = Store(Path(self.tmp.name) / "paperdighelper.sqlite")


if __name__ == "__main__":
    unittest.main()
