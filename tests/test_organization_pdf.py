"""The library snapshot says, per saved paper, which PDF state it is in (no migration, zero model tokens).

local  = a PDF is archived on this computer and its file exists
direct = a legal direct PDF is known (arXiv id or an https PDF link) but not yet downloaded
page   = only an open-access landing page is known
none   = no PDF source is known
"""
import tempfile
import unittest
from pathlib import Path

from app.db import Store
from app.organization import Organization


class SnapshotPdfStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.store = Store(self.dir / "library.sqlite")
        self.store.init()
        self.addCleanup(self.store.close)
        self.store.upsert_papers([
            {"key": "local", "title": "Archived paper", "abstract": "x"},
            {"key": "gone", "title": "Archived file removed", "abstract": "x", "arxiv_id": "2401.00001"},
            {"key": "arx", "title": "On arXiv", "abstract": "x", "arxiv_id": "2401.00002"},
            {"key": "link", "title": "Direct link", "abstract": "x"},
            {"key": "page", "title": "Landing page only", "abstract": "x"},
            {"key": "none", "title": "No source", "abstract": "x"},
            {"key": "bad", "title": "Unreadable oa", "abstract": "x"}])
        self.store.set_paper_oa("link", {"pdf_urls": ["https://example.org/a.pdf"], "landing_page": None})
        self.store.set_paper_oa("page", {"pdf_urls": [], "landing_page": "https://example.org/landing"})
        self.store.set_paper_oa("none", {"pdf_urls": [], "landing_page": None})
        self.store.conn.execute("UPDATE papers SET oa_json='not json' WHERE key='bad'")
        self.store.conn.commit()
        real = self.dir / "local.pdf"
        real.write_bytes(b"%PDF-1.4\n")
        self.store.record_pdf("local", real)
        self.store.record_pdf("gone", self.dir / "removed.pdf")          # recorded, but the file is no longer there
        for key in ("local", "gone", "arx", "link", "page", "none", "bad"):
            self.store.save_to_library(key)
        self.org = Organization(self.store)

    def pdf_states(self):
        return {p["key"]: p["pdf"] for p in self.org.snapshot()["items"]}

    def test_each_saved_paper_reports_one_of_four_pdf_states(self):
        states = self.pdf_states()
        self.assertEqual(states["local"], "local")
        self.assertEqual(states["arx"], "direct")
        self.assertEqual(states["link"], "direct")
        self.assertEqual(states["page"], "page")
        self.assertEqual(states["none"], "none")

    def test_only_a_pdf_on_disk_carries_its_path_for_show_in_folder(self):
        items = {p["key"]: p for p in self.org.snapshot()["items"]}
        self.assertTrue(items["local"]["pdf_path"].endswith(".pdf"))
        self.assertNotIn("pdf_path", items["gone"])
        self.assertNotIn("pdf_path", items["arx"])

    def test_a_recorded_pdf_whose_file_is_gone_falls_back_to_what_the_source_allows(self):
        self.assertEqual(self.pdf_states()["gone"], "direct")            # it has an arXiv id, so it can be downloaded again

    def test_unreadable_source_data_means_no_pdf_rather_than_an_error(self):
        self.assertEqual(self.pdf_states()["bad"], "none")

    def test_reading_the_snapshot_writes_nothing_for_the_pdf_state(self):
        self.org.snapshot()
        before = self.store.conn.total_changes
        self.pdf_states()
        self.assertEqual(self.store.conn.total_changes, before)


if __name__ == "__main__":
    unittest.main()


class SnapshotBaiduPageTests(unittest.TestCase):
    """A paper only Baidu Scholar reported gets its Baidu page as the link; other papers' snapshot is unchanged."""

    PAGE = "https://xueshu.baidu.com/usercenter/paper/show?paperid=p1"

    def test_the_baidu_page_is_the_link_only_when_nothing_else_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "library.sqlite")
            store.init()
            oa = {"pages": [{"source": "baidu_scholar", "url": self.PAGE}], "via": ["baidu_scholar"]}
            store.upsert_papers([{"key": "baidu:p1", "title": "百度论文", "abstract": "x", "oa": oa},
                                 {"key": "doi", "title": "Has a DOI", "abstract": "x", "doi": "https://doi.org/10.1/x", "oa": oa},
                                 {"key": "plain", "title": "Nothing", "abstract": "x"}])
            for key in ("baidu:p1", "doi", "plain"):
                store.save_to_library(key)
            items = {p["key"]: p for p in Organization(store).snapshot()["items"]}
            store.close()
        self.assertEqual(items["baidu:p1"]["url"], self.PAGE)
        self.assertEqual(items["baidu:p1"]["pdf"], "page")
        self.assertNotIn("url", items["doi"])
        self.assertNotIn("url", items["plain"])
