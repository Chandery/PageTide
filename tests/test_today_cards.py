"""Today cards: the manual AI summary button and the three kinds of small label (status, PDF source, keyword).

Static contracts on index.html / theme.css; the behaviour was checked in a browser preview and the server side
(card-level triage) is covered in test_gateway_budget.py.
"""
import re
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
index = (STATIC / "index.html").read_text(encoding="utf-8")
theme = (STATIC / "theme.css").read_text(encoding="utf-8")


def card_html():
    return index[index.index("function cardHTML"):index.index("function renderCards")]


class ManualSummaryTests(unittest.TestCase):
    def test_every_card_has_a_summary_button_and_it_sends_only_that_card(self):
        self.assertIn('data-ai="${esc(c.key)}"', card_html())
        handler = index[index.index("async function triageOne"):index.index("$('#btnDaily').onclick")]
        self.assertIn("keys: [key]", handler)
        self.assertIn("'/api/triage'", handler)
        self.assertIn("state.triagingKeys", handler)

    def test_the_button_is_a_click_not_a_side_effect_of_rendering(self):
        self.assertEqual(index.count("triageOne("), 2)            # the definition and the one click handler
        click = index[index.index("button[data-ai]"):][:160]
        self.assertIn("triageOne(ai.dataset.ai)", click)

    def test_the_card_shows_progress_and_disables_its_button_while_it_runs_and_other_cards_stay_usable(self):
        self.assertIn("state.triagingKeys.has(c.key)", index[index.index("function aiSlot"):index.index("function renderRoute")])
        self.assertIn("state.triaging || state.triagingKeys.has(c.key) ? 'disabled'", card_html())

    def test_a_card_that_already_has_a_summary_offers_to_summarise_again(self):
        self.assertIn("c.summary ? '重新速览' : 'AI 速览'", card_html())


class LabelFamiliesTests(unittest.TestCase):
    def test_status_pdf_and_keyword_labels_are_three_different_components(self):
        for cls in (".st {", ".pdf-tag {", ".kw {", ".st-done", ".st-pending", ".st-saved", ".pdf-direct", ".pdf-page", ".pdf-none"):
            self.assertIn(cls, theme)
        radius = lambda sel: re.search(re.escape(sel) + r" \{[^}]*border-radius:([^;]+);", theme).group(1)
        self.assertEqual(radius(".st"), "999px")                     # round pill
        self.assertNotEqual(radius(".pdf-tag"), radius(".st"))       # squarer
        self.assertNotEqual(radius(".kw"), radius(".st"))

    def test_the_card_uses_each_family_for_its_own_content(self):
        html = card_html()
        # A card carries no status pills (2026-10-22): the AI summary shows itself, the save button shows saved.
        for gone in ('st-done', 'st-pending', 'st-saved', 'class="kws"'):
            self.assertNotIn(gone, html)
        self.assertIn("c.pdf_status === 'page' ? pdfBadge(c.pdf_status)", html)   # only the case the reader must act on
        self.assertIn("routeBadge(c)", html)
        self.assertIn('pdf-tag pdf-', index)
        route = index[index.index("function routeBadge"):index.index("const PDF_BADGES")]
        self.assertIn('class="kw kw-', route)
        self.assertIn('class="kw-k"', route)                         # the kind (路径 / 补基础 / 探索) stays its own translatable part

    def test_the_learning_map_panel_lists_concepts_as_keyword_tags(self):
        panel = index[index.index("function renderRoute"):index.index("$('#routePanel').addEventListener")]
        self.assertIn('<span class="kw"><span class="kw-v"', panel)
        self.assertNotIn('class="chip"', panel)

    def test_keyword_tags_are_scaled_with_the_screen_and_readable_in_both_modes(self):
        block = theme[theme.index(".kw {"):]
        self.assertIn("font-size:calc(var(--fs-sm) * var(--s))", block)
        self.assertIn("color-mix(in srgb, var(--accent-text)", block)   # derived from theme colours, so dark mode follows


if __name__ == "__main__":
    unittest.main()
