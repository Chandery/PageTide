"""The learning-map page's potential directions: listed on arrival, drawn on the map as ghost nodes with a progress
outline, explained in a panel, and added only by a click once the outline is a full solid line. The server side is
in test_route_growth.py."""
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
HTML = (STATIC / "route.html").read_text(encoding="utf-8")
JS = (STATIC / "route-page.js").read_text(encoding="utf-8")
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
EDITOR = (STATIC / "route-editor.js").read_text(encoding="utf-8")


class GrowthPageTests(unittest.TestCase):
    def test_the_page_has_the_section_and_explains_the_outline_and_what_counts_as_evidence(self):
        self.assertIn('data-role="findGrowth"', HTML)
        self.assertIn('data-role="growthList"', HTML)
        for wanted in ("生长证据来自你明确认为有用或选作种子的论文", "不限于探索位", "点下面的某个方向，上面的图里才会出现",
                       "“已读懂”只影响学习进度", "导入、曝光、沉默不算兴趣", "点“加入学习图”才会加入", "旧提议会过期，不自动重判"):
            self.assertIn(wanted, HTML)

    def test_directions_are_read_when_the_page_opens_and_after_each_change_to_the_map_never_by_surprise_elsewhere(self):
        self.assertEqual(JS.count("action: 'candidates'"), 1)            # one request site, in loadGrowth
        calls = [i for i in range(len(JS)) if JS.startswith("loadGrowth()", i)]
        self.assertEqual(len(calls), 8)   # declaration, load(), save, the refresh button, after add / reject / undo and after the judge response or Conflict, and revision confirmation
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
        self.assertIn("R.ghostGraph(graph, [picked])", render)           # only the direction you clicked
        self.assertIn("growth.selected && growth.result", render)
        self.assertIn("mount(part('graph'), shown,", render)
        for save in ("action: 'save', graph: state.draft", "action: 'ground', graph: sent"):
            self.assertIn(save, JS)                                   # what is sent is the draft, not the drawing
        self.assertNotIn("graph: shown", JS)

    def test_a_ghost_node_gets_the_progress_outline_a_dashed_arrow_and_its_own_panel(self):
        self.assertIn("R.ringSVG(concept.candidate.progress, concept.candidate.status === 'ready', node.w, node.h)", JS)
        self.assertIn("(String(from).startsWith('ghost:') || String(to).startsWith('ghost:')) ? 'ghost'", JS)
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
        self.assertIn('<textarea class="edit" data-role="i" maxlength="140"', JS)
        self.assertIn("最多 140 字，可以不写", JS)

    def test_what_is_sent_out_is_said_beside_the_buttons(self):
        for wanted in ("只发送概念名、检索词、项目名称和前 3 个关键词（合计前 40 个字），以及这个项目里匹配到该概念的最多 3 篇论文的标题和摘要节选", "只发送这个概念的第一个检索词去公开文献库搜一次，结果不保存"):
            self.assertIn(wanted, JS)

    def test_the_blocks_have_styles(self):
        css = (STATIC / "project-creation.css").read_text(encoding="utf-8")
        for selector in (".concept-intro", ".concept-list", ".concept-papers", ".concept-examples"):
            self.assertIn(selector, css)


class PreviewAndJudgeTests(unittest.TestCase):
    """A direction is previewed only when you click its row; the model is asked only when you click the button."""

    def test_a_row_click_only_previews_it_and_a_second_click_or_another_node_puts_it_away(self):
        click = JS[JS.index("if (kind === 'select')"):JS.index("if (kind === 'judge')")]
        self.assertIn("growth.selected = growth.selected === id ? null : id;", click)
        self.assertNotIn("await api", click)                               # nothing is requested, nothing is saved
        self.assertIn("if (!String(id).startsWith('ghost:') && growth.selected) { growth.selected = null; render(); return; }", JS)

    def test_the_map_has_no_ghost_until_a_row_is_chosen(self):
        render = JS[JS.index("function render()"):JS.index("function renderDetail()")]
        self.assertIn("const shown = picked ? R.ghostGraph(graph, [picked]) : graph;", render)
        self.assertNotIn("R.ghostGraph(graph, growth.result.candidates)", JS)

    def test_the_judge_request_has_one_site_and_is_only_reached_by_the_button(self):
        self.assertEqual(JS.count("action: 'direction-judge'"), 1)
        self.assertIn("if (kind === 'judge') { judgeNow(); return; }", JS)
        self.assertEqual(JS.count("judgeNow()"), 2)                        # the declaration and the click
        self.assertIn("未得到有效判断：${out.reason", JS)                      # a refusal is said, not hidden

    def test_the_today_page_offers_after_useful_papers_with_a_map_and_sends_nothing_until_clicked(self):
        self.assertIn("action === 'useful' && state.route && state.route.graph && state.currentProject) card.judgeAsk = true;", INDEX)
        self.assertEqual(INDEX.count("action: 'direction-judge'"), 1)
        doing = INDEX[INDEX.index("async function doJudge"):INDEX.index("function cardHTML")]
        self.assertIn("/api/route", doing)
        click = INDEX[INDEX.index("const judge = e.target.closest"):INDEX.index("const fb = e.target.closest")]
        self.assertIn("doJudge(judge.dataset.key)", click)
        self.assertNotIn("api(", click.split("else {")[1])                  # "later" records nothing

    def test_while_you_edit_a_concept_the_papers_behind_its_sentence_stay_in_view(self):
        edit = JS[JS.index("function editConcept"):JS.index("part('add').onclick")]
        self.assertIn('data-concept-papers', edit)
        self.assertIn("showMatched(concept.id)", edit)

    def test_the_pending_block_and_rows_exist_in_the_editor_helpers(self):
        for name in ("candidateRowHTML", "pendingHTML", "judgeSummary"):
            self.assertIn(name, EDITOR)


if __name__ == "__main__":
    unittest.main()
