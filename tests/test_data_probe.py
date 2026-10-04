import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import data_probe

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2506.09985v2</id>
    <title>DINO-WM:  World Models on Pre-trained
      Visual Features enable Zero-shot Planning</title>
    <published>2025-06-11T17:59:00Z</published>
    <updated>2025-06-20T09:00:00Z</updated>
    <summary>We build a world model on frozen DINO features.</summary>
    <arxiv:primary_category term="cs.LG"/>
    <author><name>Alice</name></author>
    <author><name>Bob</name></author>
  </entry>
</feed>
"""


class DataProbeTests(unittest.TestCase):
    def test_normalize_title_collapses_punctuation_and_case(self):
        self.assertEqual(data_probe.normalize_title("DINO-WM:  World Models!"),
                         "dino wm world models")

    def test_parse_arxiv_entries_extracts_fields_and_flattens_whitespace(self):
        entries = data_probe.parse_arxiv_entries(SAMPLE)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["arxiv_id"], "2506.09985v2")
        self.assertEqual(entry["title"], "DINO-WM: World Models on Pre-trained Visual Features enable Zero-shot Planning")
        self.assertEqual(entry["primary_category"], "cs.LG")
        self.assertEqual(entry["authors"], ["Alice", "Bob"])
        self.assertEqual(entry["published"], "2025-06-11T17:59:00Z")

    def test_best_match_prefers_exact_then_prefix(self):
        entries = data_probe.parse_arxiv_entries(SAMPLE)
        exact, score = data_probe.best_match(
            "DINO-WM: World Models on Pre-trained Visual Features enable Zero-shot Planning", entries, "title")
        self.assertEqual(score, 1.0)
        self.assertEqual(exact["arxiv_id"], "2506.09985v2")
        prefix, score = data_probe.best_match("DINO-WM", entries, "title")
        self.assertEqual(score, 0.9)
        self.assertIsNotNone(prefix)

    def test_best_match_scores_partial_overlap_and_handles_empty(self):
        entries = data_probe.parse_arxiv_entries(SAMPLE)
        _, score = data_probe.best_match("World Models for Robot Manipulation", entries, "title")
        self.assertLess(score, 0.6)
        best, score = data_probe.best_match("anything", [], "title")
        self.assertIsNone(best)
        self.assertEqual(score, 0.0)

    def test_abstract_text_rebuilds_word_order(self):
        inverted = {"world": [0], "models": [2], "learn": [1]}
        self.assertEqual(data_probe.abstract_text(inverted), "world learn models")
        self.assertEqual(data_probe.abstract_text(None), "")
        self.assertEqual(data_probe.abstract_text({}), "")

    def test_openalex_ids_pulls_arxiv_from_doi(self):
        ids = data_probe.openalex_ids({"id": "https://openalex.org/W1", "doi": "https://doi.org/10.48550/arxiv.2411.04983"})
        self.assertEqual(ids["arxiv_id"], "2411.04983")
        ids = data_probe.openalex_ids({"id": "https://openalex.org/W2", "ids": {"arxiv": "2506.09985"}})
        self.assertEqual(ids["arxiv_id"], "2506.09985")
        ids = data_probe.openalex_ids({})
        self.assertIsNone(ids["arxiv_id"])

    def test_parser_rejects_malformed_xml(self):
        with self.assertRaises(Exception):
            data_probe.parse_arxiv_entries("<feed><entry>")


class MissingSeedTests(unittest.TestCase):
    """A seed OpenAlex no longer knows (404) is reported, not fatal, and is not retried."""

    SEEDS = [
        {"title": "Gone Paper", "ids": {"openalex_id": "W1"}},
        {"title": "Present Paper", "ids": {"openalex_id": "W2"}},
    ]

    def _urlopen(self, calls):
        def fake(request, timeout=None):
            url = request.full_url
            calls.append(url)
            if "/W1?" in url:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b""))
            body = json.dumps({"id": "https://openalex.org/W2", "title": "Present Paper"}).encode()
            response = mock.MagicMock()
            response.__enter__.return_value = response
            response.read.return_value = body
            response.headers = {}
            return response
        return fake

    def test_404_seed_is_not_found_and_does_not_stop_other_seeds(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(data_probe.urllib.request, "urlopen", self._urlopen(calls)), \
                mock.patch.object(data_probe.time, "sleep"):
            results = data_probe.resolve_seeds_openalex(self.SEEDS, tmp, refresh=True)
        self.assertEqual([r["status"] for r in results], ["not_found", "resolved"])
        self.assertEqual(results[0]["resolution"], "openalex_id+http_404")
        self.assertEqual(sum("/W1?" in url for url in calls), 1)  # a missing ID does not appear on retry


if __name__ == "__main__":
    unittest.main()
