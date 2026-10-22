"""Exploration is something you can see: a badge on the card that says where the paper points. The Today page does
not narrate how a batch was composed (owner, 2026-10-22: no surface details)."""
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

    def test_there_is_no_off_path_label_any_more(self):
        self.assertNotIn("offroute", INDEX + THEME)
        self.assertNotIn("路径外", INDEX)

    def test_badge_tooltips_stay_short(self):
        titles = INDEX[INDEX.index("const ROUTE_TITLES"):INDEX.index("function routeBadge")]
        for text in __import__("re").findall(r"'([^']*)'", titles):
            self.assertLessEqual(len(text), 30, text)

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
    def test_the_today_page_does_not_narrate_the_batch(self):
        self.assertNotIn("function exploreLine", INDEX)
        for gone in ("这次推荐：探索", "这次推荐里没有探索类论文", "每批最多", "宁可少推"):
            self.assertNotIn(gone, INDEX)


if __name__ == "__main__":
    unittest.main()
