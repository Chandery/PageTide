import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProjectCreationUITests(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / "app/static/project_creation.html").read_text()
        self.index = (ROOT / "app/static/index.html").read_text()

    def test_guided_creation_is_a_confirmed_local_preview_flow(self):
        for marker in ("/api/project-guidance/sessions", "/turn", "/preview", "/finalize",
                       "候选论文（勾选后才会加入项目）", "本地模式可用", "6"):
            self.assertIn(marker, self.html)
        self.assertNotIn("敬请期待", self.html)
        self.assertNotIn("AI 帮你初筛论文", self.html)

    def test_manual_creation_sends_seed_identifiers_and_url_project_wins(self):
        self.assertIn("seeds", self.html)
        self.assertIn("creation_mode:'manual'", self.html)
        self.assertIn("new URLSearchParams(window.location.search).get('project_id')", self.index)

    def test_preview_errors_replace_one_slot_and_name_openalex_outage(self):
        self.assertIn('id="previewError"', self.html)
        self.assertNotIn("insertAdjacentHTML('beforebegin'", self.html)
        self.assertIn("OpenAlex 暂时不可用", self.html)

    def test_manual_creation_keeps_seed_failures_on_screen(self):
        # Failed seeds must stay readable instead of flashing before an automatic redirect.
        self.assertIn("unavailable:", self.html)
        self.assertIn("进入项目", self.html)

    def test_learning_path_can_be_built_by_hand_in_local_mode(self):
        # Local guidance never proposes a path, so the owner must be able to add and remove stages.
        self.assertIn("添加阶段", self.html)
        self.assertIn("function addPathItem", self.html)

    def test_detail_has_explicit_project_sharing_control(self):
        self.assertIn("/api/project-papers", self.index)
        self.assertIn("加入其他项目", self.index)
        self.assertIn("收藏、反馈和画像仍按项目独立记录", self.index)


if __name__ == "__main__":
    unittest.main()
