"""PDF acquisition: OA fields kept from OpenAlex, ordered sources, guarded fetch, visible failures.

No test touches the network: the fetcher's single `_open` seam and `time.sleep` are patched,
in the style of tests/test_data_probe.py.
"""
import hashlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import migrations, pdf_fetch, sources
from app.db import Store
from app.service import App

PDF = b"%PDF-1.7\n" + b"x" * 200
PDF_B = b"%PDF-1.4\n" + b"y" * 300

WORK = {
    "id": "https://openalex.org/W1", "doi": "https://doi.org/10.1234/abc", "title": "An OA paper",
    "ids": {}, "publication_date": "2026-01-02",
    "open_access": {"is_oa": True, "oa_status": "green", "oa_url": "https://repo.example.org/p.pdf"},
    "best_oa_location": {"pdf_url": "https://repo.example.org/p.pdf", "landing_page_url": "https://repo.example.org/p",
                         "license": "cc-by", "version": "acceptedVersion"},
    "primary_location": {"pdf_url": "http://insecure.example.org/p.pdf"},
    "locations": [{"pdf_url": "https://repo.example.org/p.pdf"}, {"pdf_url": "https://other.example.org/q.pdf"},
                  {"pdf_url": None}],
}


class FakeResponse:
    def __init__(self, body=b"", headers=None, url=None):
        self._io = io.BytesIO(body)
        self.headers = headers or {}
        self._url = url

    def read(self, n=-1):
        return self._io.read(n)

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(url, code, headers=None):
    return urllib.error.HTTPError(url, code, "err", headers or {}, io.BytesIO(b""))


class Net:
    """Routes URLs to responses and records every request; robots.txt is absent (404) unless given."""

    def __init__(self, routes=None, robots=None):
        self.routes, self.robots, self.calls = routes or {}, robots, []

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            if self.robots is None:
                raise http_error(url, 404)
            return FakeResponse(self.robots.encode(), url=url)
        result = self.routes.get(url)
        if isinstance(result, list):
            result = result.pop(0) if len(result) > 1 else result[0]
        if result is None:
            raise http_error(url, 404)
        if isinstance(result, Exception):
            raise result
        return result if not isinstance(result, bytes) else FakeResponse(result, url=url)

    def pdf_calls(self):
        return [u for u in self.calls if not u.endswith("/robots.txt")]


class SlimOATests(unittest.TestCase):
    def test_slim_keeps_open_access_fields_and_only_https_pdf_urls(self):
        oa = sources.slim(WORK)["oa"]
        self.assertTrue(oa["is_oa"])
        self.assertEqual(oa["oa_status"], "green")
        self.assertEqual(oa["pdf_urls"], ["https://repo.example.org/p.pdf", "https://other.example.org/q.pdf"])
        self.assertEqual(oa["license"], "cc-by")
        self.assertEqual(oa["version"], "acceptedVersion")

    def test_slim_without_oa_data_has_no_oa(self):
        self.assertIsNone(sources.slim({"id": "https://openalex.org/W2", "title": "t"})["oa"])


class CandidateTests(unittest.TestCase):
    def test_arxiv_first_then_openalex_urls_without_duplicates(self):
        paper = {"arxiv_id": "2603.19312", "oa_json": json.dumps(sources.slim(WORK)["oa"])}
        got = pdf_fetch.candidates(paper)
        self.assertEqual([c["kind"] for c in got], ["arxiv", "openalex_oa", "openalex_oa"])
        self.assertEqual(got[0]["url"], "https://arxiv.org/pdf/2603.19312")

    def test_no_source_gives_empty_list(self):
        self.assertEqual(pdf_fetch.candidates({"arxiv_id": None, "oa_json": None}), [])

    def test_bad_oa_json_is_ignored(self):
        self.assertEqual(pdf_fetch.candidates({"arxiv_id": None, "oa_json": "{not json"}), [])


class FetchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dest = Path(tmp.name)
        self.sleep = mock.patch.object(pdf_fetch.time, "sleep").start()
        self.addCleanup(mock.patch.stopall)
        self.fetcher = pdf_fetch.Fetcher(self.dest)

    def run_fetch(self, net, url="https://arxiv.org/pdf/2603.19312", stem="2603.19312"):
        with mock.patch.object(pdf_fetch, "_open", net):
            return self.fetcher.fetch(url, stem)

    def error_kind(self, net, **kw):
        with self.assertRaises(pdf_fetch.PdfFetchError) as caught:
            self.run_fetch(net, **kw)
        return caught.exception.kind

    def test_success_writes_named_file_with_hash(self):
        result = self.run_fetch(Net({"https://arxiv.org/pdf/2603.19312": PDF}))
        digest = hashlib.sha256(PDF).hexdigest()
        self.assertEqual(result["sha256"], digest)
        self.assertEqual(result["bytes"], len(PDF))
        self.assertEqual(Path(result["path"]).read_bytes(), PDF)
        self.assertEqual(Path(result["path"]).name, f"2603.19312-{digest[:12]}.pdf")
        self.assertEqual([p.name for p in self.dest.iterdir()], [Path(result["path"]).name])  # no .part left

    def test_html_landing_page_is_not_pdf(self):
        net = Net({"https://arxiv.org/pdf/x": b"<html>login</html>"})
        self.assertEqual(self.error_kind(net, url="https://arxiv.org/pdf/x", stem="x"), "not_pdf")
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_oversize_by_header_is_refused_without_reading(self):
        big = FakeResponse(PDF, headers={"Content-Length": str(pdf_fetch.PDF_MAX_BYTES + 1)})
        self.assertEqual(self.error_kind(Net({"https://arxiv.org/pdf/x": big}), url="https://arxiv.org/pdf/x", stem="x"),
                         "too_large")

    def test_oversize_while_streaming_leaves_no_partial_file(self):
        with mock.patch.object(pdf_fetch, "PDF_MAX_BYTES", 100):
            kind = self.error_kind(Net({"https://arxiv.org/pdf/x": PDF}), url="https://arxiv.org/pdf/x", stem="x")
        self.assertEqual(kind, "too_large")
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_403_is_paywalled_and_not_retried(self):
        net = Net({"https://pub.example.org/p.pdf": http_error("https://pub.example.org/p.pdf", 403)})
        self.assertEqual(self.error_kind(net, url="https://pub.example.org/p.pdf", stem="oa"), "paywalled_or_blocked")
        self.assertEqual(len(net.pdf_calls()), 1)

    def test_404_is_not_found_and_not_retried(self):
        net = Net({})
        self.assertEqual(self.error_kind(net, url="https://pub.example.org/gone.pdf", stem="oa"), "not_found")
        self.assertEqual(len(net.pdf_calls()), 1)

    def test_429_honours_retry_after_then_gives_rate_limited(self):
        url = "https://arxiv.org/pdf/x"
        net = Net({url: http_error(url, 429, {"Retry-After": "7"})})
        self.assertEqual(self.error_kind(net, url=url, stem="x"), "rate_limited")
        self.assertEqual(len(net.pdf_calls()), 2)  # exactly one retry
        self.assertIn(mock.call(7.0), self.sleep.call_args_list)

    def test_429_then_success_retries_once(self):
        url = "https://arxiv.org/pdf/x"
        net = Net({url: [http_error(url, 429, {"Retry-After": "1"}), FakeResponse(PDF, url=url)]})
        self.assertTrue(self.run_fetch(net, url=url, stem="x")["path"])

    def test_retry_after_wait_is_bounded(self):
        url = "https://arxiv.org/pdf/x"
        net = Net({url: http_error(url, 429, {"Retry-After": "9999"})})
        self.error_kind(net, url=url, stem="x")
        self.assertTrue(all(call.args[0] <= pdf_fetch.MAX_WAIT_SECONDS for call in self.sleep.call_args_list))

    def test_network_error_is_reported(self):
        url = "https://arxiv.org/pdf/x"
        net = Net({url: urllib.error.URLError("down")})
        self.assertEqual(self.error_kind(net, url=url, stem="x"), "network_error")

    def test_http_url_is_refused_before_any_request(self):
        net = Net({})
        self.assertEqual(self.error_kind(net, url="http://pub.example.org/p.pdf", stem="oa"), "invalid_url")
        self.assertEqual(net.calls, [])

    def test_redirect_to_http_is_refused(self):
        url = "https://arxiv.org/pdf/x"
        net = Net({url: FakeResponse(PDF, url="http://evil.example.org/p.pdf")})
        self.assertEqual(self.error_kind(net, url=url, stem="x"), "invalid_url")
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_robots_disallow_is_reported_and_pdf_not_requested(self):
        net = Net({"https://arxiv.org/pdf/x": PDF}, robots="User-agent: *\nDisallow: /pdf/\n")
        self.assertEqual(self.error_kind(net, url="https://arxiv.org/pdf/x", stem="x"), "robots_disallowed")
        self.assertEqual(net.pdf_calls(), [])

    def test_robots_server_error_blocks_instead_of_assuming_allowed(self):
        net = Net({"https://arxiv.org/pdf/x": PDF})
        original = net.__call__

        def robots_500(request, timeout=None):
            if request.full_url.endswith("/robots.txt"):
                raise http_error(request.full_url, 503)
            return original(request, timeout)
        with mock.patch.object(pdf_fetch, "_open", robots_500):
            with self.assertRaises(pdf_fetch.PdfFetchError) as caught:
                self.fetcher.fetch("https://arxiv.org/pdf/x", "x")
        self.assertEqual(caught.exception.kind, "network_error")

    def test_robots_is_fetched_once_per_host(self):
        net = Net({"https://arxiv.org/pdf/a": PDF, "https://arxiv.org/pdf/b": PDF_B})
        with mock.patch.object(pdf_fetch, "_open", net):
            self.fetcher.fetch("https://arxiv.org/pdf/a", "a")
            self.fetcher.fetch("https://arxiv.org/pdf/b", "b")
        self.assertEqual(sum(u.endswith("/robots.txt") for u in net.calls), 1)

    def test_same_content_twice_is_idempotent_different_content_keeps_both(self):
        url = "https://arxiv.org/pdf/x"
        first = self.run_fetch(Net({url: PDF}), url=url, stem="x")
        again = self.run_fetch(Net({url: PDF}), url=url, stem="x")
        self.assertEqual(first["path"], again["path"])
        newer = self.run_fetch(Net({url: PDF_B}), url=url, stem="x")
        self.assertNotEqual(first["path"], newer["path"])
        self.assertTrue(Path(first["path"]).exists() and Path(newer["path"]).exists())

    def test_requests_to_one_arxiv_host_are_spaced_three_seconds(self):
        clock = [100.0]
        self.sleep.side_effect = lambda seconds: clock.__setitem__(0, clock[0] + seconds)
        net = Net({"https://arxiv.org/pdf/a": PDF, "https://arxiv.org/pdf/b": PDF_B})
        with mock.patch.object(pdf_fetch, "_open", net), mock.patch.object(pdf_fetch.time, "monotonic", lambda: clock[0]):
            self.fetcher.fetch("https://arxiv.org/pdf/a", "a")
            self.assertEqual(self.sleep.call_args_list, [])  # the first request is not delayed
            self.fetcher.fetch("https://arxiv.org/pdf/b", "b")
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [3.0])

    def test_robots_crawl_delay_longer_than_default_is_honoured(self):
        clock = [100.0]
        self.sleep.side_effect = lambda seconds: clock.__setitem__(0, clock[0] + seconds)
        net = Net({"https://arxiv.org/pdf/a": PDF, "https://arxiv.org/pdf/b": PDF_B},
                  robots="User-agent: *\nCrawl-delay: 15\nAllow: /pdf\n")
        with mock.patch.object(pdf_fetch, "_open", net), mock.patch.object(pdf_fetch.time, "monotonic", lambda: clock[0]):
            self.fetcher.fetch("https://arxiv.org/pdf/a", "a")
            self.fetcher.fetch("https://arxiv.org/pdf/b", "b")
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [15.0])

    def test_absurd_crawl_delay_is_capped(self):
        clock = [100.0]
        self.sleep.side_effect = lambda seconds: clock.__setitem__(0, clock[0] + seconds)
        net = Net({"https://arxiv.org/pdf/a": PDF, "https://arxiv.org/pdf/b": PDF_B},
                  robots="User-agent: *\nCrawl-delay: 99999\n")
        with mock.patch.object(pdf_fetch, "_open", net), mock.patch.object(pdf_fetch.time, "monotonic", lambda: clock[0]):
            self.fetcher.fetch("https://arxiv.org/pdf/a", "a")
            self.fetcher.fetch("https://arxiv.org/pdf/b", "b")
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [pdf_fetch.MAX_CRAWL_DELAY_SECONDS])


class StoreMigrationTests(unittest.TestCase):
    def test_migration_005_adds_columns_and_keeps_existing_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "db.sqlite"
            store = Store(path)
            store.init()
            store.upsert_papers([{"key": "k", "title": "T"}])
            store.record_pdf("k", "/tmp/a.pdf", "https://arxiv.org/pdf/1")
            store.close()
            conn = sqlite3.connect(str(path))
            conn.execute("DELETE FROM schema_version WHERE version=5")
            conn.commit()
            conn.close()
            store = Store(path)
            store.init()  # re-applies 005 on an already-migrated file without failing
            self.assertEqual(migrations.get_schema_version(store.conn), len(migrations.MIGRATIONS))
            self.assertGreaterEqual(len(migrations.MIGRATIONS), 5)
            columns = {r[1] for r in store.conn.execute("PRAGMA table_info(pdfs)")}
            self.assertTrue({"sha256", "bytes", "source_kind", "license"} <= columns)
            self.assertIn("oa_json", {r[1] for r in store.conn.execute("PRAGMA table_info(papers)")})
            row = store.conn.execute("SELECT path, source_url FROM pdfs WHERE paper_key='k'").fetchone()
            self.assertEqual(row["path"], "/tmp/a.pdf")

    def test_upsert_stores_oa_and_refreshes_it_for_existing_paper(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "db.sqlite")
            store.init()
            store.upsert_papers([{"key": "k", "title": "T"}])
            self.assertIsNone(store.paper("k")["oa_json"])
            store.upsert_papers([{"key": "k", "title": "T", "oa": {"is_oa": True, "pdf_urls": ["https://a/b.pdf"]}}])
            self.assertEqual(json.loads(store.paper("k")["oa_json"])["pdf_urls"], ["https://a/b.pdf"])

    def test_record_pdf_stores_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "db.sqlite")
            store.init()
            store.upsert_papers([{"key": "k", "title": "T"}])
            store.record_pdf("k", "/x.pdf", "https://u", sha256="ab", size=5, source_kind="openalex_oa", license="cc-by")
            row = dict(store.conn.execute("SELECT * FROM pdfs WHERE paper_key='k'").fetchone())
            self.assertEqual((row["sha256"], row["bytes"], row["source_kind"], row["license"]),
                             ("ab", 5, "openalex_oa", "cc-by"))


class DownloadPdfTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "harness").mkdir()
        (root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        self.app = App(root=str(root), data_dir=str(root / "data"))
        self.addCleanup(self.app.store.close)
        mock.patch.object(pdf_fetch.time, "sleep").start()
        self.addCleanup(mock.patch.stopall)

    def add(self, **paper):
        base = {"key": "k", "title": "T"}
        base.update(paper)
        self.app.store.upsert_papers([base])
        return base["key"]

    def download(self, net, key="k", **kw):
        with mock.patch.object(pdf_fetch, "_open", net):
            return self.app.download_pdf(key, **kw)

    def test_arxiv_paper_downloads_and_records_provenance(self):
        key = self.add(arxiv_id="2603.19312")
        result = self.download(Net({"https://arxiv.org/pdf/2603.19312": PDF}))
        self.assertTrue(result["ok"])
        self.assertEqual(result["source_kind"], "arxiv")
        row = dict(self.app.store.conn.execute("SELECT * FROM pdfs WHERE paper_key=?", (key,)).fetchone())
        self.assertEqual(row["sha256"], hashlib.sha256(PDF).hexdigest())
        self.assertEqual(row["source_url"], "https://arxiv.org/pdf/2603.19312")
        self.assertTrue(self.app.pdf_path(key))

    def test_non_arxiv_paper_falls_back_to_openalex_oa_url(self):
        self.add(oa=sources.slim(WORK)["oa"])
        result = self.download(Net({"https://repo.example.org/p.pdf": PDF}))
        self.assertTrue(result["ok"])
        self.assertEqual(result["source_kind"], "openalex_oa")
        row = self.app.store.conn.execute("SELECT license FROM pdfs WHERE paper_key='k'").fetchone()
        self.assertEqual(row["license"], "cc-by")

    def test_arxiv_failure_falls_through_to_next_source(self):
        self.add(arxiv_id="2603.19312", oa=sources.slim(WORK)["oa"])
        net = Net({"https://repo.example.org/p.pdf": PDF})  # arXiv URL is unrouted -> 404
        result = self.download(net)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source_kind"], "openalex_oa")

    def test_cached_file_is_reused_without_any_request(self):
        self.add(arxiv_id="2603.19312")
        self.download(Net({"https://arxiv.org/pdf/2603.19312": PDF}))
        net = Net({})
        result = self.download(net)
        self.assertTrue(result["ok"] and result["cached"])
        self.assertEqual(net.calls, [])

    def test_paper_without_any_source_reports_no_oa_source(self):
        self.add()
        with mock.patch.object(self.app.source, "work", side_effect=sources.SourceError("x", "network_error")):
            result = self.download(Net({}))
        self.assertEqual((result["ok"], result["reason"]), (False, "no_oa_source"))

    def test_missing_oa_data_is_refreshed_from_openalex_by_id(self):
        self.add(openalex_id="https://openalex.org/W1")
        with mock.patch.object(self.app.source, "work", return_value=WORK) as work:
            result = self.download(Net({"https://repo.example.org/p.pdf": PDF}))
        work.assert_called_once()
        self.assertTrue(result["ok"])

    def test_all_sources_failing_returns_visible_reason_and_attempts(self):
        self.add(oa=sources.slim(WORK)["oa"])
        url = "https://repo.example.org/p.pdf"
        net = Net({url: http_error(url, 403),
                   "https://other.example.org/q.pdf": http_error("https://other.example.org/q.pdf", 403)})
        result = self.download(net)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "paywalled_or_blocked")
        self.assertEqual(len(result["attempts"]), 2)

    def test_download_failure_does_not_block_recommendation_paths(self):
        self.add(arxiv_id="2603.19312")
        result = self.download(Net({"https://arxiv.org/pdf/2603.19312": urllib.error.URLError("offline")}))
        self.assertEqual(result["reason"], "network_error")
        self.assertIsInstance(self.app.cards(), list)  # the offline failure leaves the app usable

    def test_unknown_paper_still_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.app.download_pdf("nope")

    def test_refresh_with_changed_content_keeps_the_old_file(self):
        key = self.add(arxiv_id="2603.19312")
        first = self.download(Net({"https://arxiv.org/pdf/2603.19312": PDF}))
        second = self.download(Net({"https://arxiv.org/pdf/2603.19312": PDF_B}), refresh=True)
        self.assertNotEqual(first["path"], second["path"])
        self.assertTrue(Path(first["path"]).exists())
        self.assertEqual(self.app.pdf_path(key), Path(second["path"]))


class ContactEmailTests(unittest.TestCase):
    def test_mailto_uses_configured_email_and_cache_key_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = sources.OpenAlex(tmp)
            seen = []
            real = sources.urllib.request.urlopen

            def fake(request, timeout=None):
                seen.append(request.full_url)
                return FakeResponse(json.dumps({"results": []}).encode())
            client.mailto = "me@lab.example"
            with mock.patch.object(sources.urllib.request, "urlopen", fake), \
                    mock.patch.object(sources.time, "sleep"):
                client.search_works("x")
            self.assertIn("mailto=me%40lab.example", seen[0])
            client2 = sources.OpenAlex(tmp)  # placeholder email, same query: served from the cache
            with mock.patch.object(sources.urllib.request, "urlopen", fake):
                client2.search_works("x")
            self.assertEqual(len(seen), 1)
            self.assertIsNotNone(real)

    def test_email_validation(self):
        self.assertTrue(sources.valid_email("me@lab.example"))
        for bad in ("", "no-at", "a b@c.d", "x@y", None):
            self.assertFalse(sources.valid_email(bad))


if __name__ == "__main__":
    unittest.main()
