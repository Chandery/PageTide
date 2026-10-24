"""Update check and installer hand-off (ADR 0041). No model call, no tokens.

The only network access is to GitHub: the public "latest release" JSON of this repository and the two assets
(installer + .sha256) of that release. Nothing about the user, library or machine is sent (the User-Agent is the app
name and version, no credentials). A source run without PAGETIDE_APP_VERSION is a development build and never checks.

Applying an update never happens while the app is still running: `arm_pending` only records what to do, and the
desktop backend calls `run_pending` after its HTTP server has stopped (the shell closes its stdin on quit). That
starts the installer (Windows) or a detached script that waits for the shell process to end and then replaces the
.app (macOS). Only a file that was downloaded into <data>/updates/ and passed its SHA-256 check is used. The SHA-256
file proves the download is complete and is the one the release published; it does not prove who published it
(the builds are unsigned, an accepted risk, ADR 0041)."""
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# The GitHub repository releases are read from. The only place the repository name appears in code; the repository is
# still called by its old name and is renamed later: change this one line (and docs/RELEASE.md) after the rename.
REPO = "Chandery/PageTide"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
REDIRECT_HOSTS = ("github.com", "githubusercontent.com")   # release assets redirect to *.githubusercontent.com
CACHE_NAME = "update-check.json"
CACHE_SECONDS = 6 * 3600
FAILURE_RETRY_SECONDS = 15 * 60       # a failed check is not repeated on every page load
MAX_JSON_BYTES = 1_000_000
MAX_ASSET_BYTES = 600 * 1024 * 1024
PENDING_SECONDS = 10 * 60             # an armed update that was not followed by a quit within this time is dropped

TAG = re.compile(r"^v(\d{1,4})\.(\d{1,4})\.(\d{1,4})$")
MACOS_ASSETS = {"macos": "PageTide-macos-arm64.zip", "macos-x64": "PageTide-macos-x64.zip"}
SAFE_ASSET = re.compile(r"^PageTide[A-Za-z0-9._-]{0,80}$")
KEEP_IN_UPDATES = ("apply-update.log", "result")
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def parse_version(text):
    """(major, minor, patch) from "0.1.2" or "v0.1.2"; None for anything else (pre-release tags included)."""
    match = re.fullmatch(r"v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})", str(text or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def platform_key(platform=None, machine=None):
    """"windows" (x64 builds only exist), "macos" (Apple silicon), "macos-x64" (Intel) or None for any other system.
    An Intel build running under Rosetta reports x86_64 and so keeps getting the Intel build it has."""
    platform = sys.platform if platform is None else platform
    if platform == "win32":
        return "windows"
    if platform == "darwin":
        import platform as platform_module
        machine = platform_module.machine() if machine is None else machine
        return {"arm64": "macos", "x86_64": "macos-x64"}.get(machine)
    return None


def installer_name(key, version):
    """The one installer file name a release of `version` must have for this system."""
    if key == "windows":
        return f"PageTide_{version}_x64-setup.exe"
    return MACOS_ASSETS.get(key)


def pick_assets(assets, key, version):
    """(installer name, its .sha256 name) when the release has exactly the expected installer and checksum, else None."""
    names = {asset.get("name") for asset in assets if isinstance(asset, dict)}
    installer = installer_name(key, version)
    if installer and installer in names and installer + ".sha256" in names:
        return installer, installer + ".sha256"
    return None


def auto_check_enabled(data_dir):
    try:
        values = json.loads((Path(data_dir) / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return not (isinstance(values, dict) and values.get("autoCheckUpdates") is False)


class UpdateError(Exception):
    """A message that is safe to show to the user."""


class _GithubRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from urllib.parse import urlparse
        parsed = urlparse(newurl)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or not any(host == h or host.endswith("." + h) for h in REDIRECT_HOSTS):
            raise urllib.error.URLError("redirect outside GitHub refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Transport:
    """The real network seam. Tests pass a fake with the same two methods; no test reaches the network."""

    def __init__(self, version):
        self.user_agent = f"PageTide/{version}"

    def _open(self, url, accept, timeout):
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": accept})
        return urllib.request.build_opener(_GithubRedirects).open(request, timeout=timeout)

    def get_bytes(self, url, max_bytes=MAX_JSON_BYTES, accept="application/vnd.github+json"):
        with self._open(url, accept, 10) as response:
            data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise UpdateError("response too large")
        return data

    def download(self, url, destination, progress=None, max_bytes=MAX_ASSET_BYTES):
        received = 0
        with self._open(url, "application/octet-stream", 30) as response, open(destination, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > max_bytes:
                    raise UpdateError("download too large")
                out.write(chunk)
                if progress:
                    progress(received, total)


_state_lock = threading.Lock()
_download = {"state": "idle"}
_pending = {}


def reset_runtime_state():
    with _state_lock:
        _download.clear()
        _download["state"] = "idle"
        _pending.clear()


def download_state():
    with _state_lock:
        return {key: value for key, value in _download.items() if key in ("state", "received", "total", "message", "version")}


class Updater:
    def __init__(self, data_dir, version, transport=None, platform=None, machine=None, clock=time.time,
                 runner=subprocess.run, popen=subprocess.Popen, executable=None):
        self.data_dir = Path(data_dir)
        self.version = version or None
        self.current = parse_version(version)
        self.transport = transport or Transport(version or "dev")
        self.key = platform_key(platform, machine)
        self.platform = sys.platform if platform is None else platform
        self.clock = clock
        self.runner, self.popen = runner, popen
        self.executable = executable or sys.executable

    # ------------------------------------------------------------------ cache
    @property
    def cache_path(self):
        return self.data_dir / CACHE_NAME

    def _read_cache(self):
        try:
            value = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write_cache(self, cache):
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            temporary = self.cache_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, self.cache_path)
        except OSError:
            pass   # a cache that cannot be written only means the next check asks again

    def _fresh(self, stamp, seconds):
        # A timestamp in the future (clock change) is stale; a couple of seconds of skew is tolerated.
        return isinstance(stamp, (int, float)) and -2 <= self.clock() - stamp < seconds

    @staticmethod
    def _release_from_json(raw):
        if not isinstance(raw, dict) or raw.get("draft") or raw.get("prerelease"):
            return None
        version = parse_version(raw.get("tag_name")) if TAG.match(str(raw.get("tag_name") or "")) else None
        if not version:
            return None
        assets = {}
        for asset in raw.get("assets") or []:
            if not isinstance(asset, dict) or not isinstance(asset.get("name"), str):
                continue
            url = asset.get("browser_download_url")
            if isinstance(url, str) and SAFE_ASSET.match(asset["name"]) and url == f"{DOWNLOAD_PREFIX}{raw['tag_name']}/{asset['name']}":
                assets[asset["name"]] = {"url": url, "size": asset.get("size") if isinstance(asset.get("size"), int) else 0}
        notes = re.sub(r"\s+", " ", str(raw.get("body") or "")).strip()
        html_url = raw.get("html_url")
        return {"tag": raw["tag_name"], "version": ".".join(map(str, version)), "notes": notes[:400], "assets": assets,
                "html_url": html_url if isinstance(html_url, str) and html_url.startswith(f"https://github.com/{REPO}/") else ""}

    def _latest(self, force, network=True):
        cache = self._read_cache()
        release = cache.get("release")
        if not network:   # switch off: only what an explicit check already stored, never a request
            return release if isinstance(release, dict) else None
        if not force and isinstance(release, dict) and self._fresh(cache.get("checked_at"), CACHE_SECONDS):
            return release
        if not force and self._fresh(cache.get("failed_at"), FAILURE_RETRY_SECONDS):
            return release if isinstance(release, dict) else None
        try:
            release = self._release_from_json(json.loads(self.transport.get_bytes(LATEST_URL)))
            if release is None:
                raise ValueError("no usable release")
        except (OSError, ValueError, UpdateError):   # URLError, timeouts and bad JSON: stay silent
            cache["failed_at"] = self.clock()
            self._write_cache(cache)
            return cache.get("release") if isinstance(cache.get("release"), dict) else None
        cache.update({"release": release, "checked_at": self.clock()})
        cache.pop("failed_at", None)
        self._write_cache(cache)
        return release

    # ------------------------------------------------------------------ check
    def check(self, force=False):
        """{status: ok|unknown|disabled, reason_code, current, latest, available, notes, asset, html_url, dismissed}.
        `force` is the user pressing "check now": it skips the cache and the automatic-check switch."""
        result = {"status": "disabled", "reason_code": None, "current": self.version, "latest": None, "available": False,
                  "notes": "", "asset": None, "html_url": "", "dismissed": False}
        if not self.version:
            return {**result, "reason_code": "dev_build"}
        if not self.current:
            return {**result, "reason_code": "invalid_version"}
        network = force or auto_check_enabled(self.data_dir)
        release = self._latest(force, network)
        if force and release:
            cache = self._read_cache()
            if cache.pop("dismissed", None) is not None:   # asking explicitly brings the strip back
                self._write_cache(cache)
        if not release:
            if not network:
                return {**result, "reason_code": "auto_check_off"}
            return {**result, "status": "unknown", "reason_code": "check_failed"}
        latest = parse_version(release["version"])
        result.update(status="ok", latest=release["version"], notes=release.get("notes", ""), html_url=release.get("html_url", ""))
        if latest <= self.current:
            return {**result, "reason_code": "up_to_date"}
        picked = pick_assets([{"name": name} for name in release["assets"]], self.key, release["version"])
        if not picked:
            return {**result, "reason_code": "no_asset"}   # newer, but no installer for this system (yet)
        result.update(available=True, asset=picked[0], dismissed=self._read_cache().get("dismissed") == release["version"])
        return result

    def dismiss(self, version):
        if parse_version(version) is None:
            raise UpdateError("invalid version")
        cache = self._read_cache()
        cache["dismissed"] = ".".join(map(str, parse_version(version)))
        self._write_cache(cache)

    # --------------------------------------------------------------- download
    @property
    def updates_dir(self):
        return self.data_dir / "updates"

    def inside_updates(self, path):
        """True only for a path that resolves to something inside <data>/updates/ (never the directory itself)."""
        try:
            root = self.updates_dir.resolve()
            return root in Path(path).resolve().parents
        except OSError:
            return False

    def start_download(self, run_async=True):
        """Begin downloading the installer of the current check result; the state is polled with `download_state`."""
        with _state_lock:
            if _download.get("state") == "downloading":
                return
            _download.clear()
            _download.update(state="downloading", received=0, total=0, message="")
        worker = threading.Thread(target=self._download_job, daemon=True)
        if run_async:
            worker.start()
        else:
            worker.run()

    def _fail(self, message):
        with _state_lock:
            _download.clear()
            _download.update(state="error", message=message)

    def _download_job(self):
        try:
            info = self.check(force=True)
            if not info["available"]:
                return self._fail("没有可下载的新版本")
            assets = self._read_cache()["release"]["assets"]
            name = info["asset"]
            path = self._download_verified(name, assets[name], assets[name + ".sha256"], info["latest"])
            (self.updates_dir / "version").write_text(info["latest"], encoding="ascii")
            with _state_lock:
                _download.clear()
                _download.update(state="ready", version=info["latest"], path=str(path), sha256=self._sha256(path), name=name)
        except (OSError, ValueError, KeyError, UpdateError) as error:
            self._fail(str(error) if isinstance(error, UpdateError) else "下载失败，请稍后再试")

    @staticmethod
    def _sha256(path):
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _download_verified(self, name, asset, checksum_asset, version):
        if name != os.path.basename(name) or name != installer_name(self.key, version):
            raise UpdateError("安装包名称不符合预期")
        if asset.get("size", 0) > MAX_ASSET_BYTES:
            raise UpdateError("安装包过大")
        directory = self.updates_dir
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)   # keep only the update being installed
        directory.mkdir(parents=True, exist_ok=True)
        target, partial = directory / name, directory / (name + ".part")
        if not self.inside_updates(target) or not self.inside_updates(partial):
            raise UpdateError("下载路径无效")
        try:
            expected = self.transport.get_bytes(checksum_asset["url"], 4096, "application/octet-stream").decode("ascii", "replace").split()
            if not expected or not SHA256.match(expected[0]):
                raise UpdateError("校验文件格式无效")

            def progress(received, total):
                with _state_lock:
                    _download.update(received=received, total=total or asset.get("size", 0))
            self.transport.download(asset["url"], partial, progress)
            if self._sha256(partial) != expected[0].lower():
                raise UpdateError("校验失败，已删除下载的文件")
            os.replace(partial, target)
        except BaseException:
            for leftover in (partial, target):
                try:
                    leftover.unlink()
                except OSError:
                    pass
            raise
        return target

    # ------------------------------------------------------------------ apply
    def current_app_bundle(self):
        """The running .app on macOS (the backend lives in <app>/Contents/Resources/backend/), else None."""
        for parent in Path(self.executable).resolve().parents:
            if parent.suffix == ".app":
                return parent
        return None

    def apply(self):
        """Prepare the hand-off for the verified download. Returns {mode: installer|restart|manual, ...}; for the first
        two the caller must now quit the app (the helper is started when the backend stops, see `run_pending`)."""
        with _state_lock:
            state = dict(_download)
        path = Path(state.get("path") or "")
        if state.get("state") != "ready" or not self.inside_updates(path) or not path.is_file():
            raise UpdateError("没有已下载并校验通过的更新")
        if self._sha256(path) != state.get("sha256"):
            raise UpdateError("文件校验失败，请重新下载")
        script_dir = self.updates_dir
        parent_pid = os.getppid()
        if self.key == "windows":
            # Started by run_pending once the backend stops; the NSIS installer itself checks for the running app.
            self._arm([str(path)])
            return {"mode": "installer", "version": state.get("version")}
        if self.key in MACOS_ASSETS:
            staged = self._stage_macos(path, state.get("version"))
            bundle = self.current_app_bundle()
            if staged and bundle and os.access(bundle.parent, os.W_OK) and os.access(bundle, os.W_OK):
                script = script_dir / "apply-update.sh"
                script.write_text(MACOS_SCRIPT, encoding="ascii")
                self._arm(["/bin/sh", str(script), str(parent_pid), str(bundle), str(staged), str(script_dir / "apply-update.log"),
                           "/usr/bin/open", str(script_dir / "result")])
                return {"mode": "restart", "version": state.get("version")}
            self.reveal(path)
            return {"mode": "manual", "path": str(path), "version": state.get("version")}
        raise UpdateError("当前系统暂不支持自动更新")

    def reveal(self, path):
        try:
            self.popen(["/usr/bin/open", "-R", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def cancel(self):
        """The quit was cancelled (unsaved drafts): forget the armed update so a later ordinary quit does not run it."""
        with _state_lock:
            _pending.clear()

    def take_result(self):
        """What the macOS script reported last time, once: None, "failed" or "rollback_failed". A failure shows the
        downloaded zip (or the backup of the old app when the rollback failed) in Finder for a manual replacement."""
        path = self.updates_dir / "result"
        try:
            text = path.read_text(encoding="utf-8").strip()
            path.unlink()
        except OSError:
            return None
        if text.startswith("rollback-failed"):
            backup = Path(text[len("rollback-failed"):].strip())
            if backup.name.startswith(".PageTide-update-old.") and backup.exists():
                self.reveal(backup)
            return "rollback_failed"
        if text == "failed":
            zips = sorted(self.updates_dir.glob("*.zip"))
            if zips:
                self.reveal(zips[0])
            return "failed"
        return None

    def startup_cleanup(self):
        """Once the running version is at least the downloaded one the installer is no longer needed: empty updates/
        except the script log and result."""
        try:
            downloaded = parse_version((self.updates_dir / "version").read_text(encoding="ascii"))
        except OSError:
            downloaded = None
        if not self.updates_dir.is_dir() or (downloaded and self.current and downloaded > self.current):
            return
        for item in self.updates_dir.iterdir():
            if item.name in KEEP_IN_UPDATES:
                continue
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item, ignore_errors=True)
            else:
                try:
                    item.unlink()
                except OSError:
                    pass

    def _stage_macos(self, archive, version):
        """Unpack the verified zip next to it; the new .app, or None when ditto fails or the archive is not one app.
        An app whose CFBundleShortVersionString is not the release version is refused."""
        target = self.updates_dir / "extracted"
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        try:
            done = self.runner(["/usr/bin/ditto", "-x", "-k", str(archive), str(target)], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=300)
        except (OSError, subprocess.SubprocessError):
            return None
        apps = [item for item in target.iterdir() if item.suffix == ".app"]
        if done.returncode != 0 or len(apps) != 1 or not (apps[0] / "Contents" / "MacOS").is_dir():
            return None
        try:
            with open(apps[0] / "Contents" / "Info.plist", "rb") as handle:
                found = plistlib.load(handle).get("CFBundleShortVersionString")
        except (OSError, ValueError, plistlib.InvalidFileException):
            found = None
        if found != version:
            raise UpdateError("安装包里的版本与发布版本不一致，已拒绝")
        return apps[0]

    def _arm(self, command):
        with _state_lock:
            _pending.clear()
            _pending.update(command=command, armed_at=self.clock())


def run_pending(popen=subprocess.Popen, clock=time.time, platform=None):
    """Start the armed helper, detached. Called once, after the backend stopped serving. Returns whether it started."""
    with _state_lock:
        pending = dict(_pending)
        _pending.clear()
    if not pending or not 0 <= clock() - pending["armed_at"] < PENDING_SECONDS:
        return False
    options = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if (sys.platform if platform is None else platform) == "win32":
        options["creationflags"] = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    try:
        popen(pending["command"], **options)
    except OSError:
        return False
    return True


# Arguments: <pid of the app shell> <current .app> <new .app> <log file> <open command> <result file>.
# The result file says "ok", "failed" or "rollback-failed <backup>"; the next start reads it (take_result).
# The old app is moved aside, never deleted before the new one is in place; any failure puts it back.
MACOS_SCRIPT = r'''#!/bin/sh
PID="$1"; OLD="$2"; NEW="$3"; LOG="$4"; OPEN="$5"; RESULT="$6"
exec >>"$LOG" 2>&1
echo "update started $(date)"
n=0
while kill -0 "$PID" 2>/dev/null; do
  n=$((n+1))
  if [ "$n" -gt 600 ]; then echo "app still running, nothing changed"; exit 1; fi
  sleep 0.1
done
DIR=$(dirname "$OLD")
STAGE="$DIR/.PageTide-update-new.$$"
BACKUP="$DIR/.PageTide-update-old.$$"
if /usr/bin/ditto "$NEW" "$STAGE"; then
  if mv "$OLD" "$BACKUP"; then
    if mv "$STAGE" "$OLD"; then
      /usr/bin/xattr -dr com.apple.quarantine "$OLD"
      rm -rf "$BACKUP"
      echo "replaced"
      echo ok > "$RESULT"
    else
      echo "replace failed, restoring the old app"
      rm -rf "$STAGE"
      if mv "$BACKUP" "$OLD"; then
        echo failed > "$RESULT"
      else
        echo "rollback failed, the old app is at $BACKUP"
        echo "rollback-failed $BACKUP" > "$RESULT"
      fi
    fi
  else
    echo "could not move the old app aside, nothing changed"
    rm -rf "$STAGE"
    echo failed > "$RESULT"
  fi
else
  echo "copy failed, nothing changed"
  rm -rf "$STAGE"
  echo failed > "$RESULT"
fi
"$OPEN" "$OLD"
'''
