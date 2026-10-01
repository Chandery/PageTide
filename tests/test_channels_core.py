"""CHAN-02: channel framework, shared HTTP client, dedup, migration 005 and refresh fan-out.

No test performs a network request: urlopen is replaced and fixtures are hand-written from
the documented response formats (they are not recordings of live responses).
"""
import io
import json
import os
import sqlite3
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from app.channels import arxiv, base, crossref, dedup, openalex, presets, query, registry, usage
from app.channels import http as chttp
from app.channels.http import Client, SourceError
from app.db import Store
from app.migrations import MIGRATIONS
from app.service import App

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "channels"


def fixture(channel, name):
    return (FIX / channel / name).read_text(encoding="utf-8")


class Body(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, headers=None):
    return urllib.error.HTTPError("https://example.org/x?api_key=SECRET", code, "err", headers or {}, io.BytesIO(b""))


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = Client(self.tmp.name, label="Test", gap=0.0)
        patcher = mock.patch("app.channels.http.time.sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def get(self, url="https://example.org/api?q=a&api_key=SECRET&mailto=me@x.org", **kw):
        return self.client.get(url, **kw)

    def test_errors_map_to_kinds_and_never_carry_credentials(self):
        cases = {401: "auth_required", 403: "auth_required", 404: "not_found", 400: "invalid_input",
                 429: "unavailable", 503: "unavailable", 500: "network_error"}
        for code, kind in cases.items():
            with self.subTest(code), mock.patch("urllib.request.urlopen", side_effect=http_error(code)):
                with self.assertRaises(SourceError) as caught:
                    self.get()
                self.assertEqual(caught.exception.kind, kind)
                self.assertNotIn("SECRET", str(caught.exception))
                self.assertNotIn("me@x.org", str(caught.exception))

    def test_network_failure_is_bounded_and_redacted(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down SECRET")) as urlopen:
            with self.assertRaises(SourceError) as caught:
                self.get()
        self.assertEqual(caught.exception.kind, "network_error")
        self.assertEqual(urlopen.call_count, 2)
        self.assertNotIn("SECRET", str(caught.exception))

    def test_auth_and_not_found_are_not_retried(self):
        for code in (401, 404):
            with mock.patch("urllib.request.urlopen", side_effect=http_error(code)) as urlopen:
                with self.assertRaises(SourceError):
                    self.get()
            self.assertEqual(urlopen.call_count, 1)

    def test_retry_after_wait_is_bounded(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(429, {"Retry-After": "9999"})):
            with self.assertRaises(SourceError):
                self.get()
        self.assertLessEqual(max(call.args[0] for call in self.sleep.call_args_list), chttp.MAX_RETRY_WAIT)

    def test_cache_key_ignores_credentials_and_files_hold_no_secret(self):
        body = Body(b'{"ok": 1}')
        with mock.patch("urllib.request.urlopen", return_value=body) as urlopen:
            self.assertEqual(self.get(), {"ok": 1})
            self.assertEqual(self.get("https://example.org/api?q=a&api_key=OTHER&mailto=you@x.org"), {"ok": 1})
        self.assertEqual(urlopen.call_count, 1)
        files = list(Path(self.tmp.name).glob("*.json"))
        self.assertEqual(len(files), 1)
        self.assertNotIn("SECRET", files[0].name)

    def test_cache_expires_after_ttl_and_corrupt_entry_is_refetched(self):
        with mock.patch("urllib.request.urlopen", side_effect=lambda *a, **k: Body(b'{"n": 1}')) as urlopen:
            self.get(ttl=60)
            path = next(Path(self.tmp.name).glob("*.json"))
            os.utime(path, (time.time() - 120, time.time() - 120))
            self.get(ttl=60)
            self.assertEqual(urlopen.call_count, 2)
            path.write_text("{broken")
            self.assertEqual(self.get(ttl=60), {"n": 1})
            self.assertEqual(urlopen.call_count, 3)

    def test_bad_body_is_not_cached_and_text_mode_returns_text(self):
        with mock.patch("urllib.request.urlopen", return_value=Body(b"<html>busy</html>")):
            with self.assertRaises(SourceError) as caught:
                self.get()
        self.assertEqual(caught.exception.kind, "bad_response")
        self.assertEqual(list(Path(self.tmp.name).glob("*.json")), [])
        with mock.patch("urllib.request.urlopen", return_value=Body(b"<feed/>")):
            self.assertEqual(self.get("https://example.org/feed", parse="text"), "<feed/>")

    def test_oversized_body_is_refused(self):
        with mock.patch.object(chttp, "MAX_BODY", 10), \
                mock.patch("urllib.request.urlopen", return_value=Body(b"x" * 50)):
            with self.assertRaises(SourceError) as caught:
                self.get()
        self.assertEqual(caught.exception.kind, "bad_response")

    def test_redact_hides_credentials_and_contact(self):
        shown = chttp.redact("https://h.org/a?q=world&api_key=SECRET&mailto=me@x.org&token=T")
        self.assertIn("q=world", shown)
        for secret in ("SECRET", "me@x.org", "=T"):
            self.assertNotIn(secret, shown)

    def test_requests_to_one_host_are_spaced(self):
        client = Client(self.tmp.name, gap=5.0)
        clock = iter([100.0, 101.0, 101.0])
        chttp._host_last.clear()
        with mock.patch("app.channels.http.time.monotonic", side_effect=lambda: next(clock)):
            chttp.wait_for_host("h.example", 5.0)
            chttp.wait_for_host("h.example", 5.0)
        self.assertEqual(self.sleep.call_count, 1)  # the first call needs no wait
        self.assertAlmostEqual(self.sleep.call_args.args[0], 4.0)
        del client


class ParserTests(unittest.TestCase):
    def test_arxiv_feed(self):
        papers = arxiv.parse_feed(fixture("arxiv", "ok.xml"))
        self.assertEqual(len(papers), 2)
        first = papers[0]
        self.assertEqual(first["title"], "A Latent World Model for Manipulation")
        self.assertEqual(first["abstract"], "We learn a latent world model. It predicts futures.")
        self.assertEqual(first["arxiv_id"], "2601.01234")
        self.assertEqual(first["key"], "https://doi.org/10.48550/arxiv.2601.01234")
        self.assertEqual(first["pdf_url"], "https://arxiv.org/pdf/2601.01234v2")
        self.assertEqual(first["authors"], ["Ada Lovelace", "Alan Turing"])
        self.assertEqual((first["published"], first["topic"], first["channel"]), ("2026-01-03", "cs.RO", "arxiv"))
        self.assertEqual(papers[1]["arxiv_id"], "cs/0501001")
        self.assertEqual(papers[1]["doi"], "https://doi.org/10.1000/old.paper.1")

    def test_arxiv_empty_error_entry_and_malformed(self):
        self.assertEqual(arxiv.parse_feed(fixture("arxiv", "empty.xml")), [])
        self.assertEqual(arxiv.parse_feed(fixture("arxiv", "error.xml")), [])
        for body in ("<html></html>", "not xml"):
            with self.assertRaises(SourceError) as caught:
                arxiv.parse_feed(body)
            self.assertEqual(caught.exception.kind, "bad_response")

    def test_arxiv_refuses_entity_declarations(self):
        with self.assertRaises(SourceError) as caught:
            arxiv.parse_feed(fixture("arxiv", "entity.xml"))
        self.assertEqual(caught.exception.kind, "bad_response")

    def test_openalex_works(self):
        papers = openalex.parse_works(json.loads(fixture("openalex", "ok.json")))
        self.assertEqual(len(papers), 2)  # the record without a title is dropped
        english, chinese = papers
        self.assertEqual(english["key"], "https://doi.org/10.48550/arxiv.2601.01234")
        self.assertEqual(english["abstract"], "We learn a world model.")
        self.assertEqual(english["arxiv_id"], "2601.01234")
        self.assertEqual(english["pdf_url"], "https://arxiv.org/pdf/2601.01234")
        self.assertEqual(english["authors"], ["Ada Lovelace", "Alan Turing"])
        self.assertEqual(chinese["key"], "https://openalex.org/W4300000002")
        self.assertEqual(chinese["language"], "zh")
        self.assertIsNone(chinese["doi"])
        self.assertEqual(openalex.parse_works(json.loads(fixture("openalex", "empty.json"))), [])
        with self.assertRaises(SourceError):
            openalex.parse_works(json.loads(fixture("openalex", "malformed.json")))

    def test_crossref_works(self):
        papers = crossref.parse_works(json.loads(fixture("crossref", "ok.json")))
        self.assertEqual([p["key"] for p in papers], ["https://doi.org/10.1000/xyz.123", "https://doi.org/10.1000/abc"])
        first = papers[0]
        self.assertEqual(first["title"], "Digital Humanities and the Edition of Old Books")
        self.assertEqual(first["abstract"], "An edition of old books.")
        self.assertEqual(first["published"], "2025-03-01")
        self.assertEqual(first["authors"], ["Ada Lovelace", "Consortium X"])
        self.assertEqual(first["pdf_url"], "https://example.org/xyz.pdf")
        self.assertEqual(papers[1]["published"], "2024-01-01")
        self.assertEqual(crossref.parse_works(json.loads(fixture("crossref", "empty.json"))), [])
        with self.assertRaises(SourceError):
            crossref.parse_works(json.loads(fixture("crossref", "malformed.json")))


class ChannelSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ctx = base.Context(cache_dir=Path(self.tmp.name), credentials=lambda ch, f: "KEY" if f == "api_key" else None,
                                contact="me@x.org")
        for target in ("app.channels.http.time.sleep",):
            patcher = mock.patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def requested(self, channel, body, **kw):
        with mock.patch("urllib.request.urlopen", return_value=Body(body.encode())) as urlopen:
            papers = channel.search(self.ctx, "world model", "2024-01-01", 10, **kw)
        return papers, urlopen.call_args.args[0].full_url

    def test_arxiv_request_shape_and_date_floor(self):
        papers, url = self.requested(arxiv.ArXiv(), fixture("arxiv", "ok.xml"))
        self.assertIn("export.arxiv.org/api/query", url)
        self.assertIn("search_query=all%3A%22world+model%22", url)
        self.assertEqual([p["arxiv_id"] for p in papers], ["2601.01234"])  # the 2005 entry is below the 2024 floor
        with mock.patch("urllib.request.urlopen", return_value=Body(fixture("arxiv", "ok.xml").encode())):
            everything = arxiv.ArXiv().search(self.ctx, "other term", "", 10)
        self.assertEqual(len(everything), 2)

    def test_openalex_request_carries_the_key_but_cache_and_errors_do_not(self):
        papers, url = self.requested(openalex.OpenAlexChannel(), fixture("openalex", "ok.json"))
        self.assertIn("title_and_abstract.search%3Aworld+model", url)
        self.assertIn("api_key=KEY", url)
        self.assertIn("mailto=me%40x.org", url)
        self.assertEqual(len(papers), 2)
        for path in Path(self.tmp.name).rglob("*"):
            self.assertNotIn("KEY", path.name)
            if path.is_file():
                self.assertNotIn("api_key", path.read_text())  # the cache holds the body only
        with mock.patch("urllib.request.urlopen", side_effect=http_error(403)):
            with self.assertRaises(SourceError) as caught:
                openalex.OpenAlexChannel().search(self.ctx, "other term", "2024-01-01", 10)
        self.assertEqual(caught.exception.kind, "auth_required")
        self.assertNotIn("KEY", str(caught.exception))

    def test_crossref_request_shape(self):
        papers, url = self.requested(crossref.Crossref(), fixture("crossref", "ok.json"))
        self.assertIn("api.crossref.org/works", url)
        self.assertIn("query.bibliographic=world+model", url)
        self.assertIn("from-pub-date%3A2024-01-01", url)
        self.assertEqual(len(papers), 2)


class QueryRoutingTests(unittest.TestCase):
    def test_script_routing(self):
        terms = ["world model", "数字人文", "robot", "数字人文", "  "]
        self.assertEqual(query.terms_for(registry.get("arxiv"), terms), ["world model", "robot"])
        self.assertEqual(query.terms_for(registry.get("openalex"), terms), ["world model", "数字人文", "robot"])
        self.assertEqual(query.terms_for(registry.get("openalex"), terms, limit=2), ["world model", "数字人文"])

    def test_filter_syntax_characters_are_removed(self):
        self.assertEqual(query.clean("a,b:c|d  e"), "a b c d e")


class PresetTests(unittest.TestCase):
    def test_every_preset_lists_known_shape(self):
        for name, spec in presets.PRESETS.items():
            self.assertTrue(spec["label"], name)
            self.assertEqual(len(spec["channels"]), len(set(spec["channels"])), name)
        self.assertEqual(presets.channels_for("unknown"), presets.channels_for(presets.DEFAULT))
        self.assertFalse(presets.valid("nope"))

    def test_implemented_channels_are_registered_once(self):
        self.assertEqual(sorted(registry.ids()), ["arxiv", "crossref", "openalex"])
        self.assertEqual(len(registry.ids()), len(set(registry.ids())))
        for channel in registry.all_channels():
            self.assertTrue(channel.name and channel.terms_url.startswith("https://"), channel.id)


class DedupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "t.sqlite")
        self.store.init()
        self.addCleanup(self.store.close)

    def paper(self, key, title, **kw):
        return {"key": key, "title": title, "published": "2025-05-01", "abstract": "", **kw}

    def test_doi_spellings_and_arxiv_ids_agree(self):
        self.assertEqual(base.canonical_doi("DOI:10.1000/ABC.1)"), "https://doi.org/10.1000/abc.1")
        self.assertEqual(base.canonical_doi("https://dx.doi.org/10.1000/abc"), "https://doi.org/10.1000/abc")
        self.assertEqual(base.canonical_doi("none"), "")
        for spelling in ("2601.01234", "2601.01234v3", "https://arxiv.org/abs/2601.01234v2", "arXiv:2601.01234"):
            self.assertEqual(dedup.arxiv_id(spelling), "2601.01234", spelling)
        self.assertEqual(dedup.arxiv_id("https://arxiv.org/abs/cs/0501001v1"), "cs/0501001")

    def test_same_paper_from_two_channels_is_one_row_that_fills_gaps(self):
        a = self.paper("https://openalex.org/W1", "Latent world model for manipulation",
                       openalex_id="https://openalex.org/W1", doi="https://doi.org/10.48550/arxiv.2601.01234",
                       channel="openalex")
        b = self.paper("https://doi.org/10.48550/arxiv.2601.01234", "Latent World Model for Manipulation!",
                       doi="https://doi.org/10.48550/arxiv.2601.01234", arxiv_id="2601.01234", abstract="Has abstract.",
                       pdf_url="https://arxiv.org/pdf/2601.01234", channel="arxiv", query="world model")
        self.assertEqual(self.store.upsert_papers([a], project_id=None), 1)
        self.assertEqual(self.store.upsert_papers([b]), 0)
        rows = self.store.papers()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["key"], "https://openalex.org/W1")
        self.assertEqual((rows[0]["abstract"], rows[0]["pdf_url"], rows[0]["arxiv_id"]),
                         ("Has abstract.", "https://arxiv.org/pdf/2601.01234", "2601.01234"))
        self.assertEqual(b["key"], "https://openalex.org/W1")  # callers continue with the canonical key
        sources = {r["channel"] for r in self.store.conn.execute("SELECT channel FROM paper_sources")}
        self.assertEqual(sources, {"openalex", "arxiv"})

    def test_a_stored_value_is_never_overwritten(self):
        self.store.upsert_papers([self.paper("k1", "Some specific long title here", abstract="Original.",
                                             doi="https://doi.org/10.1000/x")])
        self.store.upsert_papers([self.paper("k2", "Other", abstract="Replacement.", doi="10.1000/X")])
        self.assertEqual(self.store.paper("k1")["abstract"], "Original.")

    def test_title_and_year_merge_only_when_specific(self):
        long_title = "A sufficiently specific title about planning"
        self.store.upsert_papers([self.paper("a", long_title)])
        self.assertEqual(self.store.upsert_papers([self.paper("b", long_title.upper())]), 0)
        self.assertEqual(self.store.upsert_papers([self.paper("c", long_title, published="2024-05-01")]), 1)
        self.assertEqual(self.store.upsert_papers([self.paper("d", long_title, published=None)]), 1)
        self.store.upsert_papers([self.paper("e", "Survey")])
        self.assertEqual(self.store.upsert_papers([self.paper("f", "Survey")]), 1)  # generic title never merges

    def test_chinese_titles_without_ids_stay_distinct_and_merge_when_equal(self):
        self.store.upsert_papers([self.paper("c1", "数字人文视野下的古籍整理研究")])
        self.assertEqual(self.store.upsert_papers([self.paper("c2", "地方志的数字化与利用")]), 1)
        self.assertEqual(self.store.upsert_papers([self.paper("c3", "数字人文视野下的 古籍整理研究")]), 0)

    def test_project_link_goes_to_the_existing_paper(self):
        one = self.store.conn.execute("SELECT id FROM projects").fetchone()["id"]
        from app.project import ProjectManager
        other = ProjectManager(self.store).create_project("B")
        self.store.upsert_papers([self.paper("a", "A sufficiently specific title about planning", doi="10.1000/a",
                                             project_id=one)])
        self.store.upsert_papers([self.paper("b", "Completely different wording of it", doi="https://doi.org/10.1000/A",
                                             project_id=other)])
        self.assertEqual(len(self.store.papers()), 1)
        self.assertEqual({r["project_id"] for r in self.store.conn.execute("SELECT project_id FROM project_papers")},
                         {one, other})


class MigrationTests(unittest.TestCase):
    def legacy_db(self, path):
        """A database as migration 004 left it, holding one OpenAlex paper."""
        store = Store(path)
        store.conn.executescript(__import__("app.db", fromlist=["SCHEMA"]).SCHEMA)
        store._migrate()
        from app.migrations import apply_migrations
        # Run migrations 1-4 only by stopping the list short.
        with mock.patch("app.migrations.MIGRATIONS", MIGRATIONS[:4]):
            apply_migrations(store.conn)
        store.conn.execute(
            "INSERT INTO papers(key, openalex_id, doi, arxiv_id, title, published, created_at, project_id) "
            "VALUES ('https://doi.org/10.48550/arxiv.2601.01234','https://openalex.org/W9',"
            "'https://doi.org/10.48550/arxiv.2601.01234','https://arxiv.org/abs/2601.01234',"
            "'Legacy Paper About Latent Models','2026-01-03','2026-01-04','default_project')")
        store.conn.commit()
        return store

    def test_backfill_is_complete_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.sqlite"
            self.legacy_db(path).close()
            store = Store(path)
            store.init()
            self.assertEqual(sorted(p.name for p in Path(tmp).glob("*.bak")), ["p.sqlite.pre-v4.bak"])
            row = store.paper("https://doi.org/10.48550/arxiv.2601.01234")
            self.assertEqual((row["year"], row["channel"], row["title_norm"]),
                             (2026, "openalex", "legacy paper about latent models"))
            ids = {(r["scheme"], r["value"]) for r in store.conn.execute("SELECT * FROM paper_ids")}
            self.assertEqual(ids, {("doi", "https://doi.org/10.48550/arxiv.2601.01234"), ("arxiv", "2601.01234"),
                                   ("openalex", "W9")})
            self.assertEqual([r["channel"] for r in store.conn.execute(
                "SELECT channel FROM project_channels WHERE project_id='default_project' ORDER BY rowid")],
                presets.LEGACY_CHANNELS)
            self.assertEqual(store.conn.execute("SELECT discipline FROM projects").fetchone()[0], "cs_ai")
            from app.migrations import migrate_005_channels
            migrate_005_channels(store.conn)  # running it again changes nothing
            self.assertEqual(store.conn.execute("SELECT COUNT(*) FROM paper_ids").fetchone()[0], 3)
            self.assertEqual(store.conn.execute("SELECT COUNT(*) FROM project_channels").fetchone()[0], 3)
            store.close()

    def test_fresh_database_reaches_the_latest_version_with_all_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "p.sqlite")
            store.init()
            tables = {r[0] for r in store.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for name in ("paper_ids", "paper_sources", "project_channels", "channel_usage", "channel_status"):
                self.assertIn(name, tables)
            columns = {r[1] for r in store.conn.execute("PRAGMA table_info(papers)")}
            self.assertTrue({"language", "url", "pdf_url", "channel", "authors", "title_norm", "year"} <= columns)
            store.close()


class UsageTests(unittest.TestCase):
    def test_reservation_is_atomic_per_day_and_refuses_over_the_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "p.sqlite")
            store.init()
            usage.reserve(store.conn, "x", 2)
            usage.reserve(store.conn, "x", 2)
            with self.assertRaises(SourceError) as caught:
                usage.reserve(store.conn, "x", 2)
            self.assertEqual(caught.exception.kind, "quota_exhausted")
            self.assertEqual(usage.used(store.conn, "x"), 2)
            usage.reserve(store.conn, "y", 2)  # another channel has its own allowance
            store.close()


class FakeChannel(base.Channel):
    scripts = ("latin",)

    def __init__(self, id, papers=None, error=None, scripts=("latin",), auth="none"):
        self.id, self.name, self._papers, self._error = id, id, papers or [], error
        self.scripts, self.auth, self.terms_url, self.calls = scripts, auth, "https://x.org", []

    def search(self, ctx, term, since, limit):
        self.calls.append(term)
        if self._error:
            raise self._error
        return [dict(p, key=f"{p['key']}-{term}", title=f"{p['title']} {term}") for p in self._papers]


def one(key, title="Planning with latent world models"):
    return {"key": key, "title": title, "abstract": "", "published": "2026-02-01", "channel": "fake"}


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = App(root=ROOT, data_dir=Path(self.tmp.name))
        self.project = self.app.create_project("P", "manual", ["world model", "数字人文", "robot"])["project_id"]

    def fake(self, *channels):
        by_id = {c.id: c for c in channels}
        self.app.projects.set_channels(self.project, list(by_id))
        patcher = mock.patch("app.service.channel_registry.get", side_effect=by_id.get)
        patcher.start()
        self.addCleanup(patcher.stop)
        return by_id

    def test_new_project_starts_with_the_preset_channels(self):
        self.assertEqual(self.app.projects.channels(self.project), presets.channels_for("cs_ai"))
        self.assertEqual(self.app.projects.get_project(self.project)["discipline"], "cs_ai")
        with self.assertRaises(ValueError):
            self.app.projects.create_project("bad", discipline="nope")

    def test_refresh_searches_with_the_project_keywords_not_a_fixed_query(self):
        channels = self.fake(FakeChannel("a", [one("k1")]))
        result = self.app.refresh_candidates(project_id=self.project)
        self.assertEqual(channels["a"].calls, ["world model", "robot"])  # latin terms only, project order
        self.assertEqual(result["terms"], ["world model", "数字人文", "robot"])
        self.assertEqual(result["channels"][0]["terms"], ["world model", "robot"])
        self.assertEqual(result["added"], 2)
        self.assertEqual(self.app.store.conn.execute(
            "SELECT query FROM paper_sources ORDER BY query").fetchall()[0][0], "robot")

    def test_one_failing_channel_does_not_block_the_others(self):
        self.fake(FakeChannel("bad", error=SourceError("down", "unavailable")), FakeChannel("good", [one("k1")]))
        result = self.app.refresh_candidates(project_id=self.project)
        status = {c["channel"]: c for c in result["channels"]}
        self.assertEqual(status["bad"]["status"], "error")
        self.assertEqual(status["bad"]["kind"], "unavailable")
        self.assertEqual(status["good"]["status"], "ok")
        self.assertGreater(result["added"], 0)
        self.assertEqual([(e["channel"], e["kind"]) for e in result["errors"]], [("bad", "unavailable")])

    def test_a_failing_channel_stops_after_its_first_failed_term(self):
        channels = self.fake(FakeChannel("bad", error=SourceError("down", "unavailable")))
        self.app.refresh_candidates(project_id=self.project)
        self.assertEqual(len(channels["bad"].calls), 1)

    def test_channels_without_matching_script_credential_or_implementation_are_skipped_with_a_reason(self):
        self.fake(FakeChannel("cn", [one("k")], scripts=("cjk",)), FakeChannel("en", scripts=("latin",)),
                  FakeChannel("keyed", auth="api_key"))
        self.app.projects.set_channels(self.project, ["cn", "en", "keyed", "missing"])
        self.app.store.set_setting(f"project_default_terms_{self.project}", [])
        result = self.app.refresh_candidates(project_id=self.project)
        status = {c["channel"]: c for c in result["channels"]}
        self.assertEqual(status["cn"]["status"], "ok")
        self.assertEqual(status["cn"]["terms"], ["数字人文"])
        self.assertEqual(status["keyed"]["reason"], "needs_credential")
        self.assertEqual(status["missing"]["reason"], "not_available")

    def test_a_chinese_only_project_never_calls_the_english_only_channel(self):
        project = self.app.create_project("中", "manual", ["数字人文"])["project_id"]
        urls = []

        def respond(request, timeout=None):
            urls.append(request.full_url)
            if "openalex" in request.full_url:
                return Body(fixture("openalex", "ok.json").encode())
            return Body(fixture("crossref", "ok.json").encode())

        with mock.patch("urllib.request.urlopen", side_effect=respond), mock.patch("app.channels.http.time.sleep"):
            result = self.app.refresh_candidates(project_id=project)
        status = {c["channel"]: c for c in result["channels"]}
        self.assertEqual((status["arxiv"]["status"], status["arxiv"]["reason"]), ("skipped", "no_matching_terms"))
        self.assertFalse([u for u in urls if "arxiv.org" in u])
        self.assertEqual(status["openalex"]["terms"], ["数字人文"])
        self.assertGreater(result["added"], 0)

    def test_a_project_without_keywords_reports_it_instead_of_searching_a_default(self):
        empty = self.app.create_project("空", "manual", [])["project_id"]
        with mock.patch("urllib.request.urlopen") as urlopen:
            result = self.app.refresh_candidates(project_id=empty)
        urlopen.assert_not_called()
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["errors"][0]["kind"], "invalid_input")

    def test_the_migrated_default_project_keeps_its_world_model_query(self):
        channels = self.fake(FakeChannel("a"))
        default = self.app.get_default_project_id()
        self.app.projects.set_channels(default, ["a"])
        self.app.refresh_candidates(project_id=default)
        self.assertEqual(channels["a"].calls, ["world model"])

    def test_daily_ceiling_is_enforced_before_the_request(self):
        channels = self.fake(FakeChannel("a", [one("k1")]))
        channels["a"].daily_cap = 1
        result = self.app.refresh_candidates(project_id=self.project)
        self.assertEqual(channels["a"].calls, ["world model"])  # one reserved, the second refused
        self.assertEqual(result["errors"][0]["kind"], "quota_exhausted")
        again = self.app.refresh_candidates(project_id=self.project)
        self.assertEqual(channels["a"].calls, ["world model"])
        self.assertEqual(again["channels"][0]["status"], "error")

    def test_deleting_a_project_removes_its_channel_rows(self):
        self.app.projects.delete_project(self.project)
        self.assertEqual(self.app.store.conn.execute(
            "SELECT COUNT(*) FROM project_channels WHERE project_id=?", (self.project,)).fetchone()[0], 0)


class SmokeToolTests(unittest.TestCase):
    def test_rows_report_failures_and_skips_honestly(self):
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        import channel_smoke
        ctx = base.Context(cache_dir=Path(tempfile.mkdtemp()))
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("denied")), \
                mock.patch("app.channels.http.time.sleep"):
            rows = channel_smoke.run_channel(registry.get("arxiv"), ctx)
        self.assertEqual([(r["term"], r["status"], r["kind"]) for r in rows], [("world model", "error", "network_error")])
        rows = channel_smoke.run_channel(FakeChannel("cn", scripts=("cjk",)), ctx, terms=["english only"])
        self.assertEqual(rows[0]["status"], "skipped")
        table = channel_smoke.render(rows, "now")
        self.assertIn("| cn |", table)


if __name__ == "__main__":
    unittest.main()
