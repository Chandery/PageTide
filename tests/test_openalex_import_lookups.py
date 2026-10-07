"""The two OpenAlex requests library import adds: many DOIs in one request, and a title read from a PDF.

No network: `_fetch` is replaced, so these pin the request each one makes and how an answer from the server that
means "your request is wrong" differs from "the network is down" (the importer pauses for the second, not the first)."""
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.sources import OpenAlex, SourceError


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = OpenAlex(Path(self.tmp.name) / "cache")

    def requested(self, patched):
        return [urllib.parse.parse_qs(urllib.parse.urlsplit(call.args[0]).query) for call in patched.call_args_list]


class WorksByDoisTests(Base):
    def test_all_the_dois_go_in_one_or_filter_request_sized_to_the_list(self):
        with mock.patch.object(OpenAlex, "_fetch", return_value={"results": [{"id": "W1"}]}) as fetch:
            out = self.client.works_by_dois(["https://doi.org/10.1/a", "https://doi.org/10.1/b", "https://doi.org/10.1/a"])
        self.assertEqual(out, [{"id": "W1"}])
        (query,) = self.requested(fetch)
        self.assertEqual(query["filter"], ["doi:https://doi.org/10.1/a|https://doi.org/10.1/b"])
        self.assertEqual(query["per-page"], ["2"])

    def test_a_doi_that_could_change_the_filter_is_never_put_in_it(self):
        with mock.patch.object(OpenAlex, "_fetch", return_value={"results": []}) as fetch:
            self.assertEqual(self.client.works_by_dois(["https://doi.org/10.1/a,b", "https://doi.org/10.1/c|d", ""]), [])
        fetch.assert_not_called()

    def test_a_400_answer_means_the_request_was_wrong_not_that_the_network_is_down(self):
        error = SourceError("OpenAlex fetch failed: https://api.openalex.org/works?x: HTTP Error 400: Bad Request", "network_error")
        with mock.patch.object(OpenAlex, "_fetch", side_effect=error):
            with self.assertRaises(SourceError) as caught:
                self.client.works_by_dois(["https://doi.org/10.1/a"])
        self.assertEqual(caught.exception.kind, "invalid_input")

    def test_a_real_network_failure_and_a_server_error_are_still_network_errors(self):
        for text in ("OpenAlex fetch failed: u: <urlopen error [Errno 8] nodename nor servname provided>", "OpenAlex fetch failed: u: HTTP Error 500: Server Error"):
            with mock.patch.object(OpenAlex, "_fetch", side_effect=SourceError(text, "network_error")):
                with self.assertRaises(SourceError) as caught:
                    self.client.works_by_dois(["https://doi.org/10.1/a"])
            self.assertEqual(caught.exception.kind, "network_error", text)

    def test_being_rate_limited_stays_unavailable(self):
        with mock.patch.object(OpenAlex, "_fetch", side_effect=SourceError("HTTP Error 429: Too Many Requests", "unavailable")):
            with self.assertRaises(SourceError) as caught:
                self.client.works_by_dois(["https://doi.org/10.1/a"])
        self.assertEqual(caught.exception.kind, "unavailable")


class TitleLookupTests(Base):
    def test_one_title_filter_request_is_enough_when_it_finds_something(self):
        with mock.patch.object(OpenAlex, "_fetch", return_value={"results": [{"id": "W1"}]}) as fetch:
            out = self.client.title_lookup("Attention is all you need")
        self.assertEqual(out, [{"id": "W1"}])
        (query,) = self.requested(fetch)
        self.assertEqual(query["filter"], ["title.search:Attention is all you need"])
        self.assertEqual(query["per-page"], ["5"])

    def test_a_relevance_search_is_only_added_when_the_filter_finds_nothing(self):
        with mock.patch.object(OpenAlex, "_fetch", side_effect=[{"results": []}, {"results": [{"id": "W2"}]}]) as fetch:
            self.assertEqual(self.client.title_lookup("Noisy title extracted from a PDF"), [{"id": "W2"}])
        first, second = self.requested(fetch)
        self.assertIn("filter", first)
        self.assertEqual(second["search"], ["Noisy title extracted from a PDF"])

    def test_the_title_cannot_change_the_structure_of_the_filter(self):
        with mock.patch.object(OpenAlex, "_fetch", return_value={"results": [{"id": "W1"}]}) as fetch:
            self.client.title_lookup('A, B|C: "quoted" title')
        (query,) = self.requested(fetch)
        self.assertEqual(query["filter"], ["title.search:A B C quoted title"])

    def test_an_empty_title_makes_no_request(self):
        with mock.patch.object(OpenAlex, "_fetch") as fetch:
            self.assertEqual(self.client.title_lookup("  ,|: "), [])
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
