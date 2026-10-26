"""Every stylesheet closes each block it opens: one unclosed `{` silently swallows every rule after it (2026-10-26: the
manage-project page lost its red delete button and keyword styles that way)."""
import pathlib
import re
import unittest

STATIC = pathlib.Path(__file__).resolve().parents[1] / "app" / "static"


class CssBalanceTests(unittest.TestCase):
    def test_braces_balance_in_every_stylesheet(self):
        for path in sorted(STATIC.rglob("*.css")):
            if "vendor" in path.parts:
                continue
            text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
            depth = 0
            for char in text:
                depth += (char == "{") - (char == "}")
                self.assertGreaterEqual(depth, 0, path.name)
            self.assertEqual(depth, 0, path.name)

    def test_no_media_block_opens_inside_another_by_accident(self):
        for path in sorted(STATIC.glob("*.css")):
            self.assertNotRegex(path.read_text(encoding="utf-8"), r"@media\([^)]*\)\{@media", path.name)


if __name__ == "__main__":
    unittest.main()
