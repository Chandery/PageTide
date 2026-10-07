"""Import batches: lazy tables, streamed PDF upload into a staging folder, in-batch duplicates, safe paths.

Nothing here touches the network or the library itself; a batch is only a staging area until it is committed."""
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import library_import
from app.db import Store
from app.library_import import LibraryImport
from app.project import ProjectManager

PDF_A = b"%PDF-1.7\n" + b"a" * 300
PDF_B = b"%PDF-1.5\n" + b"b" * 300


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / "paperdighelper.sqlite")
        self.store.init()
        self.project = ProjectManager(self.store).create_project("导入测试")
        self.imp = LibraryImport(self.data, self.store)

    def batch(self, source="folder", root="我的论文", **options):
        return self.imp.create_batch(self.project, source, root, options)["id"]

    def add(self, batch, path, data, hints=None, modified=1700000000):
        return self.imp.add_pdf(batch, path, io.BytesIO(data), len(data), modified, hints)


class BatchTests(Base):
    def test_creating_a_batch_needs_an_existing_project_and_a_known_source(self):
        with self.assertRaises(ValueError):
            self.imp.create_batch("nope", "folder", "x", {})
        with self.assertRaises(ValueError):
            self.imp.create_batch(self.project, "dropbox", "x", {})

    def test_tables_are_created_lazily_and_twice_is_harmless(self):
        LibraryImport(self.data, self.store)
        names = {r[0] for r in self.store.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"import_batches", "import_items"} <= names)

    def test_options_keep_only_the_known_switches(self):
        batch = self.imp.create_batch(self.project, "folder", "root",
                                      {"online": False, "folder_categories": True, "evil": "x"})
        self.assertEqual(batch["options"]["online"], False)
        self.assertNotIn("evil", batch["options"])
        self.assertEqual(batch["options"]["folder_categories"], True)
        self.assertEqual(self.imp.create_batch(self.project, "files", "", {})["options"]["online"], True)

    def test_a_new_batch_lists_for_its_project_and_starts_collecting(self):
        batch = self.batch()
        listed = self.imp.list_batches(self.project)
        self.assertEqual([b["id"] for b in listed], [batch])
        self.assertEqual(listed[0]["status"], "collecting")
        self.assertEqual(self.imp.list_batches("other"), [])


class UploadTests(Base):
    def test_a_pdf_is_staged_by_content_and_recorded_as_pending(self):
        batch = self.batch()
        item = self.add(batch, "我的论文/RL/a.pdf", PDF_A, {"doi": "10.1/x", "titles": ["A title"]})
        sha = hashlib.sha256(PDF_A).hexdigest()
        self.assertEqual(item["sha256"], sha)
        self.assertEqual(item["state"], "pending")
        self.assertEqual(item["original_name"], "a.pdf")
        self.assertEqual(item["folders"], [["RL"]])
        self.assertEqual(item["hints"], {"doi": "10.1/x", "titles": ["A title"]})
        staged = self.data / "imports" / "batches" / batch / f"{sha}.pdf"
        self.assertEqual(staged.read_bytes(), PDF_A)
        self.assertEqual(list(staged.parent.glob("*.part")), [])

    def test_the_root_folder_name_is_not_a_category(self):
        batch = self.batch(root="我的论文")
        self.assertEqual(self.add(batch, "我的论文/top.pdf", PDF_A)["folders"], [[]])
        self.assertEqual(self.add(batch, "我的论文/A/B/deep.pdf", PDF_B)["folders"], [["A", "B"]])

    def test_a_non_pdf_is_refused_and_leaves_no_partial_file(self):
        batch = self.batch()
        with self.assertRaises(ValueError):
            self.add(batch, "r/a.pdf", b"PK\x03\x04 not a pdf at all")
        self.assertEqual(list((self.data / "imports" / "batches" / batch).glob("*")), [])
        self.assertEqual(self.imp.batch(batch)["counts"], {})

    def test_an_oversize_file_is_refused_while_streaming(self):
        batch = self.batch()
        with mock.patch.object(library_import, "MAX_FILE_BYTES", 100):
            with self.assertRaises(ValueError):
                self.add(batch, "r/big.pdf", PDF_A)
        self.assertEqual(list((self.data / "imports" / "batches" / batch).glob("*")), [])

    def test_a_declared_length_that_lies_is_caught(self):
        batch = self.batch()
        with self.assertRaises(ValueError):
            self.imp.add_pdf(batch, "r/a.pdf", io.BytesIO(PDF_A[:50]), len(PDF_A), 0, None)
        self.assertEqual(list((self.data / "imports" / "batches" / batch).glob("*")), [])

    def test_the_same_content_in_two_folders_is_one_item_in_both_categories(self):
        batch = self.batch(root="r")
        first = self.add(batch, "r/RL/a.pdf", PDF_A)
        second = self.add(batch, "r/Survey/copy of a.pdf", PDF_A)
        self.assertEqual(second["state"], "duplicate")
        self.assertEqual(second["duplicate_of"], first["id"])
        merged = self.imp.item(batch, first["id"])
        self.assertEqual(sorted(merged["folders"]), [["RL"], ["Survey"]])
        self.assertEqual(self.imp.batch(batch)["counts"], {"pending": 1, "duplicate": 1})

    def test_the_batch_says_how_many_rows_are_only_copies_of_another_file(self):
        batch = self.batch(root="r")
        self.add(batch, "r/a.pdf", PDF_A)
        self.add(batch, "r/b.pdf", PDF_A)
        self.add(batch, "r/c.pdf", PDF_A)
        self.add(batch, "r/d.pdf", PDF_B)
        detail = self.imp.batch(batch)
        self.assertEqual((detail["copies"], detail["counts"]), (2, {"pending": 2, "duplicate": 2}))
        self.assertEqual([i["relative_path"] for i in detail["items"]], ["r/a.pdf", "r/d.pdf"])

    def test_sending_the_same_path_again_resumes_without_a_new_row(self):
        batch = self.batch(root="r")
        first = self.add(batch, "r/a.pdf", PDF_A, modified=5)
        again = self.add(batch, "r/a.pdf", PDF_A, modified=5)
        self.assertEqual(again["id"], first["id"])
        self.assertEqual(sum(self.imp.batch(batch)["counts"].values()), 1)

    def test_a_changed_file_at_the_same_path_replaces_the_staged_content(self):
        batch = self.batch(root="r")
        self.add(batch, "r/a.pdf", PDF_A, modified=5)
        changed = self.add(batch, "r/a.pdf", PDF_B, modified=9)
        self.assertEqual(changed["sha256"], hashlib.sha256(PDF_B).hexdigest())
        self.assertEqual(sum(self.imp.batch(batch)["counts"].values()), 1)

    def test_hostile_paths_cannot_leave_the_batch(self):
        batch = self.batch(root="r")
        for bad in ("r/../../etc/a.pdf", "../a.pdf", "", "r/\x00a.pdf"):
            with self.assertRaises(ValueError, msg=bad):
                self.add(batch, bad, PDF_A)
        item = self.add(batch, "/abs/olute/a.pdf", PDF_A)
        self.assertEqual(item["relative_path"], "abs/olute/a.pdf")
        self.assertTrue(all(str(p).startswith(str(self.data)) for p in self.data.rglob("*.pdf")))

    def test_control_characters_and_overlong_names_are_cleaned(self):
        batch = self.batch(root="r")
        item = self.add(batch, "r/" + "x" * 500 + ".pdf", PDF_A)
        self.assertLessEqual(len(item["original_name"]), 200)
        item = self.add(batch, "r/a\tb\nc.pdf", PDF_B)
        self.assertEqual(item["original_name"], "a b c.pdf")

    def test_the_batch_size_is_capped(self):
        batch = self.batch(root="r")
        with mock.patch.object(library_import, "MAX_FILES", 1):
            self.add(batch, "r/a.pdf", PDF_A)
            with self.assertRaises(ValueError):
                self.add(batch, "r/b.pdf", PDF_B)

    def test_hints_keep_only_short_known_fields(self):
        batch = self.batch(root="r")
        item = self.add(batch, "r/a.pdf", PDF_A, {"arxiv": "2401.00001", "doi": "10.1/x", "evil": "x",
                                                  "titles": ["t" * 500, "second", "", 3, "4", "5", "6"]})
        self.assertEqual(set(item["hints"]), {"arxiv", "doi", "titles"})
        self.assertLessEqual(len(item["hints"]["titles"]), 3)
        self.assertTrue(all(len(t) <= 300 for t in item["hints"]["titles"]))

    def test_uploading_into_a_closed_batch_is_refused(self):
        batch = self.batch(root="r")
        self.imp.discard(batch)
        with self.assertRaises(ValueError):
            self.add(batch, "r/a.pdf", PDF_A)


class ReferenceManagerFolderTests(Base):
    def test_attachment_folders_of_a_zotero_export_are_not_categories(self):
        batch = self.batch(source="zotero", root="My Library")
        self.assertEqual(self.add(batch, "My Library/files/12/paper.pdf", PDF_A)["folders"], [[]])
        self.assertEqual(self.add(batch, "My Library/files/345/Sub/x.pdf", PDF_B)["folders"], [["Sub"]])

    def test_a_folder_that_is_really_called_files_is_kept_when_it_holds_no_numbered_folder(self):
        batch = self.batch(root="r")
        self.assertEqual(self.add(batch, "r/files/a.pdf", PDF_A)["folders"], [["files"]])

    def test_in_a_zotero_export_the_files_folder_is_never_a_category_even_without_numbered_folders(self):
        batch = self.batch(source="zotero", root="My Library")
        self.assertEqual(self.add(batch, "My Library/files/flat.pdf", PDF_A)["folders"], [[]])
        self.assertEqual(self.add(batch, "My Library/files/12/numbered.pdf", PDF_B)["folders"], [[]])
        # only the first level: a folder of the same name deeper down is the person's own
        self.assertEqual(self.add(batch, "My Library/Notes/files/x.pdf", b"%PDF-1.7\n" + b"c" * 300)["folders"], [["Notes", "files"]])

    def test_a_real_files_folder_with_a_year_inside_is_the_persons_own_structure_outside_an_export(self):
        batch = self.batch(root="Papers")
        self.assertEqual(self.add(batch, "Papers/files/2023/x.pdf", PDF_A)["folders"], [["files", "2023"]])
        zotero = self.batch(source="zotero", root="Papers")
        self.assertEqual(self.add(zotero, "Papers/files/2023/y.pdf", PDF_B)["folders"], [[]])

    def test_the_raw_zotero_storage_folder_has_no_categories_from_its_item_keys(self):
        batch = self.batch(root="storage")
        self.assertEqual(self.add(batch, "storage/ABCD1234/a.pdf", PDF_A)["folders"], [[]])
        self.assertEqual(self.add(batch, "storage/ABCD1235/Notes/b.pdf", PDF_B)["folders"], [["Notes"]])

    def test_an_eight_letter_folder_in_an_ordinary_library_is_a_category(self):
        batch = self.batch(root="lib")
        self.assertEqual(self.add(batch, "lib/ROBOTICS/a.pdf", PDF_A)["folders"], [["ROBOTICS"]])


class ResumeIndexTests(Base):
    def test_the_index_lists_every_uploaded_file_as_path_size_and_modified_time(self):
        batch = self.batch(root="r")
        self.add(batch, "r/a.pdf", PDF_A, modified=5)
        self.add(batch, "r/b/c.pdf", PDF_B, modified=9)
        self.assertEqual(self.imp.resume_index(batch),
                         [["r/a.pdf", len(PDF_A), 5], ["r/b/c.pdf", len(PDF_B), 9]])

    def test_it_is_not_capped_like_a_page_of_items(self):
        batch = self.batch(root="r")
        for i in range(230):
            data = b"%PDF-1.7\n" + f"{i}".encode() * 30
            self.imp.add_pdf(batch, f"r/f{i}.pdf", io.BytesIO(data), len(data), i, None)
        self.assertEqual(len(self.imp.resume_index(batch)), 230)
        self.assertEqual(len(self.imp.batch(batch)["items"]), 200)

    def test_a_copy_of_the_same_content_is_listed_too_so_a_resume_does_not_resend_it(self):
        batch = self.batch(root="r")
        self.add(batch, "r/a.pdf", PDF_A, modified=1)
        self.add(batch, "r/copy.pdf", PDF_A, modified=2)
        self.assertEqual([row[0] for row in self.imp.resume_index(batch)], ["r/a.pdf", "r/copy.pdf"])


class DiscardTests(Base):
    def test_discarding_removes_the_staging_folder_and_marks_the_batch(self):
        batch = self.batch(root="r")
        self.add(batch, "r/a.pdf", PDF_A)
        self.imp.discard(batch)
        self.assertFalse((self.data / "imports" / "batches" / batch).exists())
        self.assertEqual(self.imp.batch(batch)["status"], "discarded")

    def test_stale_uncommitted_batches_are_purged_but_recent_ones_stay(self):
        old, recent = self.batch(root="r"), self.batch(root="r")
        self.add(old, "r/a.pdf", PDF_A)
        self.store.conn.execute("UPDATE import_batches SET updated_at='2020-01-01T00:00:00+00:00' WHERE id=?", (old,))
        self.store.conn.commit()
        self.imp.purge_stale()
        self.assertEqual([b["id"] for b in self.imp.list_batches(self.project)], [recent])
        self.assertFalse((self.data / "imports" / "batches" / old).exists())


if __name__ == "__main__":
    unittest.main()
