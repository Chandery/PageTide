"""Update check and hand-off: version compare, cache, switch, asset choice, checksum, path safety. No test reaches the network."""
import hashlib
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import server, updater

BASE = f"https://github.com/{updater.REPO}/releases/download/v0.2.0/"
WIN = "PageTide_0.2.0_x64-setup.exe"
MAC = "PageTide-macos-arm64.zip"
MAC_X64 = "PageTide-macos-x64.zip"


def release(tag="v0.2.0", names=(WIN, WIN + ".sha256", MAC, MAC + ".sha256"), **extra):
    value = {"tag_name": tag, "draft": False, "prerelease": False, "body": "Fixes\n\nand more",
             "html_url": f"https://github.com/{updater.REPO}/releases/tag/" + tag,
             "assets": [{"name": n, "size": 10, "browser_download_url": f"{BASE[:-7]}{tag}/{n}"} for n in names]}
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
        self.assertEqual(updater.pick_assets(names, "windows", "0.2.0"), (WIN, WIN + ".sha256"))
        self.assertEqual(updater.pick_assets(names, "macos", "0.2.0"), (MAC, MAC + ".sha256"))
        self.assertIsNone(updater.pick_assets(names, None, "0.2.0"))
        self.assertIsNone(updater.pick_assets([{"name": WIN}], "windows", "0.2.0"))   # no checksum, no update
        self.assertIsNone(updater.pick_assets([{"name": "evil/../" + WIN}], "windows", "0.2.0"))
        # the installer's version must be the tag's: a leftover 0.9.9 installer in a v0.2.0 release is not offered
        old = [{"name": n} for n in ("PageTide_0.9.9_x64-setup.exe", "PageTide_0.9.9_x64-setup.exe.sha256")]
        self.assertIsNone(updater.pick_assets(old, "windows", "0.2.0"))
        self.assertEqual(updater.platform_key("win32"), "windows")
        self.assertEqual(updater.platform_key("darwin", "arm64"), "macos")
        self.assertEqual(updater.platform_key("darwin", "x86_64"), "macos-x64")   # Intel Macs (CI-built since 2026-10-25)
        self.assertIsNone(updater.platform_key("darwin", "ppc"))
        self.assertIsNone(updater.platform_key("linux"))
        intel = [{"name": n} for n in (MAC, MAC + ".sha256", MAC_X64, MAC_X64 + ".sha256")]
        self.assertEqual(updater.pick_assets(intel, "macos-x64", "0.2.0"), (MAC_X64, MAC_X64 + ".sha256"))
        self.assertEqual(updater.pick_assets(intel, "macos", "0.2.0"), (MAC, MAC + ".sha256"))
        self.assertIsNone(updater.pick_assets([{"name": MAC}, {"name": MAC + ".sha256"}], "macos-x64", "0.2.0"))


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.clock = Clock()
        updater.reset_runtime_state()

    def make(self, transport, version="0.1.0", platform="darwin", machine="arm64"):
        return updater.Updater(self.data, version, transport, platform=platform, machine=machine, clock=self.clock)

    def test_a_development_build_never_checks_or_updates_itself(self):
        transport = FakeTransport(release())
        with mock.patch.dict(os.environ, {"PAGETIDE_CHANNEL": "dev"}):
            result = self.make(transport, "0.1.0").check(force=True)
        self.assertEqual((result["status"], result["reason_code"], result["available"]), ("disabled", "dev_build", False))
        self.assertEqual(transport.requests, [])

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
        self.assertTrue(result["html_url"].startswith(f"https://github.com/{updater.REPO}/"))
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
        # another tag of the same repository, or a different file name, is not this release's asset either
        for url in (BASE.replace("v0.2.0", "v0.1.0") + MAC, BASE + "other.zip", BASE + "x/../" + MAC):
            odd = release()
            odd["assets"][2]["browser_download_url"] = url
            (self.data / updater.CACHE_NAME).unlink(missing_ok=True)
            self.assertFalse(self.make(FakeTransport(odd)).check(force=True)["available"], url)

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
        checker.check(force=True)   # asking explicitly brings the strip back
        self.assertFalse(checker.check()["dismissed"])
        checker.dismiss("0.2.0")
        newer = self.make(FakeTransport(release("v0.3.0", names=("PageTide_0.3.0_x64-setup.exe", "PageTide_0.3.0_x64-setup.exe.sha256", MAC, MAC + ".sha256"))))
        newer.check(force=True)
        self.assertFalse(newer.check()["dismissed"])
        with self.assertRaises(updater.UpdateError):
            checker.dismiss("../x")

    def test_default_transport_user_agent_has_only_app_name_and_version(self):
        self.assertEqual(updater.Transport("0.1.0").user_agent, "PageTide/0.1.0")


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
                checker._download_verified(name, {"url": BASE + name}, {"url": BASE + name + ".sha256"}, "0.2.0")

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

    def test_windows_apply_arms_the_installer_itself_and_it_starts_only_after_the_quit(self):
        checker = self.checker()
        checker.start_download(run_async=False)
        started = []
        self.assertEqual(checker.apply()["mode"], "installer")
        self.assertEqual(started, [])   # nothing runs while the app is still open
        self.assertTrue(updater.run_pending(popen=lambda command, **kw: started.append((command, kw)), platform="win32"))
        command, options = started[0]
        self.assertEqual(command, [str(self.data / "updates" / WIN)])
        self.assertTrue(options["creationflags"] & 0x08 and options["creationflags"] & 0x200)   # DETACHED_PROCESS | NEW_PROCESS_GROUP
        self.assertTrue(options["close_fds"])
        self.assertFalse(updater.run_pending(popen=lambda *a, **k: started.append(1)))   # consumed
        self.assertEqual(len(started), 1)

    def test_cancel_forgets_the_armed_update(self):
        checker = self.checker()
        checker.start_download(run_async=False)
        checker.apply()
        checker.cancel()
        self.assertFalse(updater.run_pending(popen=lambda *a, **k: self.fail("cancelled update must not start")))

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
        self.old, self.new = self.root / "apps" / "PageTide.app", self.root / "new" / "PageTide.app"
        for app, text in ((self.old, "old"), (self.new, "new")):
            (app / "Contents").mkdir(parents=True)
            (app / "Contents" / "version").write_text(text)
        self.log, self.opened, self.result = self.root / "log", self.root / "opened", self.root / "result"
        self.fake_open = self.root / "open.sh"
        self.fake_open.write_text(f'#!/bin/sh\necho "$1" > "{self.opened}"\n')
        self.fake_open.chmod(0o755)

    def run_script(self, pid, new=None, env=None):
        return subprocess.run(["/bin/sh", str(self.script), str(pid), str(self.old), str(new or self.new), str(self.log), str(self.fake_open), str(self.result)],
                              timeout=60, capture_output=True, env=env)

    def test_replaces_the_app_after_the_process_ended_and_reopens_it(self):
        done = subprocess.Popen(["/usr/bin/true"])
        done.wait()
        self.run_script(done.pid)
        self.assertEqual((self.old / "Contents" / "version").read_text(), "new")
        self.assertEqual(self.opened.read_text().strip(), str(self.old))
        self.assertEqual([p.name for p in self.old.parent.iterdir()], ["PageTide.app"])   # no backup or stage left
        self.assertEqual(self.result.read_text().strip(), "ok")

    def test_missing_new_app_leaves_the_old_one_untouched_and_still_reopens_it(self):
        done = subprocess.Popen(["/usr/bin/true"])
        done.wait()
        self.run_script(done.pid, new=self.root / "missing.app")
        self.assertEqual((self.old / "Contents" / "version").read_text(), "old")
        self.assertEqual([p.name for p in self.old.parent.iterdir()], ["PageTide.app"])
        self.assertEqual(self.opened.read_text().strip(), str(self.old))
        self.assertEqual(self.result.read_text().strip(), "failed")

    def fake_mv(self, fail_on):
        """A PATH directory whose mv refuses the given source names (the script calls plain `mv`)."""
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        conditions = " ".join(f'*"{name}"*) exit 1;;' for name in fail_on)
        (bin_dir / "mv").write_text(f'#!/bin/sh\ncase "$1" in {conditions} esac\nexec /bin/mv "$@"\n')
        (bin_dir / "mv").chmod(0o755)
        return {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}

    def test_failed_swap_rolls_back_to_the_old_app_and_reports_failure(self):
        done = subprocess.Popen(["/usr/bin/true"])
        done.wait()
        self.run_script(done.pid, env=self.fake_mv([".PageTide-update-new."]))   # mv STAGE -> OLD fails
        self.assertEqual((self.old / "Contents" / "version").read_text(), "old")
        self.assertEqual([p.name for p in self.old.parent.iterdir()], ["PageTide.app"])
        self.assertEqual(self.result.read_text().strip(), "failed")
        self.assertEqual(self.opened.read_text().strip(), str(self.old))

    def test_failed_rollback_is_reported_with_the_backup_path(self):
        done = subprocess.Popen(["/usr/bin/true"])
        done.wait()
        self.run_script(done.pid, env=self.fake_mv([".PageTide-update-new.", ".PageTide-update-old."]))
        report = self.result.read_text().strip()
        self.assertTrue(report.startswith("rollback-failed "), report)
        backup = Path(report.split(" ", 1)[1])
        self.assertTrue(backup.name.startswith(".PageTide-update-old."))
        self.assertEqual((backup / "Contents" / "version").read_text(), "old")   # the old app is kept, not deleted

    def test_waits_for_the_running_app_before_touching_anything(self):
        sleeper = subprocess.Popen(["/bin/sleep", "1.5"])
        script = subprocess.Popen(["/bin/sh", str(self.script), str(sleeper.pid), str(self.old), str(self.new), str(self.log), str(self.fake_open), str(self.result)])
        try:
            threading.Event().wait(0.5)
            self.assertEqual((self.old / "Contents" / "version").read_text(), "old")
        finally:
            sleeper.wait()
            script.wait(timeout=30)
        self.assertEqual((self.old / "Contents" / "version").read_text(), "new")


def make_app(path, version, name="PageTide.app"):
    app = Path(path) / name
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "bin").write_text("x")
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleShortVersionString": version}))
    return app


class ResultAndCleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        (self.data / "updates").mkdir()
        updater.reset_runtime_state()
        self.opened = []
        self.checker = updater.Updater(self.data, "0.1.0", FakeTransport(release()), platform="darwin", machine="arm64",
                                       popen=lambda command, **kw: self.opened.append(command))

    def test_failed_replacement_is_reported_once_and_shows_the_zip(self):
        (self.data / "updates" / MAC).write_bytes(b"z")
        (self.data / "updates" / "result").write_text("failed\n")
        self.assertEqual(self.checker.take_result(), "failed")
        self.assertEqual(self.opened, [["/usr/bin/open", "-R", str(self.data / "updates" / MAC)]])
        self.assertIsNone(self.checker.take_result())

    def test_failed_rollback_shows_the_backup_and_only_a_backup(self):
        backup = self.data / "apps" / ".PageTide-update-old.123"
        backup.mkdir(parents=True)
        (self.data / "updates" / "result").write_text(f"rollback-failed {backup}\n")
        self.assertEqual(self.checker.take_result(), "rollback_failed")
        self.assertEqual(self.opened, [["/usr/bin/open", "-R", str(backup)]])
        (self.data / "updates" / "result").write_text(f"rollback-failed {self.data}\n")   # not one of our backups
        self.checker.take_result()
        self.assertEqual(len(self.opened), 1)

    def test_success_and_missing_result_report_nothing(self):
        self.assertIsNone(self.checker.take_result())
        (self.data / "updates" / "result").write_text("ok\n")
        self.assertIsNone(self.checker.take_result())
        self.assertEqual(self.opened, [])

    def test_result_is_part_of_the_check_response_over_the_server(self):
        (self.data / "updates" / "result").write_text("failed\n")
        with patch.dict(os.environ, {"PAGETIDE_DATA": str(self.data), "PAGETIDE_APP_VERSION": "0.1.0"}), \
                patch.object(server.updater, "Transport", lambda version: FakeTransport(release())):
            httpd = server.build_server(port=0, root=str(ROOT))
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            self.addCleanup(httpd.server_close)
            self.addCleanup(httpd.shutdown)
            with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_port}/api/update") as response:
                self.assertEqual(json.load(response)["apply_result"], "failed")

    def test_startup_cleanup_empties_updates_once_the_version_is_reached_but_keeps_log_and_result(self):
        updates = self.data / "updates"
        for name in (WIN, "version", "apply-update.log", "result", "apply-update.sh"):
            (updates / name).write_text("0.2.0" if name == "version" else "x")
        (updates / "extracted" / "A.app").mkdir(parents=True)
        updater.Updater(self.data, "0.1.0").startup_cleanup()   # still older: the download is needed
        self.assertTrue((updates / WIN).exists())
        updater.Updater(self.data, "0.2.0").startup_cleanup()
        self.assertEqual(sorted(p.name for p in updates.iterdir()), ["apply-update.log", "result"])
        updater.Updater(self.data, "0.1.0").startup_cleanup()   # nothing to do, no error
        updater.Updater(self.data / "missing", "0.1.0").startup_cleanup()

    def test_no_asset_for_intel_macs_has_its_own_reason(self):
        intel = updater.Updater(self.data, "0.1.0", FakeTransport(release()), platform="darwin", machine="x86_64")
        result = intel.check()
        self.assertEqual((result["status"], result["available"], result["reason_code"]), ("ok", False, "no_asset"))
        both = release(names=(WIN, WIN + ".sha256", MAC, MAC + ".sha256", MAC_X64, MAC_X64 + ".sha256"))
        (self.data / updater.CACHE_NAME).unlink(missing_ok=True)
        offered = updater.Updater(self.data, "0.1.0", FakeTransport(both), platform="darwin", machine="x86_64").check(force=True)
        self.assertEqual((offered["available"], offered["asset"]), (True, MAC_X64))


@unittest.skipUnless(sys.platform == "darwin", "macOS bundle handling")
class MacosApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        updater.reset_runtime_state()

    def zip_of(self, version):
        source = self.root / "zipsrc"
        shutil_rmtree(source)
        make_app(source, version)
        archive = self.root / "payload.zip"
        subprocess.run(["/usr/bin/ditto", "-c", "-k", "--keepParent", str(source / "PageTide.app"), str(archive)], check=True)
        return archive.read_bytes()

    def checker(self, version, executable, opened=None):
        payload = self.zip_of(version)
        files = {BASE + MAC: payload, BASE + MAC + ".sha256": (hashlib.sha256(payload).hexdigest() + "  " + MAC + "\n").encode()}
        return updater.Updater(self.root / "data", "0.1.0", FakeTransport(release(), files=files), platform="darwin", machine="arm64",
                               executable=str(executable), popen=lambda command, **kw: (opened if opened is not None else []).append(command))

    def test_current_app_bundle_is_the_enclosing_app(self):
        installed = make_app(self.root / "Applications", "0.1.0")
        binary = installed / "Contents" / "Resources" / "backend" / "pagetide-server"
        binary.parent.mkdir(parents=True)
        binary.write_text("x")
        self.assertEqual(updater.Updater(self.root, "0.1.0", executable=str(binary)).current_app_bundle(), installed.resolve())
        self.assertIsNone(updater.Updater(self.root, "0.1.0", executable="/usr/bin/python3").current_app_bundle())

    def test_writable_app_is_replaced_by_the_armed_script_after_the_quit(self):
        installed = make_app(self.root / "Applications", "0.1.0")
        (installed / "Contents" / "marker").write_text("old")
        binary = installed / "Contents" / "Resources" / "backend" / "server"
        binary.parent.mkdir(parents=True)
        binary.write_text("x")
        checker = self.checker("0.2.0", binary)
        checker.start_download(run_async=False)
        self.assertEqual(updater.download_state()["state"], "ready")
        self.assertEqual(checker.apply()["mode"], "restart")
        started = []
        self.assertTrue(updater.run_pending(popen=lambda command, **kw: started.append((command, kw))))
        command, options = started[0]
        self.assertTrue(options["start_new_session"])
        done = subprocess.Popen(["/usr/bin/true"])
        done.wait()
        opener = self.root / "open.sh"
        opener.write_text(f'#!/bin/sh\necho "$1" > "{self.root / "opened"}"\n')
        opener.chmod(0o755)
        command[2], command[6] = str(done.pid), str(opener)   # a pid that already ended; a harmless "open"
        subprocess.run(command, check=True, timeout=60)
        self.assertEqual(plistlib.loads((installed.resolve() / "Contents" / "Info.plist").read_bytes())["CFBundleShortVersionString"], "0.2.0")
        self.assertFalse((installed.resolve() / "Contents" / "marker").exists())
        self.assertEqual((self.root / "data" / "updates" / "result").read_text().strip(), "ok")
        self.assertEqual((self.root / "opened").read_text().strip(), str(installed.resolve()))

    def test_package_with_another_version_than_the_release_is_refused(self):
        installed = make_app(self.root / "Applications", "0.1.0")
        checker = self.checker("0.9.0", installed / "Contents" / "MacOS" / "bin")
        checker.start_download(run_async=False)
        with self.assertRaises(updater.UpdateError) as caught:
            checker.apply()
        self.assertIn("版本", str(caught.exception))
        self.assertFalse(updater.run_pending(popen=lambda *a, **k: self.fail("must not start")))


def shutil_rmtree(path):
    import shutil
    shutil.rmtree(path, ignore_errors=True)


class FakeResponse:
    def __init__(self, data, length=None):
        self.data, self.headers = data, {"Content-Length": str(len(data) if length is None else length)}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        chunk, self.data = (self.data[:size], self.data[size:]) if size >= 0 else (self.data, b"")
        return chunk


class NetworkGuardTests(unittest.TestCase):
    def test_redirects_leaving_github_are_refused(self):
        handler = updater._GithubRedirects()
        request = urllib.request.Request(f"https://github.com/{updater.REPO}/releases/download/v1.0.0/a")
        for target in ("https://evil.example/a", "http://github.com/a", "https://github.com.evil.example/a", "https://notgithub.com/a",
                       "file:///etc/passwd"):
            with self.assertRaises(urllib.error.URLError, msg=target):
                handler.redirect_request(request, None, 302, "Found", {}, target)
        for target in ("https://github.com/a", "https://objects.githubusercontent.com/a", "https://release-assets.githubusercontent.com/a"):
            self.assertIsNotNone(handler.redirect_request(request, None, 302, "Found", {}, target), target)

    def test_json_and_asset_size_caps(self):
        transport = updater.Transport("0.1.0")
        with patch.object(transport, "_open", lambda *a: FakeResponse(b"x" * 11)):
            with self.assertRaises(updater.UpdateError):
                transport.get_bytes("https://api.github.com/x", max_bytes=10)
            self.assertEqual(transport.get_bytes("https://api.github.com/x", max_bytes=11), b"x" * 11)
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(updater.UpdateError):
                    transport.download("https://github.com/x", Path(tmp) / "a", max_bytes=10)
                transport.download("https://github.com/x", Path(tmp) / "b", max_bytes=11)
                self.assertEqual((Path(tmp) / "b").stat().st_size, 11)

    def test_oversized_download_leaves_nothing_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            updater.reset_runtime_state()

            class Big(FakeTransport):
                def download(self, url, destination, progress=None):
                    Path(destination).write_bytes(b"x")
                    raise updater.UpdateError("download too large")
            files = {BASE + WIN + ".sha256": (("0" * 64) + "\n").encode()}
            checker = updater.Updater(tmp, "0.1.0", Big(release(), files=files), platform="win32")
            checker.start_download(run_async=False)
            self.assertEqual(updater.download_state()["state"], "error")
            self.assertEqual(list((Path(tmp) / "updates").iterdir()), [])


class DesktopHandoffOrderTests(unittest.TestCase):
    def test_update_helper_starts_before_workers_stop_and_the_server_shuts_down(self):
        from app import desktop
        calls = []

        class Httpd:
            def shutdown(self):
                calls.append("shutdown")
        with patch.object(desktop.updater, "run_pending", lambda: calls.append("run_pending")), \
                patch.object(desktop, "stop_organization_workers", lambda: calls.append("stop_workers")):
            desktop.on_parent_gone(Httpd())
        self.assertEqual(calls, ["run_pending", "stop_workers", "shutdown"])


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
        patcher = patch.dict(os.environ, {"PAGETIDE_DATA": self.tmp.name, "PAGETIDE_APP_VERSION": "0.1.0"})
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
            os.environ.pop("PAGETIDE_APP_VERSION")
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
