"""PDF routes of a paper: the order they are tried in, which count as a source, and what the reader is told when none works.

Offline only: the network seam of pdf_fetch and OpenAlex's work lookup are replaced.
"""
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_pdf_fetch import PDF, Net  # the fake network seam and a minimal valid PDF the PDF tests already use
DOI = "https://doi.org/10.1234/kg.2024.001"
BAIDU_PAGE = "https://xueshu.baidu.com/usercenter/paper/show?paperid=synthetic-p1"
OPENALEX_LANDING = "https://repo.example.org/kg"
WORK = {"id": "https://openalex.org/W42", "doi": DOI, "title": "t", "publication_date": "2024-03-01", "type": "article", "language": "zh",
        "ids": {}, "open_access": {"is_oa": True, "oa_status": "green", "oa_url": "https://repo.example.org/kg.pdf"},
        "best_oa_location": {"pdf_url": "https://repo.example.org/kg.pdf", "landing_page_url": OPENALEX_LANDING, "license": "cc-by",
                             "version": "publishedVersion"}}


class RoutesTests(unittest.TestCase):
    def setUp(self):
        from app import source_adapters, sources
        self.sa, self.sources = source_adapters, sources

    FULL = {"arxiv_id": "2603.19312", "doi": DOI,
            "oa": {"is_oa": True, "pdf_urls": ["https://repo.example.org/kg.pdf", "http://insecure.example.org/x.pdf"],
                   "landing_page": OPENALEX_LANDING, "pages": [{"source": "baidu_scholar", "url": BAIDU_PAGE}], "via": ["baidu_scholar"]}}

    def test_the_order_is_arxiv_pdf_links_landing_source_page_publisher(self):
        routes = self.sa.pdf_routes(self.FULL)
        self.assertEqual([r["kind"] for r in routes], ["arxiv_pdf", "oa_pdf", "landing", "source_page", "publisher_page"])
        self.assertEqual([r["auto"] for r in routes], [True, True, False, False, False])
        self.assertEqual([r["needs_login"] for r in routes], [False, False, False, True, True])
        self.assertEqual(routes[3]["url"], BAIDU_PAGE)
        self.assertEqual(routes[4]["url"], DOI)
        for route in routes:
            self.assertEqual(set(route), {"kind", "url", "auto", "needs_login", "label"})
            self.assertTrue(route["url"].startswith("https://"))

    def test_only_https_and_pages_on_the_sources_own_domain(self):
        paper = {"oa": {"pages": [{"source": "baidu_scholar", "url": "https://evil.example/x"}, {"source": "baidu_scholar", "url": "http://xueshu.baidu.com/y"},
                                  {"source": "baidu_scholar", "url": "https://baidu.com.evil.example/z"}, {"source": "unknown", "url": "https://xueshu.baidu.com/w"},
                                  {"source": "baidu_scholar", "url": "https://user:pw@xueshu.baidu.com/v"}, "junk", {"url": BAIDU_PAGE}],
                       "pdf_urls": ["http://insecure.example.org/x.pdf", None, 5]}, "doi": "not a doi"}
        self.assertEqual(self.sa.pdf_routes(paper), [])

    def test_a_publisher_page_needs_a_real_doi_and_is_not_repeated(self):
        self.assertEqual([r["kind"] for r in self.sa.pdf_routes({"doi": "10.1234/kg"})], ["publisher_page"])
        self.assertEqual(self.sa.pdf_routes({"doi": "10.1234/kg"})[0]["url"], "https://doi.org/10.1234/kg")
        same = {"doi": DOI, "oa": {"landing_page": DOI}}
        self.assertEqual([r["kind"] for r in self.sa.pdf_routes(same)], ["landing"])

    def test_routes_read_the_stored_text_too(self):
        paper = {k: v for k, v in self.FULL.items() if k != "oa"}
        paper["oa_json"] = json.dumps(self.FULL["oa"])
        self.assertEqual([r["kind"] for r in self.sa.pdf_routes(paper)], ["arxiv_pdf", "oa_pdf", "landing", "source_page", "publisher_page"])
        self.assertEqual(self.sa.pdf_routes({"oa_json": "{broken"}), [])

    def test_availability_is_derived_from_the_routes(self):
        pa = self.sources.pdf_availability
        self.assertEqual(pa("2603.19312", None), "direct")
        self.assertEqual(pa(None, {"pdf_urls": ["https://a.example/p.pdf"]}), "direct")
        self.assertEqual(pa(None, {"pdf_urls": [], "landing_page": "https://a.example/l"}), "page")
        self.assertEqual(pa(None, {"pages": [{"source": "baidu_scholar", "url": BAIDU_PAGE}], "via": ["baidu_scholar"]}), "page")
        self.assertEqual(pa(None, json.dumps({"pages": [{"source": "baidu_scholar", "url": BAIDU_PAGE}]})), "page")
        self.assertEqual(pa(None, {"pages": [{"source": "baidu_scholar", "url": "https://evil.example/x"}]}), "none")
        self.assertEqual(pa(None, {"pages": [{"source": "baidu_scholar", "url": "http://xueshu.baidu.com/x"}]}), "none")
        self.assertEqual(pa(None, None), "none")
        self.assertEqual(pa(None, {"is_oa": False}), "none")

    def test_a_bare_doi_is_not_a_pdf_source(self):
        from app import eligibility
        self.assertFalse(eligibility.has_pdf_source({"doi": DOI, "oa_json": None}))
        self.assertTrue(eligibility.has_pdf_source({"doi": DOI, "oa_json": json.dumps({"pages": [{"source": "baidu_scholar", "url": BAIDU_PAGE}]})}))

    def test_a_baidu_page_is_never_a_download_candidate(self):
        from app import pdf_fetch
        paper = {"oa_json": json.dumps({"pages": [{"source": "baidu_scholar", "url": BAIDU_PAGE}], "pdf_urls": []})}
        self.assertEqual(pdf_fetch.candidates(paper), [])

    def test_paper_url_prefers_arxiv_then_doi_then_openalex_then_the_baidu_page(self):
        url = self.sa.paper_url
        baidu = {"pages": [{"source": "baidu_scholar", "url": BAIDU_PAGE}]}
        self.assertEqual(url({"arxiv_id": "2603.19312", "doi": DOI, "openalex_id": "https://openalex.org/W1", "oa": baidu}), "https://arxiv.org/abs/2603.19312")
        self.assertEqual(url({"doi": DOI, "openalex_id": "https://openalex.org/W1", "oa": baidu}), DOI)
        self.assertEqual(url({"openalex_id": "https://openalex.org/W1", "oa": baidu}), "https://openalex.org/W1")
        self.assertEqual(url({"oa_json": json.dumps(baidu)}), BAIDU_PAGE)
        self.assertIsNone(url({}))
        self.assertEqual(url({"doi": "10.1/x", "oa": baidu}, doi_must_be_link=True), BAIDU_PAGE)


class AppCase(unittest.TestCase):
    def setUp(self):
        from app import pdf_fetch
        from app.service import App
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "harness").mkdir()
        (root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (root / "app").mkdir(exist_ok=True)
        (root / "app" / "budget.json").write_text((ROOT / "app" / "budget.json").read_text())
        self.pdf_fetch = pdf_fetch
        self.app = App(root=str(root), data_dir=str(root / "data"))
        self.addCleanup(self.app.store.close)
        self.app.projects.create_project("Test project", "manual", [])   # a fresh app has no project
        mock.patch.object(pdf_fetch.time, "sleep").start()
        self.addCleanup(mock.patch.stopall)

    def add(self, **paper):
        base = {"key": "k", "title": "T"}
        base.update(paper)
        self.app.store.upsert_papers([base])
        return base["key"]

    def baidu_only(self, **extra):
        return self.add(doi=DOI, oa={"pages": [{"source": "baidu_scholar", "url": BAIDU_PAGE}], "via": ["baidu_scholar"]}, **extra)

    def download(self, net, key="k", **kw):
        with mock.patch.object(self.pdf_fetch, "_open", net):
            return self.app.download_pdf(key, **kw)

    def stored_oa(self):
        return json.loads(self.app.store.paper("k")["oa_json"] or "null")


class DownloadTests(AppCase):
    def test_a_baidu_paper_with_a_doi_asks_openalex_once_and_downloads(self):
        self.baidu_only()
        net = Net({"https://repo.example.org/kg.pdf": PDF})
        with mock.patch.object(self.app.source, "work", return_value=WORK) as work:
            result = self.download(net)
        work.assert_called_once_with(DOI)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source_kind"], "openalex_oa")
        oa = self.stored_oa()
        self.assertEqual(oa["pdf_urls"], ["https://repo.example.org/kg.pdf"])
        self.assertEqual(oa["pages"][0]["source"], "baidu_scholar")             # the Baidu page survives the merge

    def test_the_lookup_uses_the_openalex_id_when_there_is_one(self):
        self.baidu_only(openalex_id="https://openalex.org/W42")
        with mock.patch.object(self.app.source, "work", return_value=WORK) as work:
            self.download(Net({"https://repo.example.org/kg.pdf": PDF}))
        work.assert_called_once_with("https://openalex.org/W42")

    def test_no_second_lookup_once_openalex_facts_are_stored(self):
        self.add(doi=DOI, oa={"is_oa": False, "pdf_urls": [], "landing_page": None, "license": None, "version": None,
                              "pages": [{"source": "baidu_scholar", "url": BAIDU_PAGE}]})
        with mock.patch.object(self.app.source, "work", side_effect=AssertionError("facts are already known")):
            result = self.download(Net({}))
        self.assertFalse(result["ok"])

    def test_no_lookup_without_a_doi_or_an_openalex_id(self):
        self.add(oa={"pages": [{"source": "baidu_scholar", "url": BAIDU_PAGE}]})
        with mock.patch.object(self.app.source, "work", side_effect=AssertionError("nothing to ask about")):
            result = self.download(Net({}))
        self.assertEqual(result["pages"], [{"kind": "source_page", "label": "百度学术", "url": BAIDU_PAGE, "needs_login": True}])

    def test_the_lookup_fills_an_unknown_language_but_never_replaces_one(self):
        self.baidu_only()
        with mock.patch.object(self.app.source, "work", return_value=WORK):
            self.download(Net({"https://repo.example.org/kg.pdf": PDF}))
        row = self.app.store.paper("k")
        self.assertEqual((row["metadata_language"], row["metadata_language_source"]), ("zh", "OpenAlex"))
        self.app.store.conn.execute("UPDATE papers SET metadata_language='en', oa_json=NULL WHERE key='k'")
        self.app.store.conn.commit()
        with mock.patch.object(self.app.source, "work", return_value=WORK):
            self.download(Net({"https://repo.example.org/kg.pdf": PDF}), refresh=True)
        self.assertEqual(self.app.store.paper("k")["metadata_language"], "en")

    def test_offline_still_returns_the_pages_in_order_with_a_reason(self):
        self.baidu_only()
        with mock.patch.object(self.app.source, "work", side_effect=self.sources_error()):
            result = self.download(Net({}))
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "landing_page_only")
        self.assertEqual([p["kind"] for p in result["pages"]], ["source_page", "publisher_page"])
        self.assertEqual([p["url"] for p in result["pages"]], [BAIDU_PAGE, DOI])
        self.assertIsNone(result["landing_page"])

    def sources_error(self):
        from app import sources
        return sources.SourceError("OpenAlex: network_error", "network_error")

    def test_failure_pages_are_baidu_then_openalex_landing_then_publisher(self):
        self.baidu_only()
        work = dict(WORK, best_oa_location={**WORK["best_oa_location"], "pdf_url": None}, open_access={"is_oa": True, "oa_status": "green", "oa_url": None},
                    locations=[])
        with mock.patch.object(self.app.source, "work", return_value=work):
            result = self.download(Net({}))
        self.assertEqual([p["kind"] for p in result["pages"]], ["source_page", "landing", "publisher_page"])
        self.assertEqual([p["url"] for p in result["pages"]], [BAIDU_PAGE, OPENALEX_LANDING, DOI])
        self.assertEqual([p["needs_login"] for p in result["pages"]], [True, False, True])
        self.assertEqual(result["landing_page"], OPENALEX_LANDING)                  # older callers keep their field
        self.assertEqual(result["reason"], "landing_page_only")
        self.assertEqual({p["label"] for p in result["pages"]}, {"百度学术", "原文页面", "出版方"})

    def test_a_failed_download_keeps_its_own_reason_and_still_lists_pages(self):
        self.baidu_only()
        url = "https://repo.example.org/kg.pdf"
        with mock.patch.object(self.app.source, "work", return_value=WORK):
            result = self.download(Net({url: urllib.error.HTTPError(url, 403, "no", {}, None)}))
        self.assertEqual(result["reason"], "paywalled_or_blocked")
        self.assertEqual([p["kind"] for p in result["pages"]], ["source_page", "landing", "publisher_page"])

    def test_without_any_page_the_reason_is_still_no_oa_source(self):
        self.add()
        result = self.download(Net({}))
        self.assertEqual((result["reason"], result["pages"], result["landing_page"]), ("no_oa_source", [], None))

    def test_the_english_interface_gets_english_labels(self):
        self.baidu_only()
        (self.app.data / "settings.json").write_text(json.dumps({"language": "en-US"}))
        with mock.patch.object(self.app.source, "work", side_effect=self.sources_error()):
            result = self.download(Net({}))
        self.assertEqual([p["label"] for p in result["pages"]], ["Baidu Scholar", "Publisher"])

    def test_pages_on_other_hosts_are_never_offered(self):
        self.add(doi=DOI, oa={"is_oa": True, "pdf_urls": [], "landing_page": "http://insecure.example.org/p",
                              "pages": [{"source": "baidu_scholar", "url": "https://evil.example/x"}]})
        result = self.download(Net({}))
        self.assertEqual([p["kind"] for p in result["pages"]], ["publisher_page"])

    def test_a_cached_pdf_is_returned_without_any_lookup(self):
        self.baidu_only()
        with mock.patch.object(self.app.source, "work", return_value=WORK):
            self.download(Net({"https://repo.example.org/kg.pdf": PDF}))
        with mock.patch.object(self.app.source, "work", side_effect=AssertionError("cached")):
            result = self.download(Net({}))
        self.assertTrue(result["ok"] and result["cached"])


class LinkTests(AppCase):
    def test_detail_library_and_creation_view_end_with_the_baidu_page_as_the_link(self):
        from app import creation
        key = self.add(oa={"pages": [{"source": "baidu_scholar", "url": BAIDU_PAGE}], "via": ["baidu_scholar"]})
        self.assertEqual(self.app.paper_detail(key)["url"], BAIDU_PAGE)
        self.app.store.save_to_library(key)
        self.assertEqual([item["url"] for item in self.app.library()], [BAIDU_PAGE])
        self.assertEqual(creation.paper_view(self.app.store.paper(key))["url"], BAIDU_PAGE)
        self.assertEqual(creation.paper_view(self.app.store.paper(key))["pdf_status"], "page")

    def test_a_doi_or_arxiv_link_still_wins(self):
        from app import creation
        key = self.add(doi=DOI, oa={"pages": [{"source": "baidu_scholar", "url": BAIDU_PAGE}]})
        self.assertEqual(self.app.paper_detail(key)["url"], DOI)
        self.assertEqual(creation.paper_view(self.app.store.paper(key))["url"], DOI)
        self.add(key="a", arxiv_id="2603.19312", oa={"pages": [{"source": "baidu_scholar", "url": BAIDU_PAGE}]})
        self.assertEqual(self.app.paper_detail("a")["url"], "https://arxiv.org/abs/2603.19312")


class CompatibilityTests(AppCase):
    def test_the_old_landing_page_rules_for_an_openalex_only_paper(self):
        self.add(oa={"is_oa": True, "oa_status": "hybrid", "pdf_urls": [], "landing_page": "https://doi.org/10.1038/x", "license": "cc-by", "version": "publishedVersion"})
        result = self.download(Net({}))
        self.assertEqual((result["ok"], result["reason"], result["landing_page"]), (False, "landing_page_only", "https://doi.org/10.1038/x"))
        self.assertEqual([p["kind"] for p in result["pages"]], ["landing"])


if __name__ == "__main__":
    unittest.main()
