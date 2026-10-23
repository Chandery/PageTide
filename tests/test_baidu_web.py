"""Baidu AI Search restricted to xueshu.baidu.com (source `baidu_web`): parser, request, quota, cache, errors, key sharing.

Offline only: urlopen is replaced by a fake. tests/fixtures/baidu_web/success.json is a trimmed copy of a REAL answer
(2026-10-23, query 知识图谱, no key inside); the error shapes are unverified synthetic ones. Every key here is a dummy.
"""
import datetime
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURES = ROOT / "tests" / "fixtures" / "baidu_web"
DUMMY = "bce-v3/ALTAK-dummyDummy0000/dummydummydummydummy0000"
PAGE = "https://xueshu.baidu.com/usercenter/paper/show?paperid="
ID_1 = "146x0jv0634t0m60eb250a40yw135131"
SEARCH_URL = "https://qianfan.baidubce.com/v2/ai_search/web_search"
SENTINEL = "MARKDOWN-OR-SNIPPET-TEXT-THAT-MUST-NOT-BE-CACHED"


def fixture(name):
    return (FIXTURES / name).read_bytes()


class Reply:
    def __init__(self, body):
        self.body, self.headers = body, {}

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
            self.calls.append({"url": request.full_url, "auth": request.get_header("Authorization"), "method": request.get_method(),
                               "data": request.data, "headers": dict(request.header_items()), "timeout": timeout})
            answer = self.answers.pop(0) if self.answers else self.default
        if self.on_call:
            self.on_call(request)
        if isinstance(answer, BaseException):
            raise answer
        return Reply(answer)

    def bodies(self):
        return [json.loads(c["data"].decode("utf-8")) for c in self.calls]


def http_error(code):
    return urllib.error.HTTPError(SEARCH_URL, code, "synthetic", {}, None)


def answer(*references):
    return json.dumps({"request_id": "r", "references": list(references)}, ensure_ascii=False).encode()


def reference(paper_id="abc123", title="一个中文论文题目", content=None, date="2026-10-19 00:00:00", url=None):
    return {"id": 1, "url": url if url is not None else PAGE + paper_id, "title": title, "date": date, "type": "web", "website": "百度学术",
            "content": content if content is not None else f"{title} 来自 掌桥科研  喜欢0 阅读量: 4 作者: 张三 , 李四 摘要: 这是一段足够长的中文摘要内容，用来测试解析。 关键词: 图谱 本体  年份: 2026 "}


class WebCase(unittest.TestCase):
    def setUp(self):
        from app import baidu_scholar, baidu_web, source_adapters, sources
        from app.db import Store
        self.baidu_scholar, self.baidu_web, self.source_adapters, self.sources = baidu_scholar, baidu_web, source_adapters, sources
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
        return self.baidu_web.BaiduWeb(self.tmp / "cache" / "baidu_web", self.tmp / "db.sqlite", api_key=key, **kwargs)

    def counter_rows(self):
        return dict(self.store.conn.execute("SELECT key, value FROM settings WHERE key LIKE 'source_usage:%'").fetchall())

    def patched(self, fake):
        return mock.patch.object(urllib.request, "urlopen", fake)

    def parse(self, name="success.json"):
        return self.baidu_web.parse_search(json.loads(fixture(name)))


class InfoTests(WebCase):
    def test_the_source_is_registered_last_and_shares_the_key_of_baidu_scholar(self):
        infos = {i.id: i for i in self.source_adapters.all_infos()}
        self.assertEqual(list(infos), ["arxiv", "openalex", "baidu_scholar", "baidu_web"])
        web, scholar = infos["baidu_web"], infos["baidu_scholar"]
        self.assertEqual((web.key, web.daily_cap, web.serves_languages, web.query_scripts), ("required", 40, ("zh",), ("cjk",)))
        self.assertEqual(web.key_shared_with, "baidu_scholar")
        self.assertEqual((web.key_env, web.key_pattern, web.key_url), (scholar.key_env, scholar.key_pattern, scholar.key_url))
        self.assertEqual(scholar.key_shared_with, "")
        self.assertEqual(web.claims_id, "CH-BAIDU-WEB-SEARCH")
        self.assertIs(self.source_adapters.info("baidu_web"), web)

    def test_the_claim_is_registered_in_the_external_facts(self):
        claims = {s["id"]: s for s in json.loads((ROOT / "harness" / "sources.json").read_text())["sources"]}
        claim = claims["CH-BAIDU-WEB-SEARCH"]
        self.assertEqual((claim["url"], claim["verified_on"]), ("https://cloud.baidu.com/doc/qianfan/s/2mh4su4uy", "2026-10-23"))
        self.assertIn("xueshu.baidu.com", claim["claim"])
        self.assertIn("UNVERIFIED", claim["verification"].upper())
        self.assertIn("CH-WANFANG-OPEN", claims)
        self.assertEqual(claims["CH-WANFANG-OPEN"]["verified_on"], "2026-10-23")
        self.assertNotIn(DUMMY, json.dumps(claims))

    def test_the_adapter_has_the_interface(self):
        adapter = self.adapter()
        for name in ("search", "verify", "pdf_routes"):
            self.assertTrue(callable(getattr(adapter, name)), name)
        self.assertEqual(adapter.info.id, "baidu_web")
        self.assertEqual(adapter.daily_cap, 40)


class ParseTests(WebCase):
    def test_the_real_answer_gives_four_papers_and_leaves_the_patent_out(self):
        papers = self.parse()
        self.assertEqual(len(papers), 4)
        self.assertEqual([p["key"] for p in papers][0], "baidu:" + ID_1)
        self.assertNotIn("申请", json.dumps(papers, ensure_ascii=False))             # the patent is not a paper

    def test_each_paper_is_mapped_field_by_field(self):
        first = self.parse()[0]
        self.assertEqual(first["title"], "基于本体的生物安全知识图谱构建研究")        # the trailing space of the answer is gone
        self.assertEqual(first["published"], "2026-10-19")
        self.assertEqual((first["doi"], first["openalex_id"], first["arxiv_id"], first["source"]), (None, None, None, None))
        self.assertEqual((first["topic"], first["group_name"], first["authors"]), ("生物安全", "field", []))
        self.assertEqual(first["oa"], {"pages": [{"source": "baidu_web", "url": PAGE + ID_1}], "via": ["baidu_web"]})
        self.assertTrue(all(p["oa"]["via"] == ["baidu_web"] for p in self.parse()))
        self.assertNotIn("metadata_language", first)                                # Baidu reports no language
        self.assertNotIn("language", first)

    def test_the_abstract_has_no_title_no_noise_no_authors_and_no_keywords(self):
        first = self.parse()[0]
        self.assertTrue(first["abstract"].startswith("[目的/意义]为推动生物安全领域知识组织与创新"))
        self.assertTrue(first["abstract"].endswith("为生物安全领域智能服务和决策支持提供知识基础."))
        for noise in ("来自", "掌桥科研", "喜欢", "阅读量", "作者:", "刘超", "摘要:", "关键词", "年份", "基于本体的生物安全知识图谱构建研究"):
            self.assertNotIn(noise, first["abstract"], noise)

    def test_content_is_split_into_authors_abstract_and_keywords(self):
        content = json.loads(fixture("success.json"))["references"][0]["content"]
        parsed = self.baidu_web.parse_content(content, "基于本体的生物安全知识图谱构建研究 ")
        self.assertEqual(parsed["authors"], ["刘超", "刘敏", "方铭勇"])
        self.assertEqual(parsed["keywords"], ["生物安全", "知识图谱", "本体", "外来入侵生物"])
        self.assertTrue(parsed["abstract"].startswith("[目的/意义]"))
        self.assertFalse(parsed["patent"])

    def test_an_answer_whose_content_starts_with_the_abstract_still_has_one(self):
        third = json.loads(fixture("success.json"))["references"][2]
        parsed = self.baidu_web.parse_content(third["content"], third["title"])
        self.assertEqual(parsed["authors"], [])
        self.assertTrue(parsed["abstract"].startswith("[目的/意义]针对单一数据源"))
        self.assertEqual(parsed["keywords"], ["多源文献融合", "学术知识图谱", "实体消歧", "文献计量学", "大模型"])

    def test_without_a_marker_a_long_remainder_is_the_abstract_and_a_short_one_is_not(self):
        text = "文章针对这个现实困境试图创建起一个以人工智能技术为主要支撑的品牌数字化传播和应用体系并开展实践研究。"
        self.assertGreaterEqual(len(text), 40)
        parsed = self.baidu_web.parse_content(" " + text, "题目")
        self.assertEqual((parsed["abstract"], parsed["keywords"], parsed["authors"]), (text, [], []))
        short = self.baidu_web.parse_content("题目 来自 某站  喜欢0 阅读量: 1 很短的一句话。", "题目")
        self.assertEqual(short["abstract"], "")
        self.assertEqual(self.baidu_web.parse_content("", "题目")["abstract"], "")
        self.assertEqual(self.baidu_web.parse_content(None, "题目")["abstract"], "")

    def test_the_real_item_without_a_marker_keeps_its_whole_text_as_the_abstract(self):
        papers = {p["key"]: p for p in self.parse()}
        sixth = next(p for k, p in papers.items() if p["title"].startswith("基于人工智能传统艺术设计"))
        self.assertTrue(sixth["abstract"].startswith("蜀绣是中国重要的文化瑰宝之一"))
        self.assertIsNone(sixth["topic"])

    def test_a_patent_is_recognised_by_its_application_number(self):
        patent = json.loads(fixture("success.json"))["references"][-1]
        self.assertTrue(self.baidu_web.parse_content(patent["content"], patent["title"])["patent"])
        payload = {"references": [reference(content="某发明 喜欢0 阅读量: 1 申请(专利)号: 2025104996 申请(专利权)人: 某公司 发明人: 张三 , 李四")]}
        self.assertEqual(self.baidu_web.parse_search(payload), [])

    def test_keywords_are_capped_and_split_on_spaces_and_commas(self):
        many = " ".join(f"词{i}" for i in range(40))
        parsed = self.baidu_web.parse_content(f"摘要: {'中文摘要内容。' * 10} 关键词: {many}  年份: 2026", "")
        self.assertEqual(len(parsed["keywords"]), 20)
        parsed = self.baidu_web.parse_content("摘要: 内容内容内容。 关键词: 甲，乙;丙 丁、戊 " + "长" * 200, "")
        self.assertEqual(parsed["keywords"][:4], ["甲", "乙", "丙", "丁"])
        self.assertTrue(all(len(k) <= 80 for k in parsed["keywords"]))

    def test_the_text_after_the_marker_is_the_abstract_up_to_the_keywords_or_the_year(self):
        parsed = self.baidu_web.parse_content("题 作者: 甲 摘要: 只有摘要没有关键词。 年份: 2025 ", "题")
        self.assertEqual((parsed["abstract"], parsed["keywords"], parsed["authors"]), ("只有摘要没有关键词。", [], ["甲"]))
        parsed = self.baidu_web.parse_content("题 摘要: 摘要到结尾", "题")
        self.assertEqual(parsed["abstract"], "摘要到结尾")

    def test_the_key_is_the_paper_id_of_the_page_and_odd_ids_get_a_stable_hash(self):
        self.assertEqual(self.parse()[1]["key"], "baidu:1f0g00n0et2x0rv0pf3r08t03p154122")
        odd = self.baidu_web.parse_search(json.loads(answer(reference(url="https://xueshu.baidu.com/usercenter/paper/show?paperid=a%20b%2Fc"))))[0]
        again = self.baidu_web.parse_search(json.loads(answer(reference(url="https://xueshu.baidu.com/usercenter/paper/show?paperid=a%20b%2Fc"))))[0]
        self.assertRegex(odd["key"], r"^baidu:t-[0-9a-f]{16}$")
        self.assertEqual(odd["key"], again["key"])
        none = self.baidu_web.parse_search(json.loads(answer(reference(url="https://xueshu.baidu.com/s?wd=x"))))[0]
        self.assertRegex(none["key"], r"^baidu:t-[0-9a-f]{16}$")

    def test_only_https_xueshu_pages_are_kept(self):
        def page(url):
            out = self.baidu_web.parse_search(json.loads(answer(reference(url=url))))
            return out[0]["oa"]["pages"] or None           # `via` stays even without a page: it is what the web switch governs by
        self.assertEqual(page("http://xueshu.baidu.com/usercenter/paper/show?paperid=a1")[0]["url"],
                         "https://xueshu.baidu.com/usercenter/paper/show?paperid=a1")           # http is upgraded
        for bad in ("https://www.baidu.com/s?wd=x", "https://xueshu.baidu.com.evil.example/p?paperid=a1", "https://evil.example/xueshu.baidu.com",
                    "https://xueshu.baidu.com\\@evil.example/p", "https://user@xueshu.baidu.com/p", "javascript:alert(1)", "", "https://xueshu.baidu.com:8443/p",
                    "https://baike.baidu.com/item/x", "ftp://xueshu.baidu.com/p"):
            self.assertIsNone(page(bad), bad)                    # the paper stays, without a page

    def test_a_paper_without_a_page_still_says_which_source_reported_it(self):
        out = self.baidu_web.parse_search(json.loads(answer(reference(url=""))))
        self.assertEqual(out[0]["oa"], {"pages": [], "via": ["baidu_web"]})

    def test_titles_are_compared_without_case_spaces_and_punctuation(self):
        mark = self.baidu_web.title_mark
        self.assertEqual(mark("基于本体的 生物安全知识图谱构建研究。"), mark("基于本体的生物安全知识图谱构建研究 "))
        self.assertEqual(mark("Knowledge-Graph  Survey"), mark("knowledge graph survey"))
        self.assertNotEqual(mark("知识图谱"), mark("知识图谱综述"))
        self.assertEqual(mark(None), "")

    def test_the_date_keeps_the_day_and_a_bad_date_is_unknown(self):
        def published(date):
            return self.baidu_web.parse_search(json.loads(answer(reference(date=date))))[0]["published"]
        self.assertEqual(published("2026-10-07 19:49:37"), "2026-10-07")
        self.assertEqual(published("2026-10-07"), "2026-10-07")
        for bad in ("", None, "2026-13-45 00:00:00", "yesterday", "0000-01-01 00:00:00", 20261007, "1-1-1"):
            self.assertIsNone(published(bad), bad)

    def test_a_paper_without_a_title_is_dropped_and_junk_items_are_skipped(self):
        payload = {"references": [reference(title="  "), "x", None, 5, [], reference(paper_id="ok1")]}
        self.assertEqual([p["key"] for p in self.baidu_web.parse_search(payload)], ["baidu:ok1"])

    def test_empty_is_empty_and_a_missing_content_gives_a_paper_without_abstract(self):
        self.assertEqual(self.parse("empty.json"), [])
        out = self.baidu_web.parse_search({"references": [{"title": "只有标题的论文题目", "url": PAGE + "t1", "date": "2026-01-02 00:00:00"}]})
        self.assertEqual((out[0]["abstract"], out[0]["topic"], out[0]["published"]), ("", None, "2026-01-02"))

    def test_long_text_is_bounded(self):
        out = self.baidu_web.parse_search({"references": [reference(title="题" * 900, content="摘要: " + "长" * 20000)]})
        self.assertLessEqual(len(out[0]["title"]), 500)
        self.assertLessEqual(len(out[0]["abstract"]), 10000)

    def test_upsert_papers_accepts_the_output(self):
        papers = self.parse()
        for paper in papers:
            paper["project_id"] = None
        self.store.upsert_papers(papers)
        row = self.store.paper("baidu:" + ID_1)
        self.assertEqual((row["title"], row["published"], row["topic"]), ("基于本体的生物安全知识图谱构建研究", "2026-10-19", "生物安全"))
        self.assertIsNone(row["metadata_language"])
        self.assertEqual(json.loads(row["oa_json"])["via"], ["baidu_web"])

    def test_malformed_and_error_payloads_raise_a_kind(self):
        parse = self.baidu_web.parse_search
        SourceError = self.sources.SourceError

        def kind(payload):
            with self.assertRaises(SourceError) as caught:
                parse(payload)
            return caught.exception.kind
        self.assertEqual(kind("text"), "bad_response")
        self.assertEqual(kind(None), "bad_response")
        self.assertEqual(kind([]), "bad_response")
        self.assertEqual(kind({"request_id": "x"}), "bad_response")
        self.assertEqual(kind({"references": None}), "bad_response")
        self.assertEqual(kind({"references": {"a": 1}}), "bad_response")
        self.assertEqual(kind(json.loads(fixture("references_not_list.json"))), "bad_response")
        self.assertEqual(kind(json.loads(fixture("error_auth.json"))), "auth_required")
        self.assertEqual(kind(json.loads(fixture("error_quota.json"))), "quota_exhausted")
        self.assertEqual(kind({"code": 500, "message": "internal server problem"}), "unavailable")
        self.assertEqual(kind({"error": {"code": "x1", "message": "Token is invalid"}}), "auth_required")
        self.assertEqual(kind({"error": {"type": "limit", "message": "too many requests"}}), "quota_exhausted")
        self.assertEqual(kind({"code": "0"}), "bad_response")                       # a success code without references is not an answer

    def test_an_error_code_with_references_is_still_an_error(self):
        with self.assertRaises(self.sources.SourceError) as caught:
            self.baidu_web.parse_search({"code": 216003, "message": "bad key", "references": []})
        self.assertEqual(caught.exception.kind, "auth_required")

    def test_the_provider_text_never_reaches_the_error(self):
        with self.assertRaises(self.sources.SourceError) as caught:
            self.baidu_web.parse_search({"code": "216003", "message": "key " + DUMMY + " refused"})
        self.assertNotIn(DUMMY, str(caught.exception))
        self.assertNotIn("refused", str(caught.exception))


class QueryTests(WebCase):
    def test_units_count_a_chinese_character_twice(self):
        units = self.baidu_web.query_units
        self.assertEqual((units("abc"), units("知识"), units("知识 graph"), units("")), (3, 4, 10, 0))

    def test_a_long_query_is_cut_to_the_limit_of_72_units(self):
        clean = self.baidu_web.clean_query
        cut = clean("知" * 80)
        self.assertEqual((len(cut), self.baidu_web.query_units(cut)), (36, 72))
        self.assertEqual(clean("a" * 100), "a" * 72)
        mixed = clean("知识图谱" * 5 + " knowledge graph construction methods and applications in biology")
        self.assertLessEqual(self.baidu_web.query_units(mixed), 72)
        self.assertTrue(mixed.startswith("知识图谱知识图谱"))
        self.assertEqual(clean("知识图谱"), "知识图谱")

    def test_the_cut_does_not_leave_a_trailing_space(self):
        cut = self.baidu_web.clean_query("知" * 35 + " " + "x" * 10)
        self.assertEqual(cut, cut.strip())
        self.assertLessEqual(self.baidu_web.query_units(cut), 72)

    def test_control_characters_and_blank_input(self):
        clean = self.baidu_web.clean_query
        self.assertEqual(clean("  知识\n\t图谱\x00    x "), "知识 图谱 x")
        for junk in (None, 5, "", "   ", "\n\x00"):
            self.assertEqual(clean(junk), "")


class RequestTests(WebCase):
    def test_the_body_has_exactly_the_documented_fields(self):
        fake = FakeUrlopen(fixture("success.json"))
        with self.patched(fake):
            self.adapter().search("知识图谱", per_page=20)
        call = fake.calls[0]
        self.assertEqual((call["method"], call["url"], call["timeout"]), ("POST", SEARCH_URL, 20))
        self.assertEqual(fake.bodies()[0], {
            "messages": [{"role": "user", "content": "知识图谱"}], "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": 20}], "search_filter": {"match": {"site": ["xueshu.baidu.com"]}}})
        headers = {k.lower(): v for k, v in call["headers"].items()}
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(call["auth"], f"Bearer {DUMMY}")

    def test_only_web_results_are_asked_for_and_nothing_else(self):
        body = json.loads(self.baidu_web.request_body("知识图谱", 5, None))
        self.assertEqual(set(body), {"messages", "search_source", "resource_type_filter", "search_filter"})
        self.assertEqual(body["resource_type_filter"], [{"type": "web", "top_k": 5}])
        self.assertEqual(body["search_filter"], {"match": {"site": ["xueshu.baidu.com"]}})
        text = json.dumps(body)
        for absent in ("video", "image", "aladdin", "range", "page_time", "edition", "markdown"):
            self.assertNotIn(absent, text)

    def test_recency_is_a_filter_only_when_given_and_known(self):
        def body(recency):
            fake = FakeUrlopen(fixture("empty.json"))
            with self.patched(fake):
                self.adapter(daily_cap=99).search("知识图谱" + str(recency), recency=recency)
            return fake.bodies()[0]
        for name in ("week", "month", "semiyear", "year"):
            self.assertEqual(body(name)["search_recency_filter"], name)
        for bad in (None, "", "decade", "WEEK", 7, "all"):
            self.assertNotIn("search_recency_filter", body(bad), bad)

    def test_the_body_does_not_depend_on_dict_order_and_keeps_chinese_readable(self):
        first = self.baidu_web.request_body("知识图谱", 12, "month")
        self.assertEqual(first, self.baidu_web.request_body("知识图谱", 12, "month"))
        self.assertIn("知识图谱".encode("utf-8"), first)

    def test_top_k_follows_per_page_within_one_to_fifty(self):
        def top_k(per_page):
            fake = FakeUrlopen(fixture("empty.json"))
            with self.patched(fake):
                self.adapter(daily_cap=99).search("词" + str(per_page), per_page=per_page)
            return fake.bodies()[0]["resource_type_filter"][0]["top_k"]
        self.assertEqual([top_k(n) for n in (20, 12, 8, 1, 0, -3, 50, 500, "x", None)], [20, 12, 8, 1, 1, 1, 50, 50, 10, 10])

    def test_a_long_query_is_trimmed_in_the_body(self):
        fake = FakeUrlopen(fixture("empty.json"))
        with self.patched(fake):
            self.adapter().search("知" * 80)
        content = fake.bodies()[0]["messages"][0]["content"]
        self.assertEqual(self.baidu_web.query_units(content), 72)

    def test_the_header_is_unredirected_and_only_for_the_qianfan_host_over_https(self):
        make = self.baidu_web.request_for
        request = make(b"{}", DUMMY)
        self.assertEqual(request.get_header("Authorization"), f"Bearer {DUMMY}")
        self.assertNotIn("Authorization", request.headers)             # not copied to a redirect target
        self.assertEqual((request.get_method(), request.full_url), ("POST", SEARCH_URL))
        for url in ("http://qianfan.baidubce.com/v2/ai_search/web_search", "https://qianfan.baidubce.com.evil.example/x",
                    "https://evil.example/qianfan.baidubce.com", "https://xueshu.baidu.com/x"):
            self.assertIsNone(make(b"{}", DUMMY, url=url).get_header("Authorization"), url)
        self.assertIsNone(make(b"{}", None).get_header("Authorization"))

    def test_the_key_is_in_no_url_and_no_body(self):
        fake = FakeUrlopen(fixture("success.json"))
        with self.patched(fake):
            self.adapter().search("知识图谱")
        call = fake.calls[0]
        self.assertNotIn(DUMMY, call["url"])
        self.assertNotIn(urllib.parse.quote(DUMMY, safe=""), call["url"])
        self.assertNotIn(DUMMY.encode(), call["data"])

    def test_the_search_has_no_pages_a_second_page_is_empty_without_a_request(self):
        fake = FakeUrlopen(fixture("success.json"))
        with self.patched(fake):
            self.assertEqual(self.adapter().search("知识图谱", page=2), [])
        self.assertEqual((fake.calls, self.counter_rows()), ([], {}))

    def test_per_page_also_trims_the_result(self):
        with self.patched(FakeUrlopen(fixture("success.json"))):
            self.assertEqual(len(self.adapter().search("知识图谱", per_page=2)), 2)

    def test_since_drops_older_known_years_but_keeps_unknown_dates(self):
        answer_body = answer(reference("o1", date="2019-05-01 00:00:00"), reference("n1", date="2026-05-01 00:00:00"), reference("u1", date="?"))
        with self.patched(FakeUrlopen(answer_body)):
            papers = self.adapter().search("知识图谱", since="2024-10-23")
        self.assertEqual([p["key"] for p in papers], ["baidu:n1", "baidu:u1"])

    def test_invalid_queries_make_no_request_and_use_no_quota(self):
        fake = FakeUrlopen(fixture("success.json"))
        with self.patched(fake):
            for bad in ("", "   ", None, 5, "\x00\n"):
                with self.assertRaises(self.sources.SourceError) as caught:
                    self.adapter().search(bad)
                self.assertEqual(caught.exception.kind, "invalid_input")
        self.assertEqual((fake.calls, self.counter_rows()), ([], {}))

    def test_without_a_key_nothing_is_sent_and_nothing_counted(self):
        fake = FakeUrlopen(fixture("success.json"))
        with self.patched(fake):
            with self.assertRaises(self.sources.SourceError) as caught:
                self.adapter(key=None).search("知识图谱")
        self.assertEqual(caught.exception.kind, "auth_required")
        self.assertEqual((fake.calls, self.counter_rows()), ([], {}))

    def test_failures_map_to_kinds_never_carry_the_key_and_are_not_retried(self):
        cases = [(http_error(401), "auth_required"), (http_error(403), "auth_required"), (http_error(429), "quota_exhausted"),
                 (http_error(404), "unavailable"), (http_error(400), "invalid_input"), (http_error(500), "unavailable"),
                 (http_error(503), "unavailable"), (urllib.error.URLError("dns " + DUMMY), "network_error"),
                 (TimeoutError(DUMMY), "network_error"), (b"<html>gateway</html>", "bad_response"), (b"", "bad_response"),
                 (fixture("error_auth.json"), "auth_required"), (fixture("error_quota.json"), "quota_exhausted"),
                 (fixture("references_not_list.json"), "bad_response")]
        for failure, kind in cases:
            fake = FakeUrlopen(failure, default=fixture("success.json"))
            with self.patched(fake):
                with self.assertRaises(self.sources.SourceError) as caught:
                    self.adapter(daily_cap=99).search("词" + kind + str(len(fake.answers)) + repr(failure)[:20])
            self.assertEqual(caught.exception.kind, kind, repr(failure))
            self.assertNotIn(DUMMY, str(caught.exception))
            self.assertEqual(len(fake.calls), 1, "no retry")

    def test_an_oversized_body_is_a_bad_response(self):
        big = b'{"references":[],"pad":"' + b"x" * (3 * 1024 * 1024) + b'"}'
        with self.patched(FakeUrlopen(big)):
            with self.assertRaises(self.sources.SourceError) as caught:
                self.adapter().search("知识图谱")
        self.assertEqual(caught.exception.kind, "bad_response")


class QuotaAndCacheTests(WebCase):
    def test_quota_is_reserved_before_the_request(self):
        seen = []
        fake = FakeUrlopen(fixture("success.json"), on_call=lambda request: seen.append(self.counter_rows()))
        with self.patched(fake):
            self.adapter().search("知识图谱")
        self.assertEqual(list(seen[0].values()), ["1"])
        self.assertEqual(len(fake.calls), 1)

    def test_the_counter_is_its_own_and_the_key_names_the_source_and_the_day(self):
        with self.patched(FakeUrlopen(fixture("success.json"))):
            self.adapter().search("知识图谱")
        (name, value), = self.counter_rows().items()
        self.assertRegex(name, r"^source_usage:baidu_web:\d{4}-\d{2}-\d{2}$")
        self.assertEqual(value, "1")

    def test_a_full_scholar_counter_does_not_block_web_and_the_other_way_round(self):
        day = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)).date().isoformat()
        self.store.conn.execute("INSERT INTO settings(key,value) VALUES(?,?)", ("source_usage:baidu_scholar:" + day, "40"))
        self.store.conn.commit()
        with self.patched(FakeUrlopen(fixture("empty.json"))):
            self.adapter().search("知识图谱")
        self.assertEqual(self.adapter().usage_today(), 1)
        self.store.conn.execute("UPDATE settings SET value='40' WHERE key=?", ("source_usage:baidu_web:" + day,))
        self.store.conn.execute("UPDATE settings SET value='3' WHERE key=?", ("source_usage:baidu_scholar:" + day,))
        self.store.conn.commit()
        scholar = self.baidu_scholar.BaiduScholar(self.tmp / "cache" / "baidu_scholar", self.tmp / "db.sqlite", api_key=DUMMY)
        with mock.patch.object(self.baidu_scholar.urllib.request, "urlopen", FakeUrlopen(
                (ROOT / "tests" / "fixtures" / "baidu_scholar" / "empty.json").read_bytes())):
            scholar.search("知识图谱")
        self.assertEqual(scholar.usage_today(), 4)

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
        self.assertEqual((len(fake.calls), adapter.usage_today()), (2, 2))

    def test_the_default_cap_is_forty(self):
        self.assertEqual(self.adapter().daily_cap, 40)
        self.assertEqual(self.baidu_web.DAILY_CAP, 40)

    def test_a_cache_hit_uses_no_quota_and_no_network(self):
        fake = FakeUrlopen(fixture("success.json"))
        with self.patched(fake):
            first = self.adapter().search("知识图谱", per_page=20)
            again = self.adapter().search("知识图谱", per_page=20)
        self.assertEqual((len(fake.calls), list(self.counter_rows().values())), (1, ["1"]))
        self.assertEqual(first, again)

    def test_a_different_body_is_a_different_cache_entry(self):
        fake = FakeUrlopen(default=fixture("success.json"))
        with self.patched(fake):
            adapter = self.adapter()
            adapter.search("知识图谱", per_page=20)
            adapter.search("知识图谱", per_page=12)
            adapter.search("知识图谱", per_page=20, recency="week")
            adapter.search("本体", per_page=20)
            adapter.search("知识图谱", per_page=20, recency="week")
        self.assertEqual(len(fake.calls), 4)

    def test_cache_files_are_named_by_the_body_hash_and_hold_no_key_and_no_extra_text(self):
        noisy = json.loads(fixture("success.json"))
        for item in noisy["references"]:
            item["markdown_content"] = SENTINEL
            item["snippet"] = SENTINEL
            item["web_anchor"] = SENTINEL
        with self.patched(FakeUrlopen(json.dumps(noisy, ensure_ascii=False).encode())):
            self.adapter().search("知识图谱")
        files = list((self.tmp / "cache" / "baidu_web").glob("*.json"))
        self.assertEqual(len(files), 1)
        self.assertRegex(files[0].name, r"^[0-9a-f]{16}\.json$")
        text = files[0].read_text(encoding="utf-8")
        self.assertNotIn(DUMMY, text)
        self.assertNotIn(SENTINEL, text)
        self.assertNotIn("markdown_content", text)
        self.assertIn("基于本体的生物安全知识图谱构建研究", text)          # the parsed material is kept so a cache hit needs no call
        with self.patched(FakeUrlopen(http_error(500))):                    # and the cached copy parses to the same papers
            self.assertEqual(len(self.adapter().search("知识图谱")), 4)

    def test_an_expired_or_corrupt_cache_entry_is_refetched(self):
        fake = FakeUrlopen(default=fixture("success.json"))
        with self.patched(fake):
            self.adapter().search("知识图谱")
            path = next((self.tmp / "cache" / "baidu_web").glob("*.json"))
            old = time.time() - 25 * 3600
            os.utime(path, (old, old))
            self.adapter().search("知识图谱")
            self.assertEqual(len(fake.calls), 2)
            path.write_text("{not json", encoding="utf-8")
            self.adapter().search("知识图谱")
            self.assertEqual(len(fake.calls), 3)
            path.write_text(json.dumps({"code": 216003}), encoding="utf-8")
            self.adapter().search("知识图谱")
            self.assertEqual(len(fake.calls), 4)

    def test_an_error_answer_is_never_cached(self):
        with self.patched(FakeUrlopen(fixture("error_quota.json"))):
            with self.assertRaises(self.sources.SourceError):
                self.adapter().search("知识图谱")
        self.assertEqual(list((self.tmp / "cache").rglob("*.json")), [])

    def test_the_cache_is_not_created_for_a_source_that_is_not_used(self):
        self.adapter()
        self.assertFalse((self.tmp / "cache").exists())

    def test_day_rollover_uses_the_utc_plus_8_date_and_prunes_old_counters(self):
        clock = {"now": datetime.datetime(2026, 10, 23, 15, 59, tzinfo=datetime.timezone.utc)}
        adapter = self.adapter(daily_cap=2, now=lambda: clock["now"])
        old, scholar = "source_usage:baidu_web:2026-10-01", "source_usage:baidu_scholar:2026-10-01"
        for name in (old, scholar):
            self.store.conn.execute("INSERT INTO settings(key,value) VALUES(?,?)", (name, "9"))
        self.store.conn.commit()
        with self.patched(FakeUrlopen(default=fixture("empty.json"))):
            adapter.search("一")
            adapter.search("二")
            with self.assertRaises(self.sources.SourceError):
                adapter.search("三")
            clock["now"] += datetime.timedelta(minutes=2)
            self.assertEqual(adapter.usage_today(), 0)
            adapter.search("四")
        rows = self.counter_rows()
        self.assertEqual((rows["source_usage:baidu_web:2026-10-23"], rows["source_usage:baidu_web:2026-10-24"]), ("2", "1"))
        self.assertNotIn(old, rows)
        self.assertIn(scholar, rows)                      # pruning never touches the other source's counters

    def test_two_connections_never_reserve_more_than_the_cap(self):
        fake = FakeUrlopen(default=fixture("empty.json"))
        results = []

        def work(i):
            try:
                self.adapter(daily_cap=5).search(f"并发{i}")
                results.append("ok")
            except self.sources.SourceError as exc:
                results.append(exc.kind)
        with self.patched(fake):
            threads = [threading.Thread(target=work, args=(i,)) for i in range(16)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual((results.count("ok"), results.count("quota_exhausted"), len(fake.calls)), (5, 11, 5))
        self.assertEqual(list(self.counter_rows().values()), ["5"])

    def test_the_counter_lives_in_the_settings_table_not_in_the_cache_folder(self):
        with self.patched(FakeUrlopen(fixture("empty.json"))):
            self.adapter().search("知识图谱")
        import shutil
        shutil.rmtree(self.tmp / "cache")
        self.assertEqual(self.adapter().usage_today(), 1)

    def test_the_last_status_is_a_kind_and_a_time_only_under_its_own_name(self):
        with self.patched(FakeUrlopen(http_error(401))):
            with self.assertRaises(self.sources.SourceError):
                self.adapter().search("会失败")
        status = self.store.get_setting("source_status:baidu_web")
        self.assertEqual((set(status), status["kind"]), ({"kind", "at"}, "auth_required"))
        self.assertIsNone(self.store.get_setting("source_status:baidu_scholar"))
        with self.patched(FakeUrlopen(fixture("empty.json"))):
            self.adapter().search("会成功")
        self.assertEqual(self.store.get_setting("source_status:baidu_web")["kind"], "ok")

    def test_the_dummy_key_appears_nowhere_on_disk_after_successes_and_failures(self):
        answers = (fixture("success.json"), http_error(401), urllib.error.URLError(DUMMY), fixture("error_quota.json"), b"<html>")
        for i, outcome in enumerate(answers):
            with self.patched(FakeUrlopen(outcome)):
                try:
                    self.adapter().search(f"词{i}")
                except self.sources.SourceError:
                    pass
        self.store.conn.commit()
        for path in self.tmp.rglob("*"):
            if path.is_file():
                self.assertNotIn(DUMMY.encode(), path.read_bytes(), str(path))
            self.assertNotIn(DUMMY, path.name)


class VerifyTests(WebCase):
    def test_verify_sends_one_fresh_request_with_a_fixed_word_and_stores_nothing(self):
        fake = FakeUrlopen(fixture("success.json"))
        with self.patched(fake):
            self.assertEqual(self.adapter().verify(), {"ok": True})
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.bodies()[0]["messages"][0]["content"], self.baidu_web.VERIFY_WORD)
        self.assertEqual(fake.bodies()[0]["search_filter"], {"match": {"site": ["xueshu.baidu.com"]}})
        self.assertEqual(list(self.counter_rows().values()), ["1"])
        self.assertFalse((self.tmp / "cache").exists())
        self.assertIsNone(self.store.paper("baidu:" + ID_1))

    def test_verify_is_never_answered_from_the_cache(self):
        fake = FakeUrlopen(default=fixture("success.json"))
        with self.patched(fake):
            self.adapter().search(self.baidu_web.VERIFY_WORD, per_page=3)
            self.adapter().verify()
            self.adapter().verify()
        self.assertEqual(len(fake.calls), 3)

    def test_verify_uses_the_typed_key_and_not_the_saved_one(self):
        fake = FakeUrlopen(fixture("success.json"))
        with self.patched(fake):
            self.adapter().verify(api_key="typed-key-0000/1111")
        self.assertEqual(fake.calls[0]["auth"], "Bearer typed-key-0000/1111")

    def test_verify_failures_have_kinds_and_a_missing_key_is_refused_locally(self):
        for failure, kind in ((http_error(401), "auth_required"), (http_error(404), "unavailable"), (urllib.error.URLError("x"), "network_error"),
                              (fixture("references_not_list.json"), "bad_response")):
            with self.patched(FakeUrlopen(failure)):
                with self.assertRaises(self.sources.SourceError) as caught:
                    self.adapter().verify()
            self.assertEqual(caught.exception.kind, kind)
        fake = FakeUrlopen(fixture("success.json"))
        with self.patched(fake):
            with self.assertRaises(self.sources.SourceError) as caught:
                self.adapter(key=None).verify()
        self.assertEqual((caught.exception.kind, fake.calls), ("auth_required", []))

    def test_verify_respects_the_local_cap(self):
        fake = FakeUrlopen(default=fixture("success.json"))
        adapter = self.adapter(daily_cap=1)
        with self.patched(fake):
            adapter.verify()
            with self.assertRaises(self.sources.SourceError) as caught:
                adapter.verify()
        self.assertEqual((caught.exception.kind, len(fake.calls)), ("quota_exhausted", 1))


class PageAndPolicyTests(WebCase):
    def settings(self, **values):
        (self.tmp / "settings.json").write_text(json.dumps(values))
        from app import user_settings
        return user_settings

    def test_pdf_routes_contribute_only_the_xueshu_page_of_this_source(self):
        paper = {"oa": {"pages": [{"source": "baidu_web", "url": PAGE + "a1"}, {"source": "baidu_web", "url": "https://www.baidu.com/s?wd=x"},
                                  {"source": "baidu_scholar", "url": "https://xueshu.baidu.com/usercenter/paper/show?paperid=zz"}],
                        "via": ["baidu_web"]}}
        self.assertEqual(self.adapter().pdf_routes(paper), [{"kind": "source_page", "url": PAGE + "a1", "auto": False, "needs_login": True, "label": "百度学术"}])
        self.assertEqual(self.adapter().pdf_routes({"oa_json": json.dumps(paper["oa"])})[0]["url"], PAGE + "a1")
        self.assertEqual(self.adapter().pdf_routes({}), [])
        self.assertEqual(self.adapter().pdf_routes({"oa": {"pages": [{"source": "baidu_web", "url": "http://xueshu.baidu.com/p?paperid=a"}]}}), [])

    def test_the_shared_route_list_and_link_use_the_xueshu_page(self):
        paper = {"key": "baidu:a1", "oa": {"pages": [{"source": "baidu_web", "url": PAGE + "a1"}], "via": ["baidu_web"]}}
        routes = self.source_adapters.pdf_routes(paper)
        self.assertEqual([(r["kind"], r["url"], r["label"], r["needs_login"]) for r in routes], [("source_page", PAGE + "a1", "百度学术", True)])
        self.assertEqual(self.source_adapters.paper_url(paper), PAGE + "a1")
        self.assertEqual(self.sources.pdf_availability(None, paper["oa"]), "page")

    def test_the_page_domain_of_this_source_is_xueshu_only(self):
        hostile = {"pages": [{"source": "baidu_web", "url": "https://www.baidu.com/s?wd=x"}, {"source": "baidu_web", "url": "https://evil.example/p"}]}
        self.assertEqual(self.sources.source_pages(hostile), [])
        ok = {"pages": [{"source": "baidu_web", "url": PAGE + "a1"}]}
        self.assertEqual(self.sources.source_pages(ok), [{"source": "baidu_web", "url": PAGE + "a1"}])
        self.assertEqual(self.sources.pdf_availability(None, hostile), "none")

    def test_merging_the_pages_of_both_baidu_sources_keeps_both(self):
        both = self.sources.merge_oa({"pages": [{"source": "baidu_scholar", "url": PAGE + "a1"}], "via": ["baidu_scholar"]},
                                     {"pages": [{"source": "baidu_web", "url": PAGE + "a1"}], "via": ["baidu_web"]})
        self.assertEqual(sorted(both["via"]), ["baidu_scholar", "baidu_web"])
        self.assertEqual({p["source"] for p in both["pages"]}, {"baidu_scholar", "baidu_web"})

    def test_the_web_switch_is_off_by_default_and_must_be_boolean(self):
        user_settings = self.settings()
        self.assertFalse(user_settings.baidu_web(self.tmp))
        self.assertTrue(self.settings(sourceBaiduWeb=True).baidu_web(self.tmp))
        self.assertFalse(self.settings(sourceBaiduWeb="yes").baidu_web(self.tmp))
        self.assertFalse(self.settings(sourceBaiduScholar=True).baidu_web(self.tmp))       # the scholar switch is not the web switch
        self.assertFalse(self.settings(sourceBaiduWeb=True).baidu_scholar(self.tmp))
        self.assertEqual(user_settings.validate({"sourceBaiduWeb": True})["sourceBaiduWeb"], True)
        with self.assertRaises(ValueError):
            user_settings.validate({"sourceBaiduWeb": "yes"})

    def test_a_paper_only_baidu_web_reported_follows_the_web_switch(self):
        web = {"key": "baidu:w1", "oa": {"via": ["baidu_web"], "pages": []}}
        stored = {"key": "baidu:w2", "oa_json": json.dumps({"via": ["baidu_web"]})}
        scholar = {"key": "baidu:s1", "oa": {"via": ["baidu_scholar"]}}
        legacy = {"key": "baidu:s2"}                                          # no via at all: the older Baidu Scholar form
        both = {"key": "baidu:b1", "oa": {"via": ["baidu_scholar", "baidu_web"]}}
        rows = (web, stored, scholar, legacy, both)
        cases = [(dict(sourceBaiduWeb=True), [True, True, False, False, True]),
                 (dict(sourceBaiduScholar=True), [False, False, True, True, True]),
                 (dict(sourceBaiduScholar=True, sourceBaiduWeb=True), [True] * 5),
                 (dict(sourceBaiduScholar=False, sourceBaiduWeb=False), [False] * 5)]
        for values, expected in cases:
            user_settings = self.settings(sourceArxiv=False, sourceOpenAlex=False, **values)
            self.assertEqual([user_settings.source_allowed(self.tmp, p) for p in rows], expected, values)

    def test_a_paper_openalex_also_knows_is_allowed_while_either_source_is_on(self):
        paper = {"key": "https://doi.org/10.1/z", "openalex_id": "https://openalex.org/W2", "oa": {"via": ["baidu_web"]}}
        for values, expected in ((dict(sourceOpenAlex=True), True), (dict(sourceOpenAlex=False, sourceBaiduWeb=True), True),
                                 (dict(sourceOpenAlex=False, sourceBaiduScholar=True), False), (dict(sourceOpenAlex=False), False)):
            self.assertEqual(self.settings(**values).source_allowed(self.tmp, paper), expected, values)

    def test_the_policy_object_carries_the_web_switch_and_old_callers_still_work(self):
        policy = self.settings(sourceBaiduWeb=True).source_policy(self.tmp)
        self.assertTrue(policy.baidu_web)
        self.assertFalse(policy.baidu)
        from app.user_settings import SourcePolicy
        self.assertFalse(SourcePolicy(True, True, True).baidu_web)

    def test_the_recency_filter_follows_only_a_window_the_owner_chose(self):
        for value, expected in (("recent", "week"), ("month", "month"), ("all", None), ("odd", None), (None, None)):
            user_settings = self.settings(**({"timePreference": value} if value else {}))
            self.assertEqual(user_settings.recency_filter(self.tmp), expected, value)


if __name__ == "__main__":
    unittest.main()
