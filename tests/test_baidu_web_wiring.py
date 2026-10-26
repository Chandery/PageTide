"""Baidu AI Search restricted to xueshu.baidu.com (`baidu_web`) in the daily feed, project creation, seed search, settings and
eligibility. Offline only: urlopen is replaced by a router that answers the Qianfan search from the REAL trimmed fixture
(tests/fixtures/baidu_web/success.json) and, for the both-sources cases, Baidu Scholar from its synthetic fixtures.
Every key here is a dummy.
"""
import datetime
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WEB = ROOT / "tests" / "fixtures" / "baidu_web"
SCHOLAR = ROOT / "tests" / "fixtures" / "baidu_scholar"
KEY = "bce-v3/ALTAK-dummyDummy0000/dummydummydummydummy0000"
KEYWORDS = ["知识图谱", "信息抽取", "本体构建", "数字人文", "knowledge graph"]
ID_1 = "146x0jv0634t0m60eb250a40yw135131"
KEY_1 = "baidu:" + ID_1
TITLE_1 = "基于本体的生物安全知识图谱构建研究"
PAGE_1 = "https://xueshu.baidu.com/usercenter/paper/show?paperid=" + ID_1


class Reply:
    def __init__(self, body):
        self.body, self.headers = body, {}

    def read(self, limit=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def scholar_answer(*items):
    return json.dumps({"code": "0", "data": list(items)}, ensure_ascii=False).encode()


def scholar_item(paper_id, title, year=2026):
    return {"paperId": paper_id, "title": title, "abstract": "这是一段足够长的中文摘要内容，讲知识图谱，用来测试合并。", "doi": "", "keyword": "测试", "publishYear": year,
            "publishInfo": {"journalName": "期刊"}, "url": "https://xueshu.baidu.com/usercenter/paper/show?paperid=" + paper_id}


def web_answer(*items):
    refs = []
    for paper_id, title, date in items:
        refs.append({"id": 1, "url": "https://xueshu.baidu.com/usercenter/paper/show?paperid=" + paper_id, "title": title + " ", "date": date, "type": "web",
                     "content": f"{title} 来自 掌桥科研  喜欢0 阅读量: 4 作者: 张三 摘要: 这是一段足够长的中文摘要内容，讲知识图谱，用来测试合并。 关键词: 测试 "})
    return json.dumps({"request_id": "r", "references": refs}, ensure_ascii=False).encode()


class Net:
    """Routes the Qianfan web search (POST), Baidu Scholar (GET) and OpenAlex; records every request."""

    def __init__(self):
        self.web, self.scholar, self.openalex = [], [], []
        self.web_answer = (WEB / "success.json").read_bytes()
        self.scholar_answer = (SCHOLAR / "success.json").read_bytes()
        self.web_error = self.scholar_error = self.openalex_error = None
        self.openalex_results = []
        self.lock = threading.Lock()

    def __call__(self, request, timeout=None):
        url = request.full_url
        if url == "https://qianfan.baidubce.com/v2/ai_search/web_search":
            assert request.get_method() == "POST", request.get_method()
            with self.lock:
                self.web.append({"body": json.loads(request.data.decode("utf-8")), "auth": request.get_header("Authorization")})
            if self.web_error:
                raise self.web_error
            return Reply(self.web_answer)
        if "qianfan.baidubce.com/v2/tools/baidu_scholar/search" in url:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            with self.lock:
                self.scholar.append({"wd": query["wd"][0], "page": int(query["pageNum"][0]), "auth": request.get_header("Authorization")})
            if self.scholar_error:
                raise self.scholar_error
            return Reply(self.scholar_answer)
        if "api.openalex.org" in url:
            with self.lock:
                self.openalex.append(url)
            if self.openalex_error:
                raise self.openalex_error
            return Reply(json.dumps({"results": self.openalex_results}).encode())
        raise AssertionError("unexpected request: " + url)

    def web_queries(self):
        return [c["body"]["messages"][0]["content"] for c in self.web]


def http_error(code, body=None):
    return urllib.error.HTTPError("https://qianfan.baidubce.com/x", code, "no", {}, io.BytesIO(body) if body is not None else None)


DAILY = b'{"code":"18","message":"Open api daily request limit reached (synthetic)"}'


class WiringCase(unittest.TestCase):
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
        os.environ.pop("BAIDU_SCHOLAR_API_KEY", None)
        os.environ["OPENALEX_API_KEY"] = "test-openalex-key-0000"  # OpenAlex is only searched with a key
        sleeper = mock.patch("time.sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)
        from app import creation
        creation._SEED_CACHE.clear()
        creation._BAIDU_SEEDS.clear()
        from app.service import App
        self.app = App(root=str(self.root), data_dir=str(self.root / "data"))
        self.addCleanup(self.app.store.close)
        self.set_user_settings(self.app, timePreference="all", sourceBaiduWeb=True, baiduScholarConfirmed=True)
        self.app.save_source_key("baidu_scholar", KEY)          # one key serves both Baidu sources
        self.net = Net()

    def patched(self):
        return mock.patch.object(urllib.request, "urlopen", self.net)

    def stored(self, key):
        return self.app.store.paper(key)


class FeedCase(WiringCase):
    def setUp(self):
        super().setUp()
        self.pid = self.app.create_project("知识图谱", "manual", KEYWORDS)["project_id"]
        self.app.set_project_language(self.pid, None, ["zh"])
        day = mock.patch.object(type(self.app), "batch_day", lambda s: "2026-10-23")
        day.start()
        self.addCleanup(day.stop)

    def refresh(self, **kwargs):
        with self.patched():
            return self.app.refresh_candidates(project_id=self.pid, **kwargs)


class FeedCallPolicyTests(FeedCase):
    def test_a_chinese_project_with_chinese_keywords_calls_the_web_search_with_at_most_three(self):
        result = self.refresh()
        self.assertEqual(self.net.web_queries(), ["知识图谱", "信息抽取", "本体构建"])
        self.assertEqual({c["auth"] for c in self.net.web}, {f"Bearer {KEY}"})
        self.assertEqual(self.net.scholar, [])                          # the scholar switch is off: it is not asked
        self.assertEqual(result["errors"], [])
        self.assertGreater(result["fetched"], 0)

    def test_the_request_asks_for_twenty_web_results_on_the_xueshu_site_and_nothing_else(self):
        self.refresh()
        body = self.net.web[0]["body"]
        self.assertEqual(body["resource_type_filter"], [{"type": "web", "top_k": 20}])
        self.assertEqual(body["search_filter"], {"match": {"site": ["xueshu.baidu.com"]}})
        self.assertNotIn("search_recency_filter", body)                  # the owner chose no window: recency is a weight, not a filter

    def test_the_recency_filter_follows_the_time_window_the_owner_chose(self):
        for preference, expected in (("recent", "week"), ("month", "month"), ("all", None)):
            self.net.web.clear()
            self.set_user_settings(self.app, timePreference=preference)
            for cached in (self.root / "data" / "cache" / "baidu_web").glob("*.json"):
                cached.unlink()
            self.refresh()
            self.assertEqual({c["body"].get("search_recency_filter") for c in self.net.web}, {expected}, preference)

    def test_only_keywords_with_chinese_characters_are_sent(self):
        other = self.app.create_project("mixed", "manual", ["knowledge graph", "world model", "世界模型"])["project_id"]
        self.app.set_project_language(other, None, ["zh", "en"])
        with self.patched():
            self.app.refresh_candidates(project_id=other)
        self.assertEqual(self.net.web_queries(), ["世界模型"])

    def test_the_papers_are_stored_with_the_xueshu_page_and_no_language(self):
        self.refresh()
        row = self.stored(KEY_1)
        self.assertEqual((row["title"], row["published"], row["topic"]), (TITLE_1, "2026-10-19", "生物安全"))
        self.assertTrue(row["abstract"].startswith("[目的/意义]"))
        self.assertIsNone(row["metadata_language"])
        self.assertIsNone(row["doi"])
        oa = json.loads(row["oa_json"])
        self.assertEqual((oa["via"], oa["pages"]), (["baidu_web"], [{"source": "baidu_web", "url": PAGE_1}]))
        self.assertEqual(self.app.store.conn.execute("SELECT COUNT(*) FROM papers WHERE key LIKE 'baidu:%'").fetchone()[0], 4)

    def test_no_openalex_lookup_is_made_for_papers_without_a_doi(self):
        self.refresh()
        self.assertEqual([u for u in self.net.openalex if "doi%3A" in u or "filter=doi:" in u], [])

    def test_conditions_that_do_not_hold_mean_zero_calls(self):
        self.app.set_project_language(self.pid, None, ["en"])
        self.refresh()
        self.assertEqual(self.net.web, [], "english only")
        self.app.set_project_language(self.pid, None, ["zh"])
        self.set_user_settings(self.app, sourceBaiduWeb=False)
        self.refresh()
        self.assertEqual(self.net.web, [], "switch off")
        self.set_user_settings(self.app, sourceBaiduWeb="yes")
        self.refresh()
        self.assertEqual(self.net.web, [], "switch not boolean")
        self.set_user_settings(self.app, sourceBaiduWeb=True)
        self.app.clear_source_key("baidu_scholar")
        result = self.refresh()
        self.assertEqual(self.net.web, [], "no key")
        self.assertEqual([e for e in result["errors"] if e.get("source") == "baidu_web"], [])
        english = self.app.create_project("english words", "manual", ["knowledge graph"])["project_id"]
        self.app.set_project_language(english, None, ["zh", "en"])
        self.app.save_source_key("baidu_scholar", KEY)
        with self.patched():
            self.app.refresh_candidates(project_id=english)
        self.assertEqual(self.net.web, [], "no Chinese keyword")
        pending = self.app.create_project("pending", "manual", ["知识图谱"])["project_id"]
        with self.patched():
            self.app.refresh_candidates(project_id=pending)
        self.assertEqual(self.net.web, [], "no language choice yet")

    def test_an_explicit_search_does_not_call_the_web_search(self):
        self.refresh(search="知识图谱")
        self.assertEqual(self.net.web, [])

    def test_the_learning_map_refresh_does_not_call_it(self):
        self.set_user_settings(self.app, routeBeta=True)
        with mock.patch.object(self.app, "_refresh_route_candidates", return_value={"fetched": 0, "added": 0, "field": 0, "errors": []}) as route, \
                mock.patch.object(self.app, "_route_state", return_value={"graph": {}}):
            self.refresh()
        route.assert_called_once()
        self.assertEqual(self.net.web, [])

    def test_the_web_search_alone_is_enough_when_the_openalex_sources_are_off(self):
        self.set_user_settings(self.app, sourceArxiv=False, sourceOpenAlex=False)
        result = self.refresh()
        self.assertEqual(len(self.net.web), 3)
        self.assertEqual(self.net.openalex, [])
        self.assertGreater(result["fetched"], 0)

    def test_everything_off_is_sources_disabled_and_the_learning_map_with_only_web_on_asks_nothing(self):
        self.set_user_settings(self.app, sourceArxiv=False, sourceOpenAlex=False, routeBeta=True)
        with mock.patch.object(self.app, "_refresh_route_candidates", side_effect=AssertionError("no OpenAlex source is on")), \
                mock.patch.object(self.app, "_route_state", return_value={"graph": {}}):
            result = self.refresh()
        self.assertEqual((result["reason_code"], self.net.web), ("sources_disabled", []))
        self.set_user_settings(self.app, routeBeta=False, sourceBaiduWeb=False, sourceBaiduScholar=False)
        self.assertEqual(self.refresh()["reason_code"], "sources_disabled")

    def test_the_second_refresh_of_a_day_is_answered_from_the_cache_and_costs_no_call(self):
        self.refresh()
        self.net.web.clear()
        self.refresh()
        self.assertEqual(self.net.web, [])
        self.assertEqual(self.app.adapters["baidu_web"].usage_today(), 3)


class FeedBothSourcesTests(FeedCase):
    def setUp(self):
        super().setUp()
        self.set_user_settings(self.app, sourceBaiduScholar=True)

    def test_both_sources_are_asked_and_they_share_one_counter(self):
        self.refresh()
        self.assertEqual(len(self.net.web), 3)
        self.assertEqual(len(self.net.scholar), 3)
        self.assertEqual((self.app.adapters["baidu_web"].usage_today(), self.app.adapters["baidu_scholar"].usage_today()), (6, 6))   # one allowance

    def test_a_paper_both_found_is_stored_once_and_keeps_both_pages(self):
        self.net.scholar_answer = scholar_answer(scholar_item("s-dup", TITLE_1))
        self.refresh()
        rows = self.app.store.conn.execute("SELECT key FROM papers WHERE title=?", (TITLE_1,)).fetchall()
        self.assertEqual(len(rows), 1)
        oa = json.loads(self.stored(rows[0][0])["oa_json"])
        self.assertEqual(sorted(oa["via"]), ["baidu_scholar", "baidu_web"])
        self.assertEqual({p["source"] for p in oa["pages"]}, {"baidu_scholar", "baidu_web"})

    def test_the_same_key_from_both_is_one_paper(self):
        self.net.scholar_answer = scholar_answer(scholar_item(ID_1, "另一个标题写法"))
        self.refresh()
        self.assertEqual(self.app.store.conn.execute("SELECT COUNT(*) FROM papers WHERE key=?", (KEY_1,)).fetchone()[0], 1)
        self.assertEqual(sorted(json.loads(self.stored(KEY_1)["oa_json"])["via"]), ["baidu_scholar", "baidu_web"])

    def test_titles_that_differ_only_in_spaces_and_punctuation_are_one_paper(self):
        self.net.scholar_answer = scholar_answer(scholar_item("s-dup2", "基于本体的 生物安全知识图谱构建研究。"))
        self.refresh()
        rows = self.app.store.conn.execute("SELECT key FROM papers WHERE title LIKE '基于本体的%'").fetchall()
        self.assertEqual(len(rows), 1)

    def test_scholar_unavailable_does_not_stop_the_web_search(self):
        self.net.scholar_error = http_error(404)
        result = self.refresh()
        self.assertEqual(len(self.net.scholar), 1)                      # a 404 ends the Baidu Scholar part at the first keyword
        self.assertEqual(len(self.net.web), 3)
        self.assertEqual([e["kind"] for e in result["errors"] if e.get("source") == "baidu_scholar"], ["unavailable"])
        self.assertEqual([e for e in result["errors"] if e.get("source") == "baidu_web"], [])
        self.assertIsNotNone(self.stored(KEY_1))

    def test_a_web_failure_does_not_stop_scholar(self):
        self.net.web_error = http_error(401)
        result = self.refresh()
        self.assertEqual(len(self.net.web), 1)
        self.assertEqual(len(self.net.scholar), 3)
        self.assertEqual([e["kind"] for e in result["errors"] if e.get("source") == "baidu_web"], ["auth_required"])
        self.assertIsNotNone(self.stored("baidu:synthetic-p2"))

    def test_the_scholar_switch_alone_never_calls_the_web_search(self):
        self.set_user_settings(self.app, sourceBaiduWeb=False)
        self.refresh()
        self.assertEqual(self.net.web, [])
        self.assertEqual(len(self.net.scholar), 3)


class FeedErrorTests(FeedCase):
    def test_a_refused_key_is_reported_once_and_stops_further_calls(self):
        self.net.web_error = http_error(401)
        result = self.refresh()
        self.assertEqual(len(self.net.web), 1)
        self.assertEqual([e["kind"] for e in result["errors"] if e.get("source") == "baidu_web"], ["auth_required"])
        self.assertNotIn(KEY, json.dumps(result))

    def test_the_local_cap_is_quota_and_makes_no_call(self):
        day = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)).date().isoformat()
        self.app.store.conn.execute("INSERT INTO settings(key,value) VALUES(?,?)", ("source_usage:baidu_scholar:" + day, "40"))
        self.app.store.conn.commit()
        result = self.refresh()
        self.assertEqual(self.net.web, [])
        self.assertEqual([e["kind"] for e in result["errors"] if e.get("source") == "baidu_web"], ["quota_exhausted"])

    def test_an_unreadable_answer_is_an_error_not_a_crash_and_the_next_keyword_is_tried(self):
        self.net.web_answer = b"<html>gateway</html>"
        result = self.refresh()
        self.assertEqual(len(self.net.web), 3)
        self.assertEqual({e["kind"] for e in result["errors"] if e.get("source") == "baidu_web"}, {"bad_response"})

    def test_a_404_ends_the_web_part_at_the_first_keyword(self):
        self.net.web_error = http_error(404)
        result = self.refresh()
        self.assertEqual(len(self.net.web), 1)
        self.assertEqual([e["kind"] for e in result["errors"] if e.get("source") == "baidu_web"], ["unavailable"])

    def test_a_web_failure_keeps_the_openalex_results(self):
        self.net.web_error = http_error(401)
        work = {"id": "https://openalex.org/W7", "doi": "https://doi.org/10.1/en7", "title": "知识图谱 survey", "publication_date": "2025-01-01",
                "type": "article", "ids": {}, "primary_location": {"source": {"display_name": "Journal"}}}
        self.net.openalex_results = [work]
        self.refresh()
        self.assertIsNotNone(self.stored("https://doi.org/10.1/en7"))


class BoundaryTests(FeedCase):
    """An unexpected exception from one source is a failed source, not a crashed refresh, search or seed lookup."""

    def setUp(self):
        super().setUp()
        self.set_user_settings(self.app, sourceBaiduScholar=True)

    def errors(self, result, source):
        return [e["kind"] for e in result["errors"] if e.get("source") == source]

    def test_the_feed_survives_an_unexpected_exception_of_either_source(self):
        with mock.patch.object(self.app.adapters["baidu_scholar"], "search", side_effect=RuntimeError("boom " + KEY)):
            result = self.refresh()
        self.assertEqual(self.errors(result, "baidu_scholar"), ["unavailable"])
        self.assertEqual(len(self.net.web), 3)
        self.assertIsNotNone(self.stored(KEY_1))
        self.assertNotIn(KEY, json.dumps(result))
        self.net.web.clear()
        for cached in (self.root / "data" / "cache" / "baidu_web").glob("*.json"):
            cached.unlink()
        with mock.patch.object(self.app.adapters["baidu_web"], "search", side_effect=ValueError("boom " + KEY)):
            result = self.refresh()
        self.assertEqual(self.errors(result, "baidu_web"), ["unavailable"])
        self.assertEqual(len(self.net.scholar), 3)
        self.assertNotIn(KEY, json.dumps(result))

    def test_creation_and_seed_search_survive_an_unexpected_exception_of_one_source(self):
        with mock.patch.object(self.app.adapters["baidu_scholar"], "search", side_effect=RuntimeError("boom")), self.patched():
            papers, problem = self.app._baidu_search("知识图谱", per_page=10, web_per_page=12)
            result = self.app.seed_search(TITLE_1)
        self.assertEqual((problem, [p["key"] for p in papers][:1]), (None, [KEY_1]))
        self.assertEqual(result["items"][0]["key"], KEY_1)
        with mock.patch.object(self.app.adapters["baidu_scholar"], "search", side_effect=RuntimeError("boom")), \
                mock.patch.object(self.app.adapters["baidu_web"], "search", side_effect=RuntimeError("boom")):
            self.assertEqual(self.app._baidu_search("知识图谱"), ([], "unavailable"))

    def test_a_lone_surrogate_in_a_search_phrase_reaches_neither_source(self):
        with self.patched():
            self.app._baidu_search("知识图谱\ud800构建")
        self.assertEqual(self.net.web_queries(), ["知识图谱构建"])
        self.assertEqual([c["wd"] for c in self.net.scholar], ["知识图谱构建"])


class EmptyTitleTests(FeedCase):
    """A title of only punctuation (or none) has an empty comparison mark: it never makes two different papers one."""

    def setUp(self):
        super().setUp()
        self.set_user_settings(self.app, sourceBaiduScholar=True)
        self.net.scholar_answer = scholar_answer(scholar_item("s-punct", "。。。"))
        self.net.web_answer = web_answer(("w-punct", "！！！", "2026-10-19 00:00:00"))

    def test_creation_keeps_both(self):
        with self.patched():
            papers, problem = self.app._baidu_search("知识图谱")
        self.assertEqual((problem, sorted(p["title"] for p in papers)), (None, ["。。。", "！！！"]))

    def test_the_feed_keeps_both(self):
        self.refresh()
        self.assertEqual(self.app.store.conn.execute("SELECT COUNT(*) FROM papers WHERE title IN ('。。。','！！！')").fetchone()[0], 2)

    def test_the_seed_merge_keeps_a_baidu_hit_beside_an_untitled_result(self):
        from app import baidu_web, creation
        hit = baidu_web.parse_search(json.loads(self.net.web_answer))
        out = creation.merge_baidu({"status": "ok", "items": [{"key": "W1", "title": ""}]}, "查询", hit, None)
        self.assertEqual(sorted(i["key"] for i in out["items"]), sorted(["W1", hit[0]["key"]]))

    def test_the_same_nonempty_title_is_still_one_paper(self):
        self.net.scholar_answer = scholar_answer(scholar_item("s-same", "同一个标题。"))
        self.net.web_answer = web_answer(("w-same", "同一个 标题", "2026-10-19 00:00:00"))
        with self.patched():
            papers, _ = self.app._baidu_search("知识图谱")
        self.assertEqual(len(papers), 1)


class EligibilityTests(FeedCase):
    def pool(self, pid=None):
        return {p["key"]: p["_eligibility"] for p in self.app.recommendation_pool(pid or self.pid)}

    def test_a_chinese_project_may_recommend_a_paper_with_only_a_xueshu_page(self):
        self.refresh()
        verdict = self.pool()[KEY_1]
        self.assertTrue(verdict["eligible"], verdict)
        self.assertEqual((verdict["language"]["metadata_language"], verdict["language"]["metadata_source"]), ("zh", "title+abstract"))

    def test_the_cards_link_to_the_xueshu_page_and_say_it_is_a_page(self):
        self.refresh()
        cards = {c["key"]: c for c in self.app.build_batch(limit=5, project_id=self.pid)["cards"]}
        self.assertIn(KEY_1, cards)
        self.assertEqual((cards[KEY_1]["url"], cards[KEY_1]["pdf_status"]), (PAGE_1, "page"))

    def test_an_english_only_project_excludes_a_chinese_web_paper(self):
        self.refresh()
        english = self.app.create_project("english", "manual", ["knowledge graph"])["project_id"]
        self.app.set_project_language(english, None, ["en"])
        self.app.store.add_project_paper(english, KEY_1, "discovered")
        verdict = self.pool(english)[KEY_1]
        self.assertEqual((verdict["eligible"], verdict["reason"]), (False, "language_not_allowed"))

    def test_a_web_paper_without_an_abstract_is_not_eligible(self):
        self.net.web_answer = json.dumps({"references": [{"url": "https://xueshu.baidu.com/usercenter/paper/show?paperid=na1", "title": "知识图谱只有标题的中文论文题目",
                                                          "date": "2026-10-19 00:00:00", "content": "知识图谱只有标题的中文论文题目 来自 掌桥科研  喜欢0 阅读量: 4"}]}, ensure_ascii=False).encode()
        self.refresh()
        verdict = self.pool()["baidu:na1"]
        self.assertEqual((verdict["eligible"], verdict["reason"]), (False, "no_readable_content"))

    def test_a_web_paper_without_a_page_has_no_pdf_source(self):
        self.net.web_answer = web_answer(("np1", "知识图谱没有任何链接的中文论文题目", "2026-10-19 00:00:00")).replace(b"https://xueshu.baidu.com/usercenter/paper/show?paperid=np1", b"")
        self.refresh()
        row = self.app.store.conn.execute("SELECT key FROM papers WHERE title LIKE '%没有任何链接%'").fetchone()
        verdict = self.pool()[row[0]]
        self.assertEqual((verdict["eligible"], verdict["reason"]), (False, "no_pdf_source"))

    def test_the_web_switch_governs_stored_web_papers(self):
        self.refresh()
        self.set_user_settings(self.app, sourceBaiduWeb=False)
        result = self.app.build_batch(limit=5, project_id=self.pid)
        self.assertEqual(result["cards"], [])
        self.assertGreaterEqual(result["eligibility"]["excluded"]["source_disabled"], 1)

    def test_the_scholar_switch_does_not_govern_a_web_paper(self):
        self.refresh()
        self.set_user_settings(self.app, sourceBaiduScholar=True, sourceBaiduWeb=False)
        self.assertEqual(self.app.build_batch(limit=5, project_id=self.pid)["cards"], [])
        self.set_user_settings(self.app, sourceBaiduScholar=False, sourceBaiduWeb=True)
        self.assertIn(KEY_1, [c["key"] for c in self.app.build_batch(limit=5, project_id=self.pid)["cards"]])


class CreationCase(WiringCase):
    def session(self):
        return self.app.create_guidance_session("知识图谱", "了解知识图谱的构建方法", "ai_guided")["id"]

    def search(self, query="知识图谱", languages=("zh", "en"), **kwargs):
        sid = kwargs.pop("session_id", None) or self.session()
        with self.patched():
            return self.app.guidance_search(sid, query, languages=list(languages) if languages is not None else None, **kwargs), sid


class CreationTests(CreationCase):
    def test_a_chinese_query_with_chinese_ticked_adds_web_candidates(self):
        result, sid = self.search()
        self.assertEqual(self.net.web_queries(), ["知识图谱"])
        body = self.net.web[0]["body"]
        self.assertEqual(body["resource_type_filter"], [{"type": "web", "top_k": 12}])
        self.assertNotIn("search_recency_filter", body)
        self.assertEqual(self.net.scholar, [])
        first = next(i for i in result["items"] if i["key"] == KEY_1)
        self.assertEqual((first["title"], first["url"], first["pdf_status"], first["new"]), (TITLE_1, PAGE_1, "page", True))
        self.assertNotIn("baidu", result)
        stored = {p["key"]: p for p in self.app.store.guidance_session(sid)["draft"]["candidates"]}
        self.assertEqual(stored[KEY_1]["oa"]["pages"][0], {"source": "baidu_web", "url": PAGE_1})
        self.assertNotIn(KEY, json.dumps(self.app.store.guidance_session(sid)["draft"]))

    def test_no_web_search_unless_every_condition_holds(self):
        cases = {"zh not ticked": dict(languages=["en"]), "no languages sent": dict(languages=None), "empty languages": dict(languages=[]),
                 "english query": dict(query="knowledge graph")}
        for name, kwargs in cases.items():
            self.search(**kwargs)
            self.assertEqual(self.net.web, [], name)
        self.set_user_settings(self.app, sourceBaiduWeb=False)
        self.search()
        self.assertEqual(self.net.web, [], "switch off")
        self.set_user_settings(self.app, sourceBaiduWeb=True)
        self.app.clear_source_key("baidu_scholar")
        self.search()
        self.assertEqual(self.net.web, [], "no key")

    def test_the_year_window_drops_older_papers_unless_all_years_is_chosen(self):
        self.net.web_answer = web_answer(("old1", "很早以前发表的中文论文题目", "2015-05-01 00:00:00"), ("new1", "最近发表的中文论文题目", "2026-05-01 00:00:00"))
        result, _ = self.search(query="知识图谱 窗口")
        self.assertEqual([i["key"] for i in result["items"]], ["baidu:new1"])
        result, _ = self.search(query="知识图谱 全部", all_years=True)
        self.assertEqual({i["key"] for i in result["items"]}, {"baidu:old1", "baidu:new1"})

    def test_the_same_query_twice_adds_nothing_new_and_spends_no_second_call(self):
        _, sid = self.search()
        result, _ = self.search(session_id=sid)
        self.assertEqual(len(self.net.web), 1)
        self.assertEqual([i["new"] for i in result["items"]], [False] * len(result["items"]))

    def test_with_both_sources_on_each_is_asked_once_and_a_shared_paper_is_one_candidate(self):
        self.set_user_settings(self.app, sourceBaiduScholar=True)
        self.net.scholar_answer = scholar_answer(scholar_item("s-dup", TITLE_1))
        result, sid = self.search()
        self.assertEqual((len(self.net.web), len(self.net.scholar)), (1, 1))
        titles = [i["title"] for i in result["items"]]
        self.assertEqual(titles.count(TITLE_1), 1)
        kept = [p for p in self.app.store.guidance_session(sid)["draft"]["candidates"] if p["title"] == TITLE_1]
        self.assertEqual(len(kept), 1)
        self.assertEqual({page["source"] for page in kept[0]["oa"]["pages"]}, {"baidu_scholar", "baidu_web"})      # the later source adds its page

    def test_scholar_unavailable_but_web_ok_shows_no_status(self):
        self.set_user_settings(self.app, sourceBaiduScholar=True)
        self.net.scholar_error = http_error(404)
        result, _ = self.search()
        self.assertNotIn("baidu", result)
        self.assertIn(KEY_1, [i["key"] for i in result["items"]])

    def test_a_status_appears_only_when_every_asked_source_failed_and_shows_the_most_actionable_kind(self):
        self.set_user_settings(self.app, sourceBaiduScholar=True)
        cases = [(http_error(404), http_error(429, DAILY), "quota_exhausted"),          # scholar unavailable, web out of quota: quota shows
                 (http_error(429, DAILY), http_error(404), "quota_exhausted"),
                 (http_error(404), http_error(401), "auth_required"),
                 (http_error(401), http_error(429, DAILY), "auth_required"),
                 (urllib.error.URLError("offline"), http_error(404), "network_error"),
                 (http_error(404), urllib.error.URLError("offline"), "network_error"),
                 (http_error(429, DAILY), urllib.error.URLError("offline"), "quota_exhausted"),
                 (http_error(404), http_error(500), "unavailable"),
                 (http_error(429), http_error(404), "unavailable")]                   # a per-second limit is transient, not quota
        for n, (scholar, web, expected) in enumerate(cases):
            self.net.scholar_error, self.net.web_error = scholar, web
            result, _ = self.search(query=f"知识图谱 失败{n}")
            self.assertEqual(result["baidu"], {"kind": expected}, n)
            self.assertNotIn(KEY, json.dumps(result))
        self.set_user_settings(self.app, sourceBaiduScholar=False)
        self.net.web_error = http_error(429, DAILY)
        result, _ = self.search(query="知识图谱 只有网页")
        self.assertEqual(result["baidu"], {"kind": "quota_exhausted"})

    def test_a_web_failure_is_a_short_status_and_openalex_results_still_come(self):
        self.net.openalex_results = [{"id": "https://openalex.org/W2", "doi": "https://doi.org/10.9/2", "title": "Another survey", "publication_date": "2024-03-01",
                                      "type": "article", "ids": {}, "primary_location": {"source": {"display_name": "Journal"}},
                                      "abstract_inverted_index": {"graph": [0], "survey": [1]}}]
        for error, kind in ((http_error(401), "auth_required"), (http_error(429, DAILY), "quota_exhausted"), (http_error(429), "unavailable"), (urllib.error.URLError("offline " + KEY), "network_error")):
            self.net.web_error = error
            result, _ = self.search(query=f"知识图谱{kind}")
            self.assertEqual(result["baidu"], {"kind": kind})
            self.assertIsNone(result["error"])
            self.assertEqual([i["key"] for i in result["items"]], ["https://doi.org/10.9/2"])
            self.assertNotIn(KEY, json.dumps(result))

    def test_the_local_cap_is_a_quota_status_and_makes_no_call(self):
        day = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)).date().isoformat()
        self.app.store.conn.execute("INSERT INTO settings(key,value) VALUES(?,?)", ("source_usage:baidu_scholar:" + day, "40"))
        self.app.store.conn.commit()
        result, _ = self.search()
        self.assertEqual((self.net.web, result["baidu"]), ([], {"kind": "quota_exhausted"}))

    def test_candidates_survive_creating_the_project_and_keep_the_web_page(self):
        result, sid = self.search()
        created = self.app.finalize_guidance(sid, selected_keys=[KEY_1], language_policy={"allowed_languages": ["zh"]}, skip_route=True)
        self.assertEqual(created["selected"], 1)
        self.assertEqual(json.loads(self.stored(KEY_1)["oa_json"])["via"], ["baidu_web"])

    def test_preview_passes_the_languages_to_every_query(self):
        sid = self.session()
        draft = {"keywords": ["知识图谱", "knowledge graph"], "search_queries": ["知识图谱 综述", "knowledge graph survey"]}
        with self.patched():
            result = self.app.guidance_preview(sid, draft, languages=["zh", "en"])
        self.assertEqual(self.net.web_queries(), ["知识图谱 综述"])
        self.assertTrue(any(i["key"] == KEY_1 for i in result["items"]))
        self.net.web.clear()
        with self.patched():
            self.app.guidance_preview(sid, draft, languages=["en"])
        self.assertEqual(self.net.web, [])


class SeedTests(WiringCase):
    def seed_search(self, query="知识图谱构建方法综述", **kwargs):
        with self.patched():
            return self.app.seed_search(query, **kwargs)

    def test_a_chinese_title_search_adds_web_hits_with_eight_results(self):
        result = self.seed_search(TITLE_1)
        self.assertEqual(self.net.web_queries(), [TITLE_1])
        self.assertEqual(self.net.web[0]["body"]["resource_type_filter"], [{"type": "web", "top_k": 8}])
        self.assertNotIn("search_recency_filter", self.net.web[0]["body"])
        self.assertEqual(result["status"], "ok")
        first = result["items"][0]
        self.assertEqual((first["key"], first["seed_id"], first["url"]), (KEY_1, KEY_1, PAGE_1))       # the closest title first
        self.assertNotIn("baidu", result)

    def test_a_title_read_out_of_a_dropped_pdf_english_text_off_or_no_key_is_not_sent(self):
        self.seed_search(TITLE_1, typed=False)
        self.seed_search("an english title about knowledge graphs")
        self.set_user_settings(self.app, sourceBaiduWeb=False)
        self.seed_search(TITLE_1)
        self.set_user_settings(self.app, sourceBaiduWeb=True)
        self.app.clear_source_key("baidu_scholar")
        self.seed_search(TITLE_1)
        self.assertEqual(self.net.web, [])

    def test_a_web_failure_never_breaks_the_search_and_is_reported_as_a_short_status(self):
        self.net.web_error = http_error(401)
        result = self.seed_search()
        self.assertEqual(result["baidu"], {"kind": "auth_required"})
        self.assertNotIn(KEY, json.dumps(result))

    def test_both_sources_give_one_hit_per_title(self):
        self.set_user_settings(self.app, sourceBaiduScholar=True)
        self.net.scholar_answer = scholar_answer(scholar_item("s-dup", TITLE_1))
        result = self.seed_search(TITLE_1)
        self.assertEqual(len(self.net.web) + len(self.net.scholar), 2)
        self.assertEqual([i["title"] for i in result["items"]].count(TITLE_1), 1)

    def test_a_web_hit_becomes_a_seed_from_what_baidu_said(self):
        self.seed_search(TITLE_1)
        result = self.app.create_project("中文种子", "manual", ["数字人文"], [KEY_1], language_policy={"allowed_languages": ["zh"]})
        self.assertEqual([(r["status"], r["key"]) for r in result["seed_results"]], [("resolved", KEY_1)])
        pid = result["project_id"]
        self.assertEqual(self.app.seed_keys(pid), [KEY_1])
        row = self.stored(KEY_1)
        self.assertEqual(row["title"], TITLE_1)
        self.assertEqual(json.loads(row["oa_json"])["via"], ["baidu_web"])


class SettingsTests(WiringCase):
    def test_the_status_row_of_the_web_source_shows_the_shared_key(self):
        status = self.app.sources_status()["baidu_web"]
        self.assertEqual((status["needs_key"], status["key"], status["configured"], status["daily_cap"]), (True, "required", True, 40))
        self.assertEqual((status["status_kind"], status["used_today"]), (None, 0))
        self.assertNotIn(KEY, json.dumps(self.app.sources_status()))
        self.app.clear_source_key("baidu_scholar")
        self.assertFalse(self.app.sources_status()["baidu_web"]["configured"])
        self.assertFalse(self.app.sources_status()["baidu_scholar"]["configured"])

    def test_saving_or_clearing_the_key_reaches_both_adapters(self):
        self.assertEqual((self.app.adapters["baidu_scholar"].api_key, self.app.adapters["baidu_web"].api_key), (KEY, KEY))
        self.app.clear_source_key("baidu_scholar")
        self.assertEqual((self.app.adapters["baidu_scholar"].api_key, self.app.adapters["baidu_web"].api_key), (None, None))
        self.app.save_source_key("baidu_web", "another-dummy/key-22222222")           # saving through the web row is the same key
        self.assertEqual((self.app.adapters["baidu_scholar"].api_key, self.app.adapters["baidu_web"].api_key), ("another-dummy/key-22222222",) * 2)
        self.assertTrue((self.root / "data" / "baidu_scholar.key").exists())
        self.assertFalse((self.root / "data" / "baidu_web.key").exists())

    def test_a_new_key_resets_the_recorded_status_of_both(self):
        self.app.store.set_setting("source_status:baidu_web", {"kind": "auth_required", "at": "2026-10-23T00:00:00+00:00"})
        self.app.store.set_setting("source_status:baidu_scholar", {"kind": "unavailable", "at": "2026-10-23T00:00:00+00:00"})
        self.app.save_source_key("baidu_scholar", "another-dummy/key-22222222")
        self.assertEqual((self.app.sources_status()["baidu_web"]["status_kind"], self.app.sources_status()["baidu_scholar"]["status_kind"]), (None, None))

    def test_the_test_button_of_the_web_row_makes_one_search_and_records_its_own_status(self):
        with self.patched():
            result = self.app.test_source("baidu_web")
        self.assertEqual((result["ok"], result["kind"]), (True, "ok"))
        self.assertEqual(len(self.net.web), 1)
        self.assertEqual(self.net.scholar, [])
        self.assertEqual(self.app.sources_status()["baidu_web"]["status_kind"], "ok")
        self.assertIsNone(self.app.sources_status()["baidu_scholar"]["status_kind"])
        self.assertEqual(self.app.sources_status()["baidu_web"]["used_today"], 1)

    def test_the_test_button_reports_a_kind_and_never_a_key(self):
        for error, kind in ((http_error(401), "auth_required"), (http_error(404), "unavailable"), (urllib.error.URLError(KEY), "network_error")):
            self.net.web_error = error
            with self.patched():
                result = self.app.test_source("baidu_web")
            self.assertEqual(result["kind"], kind)
            self.assertNotIn(KEY, json.dumps(result))

    def test_a_per_second_limit_is_not_recorded_as_a_used_up_day(self):
        self.net.web_error = http_error(429)
        with self.patched():
            result = self.app.test_source("baidu_web")
        self.assertEqual(result["kind"], "unavailable")
        self.assertEqual(self.app.sources_status()["baidu_web"]["status_kind"], "unavailable")
        self.net.web_error = http_error(429, DAILY)
        with self.patched():
            self.assertEqual(self.app.test_source("baidu_web")["kind"], "quota_exhausted")

    def test_both_test_buttons_count_in_the_one_allowance(self):
        with self.patched():
            self.app.test_source("baidu_web")
            self.app.test_source("baidu_scholar")
        status = self.app.sources_status()
        self.assertEqual((status["baidu_web"]["used_today"], status["baidu_scholar"]["used_today"]), (2, 2))

    def test_a_typed_key_is_tested_without_saving_and_must_have_the_shared_format(self):
        with self.patched():
            self.app.test_source("baidu_web", api_key="typed-key-0000/1111")
        self.assertEqual(self.net.web[0]["auth"], "Bearer typed-key-0000/1111")
        self.assertEqual(self.app.adapters["baidu_web"].api_key, KEY)
        with self.assertRaises(ValueError):
            self.app.test_source("baidu_web", api_key="bad key with spaces")

    def test_the_web_switch_and_the_shared_confirmation_are_valid_settings(self):
        from app import user_settings
        saved = user_settings.validate({"sourceBaiduWeb": True, "baiduScholarConfirmed": True})
        self.assertEqual(saved, {"sourceBaiduWeb": True, "baiduScholarConfirmed": True})


class KeyFileTests(WiringCase):
    def test_the_environment_variable_of_the_scholar_key_serves_both(self):
        from app import source_keys
        self.app.clear_source_key("baidu_scholar")
        with mock.patch.dict(os.environ, {"BAIDU_SCHOLAR_API_KEY": "from-env/0123456789"}):
            self.assertEqual(source_keys.load(self.app.data, "baidu_web"), "from-env/0123456789")
            self.assertEqual(source_keys.status(self.app.data, "baidu_web"), {"configured": True, "source": "environment"})
            self.assertEqual(source_keys.load(self.app.data, "baidu_scholar"), "from-env/0123456789")

    def test_the_web_source_has_the_scholar_key_file_and_never_its_own(self):
        from app import source_keys
        self.assertEqual(source_keys.key_file(self.app.data, "baidu_web"), source_keys.key_file(self.app.data, "baidu_scholar"))
        self.assertEqual(source_keys.load(self.app.data, "baidu_web"), KEY)
        self.assertTrue(source_keys.valid("baidu_web", KEY))
        self.assertFalse(source_keys.valid("baidu_web", "short"))
        if sys.platform != "win32":  # 0600 file modes are POSIX-only; on Windows the per-user profile ACL is the protection.
            self.assertEqual(oct((self.root / "data" / "baidu_scholar.key").stat().st_mode & 0o777), "0o600")
        source_keys.clear(self.app.data, "baidu_web")
        self.assertFalse(source_keys.status(self.app.data, "baidu_scholar")["configured"])

    def test_the_two_adapters_share_nothing_else(self):
        self.assertIsNot(self.app.adapters["baidu_web"], self.app.adapters["baidu_scholar"])
        self.assertNotEqual(self.app.adapters["baidu_web"].cache, self.app.adapters["baidu_scholar"].cache)

# The Baidu Scholar interface is not offered any more (app.user_settings.BAIDU_SCHOLAR_OFFERED); these tests exercise the
# adapter itself, so the offer is switched on for this module only.
_OFFER_SCHOLAR = __import__("unittest.mock", fromlist=["patch"]).patch.object(
    __import__("app.user_settings", fromlist=["x"]), "BAIDU_SCHOLAR_OFFERED", True)
# The Baidu search is not offered either (owner, 2026-10-26: 知网 replaces it); same treatment.
_OFFER_WEB = __import__("unittest.mock", fromlist=["patch"]).patch.object(
    __import__("app.user_settings", fromlist=["x"]), "BAIDU_WEB_OFFERED", True)


def setUpModule():
    _OFFER_SCHOLAR.start()
    _OFFER_WEB.start()


def tearDownModule():
    _OFFER_WEB.stop()
    _OFFER_SCHOLAR.stop()


if __name__ == "__main__":
    unittest.main()
