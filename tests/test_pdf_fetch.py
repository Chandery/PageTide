from tests.pdf_fixture import minimal_pdf
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
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import migrations, pdf_fetch, sources
from app.db import Store
from app.service import App

PDF = minimal_pdf("x" * 200)
PDF_B = minimal_pdf("y" * 300)

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
        self.routes, self.robots, self.calls, self.gates = routes or {}, robots, [], []

    def __call__(self, request, timeout=None, gate=None):
        url = request.full_url
        self.calls.append(url)
        self.gates.append(gate)
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

        def robots_500(request, timeout=None, gate=None):
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
            conn.execute("DELETE FROM schema_version WHERE version=6")
            conn.commit()
            conn.close()
            store = Store(path)
            store.init()  # re-applies 005 on an already-migrated file without failing
            self.assertEqual(migrations.get_schema_version(store.conn), len(migrations.MIGRATIONS))
            self.assertGreaterEqual(len(migrations.MIGRATIONS), 7)
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


class MigrationNumberingTests(unittest.TestCase):
    """Two branches may both add migrations; a database must never skip one because of the other's number."""

    def make_db_at_foreign_version_5(self, tmp):
        path = Path(tmp) / "db.sqlite"
        store = Store(path)
        with mock.patch.object(migrations, 'MIGRATIONS', [m for m in migrations.MIGRATIONS if migrations._number(m) < 5]):
            store.init()
        conn = store.conn
        # what the real database looked like: the channels branch's migration 005 recorded, mine never run
        conn.execute("CREATE TABLE channel_status (channel TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO schema_version (version, applied_at) VALUES (5, '2026-10-02T00:56:04+00:00')")
        conn.execute("INSERT INTO projects(id,name,creation_mode,creation_timestamp,keywords) VALUES ('default_project','默认项目','manual','2026-01-01','[]')")   # an older database that already held data had its default project
        conn.execute("INSERT INTO papers (key, title, created_at, project_id) VALUES ('k','T','2026-01-01','default_project')")
        conn.execute("INSERT INTO pdfs VALUES ('k', '/x/a.pdf', 'u', '2026-01-01')")
        conn.commit()
        store.close()
        return path

    def test_a_database_already_at_a_foreign_version_5_still_gets_the_pdf_migrations(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_db_at_foreign_version_5(tmp)
            store = Store(path)
            store.init()  # used to crash: "no such column: sha256"
            applied = {r[0] for r in store.conn.execute("SELECT version FROM schema_version")}
            self.assertTrue({1, 2, 3, 4, 5, 6, 7, 8, 9} <= applied)
            self.assertTrue({"sha256", "bytes", "source_kind", "license"} <= {r[1] for r in store.conn.execute("PRAGMA table_info(pdfs)")})
            self.assertIn("oa_json", {r[1] for r in store.conn.execute("PRAGMA table_info(papers)")})
            self.assertEqual([h["path"] for h in store.pdf_history("k")], ["/x/a.pdf"])  # backfilled
            self.assertIsNotNone(store.conn.execute("SELECT 1 FROM channel_status LIMIT 1") is not None)  # the other branch's table is untouched
            store.close()

    def test_reserved_slot_is_never_recorded_and_never_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "db.sqlite")
            store.init()
            applied = {r[0] for r in store.conn.execute("SELECT version FROM schema_version")}
            self.assertEqual(applied, {1, 2, 3, 4, 6, 7, 8, 9})
            self.assertEqual(migrations.pending(store.conn), 0)
            store.close()

    def test_a_migration_that_fails_midway_leaves_nothing_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "db.sqlite")
            store.init()

            def migrate_099_broken(conn):
                conn.execute("CREATE TABLE half_done (x INTEGER)")
                raise sqlite3.OperationalError("simulated crash after a DDL statement")
            with mock.patch.object(migrations, "MIGRATIONS", migrations.MIGRATIONS + [migrate_099_broken]):
                with self.assertRaises(sqlite3.OperationalError):
                    migrations.apply_migrations(store.conn)
            self.assertIsNone(store.conn.execute("SELECT 1 FROM sqlite_master WHERE name='half_done'").fetchone())
            self.assertNotIn(99, {r[0] for r in store.conn.execute("SELECT version FROM schema_version")})
            store.close()


class AppCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = self.root = Path(tmp.name)
        (root / "harness").mkdir()
        (root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (root / "app").mkdir(exist_ok=True)
        (root / "app" / "budget.json").write_text((ROOT / "app" / "budget.json").read_text())
        self.app = App(root=str(root), data_dir=str(root / "data"))
        self.addCleanup(self.app.store.close)
        self.app.projects.create_project("Test project", "manual", [])   # a fresh app has no project
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


class DownloadPdfTests(AppCase):
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


class AttachAndLandingTests(AppCase):
    """Manual attach for papers with no downloadable source, and the landing page shown instead."""

    DREAMER_OA = {"is_oa": True, "oa_status": "hybrid", "pdf_urls": [],
                  "landing_page": "https://doi.org/10.1038/s41586-025-08744-2", "license": "cc-by",
                  "version": "publishedVersion"}

    def upload(self, data=PDF, name="paper.pdf"):
        from app import creation
        return creation.import_pdf(self.app.data, data, name)["pdf_id"]

    def test_open_access_paper_without_pdf_link_reports_landing_page(self):
        self.add(oa=self.DREAMER_OA)
        result = self.download(Net({}))
        self.assertEqual((result["ok"], result["reason"]), (False, "landing_page_only"))
        self.assertEqual(result["landing_page"], self.DREAMER_OA["landing_page"])

    def test_a_page_the_reader_can_open_is_landing_page_only_even_when_not_open_access(self):
        # Changed 2026-10-23 (ADR 0039): any page where a person can get the file makes the reason landing_page_only.
        self.add(oa=dict(self.DREAMER_OA, is_oa=False, license=None))
        self.assertEqual(self.download(Net({}))["reason"], "landing_page_only")

    def test_not_open_access_without_any_page_is_still_no_oa_source(self):
        self.add(oa=dict(self.DREAMER_OA, is_oa=False, license=None, landing_page=None))
        self.assertEqual(self.download(Net({}))["reason"], "no_oa_source")

    def test_failed_download_still_offers_the_landing_page(self):
        self.add(oa=dict(sources.slim(WORK)["oa"], landing_page="https://repo.example.org/p"))
        url = "https://repo.example.org/p.pdf"
        result = self.download(Net({url: http_error(url, 403),
                                    "https://other.example.org/q.pdf": http_error("https://other.example.org/q.pdf", 403)}))
        self.assertEqual(result["reason"], "paywalled_or_blocked")
        self.assertEqual(result["landing_page"], "https://repo.example.org/p")

    def test_attach_records_user_import_and_makes_later_downloads_cached(self):
        key = self.add()
        result = self.app.attach_pdf(key, self.upload())
        self.assertTrue(result["ok"])
        row = dict(self.app.store.conn.execute("SELECT * FROM pdfs WHERE paper_key=?", (key,)).fetchone())
        self.assertEqual((row["source_kind"], row["sha256"], row["bytes"]),
                         ("user_import", hashlib.sha256(PDF).hexdigest(), len(PDF)))
        self.assertEqual(Path(row["path"]).read_bytes(), PDF)
        net = Net({})
        self.assertTrue(self.download(net)["cached"])
        self.assertEqual(net.calls, [])

    def test_attach_keeps_a_previously_downloaded_original(self):
        key = self.add(arxiv_id="2603.19312")
        first = self.download(Net({"https://arxiv.org/pdf/2603.19312": PDF}))
        self.app.attach_pdf(key, self.upload(PDF_B))
        self.assertTrue(Path(first["path"]).exists())
        self.assertNotEqual(self.app.pdf_path(key), Path(first["path"]))

    def test_attach_refuses_unknown_paper_and_keeps_the_upload(self):
        pdf_id = self.upload()
        with self.assertRaises(ValueError):
            self.app.attach_pdf("nope", pdf_id)
        self.assertTrue((self.app.data / "imports" / f"{pdf_id}.pdf").exists())

    def test_attach_refuses_unknown_or_malformed_upload_id(self):
        key = self.add()
        for bad in ("0" * 64, "../etc/passwd", "", None):
            with self.assertRaises(ValueError):
                self.app.attach_pdf(key, bad)
        self.assertIsNone(self.app.pdf_path(key))

    def test_upload_that_is_not_a_pdf_is_rejected_before_attaching(self):
        from app import creation
        with self.assertRaises(ValueError):
            creation.import_pdf(self.app.data, b"<html>not a pdf</html>", "x.pdf")


class AttachRouteTests(unittest.TestCase):
    def setUp(self):
        import threading
        from app import server
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "harness").mkdir()
        (self.root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (self.root / "app").mkdir(exist_ok=True)
        (self.root / "app" / "budget.json").write_text((ROOT / "app" / "budget.json").read_text())
        httpd = server.build_server(port=0, root=str(self.root))
        self.port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        self.app = server.make_app(str(self.root))
        self.app.store.upsert_papers([{"key": "k", "title": "T"}])

    def call(self, path, body=None, raw=None, origin=None):
        import urllib.request
        data = raw if raw is not None else json.dumps(body).encode()
        headers = {"Content-Type": "application/octet-stream" if raw is not None else "application/json"}
        if origin:
            headers["Origin"] = origin
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_upload_then_attach_then_reader_can_view_it(self):
        import urllib.request
        status, uploaded = self.call("/api/seeds/pdf", raw=PDF)
        self.assertEqual(status, 200)
        status, attached = self.call("/api/pdf/attach", {"key": "k", "pdf_id": uploaded["pdf_id"]})
        self.assertEqual((status, attached["ok"]), (200, True))
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/pdf/view?key=k", timeout=5) as response:
            self.assertEqual(response.read(), PDF)

    def test_every_write_route_refuses_a_foreign_origin(self):
        for path, body in (("/api/pdf/attach", {"key": "k", "pdf_id": "0" * 64}), ("/api/pdf/prepare", {"key": "k"}),
                           ("/api/pdf", {"key": "k"}), ("/api/user_settings", {"settings": {"theme": "dark"}}),
                           ("/api/settings", {"openalex_key": "dummy-openalex-key-0000"})):
            status, payload = self.call(path, body, origin="http://evil.example")
            self.assertEqual((status, payload.get("error")), (403, "cross-origin request denied"), path)
        status, _ = self.call("/api/seeds/pdf", raw=PDF, origin="http://evil.example")
        self.assertEqual(status, 403)
        self.assertEqual(self.app.pdf_path("k"), None)

    def test_same_origin_requests_still_work(self):
        status, payload = self.call("/api/pdf/attach", {"key": "k", "pdf_id": "0" * 64}, origin=f"http://127.0.0.1:{self.port}")
        self.assertEqual(status, 400)  # reached the handler (the upload id is unknown), not the origin check

    def test_attach_errors_are_400_with_a_message(self):
        status, body = self.call("/api/pdf/attach", {"key": "k", "pdf_id": "0" * 64})
        self.assertEqual(status, 400)
        self.assertIn("error", body)
        status, _ = self.call("/api/pdf/attach", {"key": "missing", "pdf_id": "0" * 64})
        self.assertEqual(status, 400)


class ReviewFixTests(AppCase):
    """Findings of the independent review (2026-10-04)."""

    def fake_clock(self):
        clock = [100.0]
        sleep = mock.patch.object(pdf_fetch.time, "sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)).start()
        mock.patch.object(pdf_fetch.time, "monotonic", lambda: clock[0]).start()
        return sleep

    def test_every_request_gets_the_same_fetcher_so_pacing_persists(self):
        # The HTTP server builds a new App per request; a per-App fetcher would forget everything.
        other = App(root=str(self.root), data_dir=str(self.app.data))
        self.addCleanup(other.store.close)
        self.assertIs(other.pdf_fetcher, self.app.pdf_fetcher)
        sleep = self.fake_clock()
        self.add(key="a", arxiv_id="2603.00001")
        self.add(key="b", arxiv_id="2603.00002")
        net = Net({"https://arxiv.org/pdf/2603.00001": PDF, "https://arxiv.org/pdf/2603.00002": PDF_B})
        with mock.patch.object(pdf_fetch, "_open", net):
            self.assertTrue(self.app.download_pdf("a")["ok"])
            self.assertTrue(other.download_pdf("b")["ok"])
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [3.0])  # spaced across two App objects
        # The reader's downloads are the person's own (owner, 2026-10-26): robots.txt is not read for them at all.
        self.assertEqual(sum(u.endswith("/robots.txt") for u in net.calls), 0)

    def test_parallel_downloads_from_one_host_are_spaced(self):
        import threading
        mock.patch.stopall()  # this test needs the real clock and the real sleep
        starts = []
        real_monotonic = time.monotonic

        def net(request, timeout=None, gate=None):
            if request.full_url.endswith("/robots.txt"):
                raise http_error(request.full_url, 404)
            starts.append(real_monotonic())
            return FakeResponse(PDF, url=request.full_url)
        fetcher = pdf_fetch.Fetcher(self.root / "pp")
        real_monotonic, real_sleep = time.monotonic, time.sleep

        def slow_monotonic():  # widens the window between "read the last request time" and "record this one"
            real_sleep(0.05)
            return real_monotonic()
        with mock.patch.object(pdf_fetch, "DEFAULT_GAP_SECONDS", 0.3), mock.patch.object(pdf_fetch, "_open", net), \
                mock.patch.object(pdf_fetch.time, "monotonic", slow_monotonic):
            threads = [threading.Thread(target=fetcher.fetch, args=(f"https://pub.example.org/{n}.pdf", n)) for n in "ab"]
            for t in threads:
                t.start()
            for t in threads:
                t.join(10)
        self.assertEqual(len(starts), 2)
        self.assertGreaterEqual(abs(starts[1] - starts[0]), 0.27)

    def test_malformed_and_odd_failures_are_reported_not_raised(self):
        import http.client
        cases = [(http.client.InvalidURL("bad"), "invalid_url"), (UnicodeEncodeError("ascii", "é", 0, 1, "x"), "invalid_url"),
                 (http.client.IncompleteRead(b"ab"), "network_error"), (http.client.BadStatusLine("x"), "network_error")]
        for error, kind in cases:
            fetcher = pdf_fetch.Fetcher(self.root / "x")
            url = "https://pub.example.org/a.pdf"
            with mock.patch.object(pdf_fetch, "_open", Net({url: error})):
                with self.assertRaises(pdf_fetch.PdfFetchError) as caught:
                    fetcher.fetch(url, "a")
            self.assertEqual(caught.exception.kind, kind, repr(error))

    def test_a_malformed_first_candidate_does_not_stop_the_next_one(self):
        import http.client
        self.add(oa={"is_oa": True, "pdf_urls": ["https://bad.example.org/a b.pdf", "https://good.example.org/p.pdf"]})
        net = Net({"https://bad.example.org/a b.pdf": http.client.InvalidURL("space"), "https://good.example.org/p.pdf": PDF})
        result = self.download(net)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source_kind"], "openalex_oa")

    def test_private_and_local_hosts_are_refused_before_any_request(self):
        for url in ("https://127.0.0.1/p.pdf", "https://192.168.1.5/p.pdf", "https://10.0.0.2/p.pdf",
                    "https://[::1]/p.pdf", "https://localhost/p.pdf", "https://printer.local/p.pdf"):
            net = Net({})
            with mock.patch.object(pdf_fetch, "_open", net):
                with self.assertRaises(pdf_fetch.PdfFetchError) as caught:
                    pdf_fetch.Fetcher(self.root / "x").fetch(url, "a")
            self.assertEqual((caught.exception.kind, net.calls), ("invalid_url", []), url)

    def test_userinfo_and_default_port_do_not_create_a_second_host_identity(self):
        net = Net({"https://user@arxiv.org:443/pdf/x": PDF})
        with mock.patch.object(pdf_fetch, "_open", net):
            pdf_fetch.Fetcher(self.root / "x").fetch("https://user@arxiv.org:443/pdf/x", "x")
        self.assertIn("https://arxiv.org/robots.txt", net.calls)

    def test_redirect_hops_must_be_https_and_public_and_pass_the_gate(self):
        seen = []
        handler = pdf_fetch._Redirects(gate=seen.append)
        request = urllib.request.Request("https://pub.example.org/a.pdf")
        for bad in ("http://cdn.example.org/p.pdf", "https://127.0.0.1/secret", "https://localhost/x", "https://10.1.1.1/x"):
            with self.assertRaises(pdf_fetch.PdfFetchError, msg=bad):
                handler.redirect_request(request, None, 302, "Found", {}, bad)
        self.assertEqual(seen, [])
        redirected = handler.redirect_request(request, None, 302, "Found", {}, "https://cdn.example.org/p.pdf")
        self.assertEqual(redirected.full_url, "https://cdn.example.org/p.pdf")
        self.assertEqual(seen, ["https://cdn.example.org/p.pdf"])

    def test_redirect_target_host_gets_robots_and_pacing(self):
        sleep = self.fake_clock()
        fetcher = pdf_fetch.Fetcher(self.root / "x")
        with mock.patch.object(pdf_fetch, "_open", Net({}, robots="User-agent: *\nDisallow: /private/\n")):
            fetcher._redirect_gate("https://cdn.example.org/public/p.pdf")
            fetcher._redirect_gate("https://cdn.example.org/public/q.pdf")
            self.assertEqual([c.args[0] for c in sleep.call_args_list], [1.0])  # second hop to the same host is paced
            with self.assertRaises(pdf_fetch.PdfFetchError) as caught:
                fetcher._redirect_gate("https://cdn.example.org/private/p.pdf")
        self.assertEqual(caught.exception.kind, "robots_disallowed")

    def test_robots_429_is_unavailable_not_permission(self):
        url = "https://pub.example.org/a.pdf"

        def too_many(request, timeout=None, gate=None):
            if request.full_url.endswith("/robots.txt"):
                raise http_error(request.full_url, 429)
            raise AssertionError("the PDF must not be requested")
        with mock.patch.object(pdf_fetch, "_open", too_many):
            with self.assertRaises(pdf_fetch.PdfFetchError) as caught:
                pdf_fetch.Fetcher(self.root / "x").fetch(url, "a")
        self.assertEqual(caught.exception.kind, "network_error")


    def test_fetch_hands_the_redirect_gate_to_the_opener(self):
        net = Net({"https://arxiv.org/pdf/x": PDF})
        with mock.patch.object(pdf_fetch, "_open", net):
            pdf_fetch.Fetcher(self.root / 'f').fetch("https://arxiv.org/pdf/x", "x")
        self.assertEqual(net.gates[-1].__func__, pdf_fetch.Fetcher._redirect_gate)  # the PDF request, not robots.txt

    def test_alternate_ip_spellings_trailing_dots_and_single_label_hosts_are_refused(self):
        for url in ("https://2130706433/p.pdf", "https://0x7f.1/p.pdf", "https://127.1/p.pdf", "https://017700000001/p.pdf",
                    "https://0/p.pdf", "https://localhost./p.pdf", "https://foo.local./p.pdf", "https://a.localhost./p.pdf",
                    "https://nas/p.pdf", "https://[::ffff:127.0.0.1]/p.pdf", "https://169.254.169.254/p.pdf",
                    "https://100.64.0.1/p.pdf", "https://example.123/p.pdf"):
            net = Net({})
            with mock.patch.object(pdf_fetch, "_open", net):
                with self.assertRaises(pdf_fetch.PdfFetchError, msg=url) as caught:
                    pdf_fetch.Fetcher(self.root / "x").fetch(url, "a")
            self.assertEqual((caught.exception.kind, net.calls), ("invalid_url", []), url)

    def test_trailing_dot_host_shares_identity_with_the_plain_name(self):
        net = Net({"https://arxiv.org./pdf/x": PDF})
        with mock.patch.object(pdf_fetch, "_open", net):
            pdf_fetch.Fetcher(self.root / "x").fetch("https://arxiv.org./pdf/x", "x")
        self.assertIn("https://arxiv.org/robots.txt", net.calls)

    def test_public_ipv6_literal_is_bracketed_in_the_robots_url(self):
        net = Net({"https://[2606:4700::1]/p.pdf": PDF})
        with mock.patch.object(pdf_fetch, "_open", net):
            pdf_fetch.Fetcher(self.root / "x").fetch("https://[2606:4700::1]/p.pdf", "x")
        self.assertIn("https://[2606:4700::1]/robots.txt", net.calls)

    def test_robots_answers_expire_and_are_refetched(self):
        clock = [100.0]
        mock.patch.object(pdf_fetch.time, "monotonic", lambda: clock[0]).start()
        net = Net({"https://arxiv.org/pdf/a": PDF, "https://arxiv.org/pdf/b": PDF_B})
        with mock.patch.object(pdf_fetch, "_open", net):
            pdf_fetch.Fetcher(self.root / 'f').fetch("https://arxiv.org/pdf/a", "a")
            clock[0] += pdf_fetch.ROBOTS_TTL_SECONDS + 1
            pdf_fetch.Fetcher(self.root / 'f').fetch("https://arxiv.org/pdf/b", "b")
        self.assertEqual(sum(u.endswith("/robots.txt") for u in net.calls), 2)

    def test_robots_redirect_loop_is_unavailable_not_permission(self):
        url = "https://pub.example.org/a.pdf"

        def redirecting(request, timeout=None, gate=None):
            if request.full_url.endswith("/robots.txt"):
                raise http_error(request.full_url, 302)
            raise AssertionError("the PDF must not be requested")
        with mock.patch.object(pdf_fetch, "_open", redirecting):
            with self.assertRaises(pdf_fetch.PdfFetchError) as caught:
                pdf_fetch.Fetcher(self.root / "x").fetch(url, "a")
        self.assertEqual(caught.exception.kind, "network_error")

    def test_replacing_a_pdf_keeps_where_the_old_one_came_from(self):
        key = self.add(arxiv_id="2603.19312")
        first = self.download(Net({"https://arxiv.org/pdf/2603.19312": PDF}))
        self.app.attach_pdf(key, creation_upload(self.app, PDF_B))
        history = self.app.store.pdf_history(key)
        self.assertEqual([h["source_kind"] for h in history], ["arxiv", "user_import"])
        self.assertEqual(history[0]["sha256"], hashlib.sha256(PDF).hexdigest())
        self.assertEqual(history[0]["source_url"], "https://arxiv.org/pdf/2603.19312")
        self.assertEqual(history[0]["path"], first["path"])

    def test_recording_the_same_file_twice_adds_one_history_row(self):
        self.add()
        for _ in range(2):
            self.app.store.record_pdf("k", "/x/a.pdf", "u", sha256="ab", size=1, source_kind="arxiv")
        self.assertEqual(len(self.app.store.pdf_history("k")), 1)

    def test_a_copy_that_comes_back_after_another_is_a_new_last_entry(self):
        self.add()
        for path in ("/x/a.pdf", "/x/b.pdf", "/x/a.pdf"):
            self.app.store.record_pdf("k", path, "u", sha256=path, size=1, source_kind="arxiv")
        self.assertEqual([h["path"] for h in self.app.store.pdf_history("k")], ["/x/a.pdf", "/x/b.pdf", "/x/a.pdf"])

    def test_migration_006_backfills_history_from_existing_rows(self):
        self.add()
        self.app.store.record_pdf("k", "/x/a.pdf", "u", sha256="ab", size=1, source_kind="arxiv")
        conn = self.app.store.conn
        conn.execute("DROP TABLE pdf_versions")
        conn.execute("DELETE FROM schema_version WHERE version=7")
        conn.commit()
        migrations.apply_migrations(conn)
        self.assertEqual([h["sha256"] for h in self.app.store.pdf_history("k")], ["ab"])

    def test_migration_does_not_swallow_a_locked_database(self):
        class Locked:
            def __init__(self):
                self.versions = []

            def execute(self, sql, *args):
                if sql.startswith("ALTER TABLE"):
                    raise sqlite3.OperationalError("database is locked")

        with self.assertRaises(sqlite3.OperationalError):
            migrations.migrate_006_pdf_acquisition(Locked())


def creation_upload(app, data):
    from app import creation
    return creation.import_pdf(app.data, data, "p.pdf")["pdf_id"]


if __name__ == "__main__":
    unittest.main()
