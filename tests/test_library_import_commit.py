"""Committing a reviewed batch: one transaction writes papers, links, library saves and archived PDFs.

What an import must NOT do is as important as what it does: no feedback, no seeds, no overwritten PDFs."""
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.db import Store
from app.library_import import LibraryImport
from app.project import ProjectManager


def pdf(n):
    return b"%PDF-1.7\n" + f"paper {n}".encode() * 40


def paper(n, title=None):
    return {"key": f"https://doi.org/10.1000/p{n}", "doi": f"https://doi.org/10.1000/p{n}", "title": title or f"Matched paper {n}",
            "abstract": "An abstract.", "openalex_id": f"https://openalex.org/W{n}", "published": "2020-01-01",
            "group_name": "imported", "authors": ["A. Author"]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / "paperdighelper.sqlite")
        self.store.init()
        self.project = ProjectManager(self.store).create_project("导入测试")
        self.imp = LibraryImport(self.data, self.store)
        self.n = 0

    def batch(self, **options):
        self.batch_id = self.imp.create_batch(self.project, "folder", "r", options)["id"]
        return self.batch_id

    def add(self, path=None, data=None):
        self.n += 1
        data = data or pdf(self.n)
        return self.imp.add_pdf(self.batch_id, path or f"r/f{self.n}.pdf", io.BytesIO(data), len(data), 1, None)

    def settle(self, item, state, **fields):
        self.imp._set(item["id"], state, **fields)
        return self.imp.item(self.batch_id, item["id"])

    def matched(self, n=None, **kw):
        item = self.add(**kw)
        return self.settle(item, "matched", match_source="title", paper=paper(self.n if n is None else n))

    def count(self, sql, *args):
        return self.store.conn.execute(sql, args).fetchone()[0]


class CommitTests(Base):
    def test_a_matched_pdf_becomes_a_saved_imported_paper_with_its_archived_file(self):
        self.batch()
        item = self.matched(1)
        result = self.imp.commit(self.batch_id)
        key = "https://doi.org/10.1000/p1"
        self.assertEqual(self.store.paper(key)["title"], "Matched paper 1")
        self.assertEqual(self.count("SELECT relation_kind FROM project_papers WHERE project_id=? AND paper_key=?", self.project, key), "imported")
        self.assertEqual(self.count("SELECT COUNT(*) FROM project_library WHERE project_id=? AND paper_key=?", self.project, key), 1)
        row = self.store.conn.execute("SELECT * FROM pdfs WHERE paper_key=?", (key,)).fetchone()
        self.assertEqual(row["sha256"], item["sha256"])
        self.assertEqual(row["bytes"], len(pdf(1)))
        self.assertEqual((row["source_kind"], row["source_url"]), ("user_import", f"user-import:batch/{self.batch_id}"))
        self.assertEqual(Path(row["path"]).read_bytes(), pdf(1))
        self.assertEqual(Path(row["path"]), self.data / "pdfs" / f"import-{item['sha256'][:24]}.pdf")
        self.assertEqual(self.imp.batch(self.batch_id)["status"], "committed")
        self.assertFalse((self.data / "imports" / "batches" / self.batch_id).exists())
        self.assertEqual((result["new_papers"], result["pdfs_archived"]), (1, 1))

    def test_an_import_is_never_a_signal_about_what_the_person_likes(self):
        self.batch()
        self.matched(1)
        self.matched(2)
        self.imp.commit(self.batch_id)
        self.assertEqual(self.count("SELECT COUNT(*) FROM feedback"), 0)
        self.assertEqual(self.count("SELECT COUNT(*) FROM exposures"), 0)
        self.assertEqual(self.count("SELECT COUNT(*) FROM settings WHERE key LIKE 'seed_keys%'"), 0)

    def test_a_pdf_nothing_could_identify_is_kept_under_a_key_made_from_its_content(self):
        self.batch()
        item = self.add("r/scan 0042.pdf")
        sha = item["sha256"]
        self.settle(item, "unmatched", match_source="unresolved", paper={"key": "pdf:" + sha, "title": "scan 0042", "unresolved": True})
        result = self.imp.commit(self.batch_id)
        self.assertEqual(self.store.paper("pdf:" + sha)["title"], "scan 0042")
        self.assertEqual(self.count("SELECT COUNT(*) FROM project_library WHERE paper_key=?", "pdf:" + sha), 1)
        self.assertEqual(self.count("SELECT COUNT(*) FROM pdfs WHERE paper_key=?", "pdf:" + sha), 1)
        self.assertEqual(result["unresolved"], 1)

    def test_a_paper_already_known_is_linked_and_its_metadata_is_left_alone(self):
        other = ProjectManager(self.store).create_project("另一个项目")
        self.store.upsert_papers([{"key": "k1", "title": "Original title", "abstract": "Original"}], project_id=other)
        self.batch()
        item = self.add()
        self.settle(item, "duplicate", match_source="existing", paper_key="k1", paper={"key": "k1", "title": "Original title"})
        result = self.imp.commit(self.batch_id)
        self.assertEqual(self.store.paper("k1")["abstract"], "Original")
        self.assertEqual(self.count("SELECT COUNT(*) FROM papers"), 1)
        self.assertEqual(self.count("SELECT COUNT(*) FROM project_library WHERE project_id=? AND paper_key='k1'", self.project), 1)
        self.assertEqual(self.count("SELECT COUNT(*) FROM pdfs WHERE paper_key='k1'"), 1)
        self.assertEqual((result["new_papers"], result["linked_existing"]), (0, 1))

    def test_an_existing_current_pdf_is_kept_unless_replacing_was_asked_for(self):
        self.store.upsert_papers([{"key": "k1", "title": "T"}], project_id=self.project)
        self.store.record_pdf("k1", "/old/a.pdf", "https://arxiv.org/pdf/1", sha256="a" * 64, size=1, source_kind="arxiv")
        self.batch()
        item = self.add()
        self.settle(item, "duplicate", match_source="existing", paper_key="k1", paper={"key": "k1", "title": "T"})
        result = self.imp.commit(self.batch_id)
        self.assertEqual(self.store.conn.execute("SELECT path FROM pdfs WHERE paper_key='k1'").fetchone()[0], "/old/a.pdf")
        self.assertEqual(result["pdfs_archived"], 0)
        self.assertEqual(list((self.data / "pdfs").glob("*")) if (self.data / "pdfs").exists() else [], [])

    def test_replacing_the_pdf_keeps_the_old_one_in_the_history(self):
        self.store.upsert_papers([{"key": "k1", "title": "T"}], project_id=self.project)
        self.store.record_pdf("k1", "/old/a.pdf", "https://arxiv.org/pdf/1", sha256="a" * 64, size=1, source_kind="arxiv")
        self.batch(replace_pdf=True)
        item = self.add()
        self.settle(item, "duplicate", match_source="existing", paper_key="k1", paper={"key": "k1", "title": "T"})
        self.imp.commit(self.batch_id)
        history = self.store.pdf_history("k1")
        self.assertEqual([h["source_kind"] for h in history], ["arxiv", "user_import"])
        self.assertEqual(history[-1]["sha256"], item["sha256"])

    def test_the_same_file_already_archived_for_that_paper_is_not_written_twice(self):
        self.batch()
        item = self.matched(1)
        self.store.upsert_papers([{"key": "https://doi.org/10.1000/p1", "title": "T"}], project_id=self.project)
        self.store.record_pdf("https://doi.org/10.1000/p1", "/x/a.pdf", "u", sha256=item["sha256"], size=1, source_kind="user_import")
        result = self.imp.commit(self.batch_id)
        self.assertEqual(result["pdfs_archived"], 0)
        self.assertEqual(len(self.store.pdf_history("https://doi.org/10.1000/p1")), 1)

    def test_items_without_an_outcome_are_left_out_and_counted(self):
        self.batch()
        self.matched(1)
        self.settle(self.add(), "needs_choice", candidates=[])
        self.settle(self.add(), "failed", error="bad reply")
        self.settle(self.add(), "excluded")
        result = self.imp.commit(self.batch_id)
        self.assertEqual((result["new_papers"], result["skipped_needs_choice"], result["skipped_failed"], result["excluded"]), (1, 1, 1, 1))
        self.assertEqual(self.count("SELECT COUNT(*) FROM project_library"), 1)

    def test_two_different_pdfs_of_one_paper_do_not_replace_each_other(self):
        # e.g. a preprint and the published version, both matched to the same paper
        self.batch()
        first, second = self.matched(1, path="r/preprint.pdf"), self.matched(1, path="r/published.pdf", data=pdf(901))
        result = self.imp.commit(self.batch_id)
        key = "https://doi.org/10.1000/p1"
        self.assertEqual(self.store.pdf_history(key)[-1]["sha256"], first["sha256"])   # the first file is the current one
        self.assertEqual(len(self.store.pdf_history(key)), 1)
        self.assertEqual((result["new_papers"], result["pdfs_archived"], result["extra_pdfs"]), (1, 1, 1))
        self.assertEqual(result["extra_pdf_names"], ["published.pdf"])
        self.assertEqual(self.count("SELECT COUNT(*) FROM project_library"), 1)
        self.assertEqual(sorted(p.name for p in (self.data / "pdfs").glob("*")), [f"import-{first['sha256'][:24]}.pdf"])

    def test_asked_to_replace_every_file_is_kept_in_the_history_and_the_last_is_current(self):
        self.batch(replace_pdf=True)
        first, second = self.matched(1, path="r/preprint.pdf"), self.matched(1, path="r/published.pdf", data=pdf(901))
        result = self.imp.commit(self.batch_id)
        history = self.store.pdf_history("https://doi.org/10.1000/p1")
        self.assertEqual([h["sha256"] for h in history], [first["sha256"], second["sha256"]])
        self.assertEqual((result["pdfs_archived"], result["extra_pdfs"]), (2, 0))

    def test_a_paper_this_batch_just_added_is_not_reported_as_already_in_the_library(self):
        self.batch()
        self.matched(1, path="r/a.pdf")
        self.matched(1, path="r/b.pdf", data=pdf(902))
        self.assertEqual(self.imp.commit(self.batch_id)["already_in_library"], 0)

    def test_it_refuses_while_items_are_still_being_matched(self):
        self.batch()
        self.matched(1)
        self.add()  # still pending
        with self.assertRaises(ValueError):
            self.imp.commit(self.batch_id)
        self.assertEqual(self.count("SELECT COUNT(*) FROM papers"), 0)

    def test_a_failure_half_way_leaves_nothing_behind_and_a_retry_completes(self):
        self.batch()
        self.matched(1)
        self.matched(2)
        real = self.store.record_pdf
        calls = []

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("disk full")
            return real(*args, **kwargs)
        with mock.patch.object(self.store, "record_pdf", flaky):
            with self.assertRaises(RuntimeError):
                self.imp.commit(self.batch_id)
        for table in ("papers", "project_library", "pdfs", "project_papers"):
            self.assertEqual(self.count(f"SELECT COUNT(*) FROM {table}"), 0, table)
        self.assertEqual(self.imp.batch(self.batch_id)["status"], "review")
        self.assertEqual(self.count("SELECT COUNT(*) FROM import_items WHERE committed=1"), 0)
        result = self.imp.commit(self.batch_id)
        self.assertEqual(result["new_papers"], 2)
        self.assertEqual(self.count("SELECT COUNT(*) FROM project_library"), 2)

    def test_a_committed_batch_cannot_be_committed_again(self):
        self.batch()
        self.matched(1)
        self.imp.commit(self.batch_id)
        with self.assertRaises(ValueError):
            self.imp.commit(self.batch_id)

    def test_a_staged_file_that_no_longer_matches_its_hash_fails_only_that_item(self):
        self.batch()
        good, bad = self.matched(1), self.matched(2)
        (self.data / "imports" / "batches" / self.batch_id / f"{bad['sha256']}.pdf").write_bytes(b"%PDF-1.7 tampered")
        result = self.imp.commit(self.batch_id)
        self.assertEqual((result["new_papers"], result["skipped_failed"]), (1, 1))
        self.assertEqual(self.imp.item(self.batch_id, bad["id"])["state"], "failed")
        self.assertEqual(self.count("SELECT COUNT(*) FROM project_library"), 1)

    def test_identical_copies_share_one_paper_and_remember_every_folder(self):
        self.batch()
        data = pdf(7)
        first = self.add("r/RL/a.pdf", data)
        self.add("r/Survey/a copy.pdf", data)
        self.settle(first, "matched", match_source="title", paper=paper(7))
        result = self.imp.commit(self.batch_id)
        self.assertEqual(result["new_papers"], 1)
        self.assertEqual(self.imp.placements(self.batch_id),
                         [{"key": "https://doi.org/10.1000/p7", "folders": [["RL"], ["Survey"]]}])
        self.assertEqual(self.count("SELECT COUNT(*) FROM import_items WHERE committed=1"), 2)

    def test_placements_list_every_committed_paper_with_its_folders(self):
        self.batch()
        self.matched(1, path="r/A/B/x.pdf")
        self.matched(2, path="r/y.pdf")
        self.imp.commit(self.batch_id)
        self.assertEqual(sorted((p["key"][-2:], p["folders"]) for p in self.imp.placements(self.batch_id)),
                         [("p1", [["A", "B"]]), ("p2", [[]])])


if __name__ == "__main__":
    unittest.main()
