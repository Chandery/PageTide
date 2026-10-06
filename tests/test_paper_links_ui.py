"""Connected Papers links in the two paper detail panes: plain links that are built from the paper's own ids,
with nothing requested by the app (no fetch to the site, no stored result)."""
import re
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
ORG = (STATIC / "organization.js").read_text(encoding="utf-8")
LINKS = (STATIC / "paper-links.js").read_text(encoding="utf-8")


class ConnectedPapersLinkTests(unittest.TestCase):
    def test_both_detail_panes_show_the_link_and_load_the_module_first(self):
        self.assertIn("connectedPapersURL(d)", INDEX)
        self.assertIn("connectedPapersURL(p)", ORG)
        self.assertLess(INDEX.index('/paper-links.js"'), INDEX.index('/organization.js"'))

    def test_the_links_open_in_a_new_tab_without_leaking_the_page(self):
        self.assertIn('target="_blank" rel="noreferrer"', INDEX[INDEX.index("connectedPapersURL(d)"):][:400])
        self.assertIn("link.rel = 'noopener noreferrer'", ORG[ORG.index("connectedPapersURL(p)"):][:400])

    def test_the_app_never_asks_the_site_anything(self):
        self.assertNotRegex(LINKS, r"fetch\(|XMLHttpRequest|sendBeacon|new Image")
        self.assertNotRegex(ORG + INDEX, r"fetch\([^)]*connectedpapers")

    def test_the_label_does_not_promise_the_paper_exists_there(self):
        self.assertIn("不能保证它找得到", INDEX)


if __name__ == "__main__":
    unittest.main()
