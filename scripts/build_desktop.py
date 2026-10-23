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
    """PDH_BUILD_PYTHON wins; else the local macOS build venv when present; else this interpreter."""
    configured = os.environ.get("PDH_BUILD_PYTHON")
    if configured:
        return configured
    venv = ROOT / ".local" / "desktop-build-env" / "bin" / "python"
    return str(venv) if sys.platform == "darwin" and venv.exists() else sys.executable


def main():
    if RESOURCES.exists():
        shutil.rmtree(RESOURCES)
    SERVER_DIR.mkdir(parents=True)
    subprocess.run(
        [
            build_python(),
            "-m", "PyInstaller",
            "--noconfirm",
            "--onedir",
            "--name",
            "paperdighelper-server",
            "--distpath", str(ROOT / ".local" / "desktop-dist"),
            "--workpath", str(ROOT / ".local" / "desktop-work"),
            "--specpath", str(ROOT / ".local"),
            "--add-data",
            f"{ROOT / 'app' / 'static'}{SEP}app/static",
            "--add-data",
            f"{ROOT / 'harness' / 'budget.json'}{SEP}harness",
            "--add-data",
            f"{ROOT / 'harness' / 'seeds.json'}{SEP}harness",
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
