from tests.pdf_fixture import minimal_pdf
"""Building blocks of library import: one-transaction store writes and the shared content-addressed PDF archive.

An import commit writes papers, project links, library saves and PDF records for hundreds of items; each
of those Store calls used to commit on its own, so a crash half way left a half-imported library."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import creation
from app.db import Store
from app.project import ProjectManager

PDF = minimal_pdf("x" * 200)


def make_store(tmp):
    store = Store(Path(tmp) / "db.sqlite")
    store.init()
    project = ProjectManager(store).create_project("导入测试")
    return store, project


class StoreCommitFlagTests(unittest.TestCase):
    def test_save_to_library_without_commit_is_undone_by_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, project = make_store(tmp)
            store.upsert_papers([{"key": "k", "title": "T"}], project_id=project)
            store.save_to_library("k", project_id=project, commit=False)
            store.conn.rollback()
            self.assertEqual(store.conn.execute("SELECT COUNT(*) FROM project_library").fetchone()[0], 0)
            self.assertEqual(store.conn.execute("SELECT COUNT(*) FROM library").fetchone()[0], 0)

    def test_save_to_library_commits_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, project = make_store(tmp)
            store.upsert_papers([{"key": "k", "title": "T"}], project_id=project)
            store.save_to_library("k", project_id=project)
            store.conn.rollback()
            self.assertEqual(store.conn.execute("SELECT COUNT(*) FROM project_library").fetchone()[0], 1)

    def test_record_pdf_without_commit_is_undone_by_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, project = make_store(tmp)
            store.upsert_papers([{"key": "k", "title": "T"}], project_id=project)
            store.record_pdf("k", "/tmp/a.pdf", "user-import", sha256="a" * 64, size=5,
                             source_kind="user_import", commit=False)
            store.conn.rollback()
            self.assertEqual(store.conn.execute("SELECT COUNT(*) FROM pdfs").fetchone()[0], 0)
            self.assertEqual(store.conn.execute("SELECT COUNT(*) FROM pdf_versions").fetchone()[0], 0)

    def test_an_imported_link_is_not_downgraded_to_shared_by_the_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, project = make_store(tmp)
            store.upsert_papers([{"key": "k", "title": "T", "relation_kind": "imported"}], project_id=project)
            store.save_to_library("k", project_id=project)
            kind = store.conn.execute("SELECT relation_kind FROM project_papers WHERE paper_key='k'").fetchone()[0]
            self.assertEqual(kind, "imported")


class ArchivePdfTests(unittest.TestCase):
    def test_copies_by_content_and_leaves_the_source_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "staged.pdf.bin"
            source.write_bytes(PDF)
            sha = hashlib.sha256(PDF).hexdigest()
            target = creation.archive_pdf(tmp, sha, source)
            self.assertEqual(target, Path(tmp) / "pdfs" / f"import-{sha[:24]}.pdf")
            self.assertEqual(target.read_bytes(), PDF)
            self.assertTrue(source.exists())

    def test_calling_twice_is_idempotent_and_never_rewrites_an_archived_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "staged"
            source.write_bytes(PDF)
            sha = hashlib.sha256(PDF).hexdigest()
            first = creation.archive_pdf(tmp, sha, source)
            mtime = first.stat().st_mtime_ns
            second = creation.archive_pdf(tmp, sha, source)
            self.assertEqual(first, second)
            self.assertEqual(second.stat().st_mtime_ns, mtime)

    def test_refuses_a_source_whose_content_does_not_match_the_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "staged"
            source.write_bytes(PDF)
            with self.assertRaises(ValueError):
                creation.archive_pdf(tmp, "0" * 64, source)
            self.assertFalse((Path(tmp) / "pdfs").exists() and any((Path(tmp) / "pdfs").iterdir()))

    def test_refuses_a_malformed_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "staged"
            source.write_bytes(PDF)
            with self.assertRaises(ValueError):
                creation.archive_pdf(tmp, "../../etc/passwd", source)


if __name__ == "__main__":
    unittest.main()
