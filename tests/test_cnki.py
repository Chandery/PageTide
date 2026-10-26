"""知网 (CNKI), ADR 0045: the server side. Offline; the server never contacts CNKI.

What the desktop app's CNKI window reads comes back as untrusted page text: only validated fields are kept, the key is built
from CNKI's own database code and file name, a page link must be https on kns.cnki.net. The plan only enables the window when
the switch is on and the project takes Chinese papers and has Chinese keywords (at most three). Ingest adds and links papers,
merges a same-title paper into the one the library has, and never overwrites a stored abstract. Creation candidates and seed
hits merge like Baidu's; a 知网 seed is added by its own key, never by DOI (no DOI goes to OpenAlex).
"""
import json
import os
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

KEYWORDS = ["世界模型", "具身智能", "视频生成", "自动驾驶", "world model"]
ABSTRACT = "本文提出一种基于世界模型的强化学习方法，" * 30     # longer than the 503 characters CNKI shows before 更多


def item(n=1, **over):
    base = {"dbname": "CJFQ", "filename": f"JSJX2026100{n:02d}", "title": f"世界模型驱动的具身智能研究{n}",
            "url": f"https://kns.cnki.net/kcms2/article/abstract?v=enc{n}", "abstract": ABSTRACT,
            "keywords": ["世界模型;", "具身智能"], "date": "2026-10-20 14:33", "doi": "10.16383/j.aas.c26008" + str(n),
            "authors": ["张三", "李四"], "source": "自动化学报", "resource": "JOURNAL"}
    base.update(over)
    return base


def offline(request, timeout=None):
    raise AssertionError("the server must not contact anything here: " + getattr(request, "full_url", str(request)))


class Case(unittest.TestCase):
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
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for name in ("OPENALEX_API_KEY", "BAIDU_SCHOLAR_API_KEY"):
            os.environ.pop(name, None)
        net = mock.patch.object(urllib.request, "urlopen", offline)
        net.start()
        self.addCleanup(net.stop)
        from app import creation
        creation._SEED_CACHE.clear()
        creation._BAIDU_SEEDS.clear()
        from app.service import App
        self.app = App(root=str(self.root), data_dir=str(self.root / "data"))
        self.addCleanup(self.app.store.close)
        self.set_user_settings(self.app, timePreference="all", sourceArxiv=False, sourceOpenAlex=False, sourceCnki=True)
        self.pid = self.app.create_project("世界模型", "manual", KEYWORDS)["project_id"]
        self.app.set_project_language(self.pid, None, ["zh"])
        day = mock.patch.object(type(self.app), "batch_day", lambda s: "2026-10-26")
        day.start()
        self.addCleanup(day.stop)

    def paper(self, key):
        return self.app.store.paper(key)


class ItemValidationTests(unittest.TestCase):
    def setUp(self):
        from app import cnki
        self.cnki = cnki

    def test_a_good_item_becomes_a_paper_keyed_by_cnki_ids(self):
        paper = self.cnki.paper_from_item(item())
        self.assertEqual(paper["key"], "cnki:CJFQ:JSJX202610001")
        self.assertEqual((paper["published"], paper["doi"], paper["topic"]), ("2026-10-20", "10.16383/j.aas.c260081", "世界模型"))
        self.assertEqual(paper["abstract"], ABSTRACT.strip())
        self.assertEqual(paper["oa"], {"pages": [{"source": "cnki", "url": "https://kns.cnki.net/kcms2/article/abstract?v=enc1"}],
                                       "via": ["cnki"], "abstract_partial": False})
        self.assertEqual(paper["authors"], [])                    # authors and journal are not stored
        self.assertNotIn("metadata_language", paper)
        self.assertIsNone(paper["openalex_id"])

    def test_an_item_without_valid_ids_or_title_is_dropped(self):
        for name, bad in {"no filename": item(filename=""), "lowercase db": item(dbname="cjfq1"),
                          "filename with slash": item(filename="../etc"), "no title": item(title="  "),
                          "not a dict": "cnki:CJFQ:X", "db too long": item(dbname="ABCDEFGHI")}.items():
            with self.subTest(name):
                self.assertIsNone(self.cnki.paper_from_item(bad))

    def test_a_link_off_kns_cnki_net_is_not_kept_but_the_paper_is(self):
        for url in ("https://evil.example/kns.cnki.net", "http://kns.cnki.net/x", "https://kns.cnki.net.evil.example/",
                    "https://user@kns.cnki.net/", "https://kns.cnki.net\\@evil.example/", "javascript:alert(1)"):
            with self.subTest(url):
                paper = self.cnki.paper_from_item(item(url=url))
                self.assertEqual(paper["oa"], {"pages": [], "via": ["cnki"], "abstract_partial": False})

    def test_lengths_are_capped_and_dates_normalised(self):
        paper = self.cnki.paper_from_item(item(title="题" * 900, abstract="摘" * 20000, keywords=["词" * 100] * 30, date="2026-3"))
        self.assertEqual((len(paper["title"]), len(paper["abstract"]), len(paper["topic"])), (500, 8000, 60))
        self.assertEqual(paper["published"], "2026-03-01")
        for raw, want in {"2026": "2026-01-01", "2026-10-20": "2026-10-20", "": None, "昨天": None, "2026-13-01": None,
                          "1800-01-01": None}.items():
            self.assertEqual(self.cnki.paper_from_item(item(date=raw))["published"], want, raw)

    def test_non_string_fields_are_ignored(self):
        paper = self.cnki.paper_from_item(item(abstract=["x"], keywords="世界模型", doi=42, url=None))
        self.assertEqual((paper["abstract"], paper["topic"], paper["doi"], paper["oa"]["pages"]), (None, None, None, []))

    def test_a_list_is_required_and_duplicates_and_extras_are_dropped(self):
        with self.assertRaises(ValueError):
            self.cnki.papers_from_items({"items": []})
        many = [item(n % 150) for n in range(300)]
        papers = self.cnki.papers_from_items(many)
        self.assertEqual(len(papers), len({p["key"] for p in papers}))
        self.assertLessEqual(len(papers), self.cnki.MAX_ITEMS)

    def test_unknown_problems_count_as_unavailable(self):
        self.assertEqual([self.cnki.problem_of(v) for v in (None, "", "verification_needed", "<script>", 3)],
                         [None, None, "verification_needed", "unavailable", "unavailable"])

    def test_the_source_needs_no_key_serves_chinese_and_cannot_search_from_the_server(self):
        from app.sources import SourceError
        info = self.cnki.CNKI_INFO
        self.assertEqual((info.key, info.serves_languages, info.query_scripts, info.daily_cap), ("none", ("zh",), ("cjk",), None))
        with self.assertRaises(SourceError):
            self.cnki.Cnki().search("世界模型")


class SourcePolicyTests(unittest.TestCase):
    def test_a_cnki_paper_follows_only_the_cnki_switch(self):
        from app.user_settings import SourcePolicy
        from app import cnki
        paper = cnki.paper_from_item(item())
        self.assertFalse(SourcePolicy(True, True, True, True, cnki=False).allows(paper))
        self.assertTrue(SourcePolicy(False, False, False, False, cnki=True).allows(paper))
        legacy = {"key": "cnki:CJFQ:X1", "title": "t"}                         # no `via` stored: the key says 知网
        self.assertEqual(SourcePolicy.reporters(legacy), {"cnki"})
        self.assertFalse(SourcePolicy.from_baidu(legacy))
        both = {**paper, "oa": {"via": ["cnki", "baidu_web"]}}
        self.assertTrue(SourcePolicy(False, False, False, True, cnki=False).allows(both))
        self.assertEqual(SourcePolicy.baidu_reporters(both), {"baidu_web"})


class PlanTests(Case):
    def test_the_plan_sends_at_most_three_chinese_keywords(self):
        plan = self.app.cnki_plan(self.pid)
        self.assertTrue(plan["enabled"])
        self.assertEqual(plan["queries"], ["世界模型", "具身智能", "视频生成"])
        self.assertEqual((plan["max_new"], plan["known"], plan["since"]), (100, [], None))

    def test_the_plan_is_off_with_a_reason(self):
        self.set_user_settings(self.app, sourceCnki=False)
        self.assertEqual(self.app.cnki_plan(self.pid)["reason_code"], "sources_disabled")
        self.set_user_settings(self.app, sourceCnki=True)
        english = self.app.create_project("english", "manual", ["世界模型"])["project_id"]
        self.app.set_project_language(english, None, ["en"])
        self.assertEqual(self.app.cnki_plan(english)["reason_code"], "language_not_allowed")
        latin = self.app.create_project("latin", "manual", ["world model"])["project_id"]
        self.app.set_project_language(latin, None, ["zh"])
        plan = self.app.cnki_plan(latin)
        self.assertEqual((plan["enabled"], plan["reason_code"], plan["queries"]), (False, "no_keywords", []))

    def test_known_ids_list_what_the_library_has(self):
        self.app.cnki_ingest(self.pid, [item(1), item(2)])
        self.assertEqual(sorted(self.app.cnki_plan(self.pid)["known"]), ["CJFQ:JSJX202610001", "CJFQ:JSJX202610002"])

    def test_the_time_window_follows_the_setting(self):
        self.set_user_settings(self.app, timePreference="month")
        self.assertRegex(self.app.cnki_plan(self.pid)["since"], r"^\d{4}-\d{2}-\d{2}$")


class IngestTests(Case):
    def test_papers_are_added_and_linked_to_the_project(self):
        result = self.app.cnki_ingest(self.pid, [item(1), item(2), {"junk": True}])
        self.assertEqual((result["fetched"], result["added"], result["new_to_project"], result["problem"]), (2, 2, 2, None))
        stored = self.paper("cnki:CJFQ:JSJX202610001")
        self.assertEqual((stored["title"], stored["abstract"], stored["published"]), ("世界模型驱动的具身智能研究1", ABSTRACT.strip(), "2026-10-20"))
        self.assertEqual(json.loads(stored["oa_json"])["via"], ["cnki"])
        last = self.app.store.get_setting("cnki_last_" + self.pid)
        self.assertEqual((last["added"], last["problem"]), (2, None))

    def test_a_known_paper_keeps_its_abstract_when_reported_again_without_one(self):
        self.app.cnki_ingest(self.pid, [item(1)])
        other = self.app.create_project("另一个", "manual", ["世界模型"])["project_id"]
        self.app.set_project_language(other, None, ["zh"])
        result = self.app.cnki_ingest(other, [item(1, abstract=None)])
        self.assertEqual((result["added"], result["new_to_project"]), (0, 1))
        self.assertEqual(self.paper("cnki:CJFQ:JSJX202610001")["abstract"], ABSTRACT.strip())

    def test_a_same_title_paper_already_in_the_library_gains_the_cnki_page_instead_of_a_twin(self):
        self.set_user_settings(self.app, sourceBaiduWeb=True)
        self.app.store.upsert_papers([{"key": "baidu:p1", "title": "世界模型驱动的具身智能研究 1", "abstract": "百度摘要",
                                       "published": "2026-01-01", "group_name": "field", "project_id": self.pid,
                                       "oa": {"pages": [], "via": ["baidu_web"]}}])
        result = self.app.cnki_ingest(self.pid, [item(1)])
        self.assertEqual(result["added"], 0)
        self.assertIsNone(self.paper("cnki:CJFQ:JSJX202610001"))
        oa = json.loads(self.paper("baidu:p1")["oa_json"])
        self.assertEqual(oa["via"], ["baidu_web", "cnki"])
        self.assertEqual(oa["pages"][0]["url"], "https://kns.cnki.net/kcms2/article/abstract?v=enc1")
        self.assertEqual(self.paper("baidu:p1")["abstract"], "百度摘要")

    def test_future_and_too_old_papers_are_left_out(self):
        self.set_user_settings(self.app, timePreference="month")
        result = self.app.cnki_ingest(self.pid, [item(1, date="2027-01-01"), item(2, date="2019-05-01"), item(3)])
        self.assertEqual(result["fetched"], 1)
        self.assertIsNotNone(self.paper("cnki:CJFQ:JSJX202610003"))

    def test_cnki_papers_count_in_the_latest_refresh_record(self):
        key = "last_refresh_result_" + self.pid
        self.app.store.set_setting(key, {"at": "2026-10-26T05:20:00+00:00", "fetched": 0, "new_to_project": 0})
        self.app.cnki_ingest(self.pid, [item(1), item(2)])
        self.app.cnki_ingest(self.pid, [item(3)])
        self.assertEqual(self.app.store.get_setting(key), {"at": "2026-10-26T05:20:00+00:00", "fetched": 3, "new_to_project": 3})
        self.app.cnki_ingest(self.pid, [], problem="unavailable")                  # nothing read: the record stays
        self.assertEqual(self.app.store.get_setting(key)["fetched"], 3)

    def test_the_problem_is_reported_and_what_was_read_is_kept(self):
        result = self.app.cnki_ingest(self.pid, [item(1)], problem="verification_needed")
        self.assertEqual((result["added"], result["problem"]), (1, "verification_needed"))

    def test_ingest_is_refused_when_the_plan_would_not_run(self):
        self.set_user_settings(self.app, sourceCnki=False)
        with self.assertRaises(ValueError):
            self.app.cnki_ingest(self.pid, [item(1)])
        self.assertIsNone(self.paper("cnki:CJFQ:JSJX202610001"))

    def test_a_refresh_with_only_cnki_on_runs_and_fetches_nothing_itself(self):
        result = self.app.refresh_candidates(project_id=self.pid)
        self.assertNotIn("reason_code", result)
        self.assertEqual((result["fetched"], result["errors"]), (0, []))


SNIPPET = "自动驾驶作为具身智能的关键应用方向,正经历从模块化结构向端到端框架的深刻变革..."


class PartialAbstractTests(Case):
    """Refreshes read results pages only (CNKI's snippet); the full abstract comes when the person opens the paper."""

    def snippet_item(self, n=1, **over):
        return item(n, abstract=SNIPPET, abstract_partial=True, doi="", **over)

    def test_a_snippet_is_stored_without_its_dots_and_marked_partial(self):
        self.app.cnki_ingest(self.pid, [self.snippet_item()])
        stored = self.paper("cnki:CJFQ:JSJX202610001")
        self.assertEqual(stored["abstract"], SNIPPET[:-3])
        self.assertTrue(json.loads(stored["oa_json"])["abstract_partial"])
        from app import cnki
        self.assertTrue(cnki.paper_from_item(item(abstract="摘要到这里……"))["oa"]["abstract_partial"])   # dots alone say "cut"
        self.assertFalse(cnki.paper_from_item(item())["oa"]["abstract_partial"])

    def test_a_snippet_is_enough_to_be_recommendable(self):
        from app import eligibility
        self.app.cnki_ingest(self.pid, [self.snippet_item()])
        self.assertTrue(eligibility.usable_abstract(self.paper("cnki:CJFQ:JSJX202610001")["abstract"]))

    def test_the_detail_offers_the_cnki_page_while_the_abstract_is_partial(self):
        self.app.cnki_ingest(self.pid, [self.snippet_item()])
        detail = self.app.paper_detail("cnki:CJFQ:JSJX202610001", self.pid)
        self.assertEqual(detail["cnki"], {"abstract_partial": True, "target": {
            "url": "https://kns.cnki.net/kcms2/article/abstract?v=enc1", "dbname": "CJFQ", "filename": "JSJX202610001",
            "title": "世界模型驱动的具身智能研究1"}})
        self.set_user_settings(self.app, sourceCnki=False)
        self.assertNotIn("cnki", self.app.paper_detail("cnki:CJFQ:JSJX202610001", self.pid))

    def test_the_full_abstract_replaces_the_snippet_once(self):
        self.app.cnki_ingest(self.pid, [self.snippet_item()])
        result = self.app.cnki_abstract("cnki:CJFQ:JSJX202610001", item(1))
        self.assertEqual((result["updated"], result["abstract"]), (True, ABSTRACT.strip()))
        stored = self.paper("cnki:CJFQ:JSJX202610001")
        self.assertEqual((stored["abstract"], stored["doi"]), (ABSTRACT.strip(), "10.16383/j.aas.c260081"))
        self.assertFalse(json.loads(stored["oa_json"])["abstract_partial"])
        self.assertNotIn("cnki", self.app.paper_detail("cnki:CJFQ:JSJX202610001", self.pid))
        again = self.app.cnki_abstract("cnki:CJFQ:JSJX202610001", item(1, abstract="另一段更长的文字" * 200))
        self.assertFalse(again["updated"])                                    # a complete abstract is never overwritten
        self.app.cnki_ingest(self.pid, [self.snippet_item()])                 # the next refresh reports the snippet again
        self.assertFalse(json.loads(self.paper("cnki:CJFQ:JSJX202610001")["oa_json"])["abstract_partial"])
        self.assertEqual(self.paper("cnki:CJFQ:JSJX202610001")["abstract"], ABSTRACT.strip())

    def test_a_cut_shorter_or_mismatched_abstract_changes_nothing(self):
        self.app.cnki_ingest(self.pid, [self.snippet_item()])
        for name, key, payload in (("still cut", "cnki:CJFQ:JSJX202610001", item(1, abstract=ABSTRACT + "......")),
                                   ("shorter", "cnki:CJFQ:JSJX202610001", item(1, abstract="短")),):
            with self.subTest(name):
                self.assertFalse(self.app.cnki_abstract(key, payload)["updated"])
        with self.assertRaises(ValueError):
            self.app.cnki_abstract("cnki:CJFQ:JSJX202610001", item(2))      # another paper's page
        with self.assertRaises(ValueError):
            self.app.cnki_abstract("baidu:x", item(1))
        with self.assertRaises(LookupError):
            self.app.cnki_abstract("cnki:CJFQ:JSJX202610099", item(99))
        self.assertEqual(self.paper("cnki:CJFQ:JSJX202610001")["abstract"], SNIPPET[:-3])

    def test_the_full_abstract_needs_the_switch(self):
        self.app.cnki_ingest(self.pid, [self.snippet_item()])
        self.set_user_settings(self.app, sourceCnki=False)
        with self.assertRaises(ValueError):
            self.app.cnki_abstract("cnki:CJFQ:JSJX202610001", item(1))


class ReviewFixTests(Case):
    """Defects found by the independent review (2026-10-26), kept fixed."""

    def test_downloading_a_cnki_pdf_never_sends_its_doi_to_openalex(self):
        self.app.cnki_ingest(self.pid, [item(1)])                     # stored with a DOI
        asked = []
        with mock.patch.object(self.app.source, "work", side_effect=lambda ident: asked.append(ident) or {}):
            result = self.app.download_pdf("cnki:CJFQ:JSJX202610001")
        self.assertEqual(asked, [])
        self.assertFalse(result["ok"] if isinstance(result, dict) else False)

    def test_two_cnki_entries_with_one_title_stay_two_papers(self):
        self.app.cnki_ingest(self.pid, [item(1)])
        thesis = item(2, dbname="CMFD", title="世界模型驱动的具身智能研究1", abstract="学位论文的摘要" * 5)
        self.assertEqual(self.app.cnki_ingest(self.pid, [thesis])["added"], 1)
        self.assertEqual(self.paper("cnki:CJFQ:JSJX202610001")["abstract"], ABSTRACT.strip())
        self.assertIsNotNone(self.paper("cnki:CMFD:JSJX202610002"))

    def test_a_same_title_paper_from_another_year_is_not_merged(self):
        self.set_user_settings(self.app, sourceBaiduWeb=True)
        self.app.store.upsert_papers([{"key": "baidu:old", "title": "世界模型驱动的具身智能研究1", "abstract": "旧文",
                                       "published": "2019-01-01", "group_name": "field", "project_id": self.pid,
                                       "oa": {"pages": [], "via": ["baidu_web"]}}])
        self.assertEqual(self.app.cnki_ingest(self.pid, [item(1)])["added"], 1)
        self.assertEqual(json.loads(self.paper("baidu:old")["oa_json"])["via"], ["baidu_web"])

    def test_a_merged_paper_is_never_marked_as_cut(self):
        self.set_user_settings(self.app, sourceBaiduWeb=True)
        self.app.store.upsert_papers([{"key": "baidu:p1", "title": "世界模型驱动的具身智能研究1", "abstract": "百度的完整摘要",
                                       "published": "2026-03-01", "group_name": "field", "project_id": self.pid,
                                       "oa": {"pages": [], "via": ["baidu_web"]}}])
        self.app.cnki_ingest(self.pid, [item(1, abstract="片段...", abstract_partial=True)])
        self.assertNotIn("abstract_partial", json.loads(self.paper("baidu:p1")["oa_json"]))
        self.assertNotIn("cnki", self.app.paper_detail("baidu:p1", self.pid))

    def test_a_short_complete_abstract_is_not_fetched_again(self):
        self.app.cnki_ingest(self.pid, [item(1, abstract="很短")])
        self.assertNotIn("cnki", self.app.paper_detail("cnki:CJFQ:JSJX202610001", self.pid))


class CreationTests(Case):
    def session(self):
        return self.app.create_guidance_session("世界模型", "了解世界模型", "ai_guided")["id"]

    def test_the_page_is_asked_to_search_cnki_only_for_a_chinese_query_with_chinese_ticked(self):
        sid = self.session()
        self.assertTrue(self.app.guidance_search(sid, "世界模型", languages=["zh"]).get("cnki_ask"))
        self.assertNotIn("cnki_ask", self.app.guidance_search(sid, "世界模型", languages=["en"]))
        self.assertNotIn("cnki_ask", self.app.guidance_search(sid, "world model", languages=["zh"]))
        self.set_user_settings(self.app, sourceCnki=False)
        self.assertNotIn("cnki_ask", self.app.guidance_search(sid, "世界模型", languages=["zh"]))

    def test_cnki_candidates_merge_into_the_session(self):
        sid = self.session()
        result = self.app.cnki_guidance(sid, "世界模型", [item(n) for n in range(1, 15)], languages=["zh"])
        self.assertEqual(len(result["items"]), 10)
        self.assertEqual(result["items"][0]["matched_queries"], ["世界模型"])
        self.assertTrue(result["items"][0]["abstract"])
        again = self.app.cnki_guidance(sid, "具身智能", [item(1)], problem="verification_needed", languages=["zh"])
        self.assertEqual((again["items"][0]["matched_queries"], again["items"][0]["new"]), (["世界模型", "具身智能"], False))
        self.assertEqual(again["cnki"], {"kind": "verification_needed"})
        stored = self.app.store.guidance_session(sid)["draft"]["candidates"]
        self.assertEqual(len(stored), 10)

    def test_cnki_candidates_are_refused_when_cnki_would_not_be_asked(self):
        sid = self.session()
        for query, languages in (("世界模型", ["en"]), ("world model", ["zh"])):
            with self.assertRaises(ValueError):
                self.app.cnki_guidance(sid, query, [item(1)], languages=languages)


class SeedTests(Case):
    def test_a_typed_chinese_title_asks_cnki_and_a_hit_is_added_by_its_key(self):
        self.assertTrue(self.app.seed_search("世界模型驱动的具身智能").get("cnki_ask"))
        self.assertNotIn("cnki_ask", self.app.seed_search("世界模型驱动的具身智能", typed=False))
        result = self.app.cnki_seeds("世界模型驱动的具身智能研究1", [item(2, abstract=None), item(1, abstract=None)])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["items"][0]["seed_id"], "cnki:CJFQ:JSJX202610001")      # the exact title ranks first; key, not DOI
        from app import creation
        paper = creation.fetch_seed_paper(None, "cnki:CJFQ:JSJX202610001")
        self.assertIsNone(paper["abstract"])
        self.app.cnki_seeds("世界模型驱动的具身智能研究1", [item(1)])                     # the chosen hit after its detail page
        self.assertEqual(creation.fetch_seed_paper(None, "cnki:CJFQ:JSJX202610001")["abstract"], ABSTRACT.strip())
        self.assertEqual(creation.parse_seed("cnki:CJFQ:JSJX202610001")[0], "cnki:CJFQ:JSJX202610001")

    def test_a_seed_project_from_a_cnki_hit_never_asks_openalex(self):
        self.app.cnki_seeds("世界模型驱动的具身智能研究1", [item(1)])
        created = self.app.create_project("种子", "manual", ["世界模型"], ["cnki:CJFQ:JSJX202610001"],
                                          language_policy={"allowed_languages": ["zh"]})
        self.assertTrue(created["project_id"])
        self.assertEqual(self.paper("cnki:CJFQ:JSJX202610001")["abstract"], ABSTRACT.strip())

    def test_the_problem_is_reported_and_a_non_chinese_title_is_refused(self):
        self.assertEqual(self.app.cnki_seeds("世界模型驱动", [], problem="verification_needed")["cnki"], {"kind": "verification_needed"})
        with self.assertRaises(ValueError):
            self.app.cnki_seeds("world model", [item(1)])


class ServerTests(unittest.TestCase):
    """The routes: bounded bodies, unknown fields refused, and nothing for the demo project."""

    def test_routes_are_wired_and_capped(self):
        source = (ROOT / "app" / "server.py").read_text(encoding="utf-8")
        for route in ('"/api/cnki/plan"', '"/api/cnki/ingest"', '"/api/cnki/seeds"', 'action == "cnki"'):
            self.assertIn(route, source)
        self.assertIn('limit = 2_000_000 if cnki_route', source)

    def test_the_demo_sandbox_refuses_cnki(self):
        from app import demo
        for method, route in (("GET", "/api/cnki/plan"), ("POST", "/api/cnki/ingest"), ("POST", "/api/cnki/seeds"),
                              ("POST", "/api/project-guidance/sessions/x/cnki")):
            self.assertFalse(demo.allowed(method, route, {}), route)


class ShellTests(unittest.TestCase):
    """The desktop shell's 知网 window (src-tauri/src/cnki.rs): IPC is a critical boundary, so its shape is pinned here."""

    @classmethod
    def setUpClass(cls):
        cls.main = (ROOT / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")
        cls.cnki = (ROOT / "src-tauri" / "src" / "cnki.rs").read_text(encoding="utf-8")
        cls.driver = (ROOT / "src-tauri" / "src" / "cnki_driver.js").read_text(encoding="utf-8")
        cls.build = (ROOT / "src-tauri" / "build.rs").read_text(encoding="utf-8")

    def test_the_cnki_window_gets_exactly_two_commands_and_only_on_kns_cnki_net(self):
        grant = self.main[self.main.index('"identifier":"cnki-window"'):][:400]
        self.assertIn('"windows":[cnki::LABEL]', grant)
        self.assertIn('format!("https://{}/*", cnki::HOST)', grant)
        self.assertIn('"permissions":["allow-cnki-next", "allow-cnki-report"]', grant)
        self.assertIn('pub const HOST: &str = "kns.cnki.net";', self.cnki)
        main_grant = self.main[self.main.index('"identifier":"owned-desktop-session"'):][:500]
        self.assertIn('"windows":["main"]', main_grant)
        self.assertNotIn("cnki-next", main_grant)
        self.assertNotIn("cnki-report", main_grant)
        for command in ("cnki_start", "cnki_poll", "cnki_cancel", "cnki_next", "cnki_report"):
            self.assertIn(f'"{command}"', self.build)

    def test_each_command_checks_its_own_window(self):
        for command in ("cnki_start", "cnki_poll", "cnki_cancel"):
            body = self.cnki[self.cnki.index(f"fn {command}("):][:500]
            self.assertIn("owned_page(&window, &session)?;", body, command)
        for command in ("cnki_next", "cnki_report"):
            body = self.cnki[self.cnki.index(f"fn {command}("):][:300]
            self.assertIn("cnki_page(&window)?;", body, command)
        check = self.cnki[self.cnki.index("fn cnki_page("):][:400]
        self.assertIn("window.label() != LABEL", check)
        self.assertIn('url.scheme() != "https"', check)

    def test_the_window_navigates_only_on_kns_cnki_net_and_never_opens_the_browser(self):
        guard = self.cnki[self.cnki.index("pub fn allowed_navigation"):][:300]
        self.assertIn('url.scheme() == "https" && url.host_str() == Some(HOST) && url.port().is_none()', guard)
        built = self.cnki[self.cnki.index("let builder = WebviewWindowBuilder::new(app, LABEL"):][:2200]
        for part in (".visible(false)", "NewWindowResponse::Deny", ".data_store_identifier(", ".initialization_script(DRIVER)",
                     # CNKI sends a passed puzzle to http://kns.cnki.net/…: opened over https, never allowed as http
                     'url.scheme() == "http" && url.host_str() == Some(HOST) && url.port().is_none()',
                     'secure.set_scheme("https")', "return false;", "allowed_navigation(url)"):
            self.assertIn(part, built)
        self.assertNotIn("open_external", self.cnki)

    def test_no_window_call_is_made_while_the_run_lock_is_held(self):
        # A window call off the main thread waits for the main thread, which may be waiting for this lock: a hang.
        for function in ("fn apply_clock(", "fn record_report(", "fn decide(", "fn count_item("):
            body = self.cnki[self.cnki.index(function):]
            body = body[:body.index("\n}\n")]
            for call in (".url()", ".show()", ".hide()", ".navigate(", "show(&", "on_puzzle_page("):
                self.assertNotIn(call, body, f"{function} {call}")
        start = self.cnki[self.cnki.index("pub async fn cnki_start("):]
        locked = start[start.index("state.0.lock()"):start.index("act(&app, after);")]
        for call in (".url()", ".show()", ".hide()", ".navigate(", "cnki_window(", "puzzle_now("):
            self.assertNotIn(call, locked, f"cnki_start holds the lock around {call}")

    def test_reports_are_capped(self):
        for limit in ("MAX_ITEMS_PER_REPORT: usize = 30", "MAX_ITEM_BYTES: usize = 32 * 1024", "MAX_CURSOR_BYTES: usize = 64 * 1024",
                      "MAX_BUFFERED: usize = 600", "MAX_NEW: u64 = 100", "MAX_QUERIES: usize = 3", "VERIFY_WAIT: Duration = Duration::from_secs(300)"):
            self.assertIn(limit, self.cnki)

    def test_the_page_script_never_solves_the_puzzle(self):
        self.assertIn("if (window.top !== window || window.__pageTideCnki) return;", self.driver)
        self.assertNotIn("verify-api", self.driver)
        self.assertNotRegex(self.driver, r"(?i)pointJson|captchaType|slide\w*\(")
        self.assertIn("report({event: 'verification'})", self.driver)


if __name__ == "__main__":
    unittest.main()
