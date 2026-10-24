"""The product is called PageTide: the old name must not remain in shipped code, packaging or the web UI.

Scope: app/, scripts/, src-tauri sources and manifests, .github and app/static. The only allowed trace is the GitHub
repository address in app/updater.py (the repository is renamed later; change that one line then). Historical
records (changes/, docs/evidence/, past ADRs, HANDOFF entries) are facts of their time and are not scanned.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_NAME = re.compile(r"paper[-_ ]?dig[-_ ]?helper", re.IGNORECASE)
TEXT = {".py", ".js", ".cjs", ".html", ".css", ".json", ".toml", ".rs", ".yml", ".yaml", ".svg", ".md", ".txt", ".cfg", ".lock"}
ALLOWED_LINE = ('app/updater.py', 'REPO = "Chandery/PaperDigHelper"')


def scanned_files():
    roots = [ROOT / "app", ROOT / "scripts", ROOT / "src-tauri" / "src", ROOT / ".github"]
    files = [path for base in roots for path in base.rglob("*") if path.is_file()]
    files += [ROOT / "src-tauri" / name for name in ("Cargo.toml", "Cargo.lock", "tauri.conf.json", "build.rs")]
    files += [ROOT / name for name in ("package.json", "package-lock.json")]
    return [p for p in files if p.suffix in TEXT and "__pycache__" not in p.parts and p.exists()]


class BrandNameTests(unittest.TestCase):
    def test_old_name_is_gone_from_shipped_files(self):
        found = []
        for path in scanned_files():
            relative = path.relative_to(ROOT).as_posix()
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if OLD_NAME.search(line) and not (relative == ALLOWED_LINE[0] and line.strip() == ALLOWED_LINE[1]):
                    found.append(f"{relative}:{number}: {line.strip()[:100]}")
        self.assertEqual(found, [], "old product name found:\n" + "\n".join(found))

    def test_bundle_identity(self):
        import json
        config = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
        self.assertEqual(config["productName"], "PageTide")
        self.assertEqual(config["identifier"], "com.pagetide.desktop")
        self.assertEqual(config["bundle"]["resources"], {"resources/pagetide-server/": "backend/"})

    def test_page_titles_and_header_use_the_new_name(self):
        static = ROOT / "app" / "static"
        for page in sorted(static.glob("*.html")):
            text = page.read_text(encoding="utf-8")
            self.assertIn("PageTide", re.search(r"<title>(.*?)</title>", text, re.S).group(1) if "<title>" in text else "PageTide", page.name)
        index = (static / "index.html").read_text(encoding="utf-8")
        self.assertIn('<img class="wordmark" src="/wordmark.png" alt="PageTide">', index)
        self.assertNotIn("brand-mark", index)
        for name in ("wordmark.png", "wordmark-dark.png", "favicon.png"):
            self.assertTrue((static / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
