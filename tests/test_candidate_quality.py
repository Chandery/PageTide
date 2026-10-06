"""Route Mode slice 1: candidates for non-AI fields should be recent enough and say whether a PDF is available.

Reported: topics such as 半导体生长 returned very old papers with no legal PDF route, unlike the AI topics.
"""
import datetime
import io
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recommendation_fixtures import english_papers
from app import creation, server, sources
from app.service import App

DIRECT = {"is_oa": True, "pdf_urls": ["https://repo.example.org/p.pdf"], "landing_page": "https://doi.org/10.1/x"}
PAGE_ONLY = {"is_oa": True, "pdf_urls": [], "landing_page": "https://doi.org/10.1/y"}


def paper(n, oa=None, arxiv=None):
    return {"key": f"k{n}", "title": f"Paper {n}", "oa": oa, "arxiv_id": arxiv, "openalex_id": f"W{n}", "doi": ""}


class AvailabilityTests(unittest.TestCase):
    def test_an_arxiv_paper_or_a_direct_link_is_direct(self):
        self.assertEqual(sources.pdf_availability("2603.19312", None), "direct")
        self.assertEqual(sources.pdf_availability(None, DIRECT), "direct")

    def test_an_open_access_landing_page_only_is_page(self):
        self.assertEqual(sources.pdf_availability(None, PAGE_ONLY), "page")

    def test_nothing_known_is_none(self):
        for oa in (None, {}, {"is_oa": False, "pdf_urls": [], "landing_page": None}, "", "{not json", "null"):
            self.assertEqual(sources.pdf_availability(None, oa), "none", repr(oa))

    def test_the_stored_json_form_is_accepted(self):
        self.assertEqual(sources.pdf_availability(None, json.dumps(DIRECT)), "direct")
        self.assertEqual(sources.pdf_availability("", json.dumps(PAGE_ONLY)), "page")

    def test_a_non_https_landing_page_does_not_count(self):
        self.assertEqual(sources.pdf_availability(None, {"pdf_urls": [], "landing_page": "http://insecure.example.org/x"}), "none")

    def test_creation_papers_carry_their_status(self):
        self.assertEqual(creation.paper_view(paper(1, DIRECT))["pdf_status"], "direct")
        self.assertEqual(creation.paper_view(paper(2, PAGE_ONLY))["pdf_status"], "page")
        self.assertEqual(creation.paper_view(paper(3))["pdf_status"], "none")


class WindowTests(unittest.TestCase):
    def test_window_start_is_relative_and_handles_leap_day(self):
        self.assertEqual(sources.window_start(10, today=datetime.date(2026, 10, 5)), "2016-10-05")
        self.assertEqual(sources.window_start(5, today=datetime.date(2028, 2, 29)), "2023-02-28")


class Router:
    def __init__(self, results):
        self.results, self.urls = results, []

    def __call__(self, request, timeout=None):
        self.urls.append(request.full_url)
        reply = mock.MagicMock()
        reply.__enter__.return_value = reply
        reply.read.return_value = json.dumps({"results": self.results}).encode()
        reply.headers = {}
        return reply


def oa_work(n, direct):
    work = {"id": f"https://openalex.org/W{n}", "doi": f"https://doi.org/10.1/{n}", "title": f"Topic paper {n}",
            "publication_date": "2025-01-01", "ids": {}}
    if direct:
        work["best_oa_location"] = {"pdf_url": f"https://repo.example.org/{n}.pdf"}
        work["open_access"] = {"is_oa": True}
    return work


class OrderingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.client = sources.OpenAlex(tmp.name)
        mock.patch.object(sources.time, "sleep").start()
        self.addCleanup(mock.patch.stopall)

    def run_topic(self, works, **kw):
        with mock.patch.object(sources.urllib.request, "urlopen", Router(works)):
            return self.client.discover_topic("semiconductor growth", per_page=12, **kw)

    def ids(self, papers):
        return [int(p["openalex_id"].rsplit("W", 1)[-1]) for p in papers]

    def test_direct_pdf_comes_first_within_each_block_of_six_only(self):
        # 1..12 in relevance order; direct links are 3, 5 and 8, 11.
        works = [oa_work(n, n in (3, 5, 8, 11)) for n in range(1, 13)]
        got = self.ids(self.run_topic(works))
        self.assertEqual(got[:6], [3, 5, 1, 2, 4, 6])      # block one: direct first, relevance order kept inside
        self.assertEqual(got[6:], [8, 11, 7, 9, 10, 12])   # block two likewise; nothing crosses a block
        self.assertEqual(sorted(got), list(range(1, 13)))   # nothing is dropped

    def test_arxiv_papers_count_as_direct(self):
        works = [oa_work(1, False), {**oa_work(2, False), "ids": {"arxiv": "2603.00001"}}]
        self.assertEqual(self.ids(self.run_topic(works)), [2, 1])

    def test_recent_order_keeps_dates_and_is_not_regrouped(self):
        works = [oa_work(n, n == 3) for n in range(1, 7)]
        self.assertEqual(self.ids(self.run_topic(works, order="recent")), [1, 2, 3, 4, 5, 6])

    def test_opting_out_keeps_pure_relevance(self):
        works = [oa_work(n, n == 3) for n in range(1, 7)]
        self.assertEqual(self.ids(self.run_topic(works, prefer_pdf=False)), [1, 2, 3, 4, 5, 6])


class ServiceWindowTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "harness").mkdir()
        (self.root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (self.root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        self.app = App(root=str(self.root), data_dir=str(self.root / "data"))
        self.addCleanup(self.app.store.close)

    def session(self):
        return self.app.create_guidance_session("半导体生长", "semiconductor growth")["id"]

    def test_creation_search_defaults_to_the_last_ten_years(self):
        with mock.patch.object(self.app.source, "discover_topic", return_value=[]) as topic:
            self.app.guidance_search(self.session(), "semiconductor growth")
        self.assertEqual(topic.call_args.kwargs["from_date"], sources.window_start(10))

    def test_all_years_removes_the_bound(self):
        with mock.patch.object(self.app.source, "discover_topic", return_value=[]) as topic:
            self.app.guidance_search(self.session(), "semiconductor growth", all_years=True)
        self.assertIsNone(topic.call_args.kwargs["from_date"])

    def test_refresh_defaults_to_a_relative_five_year_window_not_a_fixed_date(self):
        project = self.app.create_project("p", "manual", ["epitaxy"])["project_id"]
        with mock.patch.object(self.app.source, "discover_topic", return_value=[]) as topic:
            self.app.refresh_candidates(project_id=project)
        self.assertEqual(topic.call_args.kwargs["from_date"], sources.window_start(5))
        with mock.patch.object(self.app.source, "discover", return_value=[]) as legacy:
            self.app.refresh_candidates()
        self.assertEqual(legacy.call_args.kwargs["from_date"], sources.window_start(5))

    def test_an_explicit_refresh_window_is_honoured(self):
        project = self.app.create_project("p", "manual", ["epitaxy"])["project_id"]
        with mock.patch.object(self.app.source, "discover_topic", return_value=[]) as topic:
            self.app.refresh_candidates(project_id=project, from_date="2020-01-01")
        self.assertEqual(topic.call_args.kwargs["from_date"], "2020-01-01")

    def test_recommendation_cards_carry_the_pdf_status(self):
        project = self.app.create_project("p", "manual", ["epitaxy"])["project_id"]
        self.app.store.upsert_papers([
            {"key": "a", "title": "epitaxy growth direct", "abstract": "epitaxy", "published": "2026-01-01", "oa": DIRECT},
            {"key": "b", "title": "epitaxy growth page", "abstract": "epitaxy", "published": "2026-01-02", "oa": PAGE_ONLY},
            {"key": "c", "title": "epitaxy growth none", "abstract": "epitaxy", "published": "2026-01-03"}], project_id=project)
        english_papers(self.app, project)
        cards = {c["key"]: c["pdf_status"] for c in self.app.build_batch(limit=5, project_id=project)["cards"]}
        self.assertEqual(cards, {"a": "direct", "b": "page", "c": "none"})


class RouteAndPageTests(unittest.TestCase):
    def test_the_search_route_passes_all_years_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "harness").mkdir()
            (root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
            (root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
            httpd = server.build_server(port=0, root=str(root))
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            self.addCleanup(httpd.server_close)
            self.addCleanup(httpd.shutdown)
            seen = {}

            def fake(self_, session_id, query, all_years=False):
                seen.update(session_id=session_id, query=query, all_years=all_years)
                return {"items": [], "total": 0, "error": None, "query": query}
            with mock.patch.object(App, "guidance_search", fake):
                for flag in (True, False):
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{httpd.server_address[1]}/api/project-guidance/sessions/s1/search",
                        data=json.dumps({"query": "q", "all_years": flag}).encode(), headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(request, timeout=5).read()
                    self.assertEqual(seen["all_years"], flag)

    def test_pages_have_the_toggle_and_the_badges(self):
        creation_html = (ROOT / "app/static/project_creation.html").read_text(encoding="utf-8")
        creation_js = (ROOT / "app/static/project-creation.js").read_text(encoding="utf-8")
        index = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
        self.assertIn('data-role="allYears"', creation_html)
        self.assertIn("all_years", creation_js)
        self.assertIn("pdf_status", creation_js)
        self.assertIn("pdf_status", index)
        for text in ("直链 PDF", "仅原文页", "无 PDF 来源"):
            self.assertIn(text, creation_js)
            self.assertIn(text, index)


if __name__ == "__main__":
    unittest.main()
