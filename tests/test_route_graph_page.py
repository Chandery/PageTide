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
    def test_the_page_asks_only_explicit_creation_or_revision_requests(self):
        js = read("route-page.js")
        generation = js[js.index("async function generateBrief()"):js.index("async function confirmRevision()")]
        self.assertEqual(generation.count("action: 'revision-generate'"), 1)
        self.assertEqual(generation.count("action: 'brief-plan'"), 1)
        self.assertIn("guarded(generateBrief)", generation)
        self.assertNotIn("action: 'plan'", js)
        self.assertNotIn("generateBrief()", js[:js.index("function defaultGoal")])

    def test_the_disclosure_explains_full_map_scope_and_confirmation(self):
        html = read("route.html")
        for needle in ("五字段", "完整有界学习图", "不发送论文、笔记、画像、反馈或其他项目", "本地日", "预览确认"):
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

    def test_existing_map_uses_patch_preview_and_draft_id_confirmation(self):
        js = read("route-page.js")
        self.assertNotIn("R.reuseIds(out.graph", js)
        self.assertIn("action: 'revision-confirm', draft_id: preview.draft_id", js)
        self.assertIn("state.preview = out.preview", js)

    def test_unapproved_scope_is_explained_and_teacher_input_retained(self):
        js = read("route-page.js")
        self.assertIn("reason_code === 'not_approved'", js)
        self.assertIn("需求和草稿已保留", js)

    def test_a_redraw_keeps_zoom_scroll_and_focus_and_does_not_drop_a_half_typed_edit(self):
        for name, holder in (("route-page.js", "state"), ("project-creation.js", "map")):
            js = read(name)
            self.assertIn(".view()", js, name)
            self.assertIn("focusNode(", js, name)
            self.assertIn("canSelect:", js, name)
        self.assertIn("canSelect", read("route-graph.js"))

    def test_the_zoom_readout_does_not_announce_itself_at_every_redraw(self):
        self.assertNotIn("aria-live", read("route-graph.js"))


class LargeScreenTests(unittest.TestCase):
    """The low-density pages grow with the screen; the dense library page keeps its size."""

    def test_the_steps_are_defined_once_in_the_shared_theme(self):
        theme = read("theme.css")
        self.assertIn(":root { --s:1; --wrap:1200px; }", theme)
        for width, scale, wrap in ((1700, "1.2", "1560px"), (2200, "1.45", "2000px"), (2800, "1.8", "2560px")):
            self.assertRegex(theme, rf"@media \(min-width:{width}px\) \{{ :root \{{ --s:{re.escape(scale)};\s+--wrap:{wrap}; \}} \}}")
        for name in ("index.html", "project-creation.css", "profile.css", "settings.html", "weekly_report.html", "route.html", "project.html"):
            self.assertNotRegex(read(name), r"--s:\s*1\.\d", f"{name} must not define its own step")

    def test_low_density_sheets_have_no_fixed_pixel_font_sizes(self):
        for name in ("project-creation.css", "profile.css", "settings.html", "weekly_report.html"):
            text = read(name)
            self.assertIsNone(re.search(r"font-size\s*:\s*[\d.]+px", text), f"{name} still has a fixed font-size")

    def test_the_main_page_scales_its_text_and_controls_but_not_the_dense_workspace(self):
        index = read("index.html")
        for rule in (".card h3 { font-size:calc(16px * var(--s))", ".hero h1 { font-size:calc(32px * var(--s))", ".tab { padding:calc(7px * var(--s)) calc(16px * var(--s))",
                     "width:min(calc(520px * var(--s)), 100vw)"):
            self.assertIn(rule, index)
        self.assertIn("#organizationRoot { --s:1; }", index)               # the library page keeps its current size at every width
        self.assertIn("@media (min-width:1700px) { .grid { grid-template-columns:repeat(3", index)
        self.assertIn("@media (min-width:2800px) { .grid { grid-template-columns:repeat(4", index)
        self.assertNotIn("--wrap, 1200px", index)                            # the fallback is no longer needed: theme.css always defines it

    def test_page_widths_follow_the_scale(self):
        self.assertIn("max-width:calc(1040px * var(--s))", read("project-creation.css"))
        self.assertIn("max-width:calc(1120px * var(--s))", read("profile.css"))
        self.assertIn("max-width: calc(680px * var(--s))", read("settings.html"))
        self.assertIn("max-width:calc(980px * var(--s))", read("weekly_report.html"))

    def test_the_detail_rail_has_two_control_sizes_and_links_match_buttons(self):
        index = read("index.html")
        self.assertIn("#detail .detail-panel button, #detail .detail-panel a.btn, #detail .detail-panel select", index)
        self.assertIn("#detail .detail-panel button.tiny, #detail .detail-panel a.btn.tiny", index)
        self.assertIn(".tiny, .btn.tiny {", index)                           # a link styled as a small button is not overridden by the later .btn rule
        self.assertIn("position:static; opacity:1", index[index.index(".detail-projects .hint"):][:200])   # the card hover hint must not hide it
        self.assertIn('class="actions-main"', index)
        self.assertNotIn("'saved' : 'primary'", index)                        # one filled primary in the rail, the save toggle is outlined

    def test_the_graph_is_drawn_at_the_screen_scale(self):
        js = read("route-graph.js")
        self.assertIn("getPropertyValue('--s')", js)
        self.assertIn("onRescale", js)


class TextMustWrapTests(unittest.TestCase):
    """project-creation.css makes every h3 and button nowrap; places that hold user or AI text must opt out, and the
    two groups of buttons on a recommendation card must line up however narrow the card is."""

    def rule(self, css, selector):
        found = re.findall(r"(?:^|[}\s])" + re.escape(selector) + r"\s*\{([^}]*)\}", css)   # every rule that has exactly this selector
        self.assertTrue(found, selector)
        return ";".join(found)

    def test_the_global_nowrap_is_opted_out_where_long_concept_names_appear(self):
        css = read("project-creation.css")
        self.assertIn("white-space:nowrap", self.rule(css, "h3"))
        self.assertIn("white-space:normal", self.rule(css, ".map-detail h3"))     # the concept title in the side panel
        self.assertIn("overflow-wrap:anywhere", self.rule(css, ".map-detail"))
        name = self.rule(css, ".rg-name")                                          # nodes are buttons, which are nowrap
        self.assertIn("white-space:normal", name)
        self.assertIn("overflow-wrap:anywhere", name)
        self.assertIn("flex:none", name)                                           # the name keeps its two lines, the state label cannot squeeze it

    def test_card_action_groups_fill_the_row_so_a_wrapped_group_is_not_left_hanging(self):
        index = read("index.html")
        self.assertIn('<span class="actions-fb">', index)
        group = self.rule(index, ".card .actions .actions-fb, .card .actions .actions-end")
        self.assertIn("flex:1 1 auto", group)
        self.assertNotIn("margin-left:auto", group)
        self.assertNotIn("justify-content:flex-end", group)
        self.assertIn("flex:1 1 auto", self.rule(index, ".card .actions .actions-fb button, .card .actions .actions-end button"))


class OverviewPlaceholderTests(unittest.TestCase):
    def test_the_placeholder_page_is_centred_by_padding_alone(self):
        css = read("index.html")
        rule = re.search(r"\.mc-ph-body \{([^}]*)\}", css).group(1)
        self.assertNotIn("max-width", rule)   # max-width plus a (100% - 1200px)/2 padding left the content 0 px wide on wide windows
        self.assertIn("calc((100% - 1200px)/2)", rule)


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


class GhostHooksTests(unittest.TestCase):
    """The map can draw a direction that is only forming: a hook to decorate a node and a dashed arrow state."""

    def test_mount_offers_a_decorate_hook_called_for_every_node(self):
        js = read("route-graph.js")
        self.assertIn("decorate(element, concept, node)", js)
        self.assertIn("if (opts.decorate) opts.decorate(el, concept, n);", js)

    def test_the_ghost_node_and_arrow_have_their_own_look(self):
        css = read("project-creation.css")
        self.assertRegex(css, r"\.rg-node\.ghost\s*\{")
        self.assertRegex(css, r"\.rg-edge\.ghost\s*\{")
        self.assertRegex(css, r"\.rg-ring-track\s*\{")
        self.assertRegex(css, r"\.rg-ring-fill\s*\{")
        self.assertRegex(css, r"\.rg-ring\.is-ready\s+\.rg-ring-fill\s*\{")
