"""An export file next to the PDFs: its entries are joined to the PDFs they name, and carry the metadata.

A reference manager's export is the person's own curated data, so it outranks what is read off a PDF: its DOI is
used first, its title is never searched for, and when OpenAlex does not know a paper the export's own record is
kept. Entries with no PDF are only imported when asked for."""
import io
import json
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.db import Store
from app.library_import import LibraryImport
from app.project import ProjectManager
from app.sources import SourceError
from tests.library_import_fixtures import FakeClient, pdf, work

BIB = r'''
@article{a,
	title = {Attention is all you need},
	author = {Vaswani, Ashish and Shazeer, Noam},
	date = {2017-06},
	doi = {10.5555/3295222.3295349},
	abstract = {The dominant sequence transduction models.},
	journaltitle = {NeurIPS},
	file = {Full Text PDF:files/12/Vaswani.pdf:application/pdf},
}
@article{b,
	title = {A paper without a DOI},
	author = {Nobody, N.},
	year = {2020},
	file = {PDF:files/20/nodoi.pdf:application/pdf},
}
@article{c,
	title = {Only a reference, no attachment},
	author = {Ghost, G.},
	year = {2019},
	doi = {10.1000/ghost},
}
'''


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / "pagetide.sqlite")
        self.store.init()
        self.project = ProjectManager(self.store).create_project("导入测试")
        self.client = FakeClient()
        self.imp = LibraryImport(self.data, self.store, self.client)
        self.n = 0

    def batch(self, **options):
        self.batch_id = self.imp.create_batch(self.project, "zotero", "Export", options)["id"]
        return self.batch_id

    def add(self, path, hints=None, data=None):
        self.n += 1
        data = data or pdf(self.n)
        return self.imp.add_pdf(self.batch_id, path, io.BytesIO(data), len(data), 1, hints)

    def sidecar(self, text=BIB, name="My Library.bib"):
        return self.imp.add_sidecar(self.batch_id, name, text.encode("utf-8"))

    def items(self):
        return {(i["relative_path"] or i["original_name"]): i for i in self.imp.batch(self.batch_id)["items"]}


class StoringTests(Base):
    def test_the_export_is_read_and_summarised(self):
        self.batch()
        result = self.sidecar()
        self.assertEqual((result["format"], result["entries"], result["with_files"]), ("bibtex", 3, 2))
        stored = self.imp.batch(self.batch_id)["sidecar"]
        self.assertEqual((stored["filename"], stored["format"], stored["entries"]), ("My Library.bib", "bibtex", 3))

    def test_every_entry_is_a_row_without_a_file_until_it_is_joined(self):
        self.batch()
        self.sidecar()
        rows = self.imp.batch(self.batch_id)["items"]
        self.assertEqual({r["kind"] for r in rows}, {"entry"})
        self.assertTrue(all(r["relative_path"] is None and r["sha256"] is None for r in rows))

    def test_uploading_another_export_replaces_the_entries_not_yet_joined(self):
        self.batch()
        self.sidecar()
        self.sidecar("@article{z,\n title = {Only this one},\n}\n", "other.bib")
        self.assertEqual([i["original_name"] for i in self.imp.batch(self.batch_id)["items"]], ["Only this one"])

    def test_things_that_are_not_an_export_are_refused_and_nothing_is_stored(self):
        self.batch()
        for name, data in (("notes.txt", b"x"), ("empty.bib", b"nothing here"), ("big.bib", b"x" * (21 * 1024 * 1024))):
            with self.assertRaises(ValueError, msg=name):
                self.imp.add_sidecar(self.batch_id, name, data)
        self.assertEqual(self.imp.batch(self.batch_id)["items"], [])
        self.assertIsNone(self.imp.batch(self.batch_id)["sidecar"])

    def test_a_closed_batch_takes_no_export(self):
        self.batch()
        self.imp.discard(self.batch_id)
        with self.assertRaises(ValueError):
            self.sidecar()


class JoinTests(Base):
    def resolve_offline(self, **options):
        return self.imp.resolve(self.batch_id)

    def test_a_pdf_named_by_an_entry_takes_that_entrys_metadata_with_no_request(self):
        self.batch(online=False)
        self.sidecar()
        self.add("Export/files/12/Vaswani.pdf")
        self.assertEqual(self.resolve_offline(), "review")
        item = self.items()["Export/files/12/Vaswani.pdf"]
        self.assertEqual((item["state"], item["match_source"]), ("matched", "sidecar"))
        paper = item["paper"]
        self.assertEqual((paper["key"], paper["title"], paper["published"], paper["source"]),
                         ("https://doi.org/10.5555/3295222.3295349", "Attention is all you need", "2017-01-01", "NeurIPS"))
        self.assertEqual(paper["authors"], ["Vaswani, Ashish", "Shazeer, Noam"])
        self.assertEqual(self.client.calls, [])

    def test_a_joined_entry_is_not_listed_twice(self):
        self.batch(online=False, include_fileless=False)
        self.sidecar()
        self.add("Export/files/12/Vaswani.pdf")
        self.add("Export/files/20/nodoi.pdf")
        self.resolve_offline()
        listed = [i["kind"] for i in self.imp.batch(self.batch_id)["items"]]
        self.assertEqual(sorted(listed), ["entry", "pdf", "pdf"])   # the third entry has no PDF

    def test_an_entry_without_a_doi_still_gets_a_stable_key_of_its_own(self):
        self.batch(online=False)
        self.sidecar()
        self.add("Export/files/20/nodoi.pdf")
        self.resolve_offline()
        key = self.items()["Export/files/20/nodoi.pdf"]["paper"]["key"]
        self.assertTrue(key.startswith("entry:"))
        # the same entry in another batch gets the same key, so a second import links to the first
        other = self.imp.create_batch(self.project, "zotero", "Export", {"online": False})["id"]
        self.imp.add_sidecar(other, "My Library.bib", BIB.encode())
        self.imp.add_pdf(other, "Export/files/20/nodoi.pdf", io.BytesIO(pdf(77)), len(pdf(77)), 1, None)
        self.imp.resolve(other)
        again = [i for i in self.imp.batch(other)["items"] if i["kind"] == "pdf"][0]["paper"]["key"]
        self.assertEqual(again, key)

    def test_paths_match_whatever_the_folder_was_called_and_however_the_name_is_spelled(self):
        self.batch(online=False)
        # macOS file names come decomposed (NFD) from the picker and may be written either way in the export
        self.sidecar(BIB.replace("files/12/Vaswani.pdf", unicodedata.normalize("NFD", "files/12/Schölkopf.pdf")))
        self.add("Renamed Folder/files/12/Schölkopf.pdf")   # composed (NFC) here
        self.resolve_offline()
        self.assertEqual([i["match_source"] for i in self.imp.batch(self.batch_id)["items"] if i["kind"] == "pdf"], ["sidecar"])

    def test_a_pdf_in_a_deeper_folder_matches_by_its_path_tail(self):
        self.batch(online=False)
        self.sidecar()
        self.add("Export/nested/files/12/Vaswani.pdf")
        self.resolve_offline()
        self.assertEqual(self.items()["Export/nested/files/12/Vaswani.pdf"]["match_source"], "sidecar")

    def test_a_unique_file_name_is_enough_when_the_folders_do_not_line_up(self):
        self.batch(online=False)
        self.sidecar()
        self.add("Somewhere/else/Vaswani.pdf")
        self.resolve_offline()
        self.assertEqual(self.items()["Somewhere/else/Vaswani.pdf"]["match_source"], "sidecar")

    def test_an_ambiguous_file_name_is_not_guessed(self):
        self.batch(online=False, include_fileless=False)
        self.sidecar()
        self.add("A/Vaswani.pdf")
        self.add("B/Vaswani.pdf")
        self.resolve_offline()
        items = self.items()
        self.assertEqual({items["A/Vaswani.pdf"]["match_source"], items["B/Vaswani.pdf"]["match_source"]}, {"unresolved"})

    def test_a_pdf_the_export_does_not_mention_goes_through_the_normal_pipeline(self):
        self.batch(online=False)
        self.sidecar()
        self.add("Export/stray.pdf", {"titles": ["A stray paper with a title"]})
        self.resolve_offline()
        self.assertEqual(self.items()["Export/stray.pdf"]["match_source"], "unresolved")

    def test_an_entry_that_names_an_identical_copy_in_another_folder_still_finds_its_pdf(self):
        self.batch(online=False, include_fileless=False)
        self.sidecar()
        same = pdf(555)
        self.add("Export/backup/Vaswani copy.pdf", data=same)           # uploaded first, so this is the primary
        self.add("Export/files/12/Vaswani.pdf", data=same)             # the one the export names: a copy of it
        self.resolve_offline()
        listed = self.imp.batch(self.batch_id)["items"]
        self.assertEqual([(i["kind"], i["state"], i["match_source"]) for i in listed if i["kind"] == "pdf"], [("pdf", "matched", "sidecar")])
        self.assertNotIn("Attention is all you need", [i["original_name"] for i in listed if i["kind"] == "entry"])

    def test_two_pdfs_of_one_entry_become_one_paper(self):
        self.batch(online=False)
        self.sidecar(BIB.replace("files/12/Vaswani.pdf:application/pdf", "files/12/Vaswani.pdf:application/pdf;Supplement:files/14/supp.pdf:application/pdf"))
        self.add("Export/files/12/Vaswani.pdf")
        self.add("Export/files/14/supp.pdf")
        self.resolve_offline()
        keys = {i["paper"]["key"] for i in self.imp.batch(self.batch_id)["items"] if i["kind"] == "pdf"}
        self.assertEqual(keys, {"https://doi.org/10.5555/3295222.3295349"})


class OnlineTests(Base):
    def test_the_exports_doi_is_looked_up_and_the_exports_abstract_fills_a_gap(self):
        self.batch()
        self.sidecar()
        self.add("Export/files/12/Vaswani.pdf", {"doi": "10.9999/from-the-pdf"})
        self.client.dois["https://doi.org/10.5555/3295222.3295349"] = work(1, "Attention Is All You Need", "https://doi.org/10.5555/3295222.3295349")
        self.imp.resolve(self.batch_id)
        self.assertEqual(self.client.calls, [("dois", ["https://doi.org/10.5555/3295222.3295349"])])
        paper = self.items()["Export/files/12/Vaswani.pdf"]["paper"]
        self.assertEqual(paper["openalex_id"], "https://openalex.org/W1")
        self.assertEqual(paper["abstract"], "The dominant sequence transduction models.")   # the work had none, the export did

    def test_a_title_is_never_searched_for_an_entry_and_the_exports_own_record_is_kept(self):
        self.batch()
        self.sidecar()
        self.add("Export/files/20/nodoi.pdf")
        self.imp.resolve(self.batch_id)
        self.assertEqual(self.client.calls, [])
        item = self.items()["Export/files/20/nodoi.pdf"]
        self.assertEqual((item["state"], item["match_source"], item["paper"]["title"]), ("matched", "sidecar", "A paper without a DOI"))

    def test_a_lookup_that_is_refused_falls_back_to_the_exports_record_instead_of_failing(self):
        self.batch()
        self.sidecar()
        self.add("Export/files/12/Vaswani.pdf")
        self.client.fail = ("dois", SourceError("HTTP Error 400", "invalid_input"))
        self.client.work_errors["https://doi.org/10.5555/3295222.3295349"] = SourceError("HTTP Error 400", "invalid_input")
        self.imp.resolve(self.batch_id)
        item = self.items()["Export/files/12/Vaswani.pdf"]
        self.assertEqual((item["state"], item["match_source"], item["paper"]["title"]), ("matched", "sidecar", "Attention is all you need"))

    def test_a_doi_openalex_does_not_know_falls_back_to_the_exports_record(self):
        self.batch()
        self.sidecar()
        self.add("Export/files/12/Vaswani.pdf")
        self.imp.resolve(self.batch_id)   # the fake knows no DOI
        item = self.items()["Export/files/12/Vaswani.pdf"]
        self.assertEqual((item["state"], item["paper"]["key"]), ("matched", "https://doi.org/10.5555/3295222.3295349"))


class FilelessTests(Base):
    def test_entries_without_a_pdf_are_left_out_unless_asked_for_and_can_be_restored(self):
        self.batch(online=False)
        self.sidecar()
        self.add("Export/files/12/Vaswani.pdf")
        self.imp.resolve(self.batch_id)
        ghost = self.items()["Only a reference, no attachment"]
        self.assertEqual((ghost["kind"], ghost["state"]), ("entry", "excluded"))
        self.assertEqual(self.imp.act(self.batch_id, ghost["id"], "include")["state"], "matched")

    def test_when_asked_for_they_are_imported_as_references_with_no_pdf(self):
        self.batch(online=False, include_fileless=True)
        self.sidecar()
        self.imp.resolve(self.batch_id)
        self.assertEqual({i["state"] for i in self.imp.batch(self.batch_id)["items"]}, {"matched"})
        result = self.imp.commit(self.batch_id)
        self.assertEqual((result["new_papers"], result["pdfs_archived"]), (3, 0))
        self.assertEqual(self.store.paper("https://doi.org/10.1000/ghost")["title"], "Only a reference, no attachment")
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM pdfs").fetchone()[0], 0)
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM project_library").fetchone()[0], 3)

    def test_an_entry_whose_pdf_was_not_picked_is_a_reference_too(self):
        self.batch(online=False, include_fileless=True)
        self.sidecar()
        self.add("Export/files/12/Vaswani.pdf")
        self.imp.resolve(self.batch_id)
        kinds = sorted(i["kind"] for i in self.imp.batch(self.batch_id)["items"])
        self.assertEqual(kinds, ["entry", "entry", "pdf"])

    def test_an_entry_already_in_the_library_is_linked_not_duplicated(self):
        self.store.upsert_papers([{"key": "https://doi.org/10.1000/ghost", "title": "Known", "doi": "https://doi.org/10.1000/ghost"}], project_id=self.project)
        self.batch(online=False, include_fileless=True)
        self.sidecar()
        self.imp.resolve(self.batch_id)
        ghost = self.items()["Only a reference, no attachment"]
        self.assertEqual((ghost["state"], ghost["match_source"]), ("duplicate", "existing"))


class CommitTests(Base):
    def test_pdfs_and_references_commit_together_and_keep_their_folders(self):
        self.batch(online=False, include_fileless=True, root_category=True)
        self.sidecar()
        self.add("Export/files/12/Vaswani.pdf")
        self.imp.resolve(self.batch_id)
        self.imp.commit(self.batch_id)
        placed = {p["key"][-8:]: p["folders"] for p in self.imp.placements(self.batch_id)}
        self.assertEqual(len(placed), 3)
        self.assertTrue(all(folders == [[]] for folders in placed.values()))
        row = self.store.conn.execute("SELECT * FROM pdfs WHERE paper_key='https://doi.org/10.5555/3295222.3295349'").fetchone()
        self.assertEqual(row["source_kind"], "user_import")


class FoldersOfAZoteroExportTests(Base):
    def test_attachment_folders_never_become_categories_in_an_export(self):
        self.batch(online=False)
        self.sidecar()
        self.add("Export/files/12/Vaswani.pdf")
        self.resolve = self.imp.resolve(self.batch_id)
        item = self.items()["Export/files/12/Vaswani.pdf"]
        self.assertEqual(item["folders"], [[]])


if __name__ == "__main__":
    unittest.main()
