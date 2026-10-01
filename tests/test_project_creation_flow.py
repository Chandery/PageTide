"""Manual creation: identifier parsing, paper-name search, dropped PDFs. No test reaches the network."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import creation
from app.service import App
from app.sources import SourceError, slim

PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\n%%EOF\n"


def work(wid="W1", title="Latent World Models", doi="https://doi.org/10.48550/arxiv.2401.00001"):
    return {"id": f"https://openalex.org/{wid}", "doi": doi, "title": title, "publication_date": "2024-01-02",
            "ids": {}, "primary_location": {"source": {"display_name": "arXiv"}},
            "authorships": [{"author": {"display_name": "Ada Lovelace"}}, {"author": {"display_name": "Bo Chen"}}]}


class SeedParsingTests(unittest.TestCase):
    def test_every_public_identifier_shape_is_recognised(self):
        arxiv = "https://doi.org/10.48550/arxiv.2401.00001"
        for text in ("2401.00001", "arXiv:2401.00001", "https://arxiv.org/abs/2401.00001",
                     "https://arxiv.org/pdf/2401.00001.pdf", "http://www.arxiv.org/abs/2401.00001/"):
            self.assertEqual(creation.parse_seed(text)[:2], (arxiv, "2401.00001"), text)
        self.assertEqual(creation.parse_seed("2401.00001v3")[0], arxiv + "v3")
        for text in ("10.1145/3292500.3330701", "doi:10.1145/3292500.3330701",
                     "https://doi.org/10.1145/3292500.3330701", "https://dx.doi.org/10.1145/3292500.3330701."):
            self.assertEqual(creation.parse_seed(text)[0], "https://doi.org/10.1145/3292500.3330701", text)
        self.assertEqual(creation.parse_seed("https://openalex.org/w123")[0], "W123")

    def test_free_text_is_not_an_identifier(self):
        with self.assertRaises(ValueError):
            creation.parse_seed("Attention is all you need")


class SeedLookupTests(unittest.TestCase):
    def setUp(self):
        creation._SEED_CACHE.clear()
        self.client = mock.Mock()

    def test_lookup_resolves_and_remembers_the_paper(self):
        self.client.work.return_value = work()
        result = creation.lookup_seed(self.client, "2401.00001")
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["paper"]["title"], "Latent World Models")
        self.assertEqual(result["paper"]["authors"], ["Ada Lovelace", "Bo Chen"])
        self.assertEqual(result["paper"]["url"], "https://arxiv.org/abs/2401.00001")
        self.client.work.reset_mock()
        # Creating the project later asks for the same paper by its OpenAlex id: no second fetch.
        again = creation.fetch_seed_paper(self.client, "W1")
        self.assertEqual(again["title"], "Latent World Models")
        self.client.work.assert_not_called()

    def test_failures_are_statuses_the_page_can_show(self):
        self.assertEqual(creation.lookup_seed(self.client, "a paper title")["status"], "invalid_input")
        self.client.work.side_effect = SourceError("gone", "not_found")
        self.assertEqual(creation.lookup_seed(self.client, "10.1234/x")["status"], "not_found")
        self.client.work.side_effect = SourceError("busy", "unavailable")
        self.assertEqual(creation.lookup_seed(self.client, "10.1234/y")["status"], "unavailable")
        self.client.work.side_effect = RuntimeError("boom")
        self.assertEqual(creation.lookup_seed(self.client, "10.1234/z")["status"], "failed")
        with self.assertRaises(ValueError):
            creation.lookup_seed(self.client, "  ")

    def test_name_search_returns_views_and_validates_the_query(self):
        self.client.search_works.return_value = [slim(work("W1")), slim(work("W2", "Other"))]
        result = creation.search_seeds(self.client, "  latent   world models ")
        self.assertEqual(result["status"], "ok")
        self.assertEqual([i["title"] for i in result["items"]], ["Latent World Models", "Other"])
        self.client.search_works.assert_called_once_with("latent world models")
        self.client.search_works.return_value = []
        self.assertEqual(creation.search_seeds(self.client, "no such paper")["status"], "empty")
        self.client.search_works.side_effect = SourceError("busy", "unavailable")
        self.assertEqual(creation.search_seeds(self.client, "anything")["status"], "unavailable")
        with self.assertRaises(ValueError):
            creation.search_seeds(self.client, "ab")


class ImportedPdfTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_import_keeps_the_original_bytes(self):
        info = creation.import_pdf(self.dir, PDF, "../my paper?.pdf")
        self.assertEqual(info["pdf_id"], hashlib.sha256(PDF).hexdigest())
        self.assertEqual(info["filename"], "my paper_.pdf")
        self.assertEqual((self.dir / "imports" / f"{info['pdf_id']}.pdf").read_bytes(), PDF)

    def test_only_pdfs_within_the_size_limit_are_kept(self):
        with self.assertRaisesRegex(ValueError, "不是 PDF"):
            creation.import_pdf(self.dir, b"<html></html>")
        with mock.patch.object(creation, "PDF_MAX_BYTES", 10):
            with self.assertRaisesRegex(ValueError, "60 MB"):
                creation.import_pdf(self.dir, PDF)
        self.assertFalse((self.dir / "imports").exists() and list((self.dir / "imports").iterdir()))

    def test_take_moves_the_file_and_rejects_bad_ids(self):
        info = creation.import_pdf(self.dir, PDF)
        path = creation.take_imported_pdf(self.dir, info["pdf_id"])
        self.assertEqual(path.read_bytes(), PDF)
        self.assertEqual(path.parent, self.dir / "pdfs")
        for bad in ("../../etc/passwd", "x" * 64, None, info["pdf_id"]):
            with self.assertRaises(ValueError):
                creation.take_imported_pdf(self.dir, bad)

    def test_stale_uploads_are_removed(self):
        old = creation.import_pdf(self.dir, PDF)["pdf_id"]
        stale = self.dir / "imports" / f"{old}.pdf"
        import os, time
        os.utime(stale, (time.time() - 3 * 24 * 3600,) * 2)
        creation.import_pdf(self.dir, PDF + b"x")
        self.assertFalse(stale.exists())


class CreateProjectWithSeedTests(unittest.TestCase):
    def setUp(self):
        creation._SEED_CACHE.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = App(root=".", data_dir=Path(self.tmp.name) / "app")
        self.app.source = mock.Mock()
        self.app.source.work.return_value = work()

    def test_a_dropped_pdf_becomes_the_seed_papers_pdf(self):
        pdf = self.app.import_pdf(PDF, "p.pdf")
        result = self.app.create_project("带 PDF", "manual", ["world models"],
                                         [{"identifier": "2401.00001", "pdf_id": pdf["pdf_id"]}])
        outcome = result["seed_results"][0]
        self.assertEqual((outcome["status"], outcome["pdf_attached"]), ("resolved", True))
        path = self.app.pdf_path(outcome["key"])
        self.assertEqual(path.read_bytes(), PDF)
        self.assertFalse((Path(self.tmp.name) / "app" / "imports" / f"{pdf['pdf_id']}.pdf").exists())

    def test_an_expired_pdf_does_not_fail_the_seed(self):
        result = self.app.create_project("过期", "manual", [], [{"identifier": "2401.00001", "pdf_id": "0" * 64}])
        outcome = result["seed_results"][0]
        self.assertEqual((outcome["status"], outcome["pdf_attached"]), ("resolved", False))
        self.assertIn("过期", outcome["pdf_error"])

    def test_seeds_resolved_on_the_page_are_not_fetched_again(self):
        self.app.seed_lookup("2401.00001")
        self.app.source.work.reset_mock()
        result = self.app.create_project("缓存", "manual", [], ["https://openalex.org/W1"])
        self.assertEqual(result["seed_results"][0]["status"], "resolved")
        self.app.source.work.assert_not_called()


if __name__ == "__main__":
    unittest.main()
