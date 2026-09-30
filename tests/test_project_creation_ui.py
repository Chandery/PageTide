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

    def test_detail_has_explicit_project_sharing_control(self):
        self.assertIn("/api/project-papers", self.index)
        self.assertIn("加入其他项目", self.index)
        self.assertIn("收藏、反馈和画像仍按项目独立记录", self.index)


if __name__ == "__main__":
    unittest.main()
