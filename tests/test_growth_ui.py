"""The learning-map page's "new directions" section: a button to look, two buttons per proposal, undo, and a
reminder of what counts as evidence. The server side is in test_route_growth.py."""
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
HTML = (STATIC / "route.html").read_text(encoding="utf-8")
JS = (STATIC / "route-page.js").read_text(encoding="utf-8")


class GrowthPageTests(unittest.TestCase):
    def test_the_page_has_the_section_and_says_what_counts_as_evidence(self):
        self.assertIn('data-role="findGrowth"', HTML)
        self.assertIn('data-role="growthList"', HTML)
        for wanted in ("“有用”“已读懂”", "“不感兴趣”“太难”和没点过的论文都不算", "点“加入学习图”才会加入"):
            self.assertIn(wanted, HTML)

    def test_nothing_is_asked_until_the_person_clicks(self):
        # the only caller of the candidates action is findGrowth(), and the only callers of findGrowth() are the
        # button and the end of an accept / reject / undo the person just clicked
        self.assertEqual(JS.count("action: 'candidates'"), 1)
        self.assertEqual(JS.count("findGrowth()"), 3)   # the declaration, the button handler, the click handler
        self.assertNotIn("findGrowth()", JS[JS.index("(async () => {\n  if (!projectId)"):])   # not on page load

    def test_accepting_and_rejecting_carry_the_revision_so_a_stale_page_is_refused(self):
        self.assertIn("revision: state.route.revision", JS)
        self.assertIn("'candidate-accept'", JS)
        self.assertIn("'candidate-reject'", JS)

    def test_proposals_are_locked_while_edits_are_unsaved(self):
        self.assertIn("locked = state.dirty", JS)
        self.assertIn("renderGrowth();", JS)

    def test_the_step_taken_back_is_the_one_shown_and_only_while_it_is_still_the_latest(self):
        self.assertIn("event: Number(button.dataset.event)", JS)               # the page names the step it offers to undo
        self.assertIn("growth.undo.revision === state.route.revision", JS)      # any other save or mark hides the offer
        self.assertIn('data-event="${esc(growth.undo.id)}"', JS)
        self.assertIn("locked ? ' disabled", JS)                                # and it is off while edits are unsaved


if __name__ == "__main__":
    unittest.main()
