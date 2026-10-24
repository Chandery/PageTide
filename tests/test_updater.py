"""Update check and hand-off: version compare, cache, switch, asset choice, checksum, path safety. No test reaches the network."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import server, updater

BASE = "https://github.com/Chandery/PaperDigHelper/releases/download/v0.2.0/"
WIN = "PaperDigHelper_0.2.0_x64-setup.exe"
MAC = "PaperDigHelper-macos-arm64.zip"


def release(tag="v0.2.0", names=(WIN, WIN + ".sha256", MAC, MAC + ".sha256"), **extra):
    value = {"tag_name": tag, "draft": False, "prerelease": False, "body": "Fixes\n\nand more",
             "html_url": "https://github.com/Chandery/PaperDigHelper/releases/tag/" + tag,
             "assets": [{"name": n, "size": 10, "browser_download_url": BASE + n} for n in names]}
    value.update(extra)
    return value


class FakeTransport:
    def __init__(self, payload=None, error=None, files=None):
        self.payload, self.error, self.files = payload, error, files or {}
        self.requests = []

    def get_bytes(self, url, max_bytes=0, accept=""):
        self.requests.append(url)
        if self.error:
            raise self.error
        if url in self.files:
            return self.files[url]
        return json.dumps(self.payload).encode()

    def download(self, url, destination, progress=None):
        self.requests.append(url)
        Path(destination).write_bytes(self.files[url])
        if progress:
            progress(len(self.files[url]), len(self.files[url]))


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


class VersionTests(unittest.TestCase):
    def test_semantic_comparison_and_rejects(self):
        self.assertGreater(updater.parse_version("v0.10.0"), updater.parse_version("0.9.9"))
        self.assertGreater(updater.parse_version("1.0.0"), updater.parse_version("0.99.99"))
        self.assertEqual(updater.parse_version("v0.1.0"), updater.parse_version("0.1.0"))
        for bad in ("", None, "v1", "1.2", "1.2.3-beta", "1.2.3.4", "latest", "v1.2.x"):
            self.assertIsNone(updater.parse_version(bad), bad)

    def test_asset_choice_per_platform(self):
        names = [{"name": n} for n in (WIN, WIN + ".sha256", MAC, MAC + ".sha256", "notes.txt")]
        self.assertEqual(updater.pick_assets(names, "windows"), (WIN, WIN + ".sha256"))
        self.assertEqual(updater.pick_assets(names, "macos"), (MAC, MAC + ".sha256"))
        self.assertIsNone(updater.pick_assets(names, None))
        self.assertIsNone(updater.pick_assets([{"name": WIN}], "windows"))   # no checksum, no update
        self.assertIsNone(updater.pick_assets([{"name": "evil/../PaperDigHelper_0.2.0_x64-setup.exe", }], "windows"))
        self.assertEqual(updater.platform_key("win32"), "windows")
        self.assertEqual(updater.platform_key("darwin", "arm64"), "macos")
        self.assertIsNone(updater.platform_key("darwin", "x86_64"))
        self.assertIsNone(updater.platform_key("linux"))


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.clock = Clock()
        updater.reset_runtime_state()

    def make(self, transport, version="0.1.0", platform="darwin", machine="arm64"):
        return updater.Updater(self.data, version, transport, platform=platform, machine=machine, clock=self.clock)

    def test_source_run_without_version_never_requests(self):
        transport = FakeTransport(release())
        for version in (None, ""):
            result = self.make(transport, version).check(force=True)
            self.assertEqual((result["status"], result["reason_code"], result["available"]), ("disabled", "dev_build", False))
        self.assertEqual(transport.requests, [])
        self.assertEqual(self.make(transport, "garbage").check()["reason_code"], "invalid_version")

    def test_available_update_reports_version_asset_and_summary(self):
        result = self.make(FakeTransport(release())).check()
        self.assertEqual((result["status"], result["available"], result["latest"], result["asset"]), ("ok", True, "0.2.0", MAC))
        self.assertEqual(result["current"], "0.1.0")
        self.assertIn("Fixes", result["notes"])
        self.assertTrue(result["html_url"].startswith("https://github.com/Chandery/PaperDigHelper/"))
        self.assertEqual(self.make(FakeTransport(release()), platform="win32").check()["asset"], WIN)

    def test_same_older_missing_asset_and_unusable_releases_are_not_offered(self):
        self.assertEqual(self.make(FakeTransport(release("v0.1.0"))).check()["reason_code"], "up_to_date")
        self.assertFalse(self.make(FakeTransport(release("v0.0.9"))).check(force=True)["available"])
        no_mac = self.make(FakeTransport(release(names=(WIN, WIN + ".sha256")))).check(force=True)
        self.assertEqual((no_mac["available"], no_mac["reason_code"]), (False, "no_asset"))
        self.assertFalse(self.make(FakeTransport(release()), machine="x86_64").check(force=True)["available"])
        for odd in (release(draft=True), release(prerelease=True), release("v0.3.0-rc1"), {"nope": 1}):
            (self.data / updater.CACHE_NAME).unlink(missing_ok=True)
            self.assertEqual(self.make(FakeTransport(odd)).check(force=True)["status"], "unknown")

    def test_download_urls_outside_the_repository_are_dropped(self):
        evil = release()
        evil["assets"][2]["browser_download_url"] = "https://evil.example/" + MAC
        self.assertFalse(self.make(FakeTransport(evil)).check(force=True)["available"])

    def test_cache_is_used_for_six_hours_then_refreshed(self):
        transport = FakeTransport(release())
        checker = self.make(transport)
        checker.check()
        checker.check()
        self.assertEqual(len(transport.requests), 1)
        self.clock.now += 6 * 3600 - 60
        checker.check()
        self.assertEqual(len(transport.requests), 1)
        self.clock.now += 120
        checker.check()
        self.assertEqual(len(transport.requests), 2)
        checker.check(force=True)
        self.assertEqual(len(transport.requests), 3)
        # An app that was updated sees the cached release against its new version without asking again.
        newer = self.make(transport, "0.2.0").check()
        self.assertFalse(newer["available"])
        self.assertEqual(len(transport.requests), 3)

    def test_cache_dated_in_the_future_is_stale(self):
        transport = FakeTransport(release())
        self.make(transport).check()
        self.clock.now -= 3600
        self.make(transport).check()
        self.assertEqual(len(transport.requests), 2)

    def test_network_failure_is_silent_and_not_retried_on_every_call(self):
        for error in (urllib.error.URLError("offline"), TimeoutError(), ValueError("bad json")):
            self.setUp()
            transport = FakeTransport(error=error)
            checker = self.make(transport)
            result = checker.check()
            self.assertEqual((result["status"], result["available"]), ("unknown", False))
            checker.check()
            self.assertEqual(len(transport.requests), 1)
            self.clock.now += 16 * 60
            checker.check()
            self.assertEqual(len(transport.requests), 2)

    def test_failure_keeps_the_last_known_release(self):
        self.make(FakeTransport(release())).check()
        self.clock.now += 7 * 3600
        result = self.make(FakeTransport(error=OSError("down"))).check()
        self.assertTrue(result["available"])

    def test_switch_off_sends_no_request_but_manual_check_still_works(self):
        (self.data / "settings.json").write_text(json.dumps({"autoCheckUpdates": False}))
        transport = FakeTransport(release())
        checker = self.make(transport)
        result = checker.check()
        self.assertEqual((result["status"], result["reason_code"]), ("disabled", "auto_check_off"))
        self.assertEqual(transport.requests, [])
        self.assertTrue(checker.check(force=True)["available"])
        # what the explicit check stored is still shown (the strip), without any further request
        self.assertTrue(checker.check()["available"])
        self.assertEqual(len(transport.requests), 1)
        (self.data / "settings.json").write_text(json.dumps({"autoCheckUpdates": True}))
        self.assertTrue(updater.auto_check_enabled(self.data))
        (self.data / "settings.json").write_text("not json")
        self.assertTrue(updater.auto_check_enabled(self.data))   # default on

    def test_dismissed_version_is_remembered_per_version(self):
        checker = self.make(FakeTransport(release()))
        self.assertFalse(checker.check()["dismissed"])
        checker.dismiss("0.2.0")
        self.assertTrue(checker.check()["dismissed"])
        newer = self.make(FakeTransport(release("v0.3.0", names=(WIN, WIN + ".sha256", MAC, MAC + ".sha256"))))
        newer.check(force=True)
        self.assertFalse(newer.check()["dismissed"])
        with self.assertRaises(updater.UpdateError):
            checker.dismiss("../x")

    def test_default_transport_user_agent_has_only_app_name_and_version(self):
        self.assertEqual(updater.Transport("0.1.0").user_agent, "PaperDigHelper/0.1.0")


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        updater.reset_runtime_state()
        self.payload = b"installer bytes"
        self.digest = hashlib.sha256(self.payload).hexdigest()

    def checker(self, digest=None, platform="win32", **kwargs):
        files = {BASE + WIN: self.payload, BASE + WIN + ".sha256": f"{digest or self.digest}  {WIN}\n".encode()}
        return updater.Updater(self.data, "0.1.0", FakeTransport(release(), files=files), platform=platform, **kwargs)

    def test_matching_checksum_leaves_the_file_in_updates(self):
        self.checker().start_download(run_async=False)
        state = updater.download_state()
        self.assertEqual(state["state"], "ready")
        self.assertEqual((self.data / "updates" / WIN).read_bytes(), self.payload)
        self.assertEqual(list((self.data / "updates").glob("*.part")), [])

    def test_checksum_mismatch_deletes_the_file_and_reports(self):
        self.checker(digest="0" * 64).start_download(run_async=False)
        state = updater.download_state()
        self.assertEqual(state["state"], "error")
        self.assertIn("校验失败", state["message"])
        self.assertEqual(list((self.data / "updates").iterdir()), [])

    def test_malformed_checksum_file_is_an_error(self):
        self.checker(digest="zz").start_download(run_async=False)
        self.assertEqual(updater.download_state()["state"], "error")
        self.assertEqual(list((self.data / "updates").iterdir()), [])

    def test_paths_cannot_escape_the_updates_directory(self):
        checker = self.checker()
        (self.data / "updates").mkdir()
        outside = self.data / "outside.exe"
        outside.write_bytes(b"x")
        self.assertFalse(checker.inside_updates(outside))
        self.assertFalse(checker.inside_updates(self.data / "updates"))
        self.assertFalse(checker.inside_updates(self.data / "updates" / ".." / "outside.exe"))
        self.assertTrue(checker.inside_updates(self.data / "updates" / WIN))
        for name in ("../" + WIN, "sub/" + WIN, "..\\" + WIN, "other.exe"):
            with self.assertRaises(updater.UpdateError):
                checker._download_verified(name, {"url": BASE + name}, {"url": BASE + name + ".sha256"})

    def test_apply_refuses_without_a_verified_download_or_when_the_file_changed(self):
        checker = self.checker()
        with self.assertRaises(updater.UpdateError):
            checker.apply()
        checker.start_download(run_async=False)
        (self.data / "updates" / WIN).write_bytes(b"tampered")
        with self.assertRaises(updater.UpdateError):
            checker.apply()
        # a state that points outside updates/ is refused as well
        outside = self.data / "x.exe"
        outside.write_bytes(b"x")
        with updater._state_lock:
            updater._download.update(path=str(outside), sha256=hashlib.sha256(b"x").hexdigest())
        with self.assertRaises(updater.UpdateError):
            checker.apply()

    def test_windows_apply_arms_a_powershell_helper_that_runs_only_after_the_quit(self):
        checker = self.checker()
        checker.start_download(run_async=False)
        self.assertEqual(checker.apply()["mode"], "installer")
        started = []
        self.assertTrue(updater.run_pending(popen=lambda command, **kw: started.append((command, kw)), platform="win32"))
        command, options = started[0]
        self.assertIn("-File", command)
        self.assertEqual(command[command.index("-Installer") + 1], str(self.data / "updates" / WIN))
        self.assertTrue(options["creationflags"] & 0x08000000)
        self.assertFalse(updater.run_pending(popen=lambda *a, **k: started.append(1)))   # consumed
        self.assertEqual(len(started), 1)

    def test_nothing_starts_when_no_update_was_applied_or_it_expired(self):
        started = []
        self.assertFalse(updater.run_pending(popen=lambda *a, **k: started.append(1)))
        checker = self.checker(clock=Clock())
        checker.start_download(run_async=False)
        checker.apply()
        self.assertFalse(updater.run_pending(popen=lambda *a, **k: started.append(1), clock=lambda: 1_000_000.0 + 3600))
        self.assertEqual(started, [])

    def test_macos_without_a_writable_app_falls_back_to_showing_the_zip(self):
        files = {BASE + MAC: b"zip", BASE + MAC + ".sha256": (hashlib.sha256(b"zip").hexdigest() + "  " + MAC + "\n").encode()}
        opened = []
        checker = updater.Updater(self.data, "0.1.0", FakeTransport(release(), files=files), platform="darwin", machine="arm64",
                                  runner=lambda *a, **k: subprocess.CompletedProcess(a, 1),   # ditto fails
                                  popen=lambda command, **k: opened.append(command), executable="/usr/bin/python3")
        checker.start_download(run_async=False)
        result = checker.apply()
        self.assertEqual(result["mode"], "manual")
        self.assertEqual(opened[0][:2], ["/usr/bin/open", "-R"])
        self.assertTrue(checker.inside_updates(Path(opened[0][2])))
        self.assertFalse(updater.run_pending(popen=lambda *a, **k: self.fail("no helper expected")))


@unittest.skipUnless(sys.platform == "darwin", "the replacement script uses macOS ditto/xattr")
class MacosReplaceScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.script = self.root / "apply.sh"
        self.script.write_text(updater.MACOS_SCRIPT, encoding="ascii")
        self.old, self.new = self.root / "apps" / "PaperDigHelper.app", self.root / "new" / "PaperDigHelper.app"
        for app, text in ((self.old, "old"), (self.new, "new")):
            (app / "Contents").mkdir(parents=True)
            (app / "Contents" / "version").write_text(text)
        self.log, self.opened = self.root / "log", self.root / "opened"
        self.fake_open = self.root / "open.sh"
        self.fake_open.write_text(f'#!/bin/sh\necho "$1" > "{self.opened}"\n')
        self.fake_open.chmod(0o755)

    def run_script(self, pid, new=None):
        return subprocess.run(["/bin/sh", str(self.script), str(pid), str(self.old), str(new or self.new), str(self.log), str(self.fake_open)],
                              timeout=60, capture_output=True)

    def test_replaces_the_app_after_the_process_ended_and_reopens_it(self):
        done = subprocess.Popen(["/usr/bin/true"])
        done.wait()
        self.run_script(done.pid)
        self.assertEqual((self.old / "Contents" / "version").read_text(), "new")
        self.assertEqual(self.opened.read_text().strip(), str(self.old))
        self.assertEqual([p.name for p in self.old.parent.iterdir()], ["PaperDigHelper.app"])   # no backup or stage left

    def test_missing_new_app_leaves_the_old_one_untouched_and_still_reopens_it(self):
        done = subprocess.Popen(["/usr/bin/true"])
        done.wait()
        self.run_script(done.pid, new=self.root / "missing.app")
        self.assertEqual((self.old / "Contents" / "version").read_text(), "old")
        self.assertEqual([p.name for p in self.old.parent.iterdir()], ["PaperDigHelper.app"])
        self.assertEqual(self.opened.read_text().strip(), str(self.old))

    def test_waits_for_the_running_app_before_touching_anything(self):
        sleeper = subprocess.Popen(["/bin/sleep", "1.5"])
        script = subprocess.Popen(["/bin/sh", str(self.script), str(sleeper.pid), str(self.old), str(self.new), str(self.log), str(self.fake_open)])
        try:
            threading.Event().wait(0.5)
            self.assertEqual((self.old / "Contents" / "version").read_text(), "old")
        finally:
            sleeper.wait()
            script.wait(timeout=30)
        self.assertEqual((self.old / "Contents" / "version").read_text(), "new")


class HttpRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        updater.reset_runtime_state()
        self.transport = FakeTransport(release())
        self.httpd = server.build_server(port=0, root=str(ROOT))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        patcher = patch.dict(os.environ, {"PAPERDIGHELPER_DATA": self.tmp.name, "PDH_APP_VERSION": "0.1.0"})
        patcher.start()
        self.addCleanup(patcher.stop)
        factory = patch.object(server.updater, "Transport", lambda version: self.transport)
        factory.start()
        self.addCleanup(factory.stop)

    def call(self, path, body=None):
        url = f"http://127.0.0.1:{self.httpd.server_port}{path}"
        request = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def test_get_update_and_dismiss_over_http(self):
        status, data = self.call("/api/update")
        self.assertEqual((status, data["available"], data["latest"]), (200, True, "0.2.0"))
        self.assertEqual(self.call("/api/update/dismiss", {"version": "0.2.0"})[0], 200)
        self.assertTrue(self.call("/api/update")[1]["dismissed"])
        self.assertEqual(self.call("/api/update/dismiss", {"version": "bad"})[0], 409)

    def test_dev_build_over_http_is_disabled_without_a_request(self):
        with patch.dict(os.environ):
            os.environ.pop("PDH_APP_VERSION")
            data = self.call("/api/update?force=1")[1]
        self.assertEqual(data["reason_code"], "dev_build")
        self.assertEqual(self.transport.requests, [])

    def test_download_without_an_update_is_refused_and_apply_needs_a_download(self):
        self.transport.payload = release("v0.1.0")
        self.call("/api/update?force=1")
        self.assertEqual(self.call("/api/update/download", {})[0], 409)
        self.assertEqual(self.call("/api/update/apply", {})[0], 409)


if __name__ == "__main__":
    unittest.main()
