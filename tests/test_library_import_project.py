"""Deleting a project also removes what an unfinished import left for it; other projects' imports are untouched."""
import io
import tempfile
import unittest
from pathlib import Path

from app.service import App
from tests.library_import_fixtures import pdf


class DeleteProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.app = App(data_dir=self.data)
        self.addCleanup(self.app.store.close)
        self.keep = self.app.create_project("留下")["project_id"]
        self.drop = self.app.create_project("删除")["project_id"]

    def staged(self, project, name):
        imp = self.app.library_import
        batch = imp.create_batch(project, "folder", "r", {})["id"]
        data = pdf(hash(name) % 1000)
        imp.add_pdf(batch, f"r/{name}.pdf", io.BytesIO(data), len(data), 1, None)
        return batch

    def test_the_deleted_projects_batches_and_staged_files_are_removed(self):
        dropped, kept = self.staged(self.drop, "a"), self.staged(self.keep, "b")
        self.assertTrue((self.data / "imports" / "batches" / dropped).exists())
        self.app.delete_project(self.drop)
        self.assertFalse((self.data / "imports" / "batches" / dropped).exists())
        self.assertTrue((self.data / "imports" / "batches" / kept).exists())
        rows = [r[0] for r in self.app.store.conn.execute("SELECT id FROM import_batches")]
        self.assertEqual(rows, [kept])
        self.assertEqual(self.app.store.conn.execute("SELECT COUNT(*) FROM import_items").fetchone()[0], 1)

    def test_a_committed_batch_goes_with_its_project_but_the_papers_and_files_stay(self):
        imp = self.app.library_import
        batch = imp.create_batch(self.drop, "folder", "r", {})["id"]
        data = pdf(7)
        item = imp.add_pdf(batch, "r/a.pdf", io.BytesIO(data), len(data), 1, None)
        imp._set(item["id"], "matched", match_source="title", paper={"key": "https://doi.org/10.1000/p7", "title": "Kept paper"})
        imp.commit(batch)
        self.app.delete_project(self.drop)
        self.assertEqual(self.app.store.paper("https://doi.org/10.1000/p7")["title"], "Kept paper")
        self.assertTrue(list((self.data / "pdfs").glob("import-*.pdf")))
        self.assertEqual(self.app.store.conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0], 0)

    def test_the_imported_seed_list_of_the_project_is_forgotten(self):
        self.app.store.set_setting(f"import_seed_keys_{self.drop}", ["k"])
        self.app.store.set_setting(f"import_seed_keys_{self.keep}", ["k2"])
        self.app.delete_project(self.drop)
        self.assertIsNone(self.app.store.get_setting(f"import_seed_keys_{self.drop}"))
        self.assertEqual(self.app.store.get_setting(f"import_seed_keys_{self.keep}"), ["k2"])

    def test_deleting_a_project_that_never_imported_anything_still_works(self):
        self.assertEqual(self.app.delete_project(self.drop)["deleted"], self.drop)


if __name__ == "__main__":
    unittest.main()
