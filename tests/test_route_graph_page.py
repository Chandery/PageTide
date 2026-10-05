"""Static contracts for the pages that draw the learning map and manage projects.

The behaviour of the graph layout and the editor helpers is covered by the node tests; the page scripts are
checked in a browser. These tests pin what must stay true of the files themselves: load order, that nothing
calls the model on its own, the wording rules and the confirmation gate for deleting a project.
"""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
read = lambda name: (STATIC / name).read_text(encoding="utf-8")
PAGES = ("route.html", "route-page.js", "route-editor.js", "route-graph.js", "project_creation.html", "project-creation.js",
         "project.html", "project-page.js")


class LoadOrderTests(unittest.TestCase):
    def test_the_map_page_loads_helpers_then_graph_then_page(self):
        html = read("route.html")
        order = [html.index(f'/{name}"') for name in ("route-editor.js", "route-graph.js", "route-page.js")]
        self.assertEqual(order, sorted(order))

    def test_the_creation_page_loads_the_graph_after_the_editor_helpers(self):
        html = read("project_creation.html")
        self.assertLess(html.index('/route-editor.js"'), html.index('/route-graph.js"'))
        self.assertLess(html.index('/route-graph.js"'), html.index('/project-creation.js"'))

    def test_every_script_the_pages_name_is_served(self):
        for page in ("route.html", "project_creation.html", "project.html"):
            for src in re.findall(r'<script src="/([^"]+)"', read(page)):
                self.assertTrue((STATIC / src).exists(), f"{page} loads missing {src}")


class NoLayersWordingTests(unittest.TestCase):
    def test_the_old_stage_by_stage_layout_and_wording_are_gone(self):
        for name in PAGES:
            text = read(name)
            for stale in ("columns(", "map-col", "第 ${index + 1} 层", "越靠左越基础", "R.columns"):
                self.assertNotIn(stale, text, f"{name} still has {stale}")
        self.assertNotIn(".map-col", read("project-creation.css"))

    def test_a_recommendation_card_names_its_concept_not_a_layer_number(self):
        index = read("index.html")
        badge = index[index.index("function routeBadge"):index.index("const PDF_BADGES")]
        self.assertNotIn("route.layer", badge)
        self.assertNotIn("层", badge)

    def test_the_map_is_explained_as_arrows_between_concepts_not_stages(self):
        for name in ("route.html", "project-creation.js"):
            text = read(name)
            self.assertIn("箭头", text)
            self.assertIn("不同分支互不等待", text)
        self.assertIn("不是必须读完一整层", read("route.html"))

    def test_no_lateness_or_debt_wording_on_the_new_pages(self):
        for name in PAGES:
            self.assertIsNone(re.search(r"落后|逾期|拖延|欠(?!缺)|未读\s*\d|积压|补课", read(name)), name)
        pack = json.loads(read("i18n/en-US.json"))["messages"]
        for value in pack.values():
            for text in (value if isinstance(value, list) else [value]):
                self.assertIsNone(re.search(r"\b(behind schedule|overdue|backlog|catch up|unread)\b", text, re.I), text)


class AiOnlyOnClickTests(unittest.TestCase):
    def test_the_page_asks_the_model_only_from_the_draft_button(self):
        js = read("route-page.js")
        self.assertEqual(len(re.findall(r"action:\s*'plan'", js)), 1)
        handler = js[js.index("part('aiGo').onclick"):]
        self.assertLess(handler.index("action: 'plan'"), handler.index("beforeunload"))
        self.assertTrue("action: 'plan'" not in js[:js.index("function defaultGoal")], "nothing before the button handler may call plan")

    def test_the_disclosure_says_what_is_sent_and_that_nothing_is_saved_before_save(self):
        html = read("route.html")
        for needle in ("前 5 个关键词", "不发送论文、笔记、画像或别的项目", "每个项目每天最多 3 次", "保存之前，现在的学习图不会改变"):
            self.assertIn(needle, html)

    def test_the_server_only_plans_on_post(self):
        server = (ROOT / "app" / "server.py").read_text(encoding="utf-8")
        get_part = server[server.index("def do_GET"):server.index("def do_POST")]
        self.assertNotIn("route_plan", get_part)


class DraftSafetyTests(unittest.TestCase):
    """Things the independent review found about the AI draft and re-drawing the graph."""

    def test_editing_is_locked_while_a_request_runs_so_the_ai_reply_cannot_overwrite_edits(self):
        js = read("route-page.js")
        change = js[js.index("function change(next)"):js.index("function editConcept")]
        self.assertIn("state.busy", change)
        self.assertIn("!state.busy", js[js.index("part('discard').onclick"):js.index("part('save').onclick")])

    def test_an_ai_draft_reuses_the_ids_of_same_named_concepts_so_marks_survive_saving(self):
        js = read("route-page.js")
        self.assertIn("R.reuseIds(out.graph, state.route.graph)", js)
        self.assertIn("只会保留给名字相同的概念", js)

    def test_a_refusal_for_missing_approval_is_explained_not_shown_as_a_failure_of_the_ai(self):
        js = read("route-page.js")
        self.assertIn("reason_code === 'not_approved'", js)
        self.assertIn("learning_path_plan_project", js)

    def test_a_redraw_keeps_zoom_scroll_and_focus_and_does_not_drop_a_half_typed_edit(self):
        for name, holder in (("route-page.js", "state"), ("project-creation.js", "map")):
            js = read(name)
            self.assertIn(".view()", js, name)
            self.assertIn("focusNode(", js, name)
            self.assertIn("canSelect:", js, name)
        self.assertIn("canSelect", read("route-graph.js"))

    def test_the_zoom_readout_does_not_announce_itself_at_every_redraw(self):
        self.assertNotIn("aria-live", read("route-graph.js"))


class ProjectPageTests(unittest.TestCase):
    def test_delete_needs_the_exact_name_and_only_the_confirmed_click_deletes(self):
        js = read("project-page.js")
        self.assertEqual(len(re.findall(r"method:\s*'DELETE'", js)), 1)
        handler = js[js.index("part('delete').onclick"):]
        self.assertIn("matches(part('confirm').value", handler[:300])
        self.assertLess(handler.index("matches("), handler.index("'DELETE'"))
        self.assertIn("disabled = !matches(", js)

    def test_the_name_match_is_exact(self):
        js = read("project-page.js")
        body = re.search(r"function matches\(typed, name\) \{(.*?)\}\n", js, re.S).group(1)
        script = f"const matches = (typed, name) => {{{body}}}; console.log(JSON.stringify([" \
                 "matches('半导体生长','半导体生长'), matches('半导体生长 ','半导体生长'), matches('半导体','半导体生长'), " \
                 "matches('','') , matches('a', undefined), matches('A','a')]))"
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), [True, False, False, False, False, False])

    def test_the_page_says_what_is_removed_and_what_is_kept_and_that_a_backup_is_made(self):
        html = read("project.html")
        for needle in ("推荐记录", "学习图", "已下载的 PDF", "别的项目也不受影响", "数据库备份"):
            self.assertIn(needle, html)

    def test_entry_points_exist(self):
        index = read("index.html")
        self.assertIn('id="projectEdit"', index)
        self.assertIn("/project.html?project_id=", index)
        self.assertIn("onEdit:", index)
        switcher = read("project-switcher.js")
        self.assertIn("mc-edit", switcher)
        self.assertIn("document.activeElement?.classList?.contains('mc-edit')", switcher)   # Enter on the button is the button's own


class MapPageStructureTests(unittest.TestCase):
    def test_the_graph_is_mounted_with_a_detail_panel_and_a_height_limit(self):
        js, html = read("route-page.js"), read("route.html")
        self.assertIn("window.PDHGraph.mount(", js)
        self.assertIn("maxHeight:", js)
        self.assertIn('data-role="detail"', html)
        self.assertIn("overflow:auto", read("project-creation.css").replace(" ", ""))
        css = read("project-creation.css").replace(" ", "")
        self.assertIn(".rg-viewport{overflow:auto;max-height:68vh", css)
        self.assertIn("grid-template-columns:minmax(0,1fr)", css)   # a single-column layout must not be widened by its content

    def test_error_paths_still_keep_the_draft(self):
        js = read("route-page.js")
        guarded = js[js.index("async function guarded"):js.index("async function load")]
        self.assertTrue("load(" not in guarded, "a failed request must not reload (and so wipe) the draft")
        self.assertTrue("refreshRoute" in guarded)


if __name__ == "__main__":
    unittest.main()
