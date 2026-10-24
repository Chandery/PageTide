"""Daily feed with Baidu Scholar: who may call it, how often, DOI enrichment, language and eligibility. Offline only.

urlopen is replaced by a router that answers Baidu's Qianfan host from the synthetic fixtures (their field names are
UNVERIFIED) and OpenAlex from a list, and records every request. The key is a dummy value.
"""
import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURES = ROOT / "tests" / "fixtures" / "baidu_scholar"
KEY = "bce-v3/ALTAK-dummyDummy0000/dummydummydummydummy0000"
KEYWORDS = ["知识图谱", "信息抽取", "本体构建", "数字人文", "knowledge graph"]
DOI_1 = "https://doi.org/10.1234/kg.2024.001"
DOI_4 = "https://doi.org/10.5555/other.4"


def fixture(name):
    return (FIXTURES / name).read_bytes()


class Reply:
    def __init__(self, body):
        self.body, self.headers = body, {}

    def read(self, limit=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def openalex_work(n, doi, language="zh", pdf="https://repo.example.org/kg.pdf"):
    return {"id": f"https://openalex.org/W{n}", "doi": doi, "title": f"OpenAlex title {n}", "publication_date": "2024-03-01",
            "type": "article", "language": language, "ids": {},
            "open_access": {"is_oa": True, "oa_status": "green", "oa_url": pdf},
            "best_oa_location": {"pdf_url": pdf, "landing_page_url": "https://repo.example.org/kg", "license": "cc-by", "version": "publishedVersion"}}


class Net:
    """Routes Baidu and OpenAlex requests, records both."""

    def __init__(self):
        self.baidu, self.openalex = [], []
        self.baidu_answer = fixture("success.json")
        self.baidu_by_page = {}
        self.openalex_doi_results = []
        self.openalex_error = None
        self.baidu_error = None

    def wd(self, request):
        return urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)

    def __call__(self, request, timeout=None):
        url = request.full_url
        if "qianfan.baidubce.com" in url:
            query = self.wd(request)
            self.baidu.append({"wd": query["wd"][0], "page": int(query["pageNum"][0]), "auth": request.get_header("Authorization")})
            if self.baidu_error:
                raise self.baidu_error
            return Reply(self.baidu_by_page.get(int(query["pageNum"][0]), self.baidu_answer))
        if "api.openalex.org" in url:
            self.openalex.append(url)
            if "doi%3A" in url or "filter=doi:" in url:
                if self.openalex_error:
                    raise self.openalex_error
                return Reply(json.dumps({"results": self.openalex_doi_results}).encode())
            return Reply(json.dumps({"results": []}).encode())
        raise AssertionError("unexpected request: " + url)

    def doi_requests(self):
        return [u for u in self.openalex if "doi%3A" in u or "filter=doi:" in u]


class RefreshCase(unittest.TestCase):
    def setUp(self):
        from tests.recommendation_fixtures import set_user_settings
        self.set_user_settings = set_user_settings
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "harness").mkdir()
        (self.root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (self.root / "app").mkdir(exist_ok=True)
        (self.root / "app" / "budget.json").write_text((ROOT / "app" / "budget.json").read_text())
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("OPENALEX_API_KEY", "BAIDU_SCHOLAR_API_KEY"):
            os.environ.pop(name, None)
        sleeper = mock.patch("time.sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)
        from app.service import App
        self.app = App(root=str(self.root), data_dir=str(self.root / "data"))
        self.addCleanup(self.app.store.close)
        self.set_user_settings(self.app, timePreference="all", sourceBaiduScholar=True)
        self.app.save_source_key("baidu_scholar", KEY)
        self.pid = self.app.create_project("知识图谱", "manual", KEYWORDS)["project_id"]
        self.app.set_project_language(self.pid, None, ["zh"])
        self.net = Net()
        day = mock.patch.object(type(self.app), "batch_day", lambda s: self.today)
        self.today = "2026-10-23"
        day.start()
        self.addCleanup(day.stop)

    def refresh(self, **kwargs):
        with mock.patch.object(urllib.request, "urlopen", self.net):
            return self.app.refresh_candidates(project_id=self.pid, **kwargs)

    def stored(self, key):
        return self.app.store.paper(key)


class CallPolicyTests(RefreshCase):
    def test_a_chinese_project_with_chinese_keywords_calls_baidu_with_at_most_three(self):
        result = self.refresh()
        self.assertEqual([c["wd"] for c in self.net.baidu], ["知识图谱", "信息抽取", "本体构建"])
        self.assertEqual({c["auth"] for c in self.net.baidu}, {f"Bearer {KEY}"})
        self.assertEqual(result["errors"], [])
        self.assertGreater(result["fetched"], 0)
        self.assertIsNotNone(self.stored(DOI_1))
        self.assertIsNotNone(self.stored("baidu:synthetic-p2"))

    def test_only_keywords_with_chinese_characters_are_sent(self):
        other = self.app.create_project("mixed", "manual", ["knowledge graph", "world model", "世界模型"])["project_id"]
        self.app.set_project_language(other, None, ["zh", "en"])
        with mock.patch.object(urllib.request, "urlopen", self.net):
            self.app.refresh_candidates(project_id=other)
        self.assertEqual([c["wd"] for c in self.net.baidu], ["世界模型"])

    def test_english_only_project_never_calls_baidu(self):
        self.app.set_project_language(self.pid, None, ["en"])
        self.refresh()
        self.assertEqual(self.net.baidu, [])

    def test_a_project_without_a_language_choice_never_calls_baidu(self):
        pending = self.app.create_project("pending", "manual", ["知识图谱"])["project_id"]
        with mock.patch.object(urllib.request, "urlopen", self.net):
            self.app.refresh_candidates(project_id=pending)
        self.assertEqual(self.net.baidu, [])

    def test_switch_off_means_zero_calls(self):
        self.set_user_settings(self.app, sourceBaiduScholar=False)
        self.refresh()
        self.assertEqual(self.net.baidu, [])
        self.set_user_settings(self.app, sourceBaiduScholar="yes")
        self.refresh()
        self.assertEqual(self.net.baidu, [])

    def test_no_key_means_zero_calls_and_no_error(self):
        self.app.clear_source_key("baidu_scholar")
        result = self.refresh()
        self.assertEqual(self.net.baidu, [])
        self.assertEqual([e for e in result["errors"] if e.get("source") == "baidu_scholar"], [])

    def test_no_chinese_keyword_means_zero_calls(self):
        english = self.app.create_project("english words", "manual", ["knowledge graph"])["project_id"]
        self.app.set_project_language(english, None, ["zh", "en"])
        with mock.patch.object(urllib.request, "urlopen", self.net):
            self.app.refresh_candidates(project_id=english)
        self.assertEqual(self.net.baidu, [])

    def test_an_explicit_search_and_the_default_recipe_do_not_call_baidu(self):
        self.refresh(search="知识图谱")
        self.assertEqual(self.net.baidu, [])

    def test_the_learning_map_refresh_does_not_call_baidu(self):
        # Left out on purpose: that refresh plans its own queries (see ADR 0039). This records that it is out of reach.
        self.set_user_settings(self.app, routeBeta=True)
        with mock.patch.object(self.app, "_refresh_route_candidates", return_value={"fetched": 0, "added": 0, "field": 0, "errors": []}) as route, \
                mock.patch.object(self.app, "_route_state", return_value={"graph": {}}):
            self.refresh()
        route.assert_called_once()
        self.assertEqual(self.net.baidu, [])

    def test_baidu_alone_is_enough_when_the_openalex_sources_are_off(self):
        self.set_user_settings(self.app, sourceArxiv=False, sourceOpenAlex=False)
        result = self.refresh()
        self.assertEqual(len(self.net.baidu), 3)
        self.assertEqual(self.net.openalex, [])                  # not even the DOI lookup: the user switched OpenAlex's sources off
        self.assertGreater(result["fetched"], 0)

    def test_with_only_baidu_on_neither_the_distractor_probe_nor_the_learning_map_refresh_reaches_openalex(self):
        self.set_user_settings(self.app, sourceArxiv=False, sourceOpenAlex=False)
        with mock.patch.object(self.app.source, "distractors", side_effect=AssertionError("OpenAlex is switched off")):
            result = self.refresh(include_distractors=True)
        self.assertEqual(self.net.openalex, [])
        self.assertGreater(result["fetched"], 0)
        self.net.baidu.clear()
        self.set_user_settings(self.app, routeBeta=True)
        with mock.patch.object(self.app, "_refresh_route_candidates", side_effect=AssertionError("no OpenAlex source is on")), \
                mock.patch.object(self.app, "_route_state", return_value={"graph": {}}):
            result = self.refresh()
        self.assertEqual(result["reason_code"], "sources_disabled")
        self.assertEqual(self.net.baidu, [])

    def test_everything_off_is_still_sources_disabled(self):
        self.set_user_settings(self.app, sourceArxiv=False, sourceOpenAlex=False, sourceBaiduScholar=False)
        result = self.refresh()
        self.assertEqual(result["reason_code"], "sources_disabled")
        self.assertEqual((self.net.baidu, self.net.openalex), ([], []))


class CursorTests(RefreshCase):
    def test_the_page_rotates_once_a_day_per_keyword(self):
        pages = []
        for day in ("2026-10-23", "2026-10-23", "2026-10-24", "2026-10-25"):
            self.today = day
            self.net.baidu.clear()
            self.refresh()
            pages.append(sorted({c["page"] for c in self.net.baidu}))
        self.assertEqual(pages, [[0], [], [1], [2]])        # the second refresh of a day is answered from the cache

    def test_the_cycle_has_five_pages_and_an_empty_page_starts_over(self):
        seen = []
        for n in range(7):
            self.today = (datetime.date(2026, 10, 23) + datetime.timedelta(days=n)).isoformat()
            self.net.baidu.clear()
            shutil.rmtree(self.root / "data" / "cache" / "baidu_scholar", ignore_errors=True)    # days apart: no cached answer is reused
            self.refresh()
            seen.append(sorted({c["page"] for c in self.net.baidu}))
        self.assertEqual(seen, [[0], [1], [2], [3], [4], [0], [1]])
        self.net.baidu_by_page = {3: fixture("empty.json")}
        self.app.store.set_setting("baidu_cursor_" + self.pid, {})
        seen = []
        for n in range(5):
            self.today = (datetime.date(2026, 11, 10) + datetime.timedelta(days=n)).isoformat()
            self.net.baidu.clear()
            shutil.rmtree(self.root / "data" / "cache" / "baidu_scholar", ignore_errors=True)
            self.refresh()
            seen.append(sorted({c["page"] for c in self.net.baidu}))
        self.assertEqual(seen, [[0], [1], [2], [3], [0]])   # page 3 came back empty: the next day starts at the first page

    def test_a_page_whose_papers_are_all_too_old_is_not_an_empty_page(self):
        # Baidu has no date sort: a later page often holds only old papers. They are filtered out by the time window, but the
        # page itself was not empty, so the cursor still moves on instead of falling back to page 1 for ever.
        self.set_user_settings(self.app, timePreference="month")
        pages = []
        for n in range(4):
            self.today = (datetime.date(2026, 10, 23) + datetime.timedelta(days=n)).isoformat()
            self.net.baidu.clear()
            shutil.rmtree(self.root / "data" / "cache" / "baidu_scholar", ignore_errors=True)
            self.refresh()
            pages.append(sorted({c["page"] for c in self.net.baidu}))
        self.assertEqual(pages, [[0], [1], [2], [3]])
        keys = {r[0] for r in self.app.store.conn.execute("SELECT key FROM papers WHERE key LIKE 'baidu:%'")}
        self.assertEqual(keys, {"baidu:synthetic-p3"})                  # only the paper without a year (unknown, so kept) passed the window

    def test_a_cursor_belongs_to_its_keyword_and_project(self):
        self.refresh()
        cursor = self.app.store.get_setting("baidu_cursor_" + self.pid)
        self.assertEqual(set(cursor), {"知识图谱", "信息抽取", "本体构建"})
        self.assertNotIn(KEY, json.dumps(cursor))


class EnrichmentTests(RefreshCase):
    def setUp(self):
        super().setUp()
        self.net.openalex_doi_results = [openalex_work(42, DOI_1)]

    def test_one_batch_with_every_doi_and_nothing_else(self):
        self.refresh()
        requests = self.net.doi_requests()
        self.assertEqual(len(requests), 1)
        flt = urllib.parse.parse_qs(urllib.parse.urlsplit(requests[0]).query)["filter"][0]
        self.assertEqual(sorted(flt[len("doi:"):].split("|")), sorted([DOI_1, DOI_4]))

    def test_openalex_facts_are_merged_into_the_baidu_paper(self):
        self.refresh()
        row = self.stored(DOI_1)
        self.assertEqual(row["openalex_id"], "https://openalex.org/W42")
        self.assertEqual((row["metadata_language"], row["metadata_language_source"]), ("zh", "OpenAlex"))
        oa = json.loads(row["oa_json"])
        self.assertEqual(oa["pdf_urls"], ["https://repo.example.org/kg.pdf"])
        self.assertEqual(oa["pages"][0]["source"], "baidu_scholar")
        self.assertEqual(oa["via"], ["baidu_scholar"])
        self.assertEqual(row["title"], "知识图谱 构建方法综述")        # Baidu's title and abstract stay
        self.assertEqual(row["abstract"], "本文综述知识图谱的构建方法。")

    def test_a_doi_openalex_does_not_know_stays_a_baidu_only_paper(self):
        self.net.openalex_doi_results = [openalex_work(7, DOI_4)]
        self.refresh()
        row = self.stored(DOI_1)
        self.assertIsNone(row["openalex_id"])
        self.assertEqual(json.loads(row["oa_json"])["via"], ["baidu_scholar"])
        self.assertEqual(self.stored(DOI_4)["openalex_id"], "https://openalex.org/W7")

    def test_no_doi_means_no_lookup(self):
        self.net.baidu_answer = json.dumps({"code": "0", "data": [
            {"paperId": "x1", "title": "没有编号的中文论文标题", "abstract": "摘要内容", "doi": "", "keyword": "测试", "publishYear": 2024,
             "publishInfo": {"journalName": "期刊"}, "url": "https://xueshu.baidu.com/p/x1"}]}).encode()
        self.refresh()
        self.assertEqual(self.net.doi_requests(), [])

    def test_a_failed_lookup_keeps_the_baidu_papers_and_reports_it(self):
        self.net.openalex_error = urllib.error.URLError("offline")
        result = self.refresh()
        self.assertIsNotNone(self.stored(DOI_1))
        self.assertIsNone(self.stored(DOI_1)["openalex_id"])
        kinds = [(e.get("source"), e.get("kind")) for e in result["errors"]]
        self.assertIn(("openalex", "network_error"), kinds)
        self.assertGreater(result["fetched"], 0)

    def test_an_existing_openalex_row_keeps_its_language_title_and_abstract(self):
        self.app.store.upsert_papers([{"key": DOI_1, "doi": DOI_1, "openalex_id": "https://openalex.org/W42", "title": "Knowledge graph survey",
                                       "abstract": "An English abstract.", "metadata_language": "en", "metadata_language_source": "OpenAlex",
                                       "oa": {"is_oa": True, "pdf_urls": ["https://repo.example.org/kg.pdf"], "landing_page": None}}],
                                     project_id=self.pid)
        self.net.openalex_doi_results = []
        self.refresh()
        row = self.stored(DOI_1)
        self.assertEqual((row["title"], row["abstract"], row["metadata_language"]), ("Knowledge graph survey", "An English abstract.", "en"))
        oa = json.loads(row["oa_json"])
        self.assertEqual(oa["pdf_urls"], ["https://repo.example.org/kg.pdf"])        # OpenAlex's facts survive
        self.assertEqual(oa["pages"][0]["source"], "baidu_scholar")                    # and the Baidu page is added

    def test_openalex_without_a_language_does_not_erase_one(self):
        self.app.store.upsert_papers([{"key": DOI_1, "title": "t", "metadata_language": "zh", "metadata_language_source": "OpenAlex"}], project_id=self.pid)
        self.net.openalex_doi_results = [openalex_work(42, DOI_1, language=None)]
        self.refresh()
        self.assertEqual(self.stored(DOI_1)["metadata_language"], "zh")

    def test_a_later_lookup_fills_the_openalex_id_of_a_stored_baidu_paper_and_the_switches_follow(self):
        from app import user_settings
        self.net.openalex_doi_results = []
        self.refresh()
        self.assertIsNone(self.stored(DOI_1)["openalex_id"])
        self.net.openalex_doi_results = [openalex_work(42, DOI_1)]
        for cached in (self.root / "data" / "cache").glob("*.json"):            # OpenAlex's answer of the first refresh is cached for days
            cached.unlink()
        self.refresh()
        row = self.stored(DOI_1)
        self.assertEqual(row["openalex_id"], "https://openalex.org/W42")          # an existing row gets the id too
        self.set_user_settings(self.app, sourceBaiduScholar=False, sourceOpenAlex=True)
        self.assertTrue(user_settings.source_allowed(self.app.data, row))
        self.app.store.upsert_papers([{"key": DOI_1, "title": "t", "openalex_id": "https://openalex.org/W99"}])
        self.assertEqual(self.stored(DOI_1)["openalex_id"], "https://openalex.org/W42")      # a stored id is never replaced

    def test_baidu_papers_carry_no_language_before_enrichment(self):
        self.net.openalex_doi_results = []
        self.refresh()
        self.assertIsNone(self.stored("baidu:synthetic-p2")["metadata_language"])
        self.assertIsNone(self.stored(DOI_1)["metadata_language"])


class ErrorTests(RefreshCase):
    def test_a_refused_key_is_reported_once_and_stops_further_calls(self):
        self.net.baidu_error = urllib.error.HTTPError("https://qianfan.baidubce.com/x", 401, "no", {}, None)
        result = self.refresh()
        self.assertEqual(len(self.net.baidu), 1)
        errors = [e for e in result["errors"] if e.get("source") == "baidu_scholar"]
        self.assertEqual([e["kind"] for e in errors], ["auth_required"])
        self.assertNotIn(KEY, json.dumps(result))

    def test_the_local_cap_is_reported_as_quota_and_makes_no_call(self):
        day = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)).date().isoformat()
        self.app.store.conn.execute("INSERT INTO settings(key,value) VALUES(?,?)", ("source_usage:baidu_scholar:" + day, "40"))
        self.app.store.conn.commit()
        result = self.refresh()
        self.assertEqual(self.net.baidu, [])
        self.assertEqual([e["kind"] for e in result["errors"] if e.get("source") == "baidu_scholar"], ["quota_exhausted"])

    def test_an_unreadable_answer_is_an_error_not_a_crash_and_the_next_keyword_is_tried(self):
        self.net.baidu_answer = fixture("html_body.html")
        result = self.refresh()
        self.assertEqual(len(self.net.baidu), 3)
        self.assertEqual({e["kind"] for e in result["errors"] if e.get("source") == "baidu_scholar"}, {"bad_response"})

    def test_a_baidu_failure_does_not_stop_openalex_results_and_maintenance_calls_it_fine(self):
        from app import maintenance
        self.net.baidu_error = urllib.error.HTTPError("https://qianfan.baidubce.com/x", 401, "no", {}, None)
        work = {"id": "https://openalex.org/W7", "doi": "https://doi.org/10.1/en7", "title": "知识图谱 survey", "publication_date": "2025-01-01",
                "type": "article", "ids": {}, "primary_location": {"source": {"display_name": "Journal"}}}
        original = self.net.__call__

        def router(request, timeout=None):
            if "api.openalex.org" in request.full_url and "doi%3A" not in request.full_url and "filter=doi:" not in request.full_url:
                self.net.openalex.append(request.full_url)
                return Reply(json.dumps({"results": [work]}).encode())
            return original(request, timeout)
        with mock.patch.object(urllib.request, "urlopen", router):
            out = maintenance.run(self.app, self.pid)
        self.assertTrue(out["refreshed"])
        self.assertTrue(any(e.get("source") == "baidu_scholar" for e in out["errors"]))
        self.assertIsNotNone(self.stored("https://doi.org/10.1/en7"))


class EligibilityTests(RefreshCase):
    def pool(self, pid=None):
        return {p["key"]: p["_eligibility"] for p in self.app.recommendation_pool(pid or self.pid)}

    def test_a_chinese_project_may_recommend_a_baidu_paper_with_only_a_baidu_page(self):
        self.net.openalex_doi_results = []
        self.refresh()
        verdict = self.pool()[DOI_1]
        self.assertTrue(verdict["eligible"], verdict)
        self.assertEqual(verdict["language"]["metadata_language"], "zh")
        self.assertEqual(verdict["language"]["metadata_source"], "title+abstract")

    def test_the_cards_are_built_and_the_baidu_page_is_the_link(self):
        self.net.openalex_doi_results = []
        self.refresh()
        cards = self.app.build_batch(limit=5, project_id=self.pid)["cards"]
        by_key = {c["key"]: c for c in cards}
        self.assertIn(DOI_1, by_key)
        self.assertEqual(by_key[DOI_1]["pdf_status"], "page")
        self.assertEqual(by_key["baidu:synthetic-p2"]["url"], "https://xueshu.baidu.com/usercenter/paper/show?paperid=synthetic-p2")
        self.assertEqual(by_key[DOI_1]["url"], DOI_1)              # a DOI link beats the Baidu page

    def test_an_english_only_project_excludes_a_chinese_baidu_paper(self):
        self.net.openalex_doi_results = []
        self.refresh()
        english = self.app.create_project("english", "manual", ["knowledge graph"])["project_id"]
        self.app.set_project_language(english, None, ["en"])
        self.app.store.add_project_paper(english, DOI_1, "discovered")
        verdict = self.pool(english)[DOI_1]
        self.assertEqual((verdict["eligible"], verdict["reason"]), (False, "language_not_allowed"))

    def test_a_chinese_only_project_drops_an_english_baidu_paper(self):
        english_abstract = ("This paper studies how knowledge graphs are built from text and how the resulting graphs are used in "
                            "question answering and recommendation systems across many different domains and languages.")
        self.net.baidu_answer = json.dumps({"code": "0", "data": [
            {"paperId": "en1", "title": "Building knowledge graphs from text", "abstract": english_abstract, "doi": "", "keyword": "kg",
             "publishYear": 2024, "publishInfo": {"journalName": "J"}, "url": "https://xueshu.baidu.com/p/en1"}]}).encode()
        self.net.openalex_doi_results = []
        self.refresh()
        verdict = self.pool()["baidu:en1"]
        self.assertEqual((verdict["eligible"], verdict["reason"]), (False, "language_not_allowed"))

    def test_a_baidu_paper_still_needs_an_abstract(self):
        self.net.baidu_answer = json.dumps({"code": "0", "data": [
            {"paperId": "na1", "title": "只有标题的中文论文题目", "abstract": "", "doi": "", "keyword": "kg", "publishYear": 2024,
             "publishInfo": {"journalName": "J"}, "url": "https://xueshu.baidu.com/p/na1"}]}).encode()
        self.refresh()
        verdict = self.pool()["baidu:na1"]
        self.assertEqual((verdict["eligible"], verdict["reason"]), (False, "no_readable_content"))

    def test_a_baidu_paper_with_no_page_has_no_pdf_source(self):
        self.net.baidu_answer = json.dumps({"code": "0", "data": [
            {"paperId": "np1", "title": "没有任何链接的中文论文题目", "abstract": "这是一段足够长的中文摘要内容。", "doi": "", "keyword": "kg",
             "publishYear": 2024, "publishInfo": {"journalName": "J"}, "url": ""}]}).encode()
        self.refresh()
        verdict = self.pool()["baidu:np1"]
        self.assertEqual((verdict["eligible"], verdict["reason"]), (False, "no_pdf_source"))

    def test_a_bare_doi_is_not_a_pdf_source(self):
        self.net.baidu_answer = json.dumps({"code": "0", "data": [
            {"paperId": "bd1", "title": "只有编号的中文论文题目", "abstract": "这是一段足够长的中文摘要内容。", "doi": "10.9999/bare.1",
             "keyword": "kg", "publishYear": 2024, "publishInfo": {"journalName": "J"}, "url": ""}]}).encode()
        self.net.openalex_doi_results = []
        self.refresh()
        verdict = self.pool()["https://doi.org/10.9999/bare.1"]
        self.assertEqual((verdict["eligible"], verdict["reason"]), (False, "no_pdf_source"))

    def test_the_baidu_switch_governs_stored_baidu_papers(self):
        self.net.openalex_doi_results = []
        self.refresh()
        self.set_user_settings(self.app, sourceBaiduScholar=False)
        result = self.app.build_batch(limit=5, project_id=self.pid)
        self.assertEqual(result["cards"], [])
        self.assertGreaterEqual(result["eligibility"]["excluded"]["source_disabled"], 1)

    def test_a_paper_both_sources_reported_follows_either_switch(self):
        from app import user_settings
        self.net.openalex_doi_results = [openalex_work(42, DOI_1)]
        self.refresh()
        row = self.stored(DOI_1)
        self.assertEqual(row["openalex_id"], "https://openalex.org/W42")
        for values, expected in ((dict(sourceBaiduScholar=False, sourceOpenAlex=True), True),
                                 (dict(sourceBaiduScholar=True, sourceOpenAlex=False), True),
                                 (dict(sourceBaiduScholar=False, sourceOpenAlex=False), False)):
            self.set_user_settings(self.app, **values)
            self.assertEqual(user_settings.source_allowed(self.app.data, row), expected, values)


class ChineseLanguageTests(unittest.TestCase):
    def setUp(self):
        from app import paper_language
        self.zh = paper_language.chinese_text_language

    def test_a_chinese_title_with_an_agreeing_or_missing_abstract_is_chinese(self):
        self.assertEqual(self.zh("知识图谱构建方法综述", "本文综述知识图谱的构建方法。"), "zh")
        self.assertEqual(self.zh("知识图谱构建方法综述", None), "zh")
        self.assertEqual(self.zh("知识图谱构建方法综述", ""), "zh")
        self.assertEqual(self.zh("知识图谱构建方法综述", "N/A"), "zh")

    def test_a_bilingual_abstract_with_enough_chinese_still_agrees(self):
        abstract = "本文综述知识图谱的构建方法与应用。 " + "This paper reviews the construction and the applications of knowledge graphs in many fields. "
        self.assertEqual(self.zh("知识图谱构建方法综述", abstract), "zh")

    def test_not_enough_chinese_characters_is_unknown(self):
        self.assertIsNone(self.zh("知识图", None))
        self.assertIsNone(self.zh("知识图 survey of graphs", None))

    def test_chinese_must_be_the_majority_of_the_title(self):
        self.assertIsNone(self.zh("基于BERT的知识图谱构建方法 A survey of knowledge graph construction methods", None))

    def test_kana_or_hangul_means_not_chinese(self):
        self.assertIsNone(self.zh("知識グラフの構築方法に関する研究", None))
        self.assertIsNone(self.zh("지식 그래프 構築方法研究論文", None))
        self.assertIsNone(self.zh("知识图谱构建方法综述", "ナレッジグラフを構築する方法を調べた論文です。"))

    def test_an_english_abstract_disagrees(self):
        english = ("This paper studies how knowledge graphs are built from text and how the resulting graphs are used in question "
                   "answering and recommendation systems across many domains.")
        self.assertIsNone(self.zh("知识图谱构建方法综述", english))

    def test_junk_input(self):
        for title in (None, 5, "", "   ", ["知识图谱"]):
            self.assertIsNone(self.zh(title, "本文综述知识图谱的构建方法。"))
        self.assertEqual(self.zh("知识图谱构建方法综述", 5), "zh")

    def test_the_service_uses_it_when_nothing_or_only_en_was_reported(self):
        from app.service import App
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "harness").mkdir()
            (Path(tmp) / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
            (Path(tmp) / "app").mkdir(exist_ok=True)
            (Path(tmp) / "app" / "budget.json").write_text((ROOT / "app" / "budget.json").read_text())
            app = App(root=tmp, data_dir=str(Path(tmp) / "data"))
            try:
                row = {"title": "知识图谱构建方法综述", "abstract": "本文综述知识图谱的构建方法。"}
                language = app._paper_language(dict(row))
                self.assertEqual((language["metadata_language"], language["metadata_source"]), ("zh", "title+abstract"))
                reported = app._paper_language({**row, "metadata_language": "en", "metadata_language_source": "OpenAlex"})
                self.assertEqual((reported["metadata_language"], reported["metadata_source"]), ("zh", "chinese_text_over_metadata"))
                other = app._paper_language({**row, "metadata_language": "fr", "metadata_language_source": "OpenAlex"})
                self.assertEqual((other["metadata_language"], other["metadata_source"]), ("fr", "OpenAlex"))
                self.assertIsNone(app._paper_language({"title": "Knowledge graphs", "abstract": ""})["metadata_language"])
                stored = app.store.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
                self.assertEqual(stored, 0)                          # never written back
            finally:
                app.store.close()

# The Baidu Scholar interface is not offered any more (app.user_settings.BAIDU_SCHOLAR_OFFERED); these tests exercise the
# adapter itself, so the offer is switched on for this module only.
_OFFER_SCHOLAR = __import__("unittest.mock", fromlist=["patch"]).patch.object(
    __import__("app.user_settings", fromlist=["x"]), "BAIDU_SCHOLAR_OFFERED", True)


def setUpModule():
    _OFFER_SCHOLAR.start()


def tearDownModule():
    _OFFER_SCHOLAR.stop()


if __name__ == "__main__":
    unittest.main()
