"""The "已读懂" button: on the recommendation card and in the detail pane, and the wording that keeps a save
and an understanding apart."""
import re
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")


class UnderstoodButtonTests(unittest.TestCase):
    def test_the_card_and_the_detail_pane_both_offer_it(self):
        self.assertEqual(len(re.findall(r'data-fb="understood"', INDEX)), 2)

    def test_it_sits_in_the_feedback_group_of_the_card(self):
        card = INDEX[INDEX.index('<span class="actions-fb">'):INDEX.index('<span class="actions-end">')]
        self.assertIn('data-fb="understood"', card)
        self.assertIn('data-fb="irrelevant"', card)

    def test_the_button_says_it_does_not_change_interest(self):
        self.assertIn("只推进学习进度，不改变兴趣画像", INDEX)

    def test_a_familiarity_label_is_not_kept_as_the_card_feedback(self):
        handler = INDEX[INDEX.index("async function doFeedback"):INDEX.index("$('#cards').addEventListener('click'")]
        self.assertIn("card.familiarity = action", handler)

    def test_the_learning_map_page_says_saving_is_not_understanding(self):
        self.assertIn("收藏表示感兴趣，不等于读懂", (STATIC / "route.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
