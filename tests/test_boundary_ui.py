"""The optional boundary (where the reader starts, how deep to go) on the two pages that ask for an AI draft,
and the kind/reason line of a concept. The server side is in test_route_plan.py."""
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


def read(name):
    return (STATIC / name).read_text(encoding="utf-8")


class BoundaryPageTests(unittest.TestCase):
    def test_project_revision_uses_complete_fixed_fields(self):
        self.assertIn('data-role="briefFields"',read('route.html'))
        js=read('route-page.js')
        self.assertIn("Brief.read(part('briefFields'))",js)
        self.assertIn("action: 'revision-generate', brief, revision",js)
        self.assertNotIn("aiBoundary",js)

    def test_creation_uses_the_same_fields_without_boundary_enums(self):
        self.assertIn('data-role="mapBrief"',read('project_creation.html'))
        js=read('project-creation.js')
        self.assertIn("Brief.read(part('mapBrief'))",js)
        self.assertIn("{regenerate, brief}",js)
        self.assertNotIn("mapBoundary",js)

    def test_goal_required_and_unspecified_background_are_explained(self):
        for page in ('route.html','project_creation.html'):
            text=read(page)
            self.assertIn('仅学习目标必填',text)
            self.assertIn('其他项可以跳过',text)
            self.assertIn('已知基础留空表示未说明',text)

    def test_the_concept_panel_shows_the_kind_and_the_reason_as_text_not_markup(self):
        js = read("route-editor.js")
        self.assertIn("为什么在这里：</span><span data-no-i18n>${esc(concept.why)}", js)


if __name__ == "__main__":
    unittest.main()
