"""Per-source API keys: 0600 files, environment override, never echoed; service and HTTP endpoints for the settings page.

Every key in these tests is a dummy value. No test touches the network: urlopen is replaced.
"""
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURES = ROOT / "tests" / "fixtures" / "baidu_scholar"
BAIDU = "bce-v3/ALTAK-dummyDummy0000/dummydummydummydummy0000"
OPENALEX = "dummy-openalex-key-0000"
ENV_VARS = ("OPENALEX_API_KEY", "BAIDU_SCHOLAR_API_KEY")


def clean_env(case):
    patcher = mock.patch.dict(os.environ, {}, clear=False)
    patcher.start()
    case.addCleanup(patcher.stop)
    for name in ENV_VARS:
        os.environ.pop(name, None)


class Reply:
    def __init__(self, body):
        self.body, self.headers = body, {}

    def read(self, limit=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Fake:
    def __init__(self, *answers, default=None):
        self.answers, self.default, self.calls, self.lock = list(answers), default, [], threading.Lock()

    def __call__(self, request, timeout=None):
        with self.lock:
            self.calls.append({"url": request.full_url, "auth": request.get_header("Authorization")})
            answer = self.answers.pop(0) if self.answers else self.default
        if isinstance(answer, BaseException):
            raise answer
        return Reply(answer)


def http_error(code):
    return urllib.error.HTTPError("https://x.example/", code, "synthetic", {}, None)


class KeyStorageTests(unittest.TestCase):
    def setUp(self):
        from app import source_keys
        self.keys = source_keys
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name)
        clean_env(self)

    def test_round_trip_with_private_permissions_for_each_source(self):
        for source, value in (("openalex", OPENALEX), ("baidu_scholar", BAIDU)):
            with self.subTest(source):
                self.assertEqual(self.keys.status(self.data, source), {"configured": False, "source": None})
                status = self.keys.save(self.data, source, value)
                self.assertEqual(set(status), {"configured", "source"})
                self.assertTrue(status["configured"])
                self.assertNotIn(value, json.dumps(status))
                path = self.keys.key_file(self.data, source)
                self.assertEqual(path.name, f"{source}.key")
                if sys.platform != "win32":  # 0600 file modes are POSIX-only; on Windows the per-user profile ACL is the protection.
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                self.assertEqual(self.keys.load(self.data, source), value)
                self.assertFalse(self.keys.clear(self.data, source)["configured"])
                self.assertIsNone(self.keys.load(self.data, source))
                self.assertFalse(path.exists())

    def test_sources_do_not_share_keys(self):
        self.keys.save(self.data, "openalex", OPENALEX)
        self.assertIsNone(self.keys.load(self.data, "baidu_scholar"))
        self.keys.save(self.data, "baidu_scholar", BAIDU)
        self.assertEqual(self.keys.load(self.data, "openalex"), OPENALEX)

    def test_environment_variable_wins_per_source_and_is_reported_as_such(self):
        self.keys.save(self.data, "baidu_scholar", BAIDU)
        with mock.patch.dict(os.environ, {"BAIDU_SCHOLAR_API_KEY": "from-env/key-1111111"}):
            self.assertEqual(self.keys.load(self.data, "baidu_scholar"), "from-env/key-1111111")
            self.assertEqual(self.keys.status(self.data, "baidu_scholar")["source"], "environment")
            self.assertIsNone(self.keys.load(self.data, "openalex"))
        with mock.patch.dict(os.environ, {"BAIDU_SCHOLAR_API_KEY": "bad env value"}):
            self.assertEqual(self.keys.load(self.data, "baidu_scholar"), BAIDU)         # an invalid variable is ignored

    def test_invalid_keys_are_rejected_and_not_written(self):
        for bad in ("", "   ", "short", "has space inside-key", "line\nbreak-key-12345", "x" * 600, None, 12345678):
            with self.assertRaises(ValueError):
                self.keys.save(self.data, "baidu_scholar", bad)
        with self.assertRaises(ValueError):
            self.keys.save(self.data, "openalex", "a/b-slash-key-000")          # OpenAlex keys have no '/'
        self.assertFalse(self.keys.key_file(self.data, "baidu_scholar").exists())
        self.assertFalse(self.keys.key_file(self.data, "openalex").exists())

    def test_a_source_without_a_key_has_no_key_file(self):
        for source in ("arxiv", "nonsense"):
            with self.assertRaises(ValueError):
                self.keys.save(self.data, source, OPENALEX)
            self.assertEqual(self.keys.status(self.data, source), {"configured": False, "source": None})
            self.assertIsNone(self.keys.load(self.data, source))

    def test_surrounding_whitespace_is_trimmed_and_an_unreadable_file_is_unconfigured(self):
        self.keys.save(self.data, "baidu_scholar", f"  {BAIDU}\n")
        self.assertEqual(self.keys.load(self.data, "baidu_scholar"), BAIDU)
        self.keys.key_file(self.data, "baidu_scholar").write_text("garbage\nBAIDU_SCHOLAR_API_KEY=bad value\n")
        self.assertFalse(self.keys.status(self.data, "baidu_scholar")["configured"])

    def test_a_replaced_key_leaves_no_second_copy(self):
        self.keys.save(self.data, "baidu_scholar", BAIDU)
        self.keys.save(self.data, "baidu_scholar", "another-dummy/key-22222222")
        self.assertEqual(self.keys.load(self.data, "baidu_scholar"), "another-dummy/key-22222222")
        for path in self.data.rglob("*"):
            if path.is_file():
                self.assertNotIn(BAIDU, path.read_text())

    @unittest.skipIf(sys.platform == "win32", "creating symlinks needs a privilege on Windows; the planted-link case is POSIX-only")
    def test_a_leftover_or_planted_temp_file_is_never_written_through(self):
        outside = self.data.parent / "outside-target.txt"
        outside.write_text("untouched")
        self.addCleanup(lambda: outside.unlink())
        (self.data / "baidu_scholar.key.tmp").symlink_to(outside)
        stale = self.data / ".baidu_scholar.key.1234.tmp"
        stale.write_text("OLD-SECRET")
        os.chmod(stale, 0o644)
        self.keys.save(self.data, "baidu_scholar", BAIDU)
        self.assertEqual(outside.read_text(), "untouched")
        self.assertEqual(self.keys.load(self.data, "baidu_scholar"), BAIDU)
        if sys.platform != "win32":  # 0600 file modes are POSIX-only; on Windows the per-user profile ACL is the protection.
            self.assertEqual(stat.S_IMODE(self.keys.key_file(self.data, "baidu_scholar").stat().st_mode), 0o600)

    def test_the_staging_file_is_created_exclusively_with_private_permissions(self):
        seen = []
        real_open = os.open

        def spy(path, flags, mode=0o777, *args, **kwargs):
            if str(path).endswith(".tmp"):
                seen.append((flags, mode))
            return real_open(path, flags, mode, *args, **kwargs)
        with mock.patch.object(os, "open", spy):
            self.keys.save(self.data, "baidu_scholar", BAIDU)
        self.assertEqual(len(seen), 1)
        flags, mode = seen[0]
        self.assertTrue(flags & os.O_EXCL and flags & os.O_CREAT)
        self.assertEqual(mode, 0o600)
        self.assertEqual([p.name for p in self.data.iterdir()], ["baidu_scholar.key"])      # nothing left behind

    def test_clearing_also_removes_leftover_staging_files(self):
        self.keys.save(self.data, "baidu_scholar", BAIDU)
        (self.data / "baidu_scholar.key.tmp").write_text(f"BAIDU_SCHOLAR_API_KEY={BAIDU}\n")
        (self.data / ".baidu_scholar.key.99.tmp").write_text(f"BAIDU_SCHOLAR_API_KEY={BAIDU}\n")
        (self.data / "openalex.key.tmp").write_text("keep me: another source")
        self.keys.clear(self.data, "baidu_scholar")
        self.assertEqual(sorted(p.name for p in self.data.iterdir()), ["openalex.key.tmp"])

    def test_the_openalex_wrapper_is_the_same_storage(self):
        from app import openalex_key
        openalex_key.save(self.data, OPENALEX)
        self.assertEqual(self.keys.load(self.data, "openalex"), OPENALEX)
        self.assertEqual(openalex_key.key_file(self.data), self.keys.key_file(self.data, "openalex"))
        self.assertEqual(openalex_key.status(self.data), self.keys.status(self.data, "openalex"))
        self.keys.save(self.data, "openalex", "second-openalex-key-1")
        self.assertEqual(openalex_key.load(self.data), "second-openalex-key-1")
        with self.assertRaises(ValueError) as caught:
            openalex_key.save(self.data, "bad key")
        self.assertIn("OpenAlex", str(caught.exception))
        self.assertTrue(openalex_key.valid(OPENALEX) and not openalex_key.valid("x"))

    def test_a_file_written_by_the_previous_version_is_still_read(self):
        (self.data).mkdir(exist_ok=True)
        (self.data / "openalex.key").write_text(f"OPENALEX_API_KEY={OPENALEX}\n")
        self.assertEqual(self.keys.load(self.data, "openalex"), OPENALEX)


class ServiceCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "harness").mkdir()
        (self.root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (self.root / "harness" / "budget.json").write_text((ROOT / "harness" / "budget.json").read_text())
        clean_env(self)
        sleeper = mock.patch("time.sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def make_app(self):
        from app.service import App
        app = App(root=str(self.root), data_dir=str(self.root / "data"))
        self.addCleanup(app.store.close)
        return app

    def patched(self, fake):
        return mock.patch.object(urllib.request, "urlopen", fake)


class ServiceTests(ServiceCase):
    def test_the_registry_holds_both_adapters_and_the_old_client_is_unchanged(self):
        app = self.make_app()
        self.assertIs(app.adapters["openalex"], app.source)
        self.assertEqual(app.adapters["baidu_scholar"].info.id, "baidu_scholar")
        self.assertFalse((self.root / "data" / "cache" / "baidu_scholar").exists())     # nothing is created for a source never used

    def test_save_and_clear_update_the_live_adapter(self):
        app = self.make_app()
        app.save_source_key("baidu_scholar", BAIDU)
        self.assertEqual(app.adapters["baidu_scholar"].api_key, BAIDU)
        self.assertEqual(self.make_app().adapters["baidu_scholar"].api_key, BAIDU)
        app.clear_source_key("baidu_scholar")
        self.assertIsNone(app.adapters["baidu_scholar"].api_key)
        app.save_source_key("openalex", OPENALEX)
        self.assertEqual(app.source.api_key, OPENALEX)

    def test_unknown_or_keyless_sources_are_refused(self):
        app = self.make_app()
        for bad in ("arxiv", "nope", None, 5):
            with self.assertRaises(ValueError):
                app.save_source_key(bad, BAIDU)
            with self.assertRaises(ValueError):
                app.clear_source_key(bad)
            with self.assertRaises(ValueError):
                app.test_source(bad)

    def test_status_payload_has_no_secret_and_reports_the_state_in_words_of_kinds(self):
        app = self.make_app()
        status = app.sources_status()
        self.assertEqual(set(status), {"openalex", "baidu_scholar", "baidu_web"})
        self.assertEqual(status["baidu_scholar"], {"needs_key": True, "key": "required", "configured": False, "status_kind": None,
                                                   "used_today": 0, "daily_cap": 40, "key_url": status["baidu_scholar"]["key_url"]})
        self.assertTrue(status["baidu_scholar"]["key_url"].startswith("https://"))
        self.assertEqual((status["openalex"]["needs_key"], status["openalex"]["key"], status["openalex"]["used_today"]), (False, "optional", None))
        app.save_source_key("baidu_scholar", BAIDU)
        self.assertTrue(app.sources_status()["baidu_scholar"]["configured"])
        self.assertNotIn(BAIDU, json.dumps(app.sources_status()))

    def test_testing_the_saved_key_records_the_kind_and_a_new_key_resets_it(self):
        app = self.make_app()
        app.save_source_key("baidu_scholar", BAIDU)
        with self.patched(Fake(http_error(401))):
            result = app.test_source("baidu_scholar")
        self.assertEqual((result["ok"], result["kind"]), (False, "auth_required"))
        self.assertEqual(app.sources_status()["baidu_scholar"]["status_kind"], "auth_required")
        self.assertEqual(app.store.get_setting("source_status:baidu_scholar")["kind"], "auth_required")
        app.save_source_key("baidu_scholar", "another-dummy/key-22222222")
        self.assertIsNone(app.sources_status()["baidu_scholar"]["status_kind"])
        with self.patched(Fake((FIXTURES / "success.json").read_bytes())):
            result = app.test_source("baidu_scholar")
        self.assertEqual((result["ok"], result["kind"]), (True, "ok"))
        self.assertEqual(app.sources_status()["baidu_scholar"]["status_kind"], "ok")
        app.clear_source_key("baidu_scholar")
        self.assertIsNone(app.sources_status()["baidu_scholar"]["status_kind"])

    def test_a_quota_status_from_an_earlier_day_is_not_reported(self):
        import datetime
        app = self.make_app()
        app.store.set_setting("source_status:baidu_scholar", {"kind": "quota_exhausted", "at": "2026-10-01T00:00:00+00:00"})
        self.assertIsNone(app.sources_status()["baidu_scholar"]["status_kind"])
        app.store.set_setting("source_status:baidu_scholar", {"kind": "quota_exhausted",
                                                              "at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()})
        self.assertEqual(app.sources_status()["baidu_scholar"]["status_kind"], "quota_exhausted")
        app.store.set_setting("source_status:baidu_scholar", {"kind": "auth_required", "at": "2026-10-01T00:00:00+00:00"})
        self.assertEqual(app.sources_status()["baidu_scholar"]["status_kind"], "auth_required")     # a refused key stays refused
        for junk in ({"kind": "quota_exhausted", "at": "yesterday"}, {"kind": 5}, "text", None):
            app.store.set_setting("source_status:baidu_scholar", junk)
            self.assertIsNone(app.sources_status()["baidu_scholar"]["status_kind"])

    def test_testing_a_typed_key_does_not_save_it_or_change_the_recorded_status(self):
        app = self.make_app()
        fake = Fake(http_error(401))
        with self.patched(fake):
            result = app.test_source("baidu_scholar", api_key=BAIDU)
        self.assertEqual((result["ok"], result["kind"]), (False, "auth_required"))
        self.assertEqual(fake.calls[0]["auth"], f"Bearer {BAIDU}")
        self.assertFalse(app.sources_status()["baidu_scholar"]["configured"])
        self.assertIsNone(app.sources_status()["baidu_scholar"]["status_kind"])
        self.assertIsNone(app.store.get_setting("source_status:baidu_scholar"))

    def test_testing_without_any_key_sends_nothing(self):
        app = self.make_app()
        fake = Fake((FIXTURES / "success.json").read_bytes())
        with self.patched(fake):
            result = app.test_source("baidu_scholar")
        self.assertEqual((result["ok"], result["kind"], fake.calls), (False, "auth_required", []))
        self.assertTrue(result["reason"])

    def test_every_failure_has_a_short_reason_that_never_holds_the_key(self):
        app = self.make_app()
        answers = [(http_error(401), "auth_required"), ((FIXTURES / "error_quota.json").read_bytes(), "quota_exhausted"),
                   (urllib.error.URLError(BAIDU), "network_error"), (http_error(500), "unavailable"),
                   ((FIXTURES / "html_body.html").read_bytes(), "bad_response")]
        for answer, kind in answers:
            with self.patched(Fake(answer)):
                result = app.test_source("baidu_scholar", api_key=BAIDU)
            self.assertEqual(result["kind"], kind)
            self.assertLess(len(result["reason"]), 60)
            self.assertNotIn(BAIDU, json.dumps(result, ensure_ascii=False))

    def test_the_reason_follows_the_interface_language(self):
        app = self.make_app()
        (self.root / "data" / "settings.json").write_text(json.dumps({"language": "en-US"}))
        with self.patched(Fake(http_error(401))):
            reason = app.test_source("baidu_scholar", api_key=BAIDU)["reason"]
        self.assertNotRegex(reason, r"[一-鿿]")

    def test_openalex_can_be_tested_without_a_key_and_with_a_typed_one(self):
        app = self.make_app()
        fake = Fake(b"{}", http_error(401))
        with self.patched(fake):
            self.assertTrue(app.test_source("openalex")["ok"])
            self.assertEqual(app.test_source("openalex", api_key=OPENALEX)["kind"], "auth_required")
        self.assertEqual([c["auth"] for c in fake.calls], [None, f"Bearer {OPENALEX}"])

    def test_a_test_counts_one_call_today(self):
        app = self.make_app()
        app.save_source_key("baidu_scholar", BAIDU)
        with self.patched(Fake((FIXTURES / "success.json").read_bytes())):
            app.test_source("baidu_scholar")
        self.assertEqual(app.sources_status()["baidu_scholar"]["used_today"], 1)

    def test_nothing_is_ever_sent_by_creating_the_app_or_reading_status(self):
        fake = Fake(default=b"{}")
        with self.patched(fake):
            app = self.make_app()
            app.save_source_key("baidu_scholar", BAIDU)
            app.sources_status()
            app.openalex_status()
        self.assertEqual(fake.calls, [])


class ServerTests(ServiceCase):
    def serve(self):
        from app import server
        httpd = server.build_server(port=0, root=str(self.root))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd.server_address[1]

    def call(self, port, path, payload=None, raw=None):
        data = raw if raw is not None else json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                         headers={"Content-Type": "application/json"}, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()

    def real_urlopen(self):
        return urllib.request.urlopen

    def test_save_report_and_clear_a_source_key_without_echoing_it(self):
        port = self.serve()
        status, body = self.call(port, "/api/settings", {"source_key": {"id": "baidu_scholar", "value": BAIDU}})
        self.assertEqual(status, 200)
        self.assertNotIn(BAIDU, body)
        self.assertTrue(json.loads(body)["sources"]["baidu_scholar"]["configured"])
        status, body = self.call(port, "/api/settings")
        self.assertNotIn(BAIDU, body)
        sources = json.loads(body)["sources"]
        self.assertTrue(sources["baidu_scholar"]["configured"])
        self.assertFalse(sources["openalex"]["configured"])
        self.assertIn("openalex", json.loads(body))           # the older field stays for older pages
        status, body = self.call(port, "/api/settings", {"clear_source_key": "baidu_scholar"})
        self.assertFalse(json.loads(body)["sources"]["baidu_scholar"]["configured"])

    def test_the_openalex_key_works_through_both_the_old_and_the_new_request(self):
        port = self.serve()
        self.call(port, "/api/settings", {"source_key": {"id": "openalex", "value": OPENALEX}})
        body = json.loads(self.call(port, "/api/settings")[1])
        self.assertTrue(body["openalex"]["configured"] and body["sources"]["openalex"]["configured"])
        self.call(port, "/api/settings", {"clear_openalex_key": True})
        self.assertFalse(json.loads(self.call(port, "/api/settings")[1])["sources"]["openalex"]["configured"])

    def test_bad_requests_are_400_and_store_nothing(self):
        port = self.serve()
        for payload in ({"source_key": {"id": "baidu_scholar", "value": "bad key"}}, {"source_key": {"id": "arxiv", "value": BAIDU}},
                        {"source_key": {"id": "nope", "value": BAIDU}}, {"source_key": "baidu_scholar"}, {"source_key": {"id": "baidu_scholar"}},
                        {"source_key": {"id": ["baidu_scholar"], "value": BAIDU}}, {"clear_source_key": "arxiv"}, {"clear_source_key": 5}):
            status, body = self.call(port, "/api/settings", payload)
            self.assertEqual(status, 400, payload)
            self.assertNotIn(BAIDU, body)
        self.assertFalse(json.loads(self.call(port, "/api/settings")[1])["sources"]["baidu_scholar"]["configured"])

    def test_the_key_never_lands_in_the_user_settings_file(self):
        port = self.serve()
        self.call(port, "/api/settings", {"source_key": {"id": "baidu_scholar", "value": BAIDU}})
        self.call(port, "/api/user_settings", {"settings": {"theme": "dark", "sourceBaiduScholar": True}})
        for path in self.root.rglob("settings.json"):
            self.assertNotIn(BAIDU, path.read_text())
        status, body = self.call(port, "/api/user_settings")
        self.assertNotIn(BAIDU, body)
        self.assertTrue(json.loads(body)["settings"]["sourceBaiduScholar"])

    def test_source_test_uses_the_typed_key_once_and_stores_nothing(self):
        port = self.serve()
        fake = Fake((FIXTURES / "success.json").read_bytes())
        real = urllib.request.urlopen

        def router(request, timeout=None):
            if request.full_url.startswith("http://127.0.0.1"):
                return real(request, timeout=timeout)
            return fake(request, timeout=timeout)
        with mock.patch.object(urllib.request, "urlopen", router):
            status, body = self.call(port, "/api/source-test", {"id": "baidu_scholar", "api_key": BAIDU})
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual((result["ok"], result["kind"]), (True, "ok"))
        self.assertNotIn(BAIDU, body)
        self.assertEqual([c["auth"] for c in fake.calls], [f"Bearer {BAIDU}"])
        self.assertFalse(json.loads(self.call(port, "/api/settings")[1])["sources"]["baidu_scholar"]["configured"])

    def test_source_test_failure_is_a_200_with_a_kind(self):
        port = self.serve()
        real = urllib.request.urlopen

        def router(request, timeout=None):
            if request.full_url.startswith("http://127.0.0.1"):
                return real(request, timeout=timeout)
            raise http_error(401)
        with mock.patch.object(urllib.request, "urlopen", router):
            status, body = self.call(port, "/api/source-test", {"id": "baidu_scholar", "api_key": BAIDU})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["kind"], "auth_required")
        self.assertNotIn(BAIDU, body)

    def test_source_test_validates_its_request(self):
        port = self.serve()
        for payload in ({"id": "nope"}, {"id": "arxiv"}, {"id": "baidu_scholar", "api_key": 5}, {"id": "baidu_scholar", "api_key": "a\nb"},
                        {"id": "baidu_scholar", "extra": 1}, {"api_key": BAIDU}, {"id": 7}):
            status, body = self.call(port, "/api/source-test", payload)
            self.assertEqual(status, 400, payload)
            self.assertNotIn(BAIDU, body)

    def test_source_test_body_is_capped(self):
        port = self.serve()
        status, _ = self.call(port, "/api/source-test", raw=json.dumps({"id": "baidu_scholar", "api_key": "x" * 20000}).encode())
        self.assertEqual(status, 413)

    def test_the_payload_after_a_failed_test_names_the_kind_only(self):
        port = self.serve()
        self.call(port, "/api/settings", {"source_key": {"id": "baidu_scholar", "value": BAIDU}})
        real = urllib.request.urlopen

        def router(request, timeout=None):
            if request.full_url.startswith("http://127.0.0.1"):
                return real(request, timeout=timeout)
            raise http_error(401)
        with mock.patch.object(urllib.request, "urlopen", router):
            self.call(port, "/api/source-test", {"id": "baidu_scholar"})
        payload = json.loads(self.call(port, "/api/settings")[1])
        self.assertEqual(payload["sources"]["baidu_scholar"]["status_kind"], "auth_required")
        self.assertEqual(payload["sources"]["baidu_scholar"]["used_today"], 1)
        self.assertNotIn(BAIDU, json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
