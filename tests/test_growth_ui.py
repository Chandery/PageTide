"""The learning-map page's potential directions: listed on arrival, drawn on the map as ghost nodes with a progress
outline, explained in a panel, and added only by a click once the outline is a full solid line. The server side is
in test_route_growth.py."""
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
HTML = (STATIC / "route.html").read_text(encoding="utf-8")
JS = (STATIC / "route-page.js").read_text(encoding="utf-8")


class GrowthPageTests(unittest.TestCase):
    def test_the_page_has_the_section_and_explains_the_outline_and_what_counts_as_evidence(self):
        self.assertIn('data-role="findGrowth"', HTML)
        self.assertIn('data-role="growthList"', HTML)
        for wanted in ("打开这一页就会列出已经出现的潜在方向", "整圈变成实线才能加入", "“有用”“已读懂”",
                       "“不感兴趣”“太难”和没点过的论文都不算", "点“加入学习图”才会加入"):
            self.assertIn(wanted, HTML)

    def test_directions_are_read_when_the_page_opens_and_after_each_change_to_the_map_never_by_surprise_elsewhere(self):
        self.assertEqual(JS.count("action: 'candidates'"), 1)            # one request site, in loadGrowth
        calls = [i for i in range(len(JS)) if JS.startswith("loadGrowth()", i)]
        self.assertEqual(len(calls), 5)   # declaration, load(), save, the refresh button and the click handler
        load = JS[JS.index("async function load()"):JS.index("function render()")]
        self.assertIn("loadGrowth();", load)
        save = JS[JS.index("part('save').onclick"):JS.index("part('modeSeg').onclick")]
        self.assertIn("loadGrowth();", save)

    def test_a_failed_read_only_affects_this_block(self):
        grow = JS[JS.index("async function loadGrowth()"):JS.index("part('findGrowth').onclick")]
        self.assertIn("潜在方向没有读到", grow)
        self.assertIn("catch (error)", grow)

    def test_the_ghosts_are_drawn_from_a_copy_and_never_enter_the_draft(self):
        render = JS[JS.index("function render()"):JS.index("function renderDetail()")]
        self.assertIn("R.ghostGraph(graph, growth.result.candidates)", render)
        self.assertIn("mount(part('graph'), shown,", render)
        for save in ("action: 'save', graph: state.draft", "action: 'ground', graph: sent"):
            self.assertIn(save, JS)                                   # what is sent is the draft, not the drawing
        self.assertNotIn("graph: shown", JS)

    def test_a_ghost_node_gets_the_progress_outline_a_dashed_arrow_and_its_own_panel(self):
        self.assertIn("R.ringSVG(concept.candidate.progress, concept.candidate.status === 'ready', node.w, node.h)", JS)
        self.assertIn("String(to).startsWith('ghost:') ? 'ghost'", JS)
        self.assertIn("R.ghostDetailHTML(found, {locked: state.dirty})", JS)

    def test_accepting_and_rejecting_carry_the_revision_so_a_stale_page_is_refused(self):
        self.assertIn("revision: state.route.revision", JS)
        self.assertIn("'candidate-accept'", JS)
        self.assertIn("'candidate-reject'", JS)

    def test_the_same_buttons_work_in_the_list_and_in_the_panel(self):
        self.assertIn("part('growthList').onclick = growthClick;", JS)
        self.assertIn("part('detail').addEventListener('click', growthClick);", JS)

    def test_directions_are_locked_while_edits_are_unsaved(self):
        self.assertIn("locked = state.dirty", JS)
        self.assertIn("renderGrowth();", JS)

    def test_the_step_taken_back_is_the_one_shown_and_only_while_it_is_still_the_latest(self):
        self.assertIn("event: Number(button.dataset.event)", JS)
        self.assertIn("growth.undo.revision === state.route.revision", JS)
        self.assertIn('data-event="${esc(growth.undo.id)}"', JS)
        self.assertIn("locked ? ' disabled", JS)


class ConceptUnderstandingPageTests(unittest.TestCase):
    """What a node is: its sentence, its role, the project's own papers and a few public ones. Nothing here is saved
    until the person saves the map, and the AI sentence is only ever put in the edit box."""

    def test_each_read_has_exactly_one_request_site_and_the_ai_one_is_a_click(self):
        for action in ("concept-papers", "concept-examples", "concept-intro"):
            self.assertEqual(JS.count(f"action: '{action}'"), 1, action)
        self.assertIn("showMatched(id)", JS)
        self.assertIn("part('detail').addEventListener('click'", JS)
        ask = JS[JS.index("function askIntro"):JS.index("async function mark")]
        self.assertNotIn("state.draft =", ask)         # the sentence is held aside, not written into the map
        self.assertIn("state.pendingIntro = {id, text: out.intro}", ask)

    def test_the_sentence_is_labelled_by_who_wrote_it_and_editing_it_makes_it_yours(self):
        for wanted in ("这句话是 AI 写的；改过之后就算你写的。", "这句话是你写的。", "intro_by"):
            self.assertIn(wanted, JS)

    def test_the_edit_box_has_an_optional_ninety_character_introduction(self):
        self.assertIn('<textarea class="edit" data-role="i" maxlength="90"', JS)
        self.assertIn("最多 90 字，可以不写", JS)

    def test_what_is_sent_out_is_said_beside_the_buttons(self):
        for wanted in ("只发送概念名、检索词、项目名称和前 3 个关键词（合计前 80 个字）", "只发送这个概念的第一个检索词去公开文献库搜一次，结果不保存"):
            self.assertIn(wanted, JS)

    def test_the_blocks_have_styles(self):
        css = (STATIC / "project-creation.css").read_text(encoding="utf-8")
        for selector in (".concept-intro", ".concept-list", ".concept-papers", ".concept-examples"):
            self.assertIn(selector, css)


if __name__ == "__main__":
    unittest.main()
