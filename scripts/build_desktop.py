import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "src-tauri" / "resources"
SERVER_DIR = RESOURCES / "paperdighelper-server"


def main():
    if RESOURCES.exists():
        shutil.rmtree(RESOURCES)
    SERVER_DIR.mkdir(parents=True)
    subprocess.run(
        [
            str(ROOT / ".local" / "desktop-build-env" / "bin" / "python"),
            "-m", "PyInstaller",
            "--noconfirm",
            "--onedir",
            "--name",
            "paperdighelper-server",
            "--distpath", str(ROOT / ".local" / "desktop-dist"),
            "--workpath", str(ROOT / ".local" / "desktop-work"),
            "--specpath", str(ROOT / ".local"),
            "--add-data",
            f"{ROOT / 'app' / 'static'}:app/static",
            "--add-data",
            f"{ROOT / 'harness' / 'budget.json'}:harness",
            "--add-data",
            f"{ROOT / 'harness' / 'seeds.json'}:harness",
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
