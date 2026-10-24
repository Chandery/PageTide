import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "src-tauri" / "resources"
SERVER_DIR = RESOURCES / "paperdighelper-server"
SEP = os.pathsep  # --add-data SRC<sep>DEST: ':' on macOS/Linux, ';' on Windows (drive letters contain ':')


def build_python():
    """PDH_BUILD_PYTHON wins. On macOS the pinned local build venv is required (a silent fallback to
    some other interpreter could ship a differently-built backend). Elsewhere: this interpreter."""
    configured = os.environ.get("PDH_BUILD_PYTHON")
    if configured:
        return configured
    if sys.platform == "darwin":
        venv = ROOT / ".local" / "desktop-build-env" / "bin" / "python"
        if not venv.exists():
            raise SystemExit(f"Missing {venv}; create the build env or set PDH_BUILD_PYTHON to the interpreter to use.")
        return str(venv)
    return sys.executable


def python_options():
    """Windows only: UTF-8 mode in the frozen exe. The bootloader does not honour PYTHONUTF8, so text files
    were decoded with the cp1252 code page. PyInstaller 6.16 accepts `--python-option "X utf8"` (checked with
    makespec). macOS is left as built before: its locale is already UTF-8."""
    return ["--python-option", "X utf8"] if sys.platform == "win32" else []


def main():
    python = build_python()   # fail before deleting the previous resources
    if RESOURCES.exists():
        shutil.rmtree(RESOURCES)
    SERVER_DIR.mkdir(parents=True)
    subprocess.run(
        [
            python,
            "-m", "PyInstaller",
            "--noconfirm",
            "--onedir",
            *python_options(),
            "--name",
            "paperdighelper-server",
            "--distpath", str(ROOT / ".local" / "desktop-dist"),
            "--workpath", str(ROOT / ".local" / "desktop-work"),
            "--specpath", str(ROOT / ".local"),
            "--add-data",
            f"{ROOT / 'app' / 'static'}{SEP}app/static",
            "--add-data",
            f"{ROOT / 'harness' / 'budget.json'}{SEP}harness",
            "--paths",
            str(ROOT),
            str(ROOT / "scripts" / "server_entry.py"),
        ],
        cwd=ROOT,
        check=True,
    )
    built = ROOT / ".local" / "desktop-dist" / "paperdighelper-server"
    shutil.copytree(built, SERVER_DIR, dirs_exist_ok=True)
    print(f"Prepared {SERVER_DIR}")


if __name__ == "__main__":
    main()
