"""Static contracts of the project-creation page; behaviour is covered by the backend and node tests."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app/static"


class ProjectCreationUITests(unittest.TestCase):
    def setUp(self):
        self.html = (STATIC / "project_creation.html").read_text()
        self.js = (STATIC / "project-creation.js").read_text()
        self.css = (STATIC / "project-creation.css").read_text()
        self.index = (STATIC / "index.html").read_text()

    def test_the_learning_map_editor_is_wired_into_creation(self):
        self.assertIn('data-role="mapBlock"', self.html)
        self.assertIn("/route-editor.js", self.html)
        self.assertTrue((STATIC / "route-editor.js").is_file())
        for token in ("/route`", "route: mapPayload()", "action: 'ground'", "R.check(map.graph)", "已掌握", "不使用学习图"):
            self.assertIn(token, self.js)
        self.assertIn("route", self.js[self.js.index("async function finalize"):self.js.index("async function createSession")])

    def test_the_editor_never_calls_a_model_on_its_own(self):
        # generation is behind an explicit button; opening or editing the map sends nothing to the AI
        self.assertEqual(self.js.count("/route`"), 1)
        self.assertIn("part('mapGenerate').onclick = () => generateMap(false)", self.js)

    def test_page_is_split_into_markup_style_and_script(self):
        for asset in ("/project-creation.css", "/creation-pdf.js", "/project-creation.js"):
            self.assertIn(asset, self.html)
            self.assertTrue((STATIC / asset.lstrip("/")).is_file())
        self.assertNotIn("<style>", self.html)

    def test_three_modes_are_distinct_and_say_what_they_cost(self):
        for mode in ("quick", "ai_guided", "manual"):
            self.assertIn(f'data-mode="{mode}"', self.html)
        for label in ("AI · 1 次调用", "AI · 对话", "不用 AI"):
            self.assertIn(label, self.html)
        self.assertIn('role="radiogroup"', self.html)
        # Quick creation has no conversation box; guided creation does.
        quick = self.html[self.html.index('id="quickForm"'):self.html.index('id="guidedForm"')]
        self.assertNotIn("guideMessage", quick)
        self.assertIn('id="guideMessage"', self.html)

    def test_every_wait_has_a_live_status_with_elapsed_time(self):
        for region in ("quickActivity", "guidedActivity", "seedSearchActivity", "manualActivity"):
            self.assertRegex(self.html, rf'id="{region}" role="status" aria-live="polite"')
        self.assertIn('data-role="searchActivity"', self.html)
        for marker in ("function makeActivity", "setInterval(tick"):
            self.assertIn(marker, self.js)
        self.assertIn("prefers-reduced-motion", self.css)

    def test_each_ai_turn_says_whether_the_model_answered(self):
        for marker in ("未使用 AI", "本地整理：", "reason_text", "重试 AI", "retry: true", "打开设置",
                       "usage_unknown", "usage_reserved", "AI 回复不可用", "用量未确认"):
            self.assertIn(marker, self.js)
        # A failed request keeps what was typed instead of swallowing it.
        self.assertIn("guideMessage').value = message", self.js)

    def test_candidates_stream_per_query_with_placeholders_and_details(self):
        self.assertIn("/search`", self.js)
        self.assertNotIn("/preview", self.js)
        for marker in ("skeleton", "matched_queries", "展开摘要", "打开原文", "已找到", "OpenAlex 暂时不可用"):
            self.assertIn(marker, self.js)
        # The model never selects: nothing starts ticked.
        self.assertIn("selected.has(paper.key)", self.js)
        self.assertNotIn("勾选后才会加入项目", self.html)
        self.assertNotIn("selected.add(paper.key)", self.js)

    def test_manual_seeds_accept_identifiers_titles_and_dropped_pdfs(self):
        for marker in ('id="seedInput"', 'id="dropzone"', 'id="pdfPick"'):
            self.assertIn(marker, self.html)
        for marker in ("/api/seeds/resolve", "/api/seeds/search", "/api/seeds/pdf", "pdf_id",
                       "PDHPdfHints", "looksLikeIdentifier"):
            self.assertIn(marker, self.js)
        # Reading the first pages is shared with library import: one reader, loaded before the page script.
        reader = (STATIC / "pdf-hints.js").read_text(encoding="utf-8")
        for marker in ("getTextContent", "PDHCreationPdf.identify"):
            self.assertIn(marker, reader)
        self.assertLess(self.html.index('/pdf-hints.js'), self.html.index('/project-creation.js'))
        self.assertIn("creation_mode: 'manual'", self.js)

    def test_seed_failures_stay_on_screen_with_a_way_forward(self):
        for marker in ("data-do=\"again\"", "data-do=\"pick\"", "data-do=\"remove\"", "进入项目", "pdf_error"):
            self.assertIn(marker, self.js)

    def test_learning_path_can_be_built_by_hand_in_local_mode(self):
        # Local guidance never proposes a path, so the owner must be able to add and remove stages.
        self.assertIn("添加阶段", self.html)
        self.assertIn("function addPathItem", self.js)

    def test_detail_has_explicit_project_sharing_control(self):
        self.assertIn("/api/project-papers", self.index)
        self.assertIn("加入其他项目", self.index)
        self.assertNotIn("收藏、反馈和画像仍按项目独立记录", self.index)
        self.assertIn("new URLSearchParams(window.location.search).get('project_id')", self.index)

    def test_desktop_shell_lets_the_page_receive_dropped_files(self):
        self.assertIn("disable_drag_drop_handler()", (ROOT / "src-tauri/src/main.rs").read_text())


if __name__ == "__main__":
    unittest.main()


class RoutePageTests(unittest.TestCase):
    def setUp(self):
        self.html = (STATIC / "route.html").read_text()
        self.js = (STATIC / "route-page.js").read_text()
        self.index = (STATIC / "index.html").read_text()
        self.css = (STATIC / "project-creation.css").read_text()

    def test_the_page_loads_the_editor_helpers_and_its_own_script(self):
        for asset in ("/route-editor.js", "/route-page.js"):
            self.assertIn(asset, self.html)
        self.assertNotIn("<style>", self.html)

    def test_the_page_reads_and_writes_only_the_route_api_and_reaches_the_ai_only_through_the_draft_button(self):
        self.assertIn("/api/route", self.js)
        for forbidden in ("/route`", "/api/qa", "triage", "/api/daily", "/api/project-guidance", "/api/refresh"):
            self.assertNotIn(forbidden, self.js)
        self.assertEqual(self.js.count("action: 'revision-generate'"), 1)
        self.assertEqual(self.js.count("action: 'brief-plan'"), 1)   # the one model-backed action; see test_route_graph_page for when it may run

    def test_the_page_offers_the_marks_the_server_accepts_and_a_way_back(self):
        for token in ("action: 'manual'", "action: 'mode'", "action: 'save'", "action: 'ground'", "R.actionsFor", "revision"):
            self.assertIn(token, self.js)

    def test_today_links_to_the_map_and_labels_cards_by_route(self):
        self.assertIn("/route.html", self.index)
        for token in ("routePanel", "renderRoute", "c.route", "补基础", "探索", "来自学习图"):
            self.assertIn(token, self.index)

    def test_the_page_never_describes_disinterest_lateness_or_debt(self):
        helpers = (STATIC / "route-editor.js").read_text()
        today = self.index[self.index.index("function renderRoute"):self.index.index("const PDF_BADGES")]
        import json
        pack = json.loads((STATIC / "i18n" / "en-US.json").read_text())["messages"]
        for text in (self.html, self.js, helpers, today):
            for word in ("落后", "欠", "逾期", "错过", "未完成", "未读", "积压", "没读"):
                self.assertNotIn(word, text)
        for key, value in pack.items():
            if "学习图" in key or "概念" in key:
                for word in ("behind", "overdue", "unread", "backlog", "missed", "late "):
                    self.assertNotIn(word, value.lower(), key)

    def test_the_page_guards_requests_and_keeps_unsaved_edits_on_errors(self):
        for token in ("state.busy", "state.checking", "async function refreshRoute", "needsEditorHTML", "readNeeds"):
            self.assertIn(token, self.js)
        # a failed request refreshes the revision only; load() (which replaces the draft) is not called from a catch
        for name in ("async function mark", "part('modeSeg').onclick"):
            body = self.js[self.js.index(name):self.js.index(name) + 700]
            self.assertNotIn("await load()", body)
        self.assertIn("revision: state.route.revision ?? 0", self.js)   # a first save is guarded too

    def test_the_card_badge_is_translatable_in_parts(self):
        today = self.index[self.index.index("function routeBadge"):self.index.index("const PDF_BADGES")]
        self.assertNotIn("data-no-i18n>${esc(where)}", today)
        self.assertIn("ROUTE_TITLES", self.index)
