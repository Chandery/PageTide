"""The "已读懂" button: in the library (a paper must be saved first), and the wording that keeps a save
and an understanding apart."""
import re
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")


ORG = (STATIC / "organization.js").read_text(encoding="utf-8")


class UnderstoodButtonTests(unittest.TestCase):
    def test_it_is_offered_in_the_library_only(self):
        self.assertEqual(len(re.findall(r'data-fb="understood"', INDEX)), 0)
        self.assertIn('data-action="understood"', ORG)

    def test_the_library_button_is_for_saved_papers_and_names_its_project(self):
        self.assertIn("先收藏到项目", ORG)
        self.assertIn("data-project=", ORG)

    def test_it_sits_in_the_list_row_next_to_detail_and_edit_category(self):
        row = ORG[ORG.index('<div class="org-paper-actions">'):ORG.index("</article>`).join('')")]
        for part in ('data-action="detail"', 'data-action="paper-membership"', "understoodButton(p)"):
            self.assertIn(part, row)

    def test_the_button_carries_no_explanatory_tooltip(self):
        self.assertNotIn("只推进学习进度，不改变兴趣画像", ORG)

    def test_a_familiarity_label_is_not_kept_as_the_card_feedback(self):
        handler = INDEX[INDEX.index("async function doFeedback"):INDEX.index("$('#cards').addEventListener('click'")]
        self.assertIn("card.familiarity = action", handler)

    def test_the_weekly_report_goes_back_to_the_profile_tab(self):
        weekly = (STATIC / "weekly_report.html").read_text(encoding="utf-8")
        self.assertIn("/?view=profile", weekly)
        self.assertIn("get('view')", INDEX)

    def test_the_learning_map_page_no_longer_carries_the_saving_is_not_understanding_note(self):
        self.assertNotIn("收藏表示感兴趣，不等于读懂", (STATIC / "route.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
