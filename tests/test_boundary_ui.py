"""The optional boundary (where the reader starts, how deep to go) on the two pages that ask for an AI draft,
and the kind/reason line of a concept. The server side is in test_route_plan.py."""
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


def read(name):
    return (STATIC / name).read_text(encoding="utf-8")


class BoundaryPageTests(unittest.TestCase):
    def test_the_project_page_asks_for_it_and_sends_only_what_was_chosen(self):
        self.assertIn('data-role="aiBoundary"', read("route.html"))
        js = read("route-page.js")
        self.assertIn("R.readBoundary(part('aiBoundary'))", js)
        self.assertIn("...(boundary ? {boundary} : {})", js)

    def test_the_creation_page_asks_for_it_and_sends_only_what_was_chosen(self):
        self.assertIn('data-role="mapBoundary"', read("project_creation.html"))
        js = read("project-creation.js")
        self.assertIn("R.boundaryHTML('map')", js)
        self.assertIn("R.readBoundary(part('mapBoundary'))", js)
        self.assertIn("{regenerate, ...(boundary ? {boundary} : {})}", js)

    def test_both_pages_say_it_can_be_skipped_and_what_skipping_means(self):
        for page in ("route.html", "project_creation.html"):
            text = read(page)
            self.assertIn("可以跳过", text, page)
            self.assertIn("最少前置", text, page)

    def test_the_concept_panel_shows_the_kind_and_the_reason_as_text_not_markup(self):
        js = read("route-editor.js")
        self.assertIn("为什么在这里：</span><span data-no-i18n>${esc(concept.why)}", js)


if __name__ == "__main__":
    unittest.main()
