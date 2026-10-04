"""OpenAlex discovery for project creation and refresh, cache freshness and rate-limit notes.

The reported failure: a Chinese topic ("半导体生长") found no candidates because creation searched only arXiv,
only titles, with every word required, and sent Chinese text to an English-titled index. No test touches
the network: urlopen is replaced by a router that records every URL.
"""
import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import sources
from app.service import App


def work(n, title="Paper", **extra):
    return {"id": f"https://openalex.org/W{n}", "doi": f"https://doi.org/10.1/{n}", "title": f"{title} {n}",
            "publication_date": "2025-01-01", "ids": {}, **extra}


class Router:
    """Answers OpenAlex URLs from a list of (substring, results) rules and records what was asked."""

    def __init__(self, rules, headers=None):
        self.rules, self.urls, self.headers = rules, [], headers or {}

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.urls.append(url)
        decoded = urllib.parse.unquote_plus(url)
        for needle, results in self.rules:
            if needle in decoded:
                body = json.dumps({"results": results}).encode()
                break
        else:
            body = json.dumps({"results": []}).encode()
        reply = mock.MagicMock()
        reply.__enter__.return_value = reply
        reply.read.return_value = body
        reply.headers = self.headers
        return reply

    def filters(self):
        out = []
        for url in self.urls:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            out.append({k: v[0] for k, v in query.items()})
        return out


class DiscoverTopicTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.client = sources.OpenAlex(tmp.name)
        mock.patch.object(sources.time, "sleep").start()
        self.addCleanup(mock.patch.stopall)

    def run_topic(self, router, query, **kw):
        with mock.patch.object(sources.urllib.request, "urlopen", router):
            return self.client.discover_topic(query, **kw)

    def test_chinese_query_uses_relevance_search_without_arxiv_or_title_only_restrictions(self):
        router = Router([("search=半导体生长", [work(1, "介电/半导体复合薄膜生长控制")])])
        papers = self.run_topic(router, "半导体生长")
        self.assertEqual(len(papers), 1)
        sent = router.filters()
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["search"], "半导体生长")
        self.assertNotIn(sources.ARXIV_SOURCE_ID, json.dumps(sent))
        self.assertNotIn("title.search", json.dumps(sent))
        self.assertNotIn("from_publication_date", json.dumps(sent))  # no recency bound for a Chinese topic
        self.assertEqual(papers[0]["match_mode"], "relevance")

    def test_english_query_matches_title_and_abstract_in_any_source_ranked_by_relevance(self):
        router = Router([("title_and_abstract.search:semiconductor crystal growth", [work(n) for n in range(1, 6)])])
        papers = self.run_topic(router, "semiconductor crystal growth")
        self.assertEqual(len(papers), 5)
        self.assertEqual(len(router.urls), 1)  # strict was enough
        sent = router.filters()[0]
        self.assertIn("title_and_abstract.search:semiconductor crystal growth", sent["filter"])
        self.assertEqual(sent["search"], "semiconductor crystal growth")  # relevance ranks the strict matches
        self.assertNotIn("sort", sent)
        self.assertIn("type:article|preprint", sent["filter"])
        self.assertNotIn(sources.ARXIV_SOURCE_ID, sent["filter"])
        self.assertTrue(all(p["match_mode"] == "strict" for p in papers))

    def test_recent_order_sorts_strict_matches_newest_first_for_the_daily_feed(self):
        router = Router([("title_and_abstract.search:", [work(1)])])
        self.run_topic(router, "world model", order="recent", from_date="2024-01-01")
        sent = router.filters()[0]
        self.assertEqual(sent["sort"], "publication_date:desc")
        self.assertNotIn("search", sent)

    def test_sparse_strict_results_are_topped_up_by_relevance_search_without_duplicates(self):
        router = Router([("title_and_abstract.search:", [work(1)]),
                         ("search=growth of wide band gap semiconductors", [work(1), work(2), work(3)])])
        papers = self.run_topic(router, "growth of wide band gap semiconductors")
        self.assertEqual([p["openalex_id"].rsplit("/", 1)[-1] for p in papers], ["W1", "W2", "W3"])
        self.assertEqual([p["match_mode"] for p in papers], ["strict", "relevance", "relevance"])
        self.assertEqual(len(router.urls), 2)

    def test_empty_strict_result_still_returns_relevance_results(self):
        router = Router([("title_and_abstract.search:", []), ("search=very specific phrase", [work(7)])])
        papers = self.run_topic(router, "very specific phrase")
        self.assertEqual([p["match_mode"] for p in papers], ["relevance"])

    def test_query_text_cannot_inject_extra_filters(self):
        router = Router([])
        self.run_topic(router, "foo,from_publication_date:1900|bar\"baz")
        flt = router.filters()[0]["filter"]
        parts = flt.split(",")
        self.assertEqual(len(parts), 2)  # the search filter and the type filter, nothing injected
        self.assertTrue(parts[0].startswith("title_and_abstract.search:"))
        self.assertEqual(parts[1], "type:article|preprint")
        self.assertNotIn("|", parts[0])
        self.assertEqual(parts[0].count(":"), 1)  # the only colon is the filter's own

    def test_chinese_only_titles_are_kept_and_similar_ascii_prefixes_are_not_merged(self):
        router = Router([("title_and_abstract.search:", [work(1, "x")])])
        router.rules = [("search=GaN", [{**work(1), "title": "GaN 外延生长"}, {**work(2), "title": "GaN 薄膜缺陷"},
                                        {**work(3), "title": "半导体物理"}, {**work(4), "title": "晶体生长"}])]
        papers = self.run_topic(router, "GaN growth")
        self.assertEqual(sorted(p["title"] for p in papers), sorted(["GaN 外延生长", "GaN 薄膜缺陷", "半导体物理", "晶体生长"]))

    def test_chinese_refresh_order_sorts_newest_first(self):
        router = Router([])
        self.run_topic(router, "半导体生长", order="recent", from_date="2024-01-01")
        sent = router.filters()[0]
        self.assertEqual(sent["sort"], "publication_date:desc")
        self.assertIn("from_publication_date:2024-01-01", sent["filter"])

    def test_a_tiny_page_size_does_not_trigger_a_pointless_second_request(self):
        router = Router([("title_and_abstract.search:", [work(1), work(2)])])
        papers = self.run_topic(router, "world model", per_page=2)
        self.assertEqual((len(papers), len(router.urls)), (2, 1))

    def test_a_leading_exclamation_cannot_negate_the_filter(self):
        router = Router([])
        self.run_topic(router, "!semiconductor growth")
        self.assertNotIn("!", router.filters()[0]["filter"])

    def test_blank_query_returns_nothing_without_a_request(self):
        router = Router([])
        self.assertEqual(self.run_topic(router, "  ,:|  "), [])
        self.assertEqual(router.urls, [])

    def test_explicit_date_bound_is_honoured(self):
        router = Router([])
        self.run_topic(router, "world model", from_date="2024-01-01")
        self.assertIn("from_publication_date:2024-01-01", router.filters()[0]["filter"])

    def test_the_api_key_is_sent_as_a_header_on_these_requests(self):
        seen = []

        def spy(request, timeout=None):
            seen.append(request.get_header("Authorization"))
            return Router([])(request, timeout)
        self.client.api_key = "dummy-openalex-key-0000"
        self.run_topic(spy, "world model")
        self.assertTrue(seen and all(h == "Bearer dummy-openalex-key-0000" for h in seen))


class SearchWorksTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.client = sources.OpenAlex(tmp.name)
        mock.patch.object(sources.time, "sleep").start()
        self.addCleanup(mock.patch.stopall)

    def test_an_exact_title_match_comes_before_looser_relevance_hits(self):
        router = Router([("title.search:LeWorldModel", [work(1, "LeWorldModel: Stable End-to-End")]),
                         ("search=LeWorldModel", [work(2, "Fast LeWorldModel"), work(1, "LeWorldModel: Stable End-to-End")])])
        with mock.patch.object(sources.urllib.request, "urlopen", router):
            found = self.client.search_works("LeWorldModel", per_page=8)
        self.assertEqual([w["openalex_id"].rsplit("/", 1)[-1] for w in found], ["W1", "W2"])  # deduplicated, title match first

    def test_chinese_only_titles_are_not_dropped_by_the_duplicate_filter(self):
        router = Router([("title.search:", []), ("search=半导体", [{**work(1), "title": "半导体物理"}, {**work(2), "title": "晶体生长"}])])
        with mock.patch.object(sources.urllib.request, "urlopen", router):
            found = self.client.search_works("半导体", per_page=8)
        self.assertEqual(sorted(w["title"] for w in found), ["半导体物理", "晶体生长"])

    def test_two_records_with_the_same_title_are_listed_once(self):
        router = Router([("title.search:", [work(1, "Same Title"), {**work(2, "Same Title"), "title": "Same Title 1"}]),
                         ("search=Same", [])])
        with mock.patch.object(sources.urllib.request, "urlopen", router):
            found = self.client.search_works("Same", per_page=8)
        self.assertEqual(len(found), 1)

    def test_a_title_search_failure_still_returns_the_relevance_results(self):
        calls = []

        def flaky(request, timeout=None):
            calls.append(request.full_url)
            if "title.search" in urllib.parse.unquote_plus(request.full_url):
                raise urllib.error.HTTPError(request.full_url, 400, "bad", {}, io.BytesIO(b""))
            return Router([("search=", [work(5)])])(request, timeout)
        with mock.patch.object(sources.urllib.request, "urlopen", flaky):
            found = self.client.search_works("some title", per_page=8)
        self.assertEqual(len(found), 1)


class SeedRankingAndPacingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.sleep = mock.patch.object(sources.time, "sleep").start()
        self.addCleanup(mock.patch.stopall)

    def test_a_title_that_starts_with_the_typed_name_beats_a_looser_hit_even_if_returned_later(self):
        client = sources.OpenAlex(self.dir)
        router = Router([("title.search:LeWorldModel", [work(2, "Fast LeWorldModel"), work(1, "LeWorldModel: Stable End-to-End Joint-Embedding")]),
                         ("search=LeWorldModel", [work(3, "A Gift to Yann LeCun and LeWorldModel")])])
        with mock.patch.object(sources.urllib.request, "urlopen", router):
            found = client.search_works("LeWorldModel", per_page=3)
        self.assertEqual(found[0]["title"], "LeWorldModel: Stable End-to-End Joint-Embedding 1")
        self.assertEqual(len(found), 3)

    def test_the_exact_stage_fetches_more_than_it_shows_so_the_real_paper_is_not_cut_off(self):
        client = sources.OpenAlex(self.dir)
        router = Router([])
        with mock.patch.object(sources.urllib.request, "urlopen", router):
            client.search_works("some name", per_page=8)
        self.assertGreater(int(router.filters()[0]["per-page"]), 8)

    def test_the_pause_after_a_request_is_short_with_a_key_and_long_without(self):
        for key, expected in (("dummy-openalex-key-0000", sources.KEYED_GAP_SECONDS), (None, sources.GAP_SECONDS)):
            self.sleep.reset_mock()
            with tempfile.TemporaryDirectory() as tmp:
                client = sources.OpenAlex(tmp, api_key=key)
                with mock.patch.object(sources.urllib.request, "urlopen", Router([("works", [])])):
                    client._fetch("https://api.openalex.org/works?search=x")
            self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [expected])


class CacheFreshnessTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.client = sources.OpenAlex(tmp.name)
        mock.patch.object(sources.time, "sleep").start()
        self.addCleanup(mock.patch.stopall)
        self.url = "https://api.openalex.org/works/W1?mailto=x"

    def age(self, seconds):
        for path in self.dir.glob("*.json"):
            old = time.time() - seconds
            os.utime(path, (old, old))

    def fetch(self, router, ttl):
        with mock.patch.object(sources.urllib.request, "urlopen", router):
            return self.client._fetch(self.url, ttl=ttl)

    def test_fresh_entry_is_served_without_a_request(self):
        self.fetch(Router([("W1", [work(1)])]), ttl=100)
        router = Router([])
        self.assertEqual(len(self.fetch(router, ttl=100)["results"]), 1)
        self.assertEqual(router.urls, [])

    def test_expired_entry_is_refetched(self):
        self.fetch(Router([("W1", [work(1)])]), ttl=100)
        self.age(1000)
        router = Router([("W1", [work(1), work(2)])])
        self.assertEqual(len(self.fetch(router, ttl=100)["results"]), 2)
        self.assertEqual(len(router.urls), 1)

    def test_expired_entry_is_served_when_the_refetch_fails_so_offline_use_still_works(self):
        self.fetch(Router([("W1", [work(1)])]), ttl=100)
        self.age(1000)
        offline = mock.Mock(side_effect=urllib.error.URLError("offline"))
        self.assertEqual(len(self.fetch(offline, ttl=100)["results"]), 1)

    def test_a_non_json_reply_falls_back_to_the_expired_copy(self):
        self.fetch(Router([("W1", [work(1)])]), ttl=100)
        self.age(1000)
        portal = mock.MagicMock()
        portal.__enter__.return_value = portal
        portal.read.return_value = b"<html>captive portal</html>"
        portal.headers = {}
        self.assertEqual(len(self.fetch(mock.Mock(return_value=portal), ttl=100)["results"]), 1)

    def test_a_cache_file_dated_in_the_future_counts_as_expired(self):
        self.fetch(Router([("W1", [work(1)])]), ttl=100)
        self.age(-10000)  # a clock that was moved backwards
        router = Router([("W1", [work(1), work(2)])])
        self.assertEqual(len(self.fetch(router, ttl=100)["results"]), 2)

    def test_no_ttl_keeps_the_old_forever_behaviour(self):
        self.fetch(Router([("W1", [work(1)])]), ttl=None)
        self.age(10 ** 8)
        router = Router([])
        self.fetch(router, ttl=None)
        self.assertEqual(router.urls, [])

    def test_expired_and_unreachable_without_any_copy_still_raises(self):
        offline = mock.Mock(side_effect=urllib.error.URLError("offline"))
        with self.assertRaises(sources.SourceError):
            self.fetch(offline, ttl=100)


class RateLimitNoteTests(unittest.TestCase):
    def test_limits_from_response_headers_are_remembered_for_the_settings_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = sources.OpenAlex(tmp)
            headers = {"X-RateLimit-Limit": "10000", "X-RateLimit-Remaining": "9959", "X-RateLimit-Limit-USD": "1",
                       "X-RateLimit-Remaining-USD": "0.9959", "X-RateLimit-Reset": "3600"}
            with mock.patch.object(sources.urllib.request, "urlopen", Router([("works", [])], headers=headers)), \
                    mock.patch.object(sources.time, "sleep"):
                client._fetch("https://api.openalex.org/works?search=x")
            note = sources.OpenAlex(tmp).rate_limit()  # a new object, as the HTTP server builds one per request
            self.assertEqual((note["limit"], note["remaining"]), (10000, 9959))
            self.assertAlmostEqual(note["remaining_usd"], 0.9959)
            self.assertIn("observed_at", note)

    def test_one_unusable_header_does_not_discard_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = sources.OpenAlex(tmp)
            client._note_rate_limit({"X-RateLimit-Limit": "10000", "X-RateLimit-Remaining": "9959.5", "X-RateLimit-Reset": "oops"})
            note = client.rate_limit()
            self.assertEqual(note["limit"], 10000)
            self.assertNotIn("reset_seconds", note)

    def test_no_headers_means_no_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = sources.OpenAlex(tmp)
            with mock.patch.object(sources.urllib.request, "urlopen", Router([("works", [])])), mock.patch.object(sources.time, "sleep"):
                client._fetch("https://api.openalex.org/works?search=x")
            self.assertIsNone(client.rate_limit())

    def test_a_garbled_note_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ratelimit.json").write_text("{not json")
            self.assertIsNone(sources.OpenAlex(tmp).rate_limit())


class ServiceWiringTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "harness").mkdir()
        (self.root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (self.root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        self.app = App(root=str(self.root), data_dir=str(self.root / "data"))
        self.addCleanup(self.app.store.close)

    def session(self, goal="半导体生长"):
        return self.app.create_guidance_session("半导体生长", goal)["id"]

    def test_creation_papers_tell_the_page_how_they_matched(self):
        from app import creation
        self.assertEqual(creation.paper_view({"key": "k", "title": "t", "match_mode": "relevance"})["match_mode"], "relevance")

    def test_creation_search_uses_the_topic_search_not_the_arxiv_title_recipe(self):
        sid = self.session()
        found = [sources.slim(work(1, "Semiconductor growth"), group="field")]
        with mock.patch.object(self.app.source, "discover_topic", return_value=found) as topic, \
                mock.patch.object(self.app.source, "discover", side_effect=AssertionError("legacy recipe must not be used")):
            result = self.app.guidance_search(sid, "半导体生长")
        topic.assert_called_once()
        self.assertEqual(result["total"], 1)
        self.assertIsNone(result["error"])

    def test_a_search_failure_is_reported_not_raised(self):
        sid = self.session()
        with mock.patch.object(self.app.source, "discover_topic", side_effect=sources.SourceError("down", "unavailable")):
            result = self.app.guidance_search(sid, "semiconductor growth")
        self.assertEqual((result["total"], result["error"]["kind"]), (0, "unavailable"))

    def test_refresh_for_a_project_with_keywords_searches_those_keywords_not_world_model(self):
        project = self.app.create_project("半导体", "manual", ["semiconductor growth", "epitaxy", "crystal defects", "extra"])["project_id"]
        asked = []

        def fake(query, **kw):
            asked.append((query, kw.get("order"), kw.get("from_date")))
            return [sources.slim(work(len(asked), query), group="field")]
        with mock.patch.object(self.app.source, "discover_topic", side_effect=fake), \
                mock.patch.object(self.app.source, "discover", side_effect=AssertionError("must not search 'world model'")):
            result = self.app.refresh_candidates(project_id=project)
        self.assertEqual([a[0] for a in asked], ["semiconductor growth", "epitaxy", "crystal defects"])  # at most three
        self.assertTrue(all(a[1] == "recent" and a[2] == sources.window_start(5) for a in asked))
        self.assertEqual(result["field"], 3)

    def test_refresh_bounds_chinese_keywords_by_date_too_so_the_feed_is_not_old_journal_papers(self):
        project = self.app.create_project("半导体", "manual", ["半导体生长"])["project_id"]
        asked = []
        with mock.patch.object(self.app.source, "discover_topic", side_effect=lambda q, **kw: asked.append(kw) or []):
            self.app.refresh_candidates(project_id=project)
        self.assertEqual((asked[0]["order"], asked[0]["from_date"]), ("recent", sources.window_start(5)))

    def test_refresh_for_the_default_project_keeps_the_world_model_recipe(self):
        with mock.patch.object(self.app.source, "discover", return_value=[]) as legacy, \
                mock.patch.object(self.app.source, "discover_topic", side_effect=AssertionError("default project keeps its recipe")):
            self.app.refresh_candidates()
        self.assertEqual(legacy.call_args.kwargs["search"], "world model")

    def test_refresh_reports_a_failed_keyword_and_continues(self):
        project = self.app.create_project("p", "manual", ["alpha", "beta"])["project_id"]

        def fake(query, **kw):
            if query == "alpha":
                raise sources.SourceError("down", "unavailable")
            return [sources.slim(work(9, query), group="field")]
        with mock.patch.object(self.app.source, "discover_topic", side_effect=fake):
            result = self.app.refresh_candidates(project_id=project)
        self.assertEqual(result["field"], 1)
        self.assertEqual(result["errors"][0]["query"], "alpha")

    def test_the_guidance_prompt_asks_for_english_and_chinese_search_phrases_and_matches_the_registered_prompt(self):
        sentence = "search_queries 给出英文检索式（OpenAlex 的标题和摘要多为英文）；用户用中文描述时再加中文检索式。keywords 用用户的语言。"
        captured = {}

        def spy(operation, messages, dry_run=False):
            captured["system"] = messages[0]["content"]
            return {"ok": False, "degraded": True, "reason": "test"}
        sid = self.session()
        with mock.patch.object(self.app.gateway, "call", side_effect=spy):
            self.app.guidance_turn(sid, "更关注外延生长", dry_run=False)
        self.assertIn(sentence, captured["system"])
        self.assertIn(sentence, (ROOT / "prompts" / "project-guidance.md").read_text(encoding="utf-8"))

    def test_openalex_status_includes_the_remembered_rate_limit(self):
        (self.root / "data" / "cache" / "ratelimit.json").write_text(json.dumps(
            {"limit": 10000, "remaining": 9000, "observed_at": time.time()}))
        self.assertEqual(self.app.openalex_status()["rate_limit"]["remaining"], 9000)


if __name__ == "__main__":
    unittest.main()
