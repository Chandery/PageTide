"""Source adapter interface and the Baidu Scholar adapter. Offline only: urlopen is replaced by a fake.

Every Baidu field name used here is UNVERIFIED (the shape was read from Baidu's documentation page in 2026-10 and
never seen live); the fixtures in tests/fixtures/baidu_scholar are synthetic reconstructions of that documented
shape. The key in these tests is a dummy value.
"""
import datetime
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURES = ROOT / "tests" / "fixtures" / "baidu_scholar"
DUMMY = "bce-v3/ALTAK-dummyDummy0000/dummydummydummydummy0000"
AI_TEXT = "AI-GENERATED-SUMMARY-MUST-NOT-BE-STORED"


def fixture(name):
    return (FIXTURES / name).read_bytes()


class Reply:
    def __init__(self, body, headers=None):
        self.body, self.headers = body, headers or {}

    def read(self, limit=-1):
        return self.body if limit is None or limit < 0 else self.body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeUrlopen:
    """Answers each call from a queue (bytes, or an exception to raise) and records what was asked."""

    def __init__(self, *answers, default=None, on_call=None):
        self.answers, self.default, self.on_call = list(answers), default, on_call
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, request, timeout=None):
        with self.lock:
            self.calls.append({"url": request.full_url, "auth": request.get_header("Authorization"),
                               "headers": dict(request.header_items()), "timeout": timeout})
            answer = self.answers.pop(0) if self.answers else self.default
        if self.on_call:
            self.on_call(request)
        if isinstance(answer, BaseException):
            raise answer
        return Reply(answer)


def http_error(code):
    return urllib.error.HTTPError("https://qianfan.baidubce.com/x", code, "synthetic", {}, None)


class AdapterCase(unittest.TestCase):
    def setUp(self):
        from app import baidu_scholar, source_adapters, sources
        from app.db import Store
        self.baidu_scholar, self.source_adapters, self.sources = baidu_scholar, source_adapters, sources
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.store = Store(self.tmp / "db.sqlite")
        self.store.init()
        self.addCleanup(self.store.close)
        sleeper = mock.patch.object(baidu_scholar.time, "sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def adapter(self, key=DUMMY, **kwargs):
        return self.baidu_scholar.BaiduScholar(self.tmp / "cache" / "baidu_scholar", self.tmp / "db.sqlite", api_key=key, **kwargs)

    def counter_rows(self):
        return dict(self.store.conn.execute("SELECT key, value FROM settings WHERE key LIKE 'source_usage:%'").fetchall())

    def patched(self, fake):
        return mock.patch.object(self.baidu_scholar.urllib.request, "urlopen", fake)


class SourceInfoTests(AdapterCase):
    def test_registered_sources_are_the_five_the_settings_page_shows(self):
        ids = [info.id for info in self.source_adapters.all_infos()]
        self.assertEqual(ids, ["arxiv", "openalex", "baidu_scholar", "baidu_web", "cnki"])

    def test_every_source_info_is_complete(self):
        register = ROOT / "harness" / "sources.json"   # a local process file, absent from the repository
        known = ({s["id"] for s in json.loads(register.read_text())["sources"]} if register.exists() else None)
        for info in self.source_adapters.all_infos():
            with self.subTest(info.id):
                self.assertIn(info.key, ("none", "optional", "required"))
                for field in ("id", "label", "provider", "provider_quota", "sends", "claims_id"):
                    self.assertTrue(isinstance(getattr(info, field), str) and getattr(info, field).strip(), field)
                if known is not None:
                    self.assertIn(info.claims_id, known)
                self.assertTrue(info.serves_languages and info.query_scripts)
                self.assertTrue(info.daily_cap is None or (isinstance(info.daily_cap, int) and info.daily_cap > 0))
                if info.key == "none":
                    self.assertEqual((info.key_env, info.key_pattern, info.key_url), ("", "", ""))
                else:
                    for field in ("key_benefit", "key_env", "key_pattern", "key_url"):
                        self.assertTrue(getattr(info, field), field)
                    re.compile(info.key_pattern)
                    self.assertTrue(info.key_url.startswith("https://"))

    def test_key_requirements_and_the_baidu_cap(self):
        by_id = {info.id: info for info in self.source_adapters.all_infos()}
        self.assertEqual([by_id[i].key for i in ("arxiv", "openalex", "baidu_scholar")], ["none", "required", "required"])
        self.assertEqual(by_id["baidu_scholar"].daily_cap, 40)
        self.assertIn("zh", by_id["baidu_scholar"].serves_languages)
        self.assertEqual(by_id["baidu_scholar"].query_scripts, ("cjk", "latin"))

    def test_the_key_pattern_of_baidu_allows_a_slash_and_openalex_does_not(self):
        by_id = {info.id: info for info in self.source_adapters.all_infos()}
        self.assertRegex(DUMMY, by_id["baidu_scholar"].key_pattern)
        self.assertNotRegex("a/b-key-0000", "^(?:%s)$" % by_id["openalex"].key_pattern)
        for bad in ("", "short", "has space inside-key", "line\nbreak-key-12345", "x" * 600):
            self.assertIsNone(re.fullmatch(by_id["baidu_scholar"].key_pattern, bad), bad)

    def test_every_adapter_has_the_interface(self):
        with tempfile.TemporaryDirectory() as cache:
            adapters = [self.sources.OpenAlex(cache), self.adapter()]
        for adapter in adapters:
            for name in ("search", "verify", "pdf_routes"):
                self.assertTrue(callable(getattr(adapter, name)), (adapter, name))
            self.assertIn(adapter.info.id, ("openalex", "baidu_scholar"))

    def test_error_kinds_and_safe_messages(self):
        sa = self.source_adapters
        self.assertEqual(sa.http_kind(401), "auth_required")
        self.assertEqual(sa.http_kind(403), "auth_required")
        self.assertEqual(sa.http_kind(429), "quota_exhausted")
        self.assertEqual(sa.http_kind(404), "not_found")
        self.assertEqual(sa.http_kind(400), "invalid_input")
        self.assertEqual(sa.http_kind(500), "unavailable")
        self.assertEqual(sa.http_kind(503), "unavailable")
        error = sa.error_for("Baidu Scholar", "auth_required", status=401, code="bce-v3/ALTAK-x\nnoise " + DUMMY, secrets=[DUMMY])
        self.assertIsInstance(error, self.sources.SourceError)
        self.assertEqual(error.kind, "auth_required")
        self.assertNotIn(DUMMY, str(error))
        self.assertNotIn("\n", str(error))
        self.assertIn("401", str(error))


class ParseTests(AdapterCase):
    def parse(self, name="success.json"):
        return self.baidu_scholar.parse_search(json.loads(fixture(name)))

    def test_success_fixture_maps_each_documented_field(self):
        papers = self.parse()
        self.assertEqual([p["title"] for p in papers][:3], ["知识图谱 构建方法综述", "数字人文研究进展", "年份未知的论文"])
        first = papers[0]
        self.assertEqual(first["key"], "https://doi.org/10.1234/kg.2024.001")
        self.assertEqual(first["doi"], "https://doi.org/10.1234/kg.2024.001")
        self.assertEqual(first["abstract"], "本文综述知识图谱的构建方法。")
        self.assertEqual(first["published"], "2024-01-01")
        self.assertEqual(first["source"], "情报学报")
        self.assertEqual(first["topic"], "知识图谱")
        self.assertEqual(first["authors"], [])
        self.assertEqual(first["group_name"], "field")
        self.assertIsNone(first["arxiv_id"])
        self.assertIsNone(first["openalex_id"])

    def test_without_a_doi_the_key_is_the_baidu_paper_id(self):
        second = self.parse()[1]
        self.assertEqual(second["key"], "baidu:synthetic-p2")
        self.assertFalse(second.get("doi"))
        self.assertEqual(second["published"], "2021-01-01")   # a year given as text still counts
        self.assertEqual(second["topic"], "数字人文")          # a keyword list works as well as a ';' string

    def test_year_zero_and_missing_journal_are_unknown_not_invented(self):
        third = self.parse()[2]
        self.assertIsNone(third["published"])
        self.assertIsNone(third["source"])
        self.assertIsNone(third["topic"])

    def test_only_https_baidu_pages_are_kept_and_http_is_upgraded(self):
        papers = self.parse()
        self.assertEqual(papers[0]["oa"], {"pages": [{"source": "baidu_scholar", "url": "https://xueshu.baidu.com/usercenter/paper/show?paperid=synthetic-p1"}],
                                           "via": ["baidu_scholar"]})
        self.assertEqual(papers[1]["oa"]["pages"][0]["url"], "https://xueshu.baidu.com/usercenter/paper/show?paperid=synthetic-p2")
        self.assertIsNone(papers[3]["oa"])    # another host: not a Baidu page
        self.assertIsNone(papers[4]["oa"])    # javascript: is never a link
        self.assertEqual(papers[3]["key"], "https://doi.org/10.5555/other.4")   # "doi:" prefix is understood

    def test_a_paper_id_that_is_not_a_plain_token_gets_a_key_a_seed_identifier_can_carry(self):
        from app import creation
        payload = {"code": "0", "data": [{"paperId": "a b/c?d=e&f", "title": "标识里有奇怪字符的论文", "doi": ""},
                                         {"paperId": "x" * 300, "title": "标识很长的论文", "doi": ""},
                                         {"paperId": "plain-id_1.2:3", "title": "标识正常的论文", "doi": ""}]}
        keys = [p["key"] for p in self.baidu_scholar.parse_search(payload)]
        self.assertRegex(keys[0], r"^baidu:t-[0-9a-f]{16}$")
        self.assertRegex(keys[1], r"^baidu:t-[0-9a-f]{16}$")
        self.assertEqual(keys[2], "baidu:plain-id_1.2:3")
        self.assertEqual(len(set(keys)), 3)
        for key in keys:
            self.assertEqual(creation.parse_seed(key)[0], key)

    def test_no_language_is_claimed(self):
        for paper in self.parse():
            self.assertNotIn("metadata_language", paper)
            self.assertNotIn("language", paper)
            self.assertNotIn("metadata_language_source", paper)

    def test_the_ai_abstract_is_never_in_the_output(self):
        papers = self.parse()
        text = json.dumps(papers, ensure_ascii=False)
        self.assertNotIn(AI_TEXT, text)
        for paper in papers:
            self.assertFalse([k for k in paper if "ai" in k.lower() and "abstract" in k.lower()])

    def test_bad_items_are_skipped_and_empty_is_empty(self):
        self.assertEqual(len(self.parse()), 5)     # empty title and a non-object are dropped
        self.assertEqual(self.parse("empty.json"), [])

    def test_upsert_papers_accepts_the_output_and_ignores_nothing_it_needs(self):
        papers = self.parse()
        for paper in papers:
            paper["project_id"] = None
        self.store.upsert_papers(papers)
        row = self.store.paper("https://doi.org/10.1234/kg.2024.001")
        self.assertEqual(row["title"], "知识图谱 构建方法综述")
        self.assertIsNone(row["metadata_language"])
        self.assertEqual(json.loads(row["oa_json"])["via"], ["baidu_scholar"])
        self.assertEqual(self.store.paper("baidu:synthetic-p2")["published"], "2021-01-01")

    def test_malformed_payloads_raise_a_kind(self):
        for payload, kind in (({"code": "110", "message": "token invalid"}, "auth_required"),
                              ({"code": "18", "message": "daily request limit"}, "quota_exhausted"),
                              ({"code": "999", "message": "???"}, "unavailable"),
                              ({"message": "no code"}, "bad_response"), ([], "bad_response"),
                              ({"code": "0", "data": "surprise"}, "bad_response"),
                              ({"code": "0", "data": {"a": 1}}, "bad_response")):
            with self.subTest(payload=payload):
                with self.assertRaises(self.sources.SourceError) as caught:
                    self.baidu_scholar.parse_search(payload)
                self.assertEqual(caught.exception.kind, kind)
        self.assertEqual(self.baidu_scholar.parse_search({"code": 0}), [])      # a missing list is no results
        self.assertEqual(self.baidu_scholar.parse_search({"code": 0, "data": None}), [])


class PageUrlTests(AdapterCase):
    """A stored or returned page link is shown as a button and opened by a browser, which reads some URLs differently from Python."""

    def test_urls_a_browser_would_read_differently_are_refused(self):
        page_url = self.sources.page_url
        for bad in ("https://evil.example\\xueshu.baidu.com/p", "https://xueshu.baidu.com\\@evil.example/p", "https://xueshu.baidu.com/p\\q",
                    "https://xueshu.baidu.com%5c@evil.example/", "https://xueshu.baidu.com@evil.example/", "https://xueshu.baidu.com:443@evil.example/",
                    "https://x\u00fceshu.baidu.com/p", "https://xueshu.baidu.com./p", "https://xueshu_baidu.com/p", "https://xueshu.baidu.com/p\x00q",
                    "https://xueshu.baidu.com/p\nq", "//xueshu.baidu.com/p", "https:xueshu.baidu.com/p", "https://baidu.com.evil.example/p",
                    "https://xueshu.baidu.com:8443/p", "ftp://xueshu.baidu.com/p"):
            self.assertIsNone(page_url(bad, "baidu.com", upgrade=True), repr(bad))

    def test_ordinary_baidu_pages_pass(self):
        page_url = self.sources.page_url
        self.assertEqual(page_url("https://xueshu.baidu.com/usercenter/paper/show?paperid=a%2Fb&x=1#top", "baidu.com"),
                         "https://xueshu.baidu.com/usercenter/paper/show?paperid=a%2Fb&x=1#top")
        self.assertEqual(page_url("http://xueshu.baidu.com/p", "baidu.com", upgrade=True), "https://xueshu.baidu.com/p")
        self.assertIsNone(page_url("http://xueshu.baidu.com/p", "baidu.com"))
        self.assertEqual(page_url("https://XUESHU.Baidu.com/p", "baidu.com"), "https://xueshu.baidu.com/p")
        self.assertEqual(page_url("https://baidu.com/p", "baidu.com"), "https://baidu.com/p")

    def test_such_a_link_is_dropped_everywhere_a_page_is_read(self):
        hostile = "https://evil.example\\xueshu.baidu.com/p"
        payload = {"code": "0", "data": [{"paperId": "h1", "title": "链接有问题的论文", "doi": "", "url": hostile}]}
        self.assertIsNone(self.baidu_scholar.parse_search(payload)[0]["oa"])
        stored = {"pages": [{"source": "baidu_scholar", "url": hostile}], "via": ["baidu_scholar"]}
        self.assertEqual(self.sources.source_pages(stored), [])
        self.assertEqual(self.sources.pdf_availability(None, stored), "none")
        self.assertEqual(self.adapter().pdf_routes({"oa": stored}), [])
        self.assertEqual(self.source_adapters.pdf_routes({"oa": stored}), [])


class RequestTests(AdapterCase):
    def test_request_shape_and_where_the_key_goes(self):
        fake = FakeUrlopen(fixture("success.json"))
        with self.patched(fake):
            self.adapter().search("知识图谱")
        call = fake.calls[0]
        parts = urllib.parse.urlsplit(call["url"])
        self.assertEqual((parts.scheme, parts.hostname, parts.path), ("https", "qianfan.baidubce.com", "/v2/tools/baidu_scholar/search"))
        self.assertEqual(urllib.parse.parse_qs(parts.query), {"wd": ["知识图谱"], "pageNum": ["0"]})
        self.assertEqual(call["auth"], f"Bearer {DUMMY}")
        self.assertNotIn(DUMMY, call["url"])
        self.assertNotIn(urllib.parse.quote(DUMMY, safe=""), call["url"])
        self.assertNotIn("enable_ai_abstract", call["url"])
        self.assertNotIn("enable_abstract", call["url"])
        self.assertEqual(call["timeout"], 20)

    def test_the_header_is_unredirected_and_only_for_the_qianfan_host_over_https(self):
        adapter = self.adapter()
        request = adapter._request("https://qianfan.baidubce.com/v2/tools/baidu_scholar/search?wd=x&pageNum=0")
        self.assertEqual(request.get_header("Authorization"), f"Bearer {DUMMY}")
        self.assertNotIn("Authorization", request.headers)       # not copied to a redirect target
        for url in ("http://qianfan.baidubce.com/v2/x", "https://qianfan.baidubce.com.evil.example/x",
                    "https://evil.example/qianfan.baidubce.com", "https://xueshu.baidu.com/x"):
            self.assertIsNone(adapter._request(url).get_header("Authorization"), url)

    def test_page_number_is_zero_based_and_per_page_trims(self):
        fake = FakeUrlopen(fixture("success.json"))
        with self.patched(fake):
            papers = self.adapter().search("知识图谱", page=3, per_page=2)
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(fake.calls[0]["url"]).query)["pageNum"], ["2"])
        self.assertEqual(len(papers), 2)

    def test_since_drops_older_known_years_but_keeps_unknown_years(self):
        fake = FakeUrlopen(fixture("success.json"))
        with self.patched(fake):
            papers = self.adapter().search("知识图谱", since="2022-06-01", per_page=10)
        self.assertEqual([p["published"] for p in papers], ["2024-01-01", None])

    def test_invalid_queries_make_no_request_and_use_no_quota(self):
        fake = FakeUrlopen(fixture("success.json"))
        with self.patched(fake):
            for bad in ("", "   ", "\n\t", None):
                with self.assertRaises(self.sources.SourceError) as caught:
                    self.adapter().search(bad)
                self.assertEqual(caught.exception.kind, "invalid_input")
        self.assertEqual(fake.calls, [])
        self.assertEqual(self.counter_rows(), {})

    def test_control_characters_and_long_queries_are_cleaned(self):
        fake = FakeUrlopen(fixture("empty.json"))
        with self.patched(fake):
            self.adapter().search("知识\x00图谱\r\n  综述 " + "字" * 400)
        wd = urllib.parse.parse_qs(urllib.parse.urlsplit(fake.calls[0]["url"]).query)["wd"][0]
        self.assertTrue(wd.startswith("知识 图谱 综述 字字"), wd)     # a control character is a space; spaces collapse
        self.assertNotRegex(wd, r"[\x00-\x1f]")
        self.assertLessEqual(len(wd), 100)

    def test_without_a_key_nothing_is_sent_and_nothing_counted(self):
        fake = FakeUrlopen(fixture("success.json"))
        with self.patched(fake):
            with self.assertRaises(self.sources.SourceError) as caught:
                self.adapter(key=None).search("知识图谱")
        self.assertEqual(caught.exception.kind, "auth_required")
        self.assertEqual(fake.calls, [])
        self.assertEqual(self.counter_rows(), {})

    def test_failures_map_to_kinds_and_never_carry_the_key(self):
        cases = ((http_error(401), "auth_required"), (http_error(403), "auth_required"),
                 # a 429 is a per-second limit unless its body names the daily allowance: only the latter is "quota used up"
                 (http_error(429), "unavailable"),
                 (urllib.error.HTTPError("https://qianfan.baidubce.com/x", 429, "synthetic", {}, io.BytesIO(fixture("error_quota.json"))), "quota_exhausted"),
                 (http_error(500), "unavailable"), (http_error(503), "unavailable"), (http_error(400), "invalid_input"),
                 # measured 2026-10-23 with a valid key: the search address answers "404 page not found" when the service is
                 # not open to the account; that is the service being unavailable, never "no results"
                 (http_error(404), "unavailable"),
                 (urllib.error.URLError("dns failure " + DUMMY), "network_error"), (TimeoutError("slow " + DUMMY), "network_error"),
                 (fixture("html_body.html"), "bad_response"), (fixture("error_auth.json"), "auth_required"),
                 (fixture("error_quota.json"), "quota_exhausted"), (fixture("data_not_list.json"), "bad_response"))
        for answer, kind in cases:
            with self.subTest(kind=kind, answer=str(answer)[:30]):
                fake = FakeUrlopen(answer)
                with self.patched(fake):
                    with self.assertRaises(self.sources.SourceError) as caught:
                        self.adapter().search(f"词{kind}{len(fake.answers)}{id(answer)}")
                self.assertEqual(caught.exception.kind, kind)
                self.assertNotIn(DUMMY, str(caught.exception))
                self.assertEqual(len(fake.calls), 1)       # no retry: every request would spend the daily allowance

    def test_an_oversized_body_is_a_bad_response(self):
        fake = FakeUrlopen(b"{" + b" " * (3 * 1024 * 1024) + b"}")
        with self.patched(fake):
            with self.assertRaises(self.sources.SourceError) as caught:
                self.adapter().search("体积")
        self.assertEqual(caught.exception.kind, "bad_response")

    def test_empty_results_are_not_an_error(self):
        with self.patched(FakeUrlopen(fixture("empty.json"))):
            self.assertEqual(self.adapter().search("没有结果"), [])


class QuotaAndCacheTests(AdapterCase):
    def test_quota_is_reserved_before_the_request(self):
        seen = []

        def peek(request):
            seen.append(self.counter_rows())
        fake = FakeUrlopen(fixture("success.json"), on_call=peek)
        with self.patched(fake):
            self.adapter().search("知识图谱")
        self.assertEqual(list(seen[0].values()), ["1"])
        self.assertEqual(len(fake.calls), 1)

    def test_a_failed_request_still_counts(self):
        with self.patched(FakeUrlopen(http_error(500))):
            with self.assertRaises(self.sources.SourceError):
                self.adapter().search("会失败")
        self.assertEqual(list(self.counter_rows().values()), ["1"])

    def test_cap_reached_means_no_network_call(self):
        adapter = self.adapter(daily_cap=2)
        fake = FakeUrlopen(default=fixture("empty.json"))
        with self.patched(fake):
            adapter.search("一")
            adapter.search("二")
            with self.assertRaises(self.sources.SourceError) as caught:
                adapter.search("三")
        self.assertEqual(caught.exception.kind, "quota_exhausted")
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(adapter.usage_today(), 2)

    def test_the_default_cap_is_forty(self):
        self.assertEqual(self.adapter().daily_cap, 40)

    def test_a_cache_hit_uses_no_quota_and_no_network(self):
        fake = FakeUrlopen(fixture("success.json"))
        with self.patched(fake):
            first = self.adapter().search("知识图谱")
            second = self.adapter(key="another-dummy-key/0000000000").search("知识图谱")
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(list(self.counter_rows().values()), ["1"])
        self.assertEqual(first, second)

    def test_cache_files_are_named_from_the_url_and_hold_no_key_and_no_ai_text(self):
        with self.patched(FakeUrlopen(fixture("success.json"))):
            self.adapter().search("知识图谱")
        files = list((self.tmp / "cache" / "baidu_scholar").iterdir())
        self.assertEqual(len(files), 1)
        self.assertRegex(files[0].name, r"^[0-9a-f]{16}\.json$")
        content = files[0].read_text(encoding="utf-8")
        self.assertNotIn(DUMMY, content)
        self.assertNotIn(AI_TEXT, content)
        self.assertNotIn("aiAbstract", content)
        self.assertIn("synthetic-p1", content)

    def test_a_nested_ai_summary_is_not_cached_either(self):
        nested = {"code": "0", "data": [{"paperId": "n1", "title": "带嵌套摘要字段的论文", "doi": "", "url": "https://xueshu.baidu.com/p/n1",
                                         "extra": {"aiAbstract": AI_TEXT, "list": [{"ai_abstract": AI_TEXT}, {"keep": "x"}]}}], "ai_abstract": AI_TEXT}
        stripped = self.baidu_scholar.strip_ai_abstract(nested)
        self.assertNotIn(AI_TEXT, json.dumps(stripped, ensure_ascii=False))
        self.assertEqual(stripped["data"][0]["extra"]["list"][1], {"keep": "x"})
        with self.patched(FakeUrlopen(json.dumps(nested).encode())):
            self.adapter().search("嵌套")
        content = next((self.tmp / "cache" / "baidu_scholar").iterdir()).read_text(encoding="utf-8")
        self.assertNotIn(AI_TEXT, content)
        self.assertIn("n1", content)

    def test_an_expired_or_corrupt_cache_entry_is_refetched(self):
        fake = FakeUrlopen(default=fixture("success.json"))
        with self.patched(fake):
            adapter = self.adapter()
            adapter.search("知识图谱")
            path = next((self.tmp / "cache" / "baidu_scholar").iterdir())
            old = time.time() - 25 * 3600
            os.utime(path, (old, old))
            adapter.search("知识图谱")
            self.assertEqual(len(fake.calls), 2)
            path.write_text("{not json")
            adapter.search("知识图谱")
            self.assertEqual(len(fake.calls), 3)
            adapter.search("知识图谱")
            self.assertEqual(len(fake.calls), 3)       # the fresh copy is used again

    def test_an_error_answer_is_never_cached(self):
        with self.patched(FakeUrlopen(fixture("error_quota.json"), fixture("success.json"))) as fake:
            with self.assertRaises(self.sources.SourceError):
                self.adapter().search("知识图谱")
            self.assertEqual(len(self.adapter().search("知识图谱")), 5)

    def test_day_rollover_uses_the_utc_plus_8_date_and_prunes_old_counters(self):
        clock = {"now": datetime.datetime(2026, 10, 23, 15, 59, tzinfo=datetime.timezone.utc)}   # 23:59 on the 23rd in UTC+8
        adapter = self.adapter(daily_cap=2, now=lambda: clock["now"])
        old = "source_usage:baidu_scholar:2026-10-01"
        self.store.conn.execute("INSERT INTO settings(key,value) VALUES(?,?)", (old, "9"))
        self.store.conn.commit()
        with self.patched(FakeUrlopen(default=fixture("empty.json"))):
            adapter.search("一")
            adapter.search("二")
            with self.assertRaises(self.sources.SourceError):
                adapter.search("三")
            self.assertEqual(adapter.usage_today(), 2)
            clock["now"] += datetime.timedelta(minutes=2)       # 00:01 on the 24th in UTC+8
            self.assertEqual(adapter.usage_today(), 0)
            adapter.search("四")
        rows = self.counter_rows()
        self.assertEqual(rows["source_usage:baidu_scholar:2026-10-23"], "2")
        self.assertEqual(rows["source_usage:baidu_scholar:2026-10-24"], "1")
        self.assertNotIn(old, rows)

    def test_two_connections_never_reserve_more_than_the_cap(self):
        fake = FakeUrlopen(default=fixture("empty.json"))
        results = []

        def work(i):
            adapter = self.adapter(daily_cap=5)          # its own database connection
            try:
                adapter.search(f"并发{i}")
                results.append("ok")
            except self.sources.SourceError as exc:
                results.append(exc.kind)
        with self.patched(fake):
            threads = [threading.Thread(target=work, args=(i,)) for i in range(16)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(results.count("ok"), 5)
        self.assertEqual(results.count("quota_exhausted"), 11)
        self.assertEqual(len(fake.calls), 5)
        self.assertEqual(list(self.counter_rows().values()), ["5"])

    def test_the_counter_lives_in_the_settings_table_not_in_the_cache_folder(self):
        with self.patched(FakeUrlopen(fixture("empty.json"))):
            self.adapter().search("知识图谱")
        import shutil
        shutil.rmtree(self.tmp / "cache")          # what the clear-downloaded-information button does
        self.assertEqual(list(self.counter_rows().values()), ["1"])
        self.assertEqual(self.adapter().usage_today(), 1)

    def test_the_last_status_is_a_kind_and_a_time_only(self):
        with self.patched(FakeUrlopen(http_error(401))):
            with self.assertRaises(self.sources.SourceError):
                self.adapter().search("会失败")
        status = self.store.get_setting("source_status:baidu_scholar")
        self.assertEqual(set(status), {"kind", "at"})
        self.assertEqual(status["kind"], "auth_required")
        with self.patched(FakeUrlopen(fixture("empty.json"))):
            self.adapter().search("会成功")
        self.assertEqual(self.store.get_setting("source_status:baidu_scholar")["kind"], "ok")

    def test_the_dummy_key_appears_nowhere_on_disk_after_successes_and_failures(self):
        answers = (fixture("success.json"), http_error(401), urllib.error.URLError(DUMMY), fixture("error_quota.json"), fixture("html_body.html"))
        for i, answer in enumerate(answers):
            with self.patched(FakeUrlopen(answer)):
                try:
                    self.adapter().search(f"词{i}")
                except self.sources.SourceError:
                    pass
        self.store.conn.commit()
        needle = DUMMY.encode()
        for path in self.tmp.rglob("*"):
            if path.is_file():
                self.assertNotIn(needle, path.read_bytes(), str(path))
            self.assertNotIn(DUMMY, path.name)


class VerifyTests(AdapterCase):
    def test_verify_sends_one_fresh_request_with_a_fixed_word_and_stores_nothing(self):
        fake = FakeUrlopen(fixture("success.json"))
        before = self.store.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        with self.patched(fake):
            result = self.adapter().verify()
        self.assertTrue(result["ok"])
        self.assertEqual(len(fake.calls), 1)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(fake.calls[0]["url"]).query)
        self.assertEqual(query["wd"], [self.baidu_scholar.VERIFY_WORD])
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0], before)
        self.assertFalse((self.tmp / "cache" / "baidu_scholar").exists() and list((self.tmp / "cache" / "baidu_scholar").iterdir()))
        self.assertEqual(list(self.counter_rows().values()), ["1"])       # it does spend one of the provider's calls

    def test_verify_is_never_answered_from_the_cache(self):
        fake = FakeUrlopen(default=fixture("success.json"))
        with self.patched(fake):
            adapter = self.adapter()
            adapter.verify()
            adapter.verify()
        self.assertEqual(len(fake.calls), 2)

    def test_verify_uses_the_typed_key_and_not_the_saved_one(self):
        fake = FakeUrlopen(fixture("success.json"))
        typed = "typed-dummy-key/1111111111"
        with self.patched(fake):
            self.adapter(key="saved-dummy-key/2222222222").verify(api_key=typed)
        self.assertEqual(fake.calls[0]["auth"], f"Bearer {typed}")

    def test_verify_failures_have_kinds_and_a_missing_key_is_refused_locally(self):
        for answer, kind in ((http_error(401), "auth_required"), (urllib.error.URLError("x"), "network_error"), (fixture("error_quota.json"), "quota_exhausted")):
            with self.patched(FakeUrlopen(answer)):
                with self.assertRaises(self.sources.SourceError) as caught:
                    self.adapter().verify()
            self.assertEqual(caught.exception.kind, kind)
        fake = FakeUrlopen(fixture("success.json"))
        with self.patched(fake):
            with self.assertRaises(self.sources.SourceError) as caught:
                self.adapter(key=None).verify()
        self.assertEqual((caught.exception.kind, fake.calls), ("auth_required", []))

    def test_verify_respects_the_local_cap(self):
        adapter = self.adapter(daily_cap=1)
        fake = FakeUrlopen(default=fixture("success.json"))
        with self.patched(fake):
            adapter.verify()
            with self.assertRaises(self.sources.SourceError) as caught:
                adapter.verify()
        self.assertEqual((caught.exception.kind, len(fake.calls)), ("quota_exhausted", 1))


class OpenAlexAdapterTests(AdapterCase):
    def client(self, key=None):
        return self.sources.OpenAlex(self.tmp / "oa-cache", api_key=key)

    def test_info_and_verify_with_a_typed_key(self):
        fake = FakeUrlopen(json.dumps({"results": []}).encode())
        client = self.client(key="saved-openalex-key-0000")
        self.assertEqual(client.info.id, "openalex")
        self.assertEqual(client.info.key, "required")
        with mock.patch.object(self.sources.urllib.request, "urlopen", fake):
            result = client.verify(api_key="typed-openalex-key-1111")
        self.assertTrue(result["ok"])
        self.assertEqual(fake.calls[0]["auth"], "Bearer typed-openalex-key-1111")
        self.assertTrue(fake.calls[0]["url"].startswith("https://api.openalex.org/works?"))
        self.assertNotIn("openalex-key", fake.calls[0]["url"])
        self.assertEqual(client.api_key, "saved-openalex-key-0000")        # nothing stored on the client
        self.assertFalse((self.tmp / "oa-cache").exists() and list((self.tmp / "oa-cache").glob("*.json")))

    def test_verify_without_any_key_works_anonymously_and_a_wrong_key_is_auth_required(self):
        with mock.patch.object(self.sources.urllib.request, "urlopen", FakeUrlopen(b"{}")) as fake_open:
            self.assertTrue(self.client().verify()["ok"])
        with mock.patch.object(self.sources.urllib.request, "urlopen", FakeUrlopen(http_error(401))):
            with self.assertRaises(self.sources.SourceError) as caught:
                self.client(key="wrong-openalex-key-000").verify()
        self.assertEqual(caught.exception.kind, "auth_required")
        self.assertNotIn("wrong-openalex-key", str(caught.exception))

    def test_verify_is_fresh_every_time(self):
        fake = FakeUrlopen(default=b"{}")
        client = self.client()
        with mock.patch.object(self.sources.urllib.request, "urlopen", fake):
            client.verify()
            client.verify()
        self.assertEqual(len(fake.calls), 2)

    def test_search_is_relevance_discovery(self):
        client = self.client()
        with mock.patch.object(client, "discover_topic", return_value=[{"key": "k"}]) as discover:
            self.assertEqual(client.search("world model", since="2024-01-01", page=2, per_page=7), [{"key": "k"}])
        kwargs = discover.call_args.kwargs
        self.assertEqual((kwargs["per_page"], kwargs["from_date"], kwargs["page"], kwargs["order"]), (7, "2024-01-01", 2, "relevance"))


class PdfRouteTests(AdapterCase):
    ROUTE_FIELDS = {"kind", "url", "auto", "needs_login", "label"}

    def test_baidu_contributes_only_its_own_login_page(self):
        paper = self.baidu_scholar.parse_search(json.loads(fixture("success.json")))[0]
        routes = self.adapter().pdf_routes(paper)
        self.assertEqual(len(routes), 1)
        route = routes[0]
        self.assertEqual(set(route), self.ROUTE_FIELDS)
        self.assertEqual((route["kind"], route["auto"], route["needs_login"]), ("source_page", False, True))
        self.assertTrue(route["url"].startswith("https://xueshu.baidu.com/"))

    def test_baidu_routes_from_stored_oa_json_and_hostile_pages_are_dropped(self):
        paper = {"oa_json": json.dumps({"pages": [{"source": "baidu_scholar", "url": "https://evil.example/x"},
                                                  {"source": "baidu_scholar", "url": "http://xueshu.baidu.com/x"},
                                                  {"source": "other", "url": "https://xueshu.baidu.com/y"}]})}
        self.assertEqual(self.adapter().pdf_routes(paper), [])
        self.assertEqual(self.adapter().pdf_routes({"oa_json": "{not json"}), [])
        self.assertEqual(self.adapter().pdf_routes({}), [])

    def test_openalex_routes_are_arxiv_then_pdf_links_then_the_landing_page(self):
        client = self.sources.OpenAlex(self.tmp / "oa")
        paper = {"arxiv_id": "2603.19312", "oa": {"pdf_urls": ["https://a.example/p.pdf", "http://insecure.example/p.pdf"],
                                                  "landing_page": "https://a.example/landing"}}
        routes = client.pdf_routes(paper)
        self.assertEqual([r["kind"] for r in routes], ["arxiv_pdf", "oa_pdf", "landing"])
        self.assertEqual([r["auto"] for r in routes], [True, True, False])
        self.assertEqual([r["needs_login"] for r in routes], [False, False, False])
        self.assertEqual(routes[0]["url"], "https://arxiv.org/pdf/2603.19312")
        for route in routes:
            self.assertEqual(set(route), self.ROUTE_FIELDS)
            self.assertTrue(route["url"].startswith("https://"))
        self.assertEqual(client.pdf_routes({}), [])


class MergeOaTests(AdapterCase):
    OPENALEX = {"is_oa": True, "oa_status": "green", "pdf_urls": ["https://a.example/p.pdf"], "landing_page": "https://a.example/l",
                "license": "cc-by", "version": "publishedVersion"}
    BAIDU = {"pages": [{"source": "baidu_scholar", "url": "https://xueshu.baidu.com/a"}], "via": ["baidu_scholar"]}

    def test_neither_source_wipes_the_other_in_either_order(self):
        merge = self.sources.merge_oa
        a = merge(merge(None, self.OPENALEX), self.BAIDU)
        b = merge(merge(None, self.BAIDU), self.OPENALEX)
        for merged in (a, b):
            self.assertEqual({k: merged[k] for k in self.OPENALEX}, self.OPENALEX)
            self.assertEqual(merged["pages"], self.BAIDU["pages"])
            self.assertEqual(merged["via"], ["baidu_scholar"])

    def test_a_newer_openalex_report_replaces_its_own_fields_only(self):
        old = self.sources.merge_oa(self.OPENALEX, self.BAIDU)
        new = {**self.OPENALEX, "is_oa": False, "oa_status": "closed", "pdf_urls": [], "landing_page": None}
        merged = self.sources.merge_oa(old, new)
        self.assertEqual((merged["is_oa"], merged["pdf_urls"], merged["landing_page"]), (False, [], None))
        self.assertEqual(merged["pages"], self.BAIDU["pages"])

    def test_pages_and_via_are_combined_without_duplicates(self):
        again = {"pages": [{"source": "baidu_scholar", "url": "https://xueshu.baidu.com/a"},
                           {"source": "baidu_scholar", "url": "https://xueshu.baidu.com/b"}], "via": ["baidu_scholar", "other"]}
        merged = self.sources.merge_oa(self.BAIDU, again)
        self.assertEqual([p["url"] for p in merged["pages"]], ["https://xueshu.baidu.com/a", "https://xueshu.baidu.com/b"])
        self.assertEqual(merged["via"], ["baidu_scholar", "other"])

    def test_none_and_junk_inputs(self):
        merge = self.sources.merge_oa
        self.assertIsNone(merge(None, None))
        self.assertEqual(merge(self.OPENALEX, None), self.OPENALEX)
        self.assertEqual(merge("not a dict", self.BAIDU), self.BAIDU)
        self.assertEqual(merge(self.BAIDU, "junk"), self.BAIDU)

    def test_upsert_papers_merges_in_both_orders(self):
        for order in ("openalex-first", "baidu-first"):
            with self.subTest(order):
                key = f"https://doi.org/10.1/{order}"
                oa_paper = {"key": key, "title": "T", "oa": self.OPENALEX}
                baidu_paper = {"key": key, "title": "T", "oa": self.BAIDU}
                first, second = (oa_paper, baidu_paper) if order == "openalex-first" else (baidu_paper, oa_paper)
                self.store.upsert_papers([dict(first)])
                self.store.upsert_papers([dict(second)])
                stored = json.loads(self.store.paper(key)["oa_json"])
                self.assertEqual(stored["pdf_urls"], ["https://a.example/p.pdf"])
                self.assertEqual(stored["pages"], self.BAIDU["pages"])

    def test_set_paper_oa_merges_and_none_still_clears(self):
        self.store.upsert_papers([{"key": "k", "title": "T", "oa": self.BAIDU}])
        self.store.set_paper_oa("k", self.OPENALEX)
        stored = json.loads(self.store.paper("k")["oa_json"])
        self.assertEqual((stored["pdf_urls"], stored["pages"]), (["https://a.example/p.pdf"], self.BAIDU["pages"]))
        self.store.set_paper_oa("k", None)
        self.assertIsNone(self.store.paper("k")["oa_json"])

    def test_upsert_with_a_corrupt_stored_value_replaces_it(self):
        self.store.upsert_papers([{"key": "k", "title": "T"}])
        self.store.conn.execute("UPDATE papers SET oa_json='{not json' WHERE key='k'")
        self.store.upsert_papers([{"key": "k", "title": "T", "oa": self.BAIDU}])
        self.assertEqual(json.loads(self.store.paper("k")["oa_json"])["pages"], self.BAIDU["pages"])

    def test_baidu_upsert_does_not_touch_language_title_or_abstract_of_an_openalex_row(self):
        key = "https://doi.org/10.1234/kg.2024.001"
        self.store.upsert_papers([{"key": key, "title": "Knowledge graph survey", "abstract": "English abstract.",
                                   "metadata_language": "en", "metadata_language_source": "OpenAlex", "oa": self.OPENALEX}])
        papers = self.baidu_scholar.parse_search(json.loads(fixture("success.json")))
        self.store.upsert_papers([p for p in papers if p["key"] == key])
        row = self.store.paper(key)
        self.assertEqual((row["title"], row["abstract"], row["metadata_language"]), ("Knowledge graph survey", "English abstract.", "en"))
        self.assertEqual(json.loads(row["oa_json"])["is_oa"], True)


class SwitchTests(AdapterCase):
    def settings(self, **values):
        (self.tmp / "settings.json").write_text(json.dumps(values))
        from app import user_settings
        return user_settings

    def test_baidu_is_off_by_default_and_must_be_boolean(self):
        user_settings = self.settings()
        self.assertFalse(user_settings.baidu_scholar(self.tmp))
        self.assertTrue(self.settings(sourceBaiduScholar=True).baidu_scholar(self.tmp))
        self.assertFalse(self.settings(sourceBaiduScholar="yes").baidu_scholar(self.tmp))
        self.assertEqual(user_settings.validate({"sourceBaiduScholar": True})["sourceBaiduScholar"], True)
        with self.assertRaises(ValueError):
            user_settings.validate({"sourceBaiduScholar": "yes"})
        self.assertEqual(user_settings.validate({"baiduScholarConfirmed": True})["baiduScholarConfirmed"], True)
        with self.assertRaises(ValueError):
            user_settings.validate({"baiduScholarConfirmed": 1})

    def test_one_rule_decides_which_switch_governs_a_paper(self):
        arxiv = {"key": "a", "arxiv_id": "2601.00001"}
        journal = {"key": "j", "openalex_id": "https://openalex.org/W1", "source": "Nature"}
        baidu_only = {"key": "baidu:x", "oa": {"via": ["baidu_scholar"], "pages": []}}
        baidu_stored = {"key": "baidu:y", "oa_json": json.dumps({"via": ["baidu_scholar"]})}
        both = {"key": "https://doi.org/10.1/z", "openalex_id": "https://openalex.org/W2", "oa": {"via": ["baidu_scholar"]}}
        cases = [
            (dict(sourceArxiv=True, sourceOpenAlex=True, sourceBaiduScholar=False), [True, True, False, False, True]),
            (dict(sourceArxiv=False, sourceOpenAlex=False, sourceBaiduScholar=True), [False, False, True, True, True]),
            (dict(sourceArxiv=True, sourceOpenAlex=False, sourceBaiduScholar=False), [True, False, False, False, False]),
        ]
        for values, expected in cases:
            user_settings = self.settings(**values)
            got = [user_settings.source_allowed(self.tmp, p) for p in (arxiv, journal, baidu_only, baidu_stored, both)]
            self.assertEqual(got, expected, values)

    def test_the_policy_object_gives_the_same_answers(self):
        user_settings = self.settings(sourceArxiv=False, sourceOpenAlex=True, sourceBaiduScholar=False)
        policy = user_settings.source_policy(self.tmp)
        self.assertEqual((policy.arxiv, policy.general, policy.baidu), (False, True, False))
        self.assertFalse(policy.allows({"arxiv_id": "2601.00001"}))
        self.assertTrue(policy.allows({"key": "j", "openalex_id": "https://openalex.org/W1"}))


class SourcesDocTests(AdapterCase):
    DOC = ROOT / "docs" / "SOURCES.md"

    def sections(self):
        text = self.DOC.read_text(encoding="utf-8")
        parts = re.split(r"^## ", text, flags=re.M)[1:]
        return {p.split("\n", 1)[0].strip(): p for p in parts}

    def test_every_registered_source_is_documented_with_the_same_key_requirement(self):
        sections = self.sections()
        words = {"none": "无需密钥", "optional": "密钥可选", "required": "必须有密钥"}
        for info in self.source_adapters.all_infos():
            with self.subTest(info.id):
                heading = next((h for h in sections if f"`{info.id}`" in h), None)
                self.assertIsNotNone(heading, f"docs/SOURCES.md has no section for {info.id}")
                body = sections[heading]
                self.assertIn(words[info.key], body)
                for other in set(words.values()) - {words[info.key]}:
                    self.assertNotIn(other, body, f"{info.id} disagrees with its SourceInfo")
                if info.key != "none":
                    self.assertIn(info.key_url, body)
                    self.assertIn(info.key_env, body)
                if info.daily_cap:
                    self.assertIn(str(info.daily_cap), body)

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
