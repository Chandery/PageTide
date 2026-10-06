"""Exploration is something you can see: a badge on the card that says where the paper points, and a line on
the Today page that says how many of today's papers are exploration and, when there are none, why."""
import re
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
THEME = (STATIC / "theme.css").read_text(encoding="utf-8")


class ExploreBadgeTests(unittest.TestCase):
    def test_both_exploration_kinds_have_a_label_and_a_plain_explanation(self):
        kinds = INDEX[INDEX.index("const ROUTE_KINDS"):INDEX.index("function routeBadge")]
        for kind in ("explore", "explore_new"):
            self.assertIn(f"{kind}:", kinds)
        self.assertIn("探索 · 新方向", kinds)
        self.assertIn("让 AI 判断", kinds)               # what the reader can do after collecting it
        self.assertIn("没展示过，也不属于学习图里的任何概念", kinds)

    def test_there_is_no_off_path_label_any_more(self):
        self.assertNotIn("offroute", INDEX + THEME)
        self.assertNotIn("路径外", INDEX)

    def test_the_standard_for_exploration_is_stated_on_the_card_and_in_the_panel(self):
        kinds = INDEX[INDEX.index("const ROUTE_KINDS"):INDEX.index("function routeBadge")]
        self.assertIn("也不属于学习图里的任何概念", kinds)
        panel = INDEX[INDEX.index("function exploreLine"):INDEX.index("$('#routePanel').addEventListener")]
        self.assertIn("没展示过、又不属于学习图里任何概念", panel)

    def test_exploration_is_hard_to_miss(self):
        self.assertRegex(THEME, r"\.kw-explore \.kw-k, \.kw-explore_new \.kw-k \{ background:var\(--ai-text\);")   # a solid, bold tag
        self.assertIn(".card.is-explore", THEME)                                                                 # and the whole card is marked
        self.assertIn("exploring ? ' is-explore' : ''", INDEX)

    def test_the_new_direction_badge_is_styled_like_the_other_kinds(self):
        self.assertRegex(THEME, r"\.kw-explore_new \.kw-k\s*\{")

    def test_an_unknown_kind_still_draws_no_badge(self):
        badge = INDEX[INDEX.index("function routeBadge"):INDEX.index("const PDF_BADGES")]
        self.assertIn("if (!kind) return ''", badge)


class TodayLineTests(unittest.TestCase):
    def test_the_panel_counts_todays_exploration_papers(self):
        panel = INDEX[INDEX.index("function exploreLine"):INDEX.index("$('#routePanel').addEventListener")]
        self.assertIn("今天的探索位", panel)
        self.assertRegex(panel, r"kind === 'explore_new'|kind==='explore_new'")

    def test_when_there_is_none_it_says_why_without_blaming_the_reader(self):
        panel = INDEX[INDEX.index("function exploreLine"):INDEX.index("$('#routePanel').addEventListener")]
        self.assertIn("今天这一批没有探索位", panel)
        self.assertIn("探索约占", panel)
        self.assertNotRegex(panel, r"落后|没读|欠|逾期")


if __name__ == "__main__":
    unittest.main()
