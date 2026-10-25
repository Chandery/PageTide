"""arXiv's own API as the arXiv source without an OpenAlex key, and as the fallback when OpenAlex cannot answer."""
import io
import tempfile
import unittest
import urllib.error
import urllib.parse
from unittest import mock

from app import arxiv_api
from app.sources import OpenAlex, SourceError

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2410.01234v2</id>
    <published>2024-10-02T17:59:59Z</published>
    <title>World Models
      for Robot Learning</title>
    <summary>  We study world models that predict the next frame.  </summary>
    <author><name>Ada Lovelace</name></author><author><name>Alan Turing</name></author>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/hep-th/9901001v1</id>
    <published>1999-01-01T00:00:00Z</published>
    <title>An Old Style Identifier</title>
    <summary>Text.</summary>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2410.01234v1</id>
    <published>2024-10-02T17:59:59Z</published>
    <title>World Models for Robot Learning</title>
  </entry>
  <entry><id>http://arxiv.org/api/errors#incorrect_id_format</id><title>Error</title></entry>
</feed>"""


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class Opener:
    def __init__(self, body=FEED, error=None):
        self.body, self.error, self.requests = body, error, []

    def __call__(self, request, timeout):
        self.requests.append(request)
        if self.error:
            raise self.error
        return Response(self.body)


def client(opener, clock=None):
    times = iter(clock or [100.0 + 10 * i for i in range(100)])
    sleeps = []
    return arxiv_api.ArxivAPI(opener=opener, sleep=sleeps.append, clock=lambda: next(times)), sleeps


class ArxivApiTests(unittest.TestCase):
    def setUp(self):
        arxiv_api._LAST[0] = 0.0

    def test_entries_become_papers_keyed_like_openalex_arxiv_records(self):
        api, _ = client(Opener())
        papers = api.discover_topic("world model", per_page=10, from_date="2024-01-01", to_date="2026-10-25", order="recent")
        self.assertEqual([p["arxiv_id"] for p in papers], ["2410.01234", "hep-th/9901001"])   # the duplicate version and the error entry are gone
        first = papers[0]
        self.assertEqual(first["key"], "https://doi.org/10.48550/arxiv.2410.01234")
        self.assertEqual(first["title"], "World Models for Robot Learning")
        self.assertEqual(first["abstract"], "We study world models that predict the next frame.")
        self.assertEqual((first["published"], first["work_type"], first["source"]), ("2024-10-02", "preprint", "arXiv (Cornell University)"))
        self.assertEqual(first["authors"], ["Ada Lovelace", "Alan Turing"])
        self.assertEqual(first["oa"]["pdf_urls"], ["https://arxiv.org/pdf/2410.01234"])
        self.assertIsNone(first["metadata_language"])

    def test_the_phrase_is_asked_first_and_a_sparse_answer_is_topped_up_by_every_word(self):
        opener = Opener()
        api, _ = client(opener)
        api.discover_topic('world model" OR ti:x', per_page=5, from_date="2024-01-01", to_date="2026-10-25", order="recent", page=2)
        asked = [urllib.parse.parse_qs(urllib.parse.urlsplit(r.full_url).query) for r in opener.requests]
        self.assertEqual({urllib.parse.urlsplit(r.full_url).netloc for r in opener.requests}, {"export.arxiv.org"})
        dates = " AND submittedDate:[202401010000 TO 202610252359]"
        self.assertEqual(asked[0]["search_query"], ['(ti:"world model OR ti x" OR abs:"world model OR ti x")' + dates])   # quotes cannot break out
        self.assertEqual(asked[1]["search_query"], ['(ti:"world" OR abs:"world") AND (ti:"model" OR abs:"model") AND (ti:"OR" OR abs:"OR") '
                                                   'AND (ti:"ti" OR abs:"ti") AND (ti:"x" OR abs:"x")' + dates])
        self.assertEqual((asked[0]["sortBy"], asked[0]["start"], asked[0]["max_results"]), (["submittedDate"], ["5"], ["5"]))

    def test_enough_phrase_matches_need_no_second_request(self):
        opener = Opener()
        api, _ = client(opener)
        api.discover_topic("world model", per_page=2)
        self.assertEqual(len(opener.requests), 1)

    def test_chinese_text_is_not_sent(self):
        opener = Opener()
        api, _ = client(opener)
        self.assertEqual(api.discover_topic("世界模型"), [])
        self.assertEqual(opener.requests, [])

    def test_requests_are_three_seconds_apart(self):
        api, sleeps = client(Opener(), clock=[100.0, 100.5, 101.0, 101.0])
        api.discover_topic("world model", per_page=2)
        api.discover_topic("world model", per_page=2)
        self.assertEqual(sleeps, [2.5])

    def test_failures_have_kinds_and_entity_tricks_are_refused(self):
        cases = [(urllib.error.HTTPError("u", 429, "busy", {}, None), "unavailable"),
                 (urllib.error.HTTPError("u", 500, "err", {}, None), "network_error"),
                 (urllib.error.URLError("down"), "network_error")]
        for error, kind in cases:
            api, _ = client(Opener(error=error))
            with self.assertRaises(SourceError) as caught:
                api.discover_topic("world model")
            self.assertEqual(caught.exception.kind, kind)
        for body in (b"not xml", b'<!DOCTYPE x [<!ENTITY a "b">]><feed/>'):
            api, _ = client(Opener(body))
            with self.assertRaises(SourceError) as caught:
                api.discover_topic("world model")
            self.assertEqual(caught.exception.kind, "bad_response")


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.arxiv = mock.Mock()
        self.arxiv.discover_topic.return_value = [{"key": "from-arxiv"}]

    def source(self, key=None, fetch=None):
        source = OpenAlex(self.tmp.name, api_key=key)
        source.arxiv = self.arxiv
        source._fetch = mock.Mock(side_effect=fetch or (lambda *a, **k: {"results": []}))
        return source

    def test_without_a_key_arxiv_is_searched_directly_and_openalex_never(self):
        source = self.source()
        self.assertEqual(source.discover_topic("world model", source_openalex=False), [{"key": "from-arxiv"}])
        self.assertEqual(source.discover_topic("world model"), [{"key": "from-arxiv"}])   # both switches on: still no OpenAlex
        self.assertEqual(source.discover("world model"), [{"key": "from-arxiv"}])
        source._fetch.assert_not_called()

    def test_without_a_key_journals_alone_search_nothing(self):
        source = self.source()
        self.assertEqual(source.discover_topic("world model", source_arxiv=False), [])
        source._fetch.assert_not_called()
        self.arxiv.discover_topic.assert_not_called()

    def test_with_a_key_openalex_answers_and_arxiv_is_not_asked(self):
        source = self.source(key="k" * 20)
        source.discover_topic("world model")
        source._fetch.assert_called()
        self.arxiv.discover_topic.assert_not_called()

    def test_with_a_key_an_openalex_outage_falls_back_to_arxiv_for_the_rest_of_the_refresh(self):
        source = self.source(key="k" * 20, fetch=SourceError("busy", "unavailable"))
        self.assertEqual(source.discover_topic("world model", order="recent"), [{"key": "from-arxiv"}])
        calls = source._fetch.call_count
        source.discover_topic("robot learning")
        self.assertEqual(source._fetch.call_count, calls)          # OpenAlex is not waited on again
        self.assertEqual(self.arxiv.discover_topic.call_count, 2)

    def test_no_fallback_for_journals_only_or_for_a_real_answer(self):
        source = self.source(key="k" * 20, fetch=SourceError("busy", "unavailable"))
        with self.assertRaises(SourceError):
            source.discover_topic("world model", source_arxiv=False)
        source = self.source(key="k" * 20, fetch=SourceError("bad", "invalid_input"))
        with self.assertRaises(SourceError):
            source.discover_topic("world model")
        self.arxiv.discover_topic.assert_not_called()


if __name__ == "__main__":
    unittest.main()
