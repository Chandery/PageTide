"""The import page and the two ways into it: structure, wiring and entry points. No browser: these read the files,
and the page is also fetched through the real server."""
import re
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import server

STATIC = ROOT / "app" / "static"
HTML = (STATIC / "import.html").read_text(encoding="utf-8")
JS = (STATIC / "import.js").read_text(encoding="utf-8")
ORG = (STATIC / "organization.js").read_text(encoding="utf-8")
CREATE_HTML = (STATIC / "project_creation.html").read_text(encoding="utf-8")
CREATE_JS = (STATIC / "project-creation.js").read_text(encoding="utf-8")
# Elements the script builds itself, so they are not in the page markup.
BUILT_BY_SCRIPT = {"matchMore", "settleMore", "undoCats", "retryCats"}


class PageStructureTests(unittest.TestCase):
    def test_scripts_load_in_dependency_order_and_all_are_local(self):
        order = re.findall(r'<script src="(/[^"]+)"', HTML)
        self.assertEqual([s for s in order if s != "/i18n/current.js"], ["/theme.js", "/math.js", "/dialogs.js", "/creation-pdf.js", "/pdf-hints.js", "/import-files.js", "/import.js", "/tour.js"])
        self.assertNotRegex(HTML, r'(?:src|href)="https?://')
        self.assertNotRegex(HTML, r'\son(?:click|change|load)=')

    def test_every_element_the_script_looks_up_exists(self):
        ids = set(re.findall(r'\bid="([^"]+)"', HTML))
        wanted = set(re.findall(r"\$\('#([A-Za-z0-9_-]+)'\)", JS)) - BUILT_BY_SCRIPT
        self.assertEqual(sorted(wanted - ids), [])

    def test_every_step_the_script_shows_has_a_panel_and_a_progress_marker(self):
        for step, panel in (("source", "stepSource"), ("working", "stepWorking"), ("review", "stepReview"), ("done", "stepDone")):
            self.assertIn(f'id="{panel}"', HTML)
            self.assertIn(f'data-step="{step}"', HTML)

    def test_the_folder_picker_uses_the_webview_directory_input_and_pdf_picker_is_multiple(self):
        self.assertRegex(HTML, r'<input type="file" id="folderInput" webkitdirectory multiple hidden>')
        self.assertRegex(HTML, r'<input type="file" id="filesInput" accept="application/pdf,\.pdf" multiple hidden>')

    def test_the_online_lookup_says_exactly_what_is_sent(self):
        self.assertIn("只向 OpenAlex 发送 DOI、arXiv 编号和题目", HTML)
        self.assertNotIn("PDF 文件本身和你的论文库不会上传", HTML)
        self.assertIn('id="optOnline" checked', HTML)

    def test_importing_is_never_described_as_liking(self):
        # The standing reassurances were removed from the page; nothing may call an import a liking either.
        self.assertNotIn("不会被当作你的兴趣信号", HTML)
        self.assertNotIn("不会作为学习图生长的依据", HTML)
        self.assertNotRegex(HTML, r"导入.{0,6}(喜欢|感兴趣)")

    def test_an_export_file_is_uploaded_before_the_pdfs_and_the_reference_only_option_appears_with_it(self):
        self.assertIn('id="optFileless"', HTML)
        self.assertRegex(HTML, r'id="filelessRow" hidden')
        self.assertIn("include_fileless: $('#optFileless').checked", JS)
        self.assertIn("api(`/api/import/batches/${id}/sidecar`", JS)
        self.assertIn("'X-Filename': encodeURIComponent(", JS)
        self.assertLess(JS.index("await uploadSidecar("), JS.index("S.queue = [...picked.pdfs]"))
        self.assertIn("$('#filelessRow').hidden", JS)

    def test_a_reference_without_a_file_is_marked_instead_of_showing_an_empty_path(self):
        self.assertRegex(JS, r"item\.kind === 'entry' \? '<span class=\"tag\">无 PDF</span>'")

    def test_every_reason_the_server_can_pause_for_has_a_message(self):
        reasons = set(re.findall(r'_pause\(batch_id, "([a-z_]+)"\)|_Pause\("([a-z_]+)"\)', (ROOT / "app" / "library_import.py").read_text(encoding="utf-8")))
        names = {a or b for a, b in reasons}
        self.assertTrue({"openalex_quota", "network", "cancelled", "error", "busy"} <= names, names)
        for name in names:
            self.assertRegex(JS, rf"\b{name}:\s*'", name)

    def test_the_pause_button_is_bound_before_any_upload_starts(self):
        # It used to be bound only when matching began, so it did nothing while files were being read and sent.
        self.assertEqual(JS.count("$('#stop').onclick"), 1)
        self.assertLess(JS.index("$('#stop').onclick"), JS.index("async function startImport()"))
        self.assertIn("S.stage = 'upload'", JS)
        self.assertIn("S.stage = 'resolve'", JS)

    def test_files_that_could_not_be_saved_stay_visible_on_the_review_step_with_a_way_to_send_them(self):
        for element in ('id="failedBox"', 'id="failedList"', 'id="addMore"', 'id="continueBox"', 'id="continueSkip"'):
            self.assertIn(element, HTML)
        self.assertIn("S.uploadFailed", JS)
        self.assertIn("continueUpload(", JS)

    def test_an_interrupted_batch_can_be_resumed_whatever_stage_it_stopped_in(self):
        self.assertIn("['collecting', 'resolving', 'paused', 'review', 'committing']", JS)
        self.assertIn("'重试提交'", JS)
        self.assertIn("'补传并继续'", JS)

    def test_pausing_when_nothing_is_left_to_read_does_not_claim_files_are_unread(self):
        self.assertIn("`已暂停，还有 ${S.queue.length} 个文件未读取` : '已暂停'", JS)
        self.assertNotIn("已暂停：文件都已读取完。点「继续」开始匹配。", JS)
        self.assertRegex(JS, r"S\.queue\.length\s*\?")

    def test_the_person_is_never_stuck_waiting_on_a_lookup_that_cannot_finish(self):
        self.assertIn('id="settle"', HTML)
        self.assertIn("/settle", JS)
        self.assertIn("confirm(", JS[JS.index("function settleRest"):])

    def test_polling_cannot_overlap_or_show_rows_of_an_older_request(self):
        self.assertIn("S.ticking", JS)
        self.assertIn("S.rowsToken", JS)
        self.assertRegex(JS, r"detail\.status === 'resolving' && !detail\.worker_alive|!detail\.worker_alive && detail\.status === 'resolving'")

    def test_what_the_page_says_about_the_network_and_about_keeping_the_batch_is_true(self):
        # With online lookup off nothing is sent by the import itself; a lookup the person types is their own query.
        self.assertNotIn("不会向 OpenAlex 发送任何内容。", JS)
        self.assertNotIn("一直保留", JS)        # an unfinished batch is purged after 30 days; never promise otherwise
        self.assertNotIn("联网补全已关闭：导入不会自动向 OpenAlex 发送任何内容", JS)   # the standing network note is gone

    def test_a_second_pdf_for_the_same_paper_is_reported_on_the_done_step(self):
        self.assertIn("result.extra_pdfs", JS)
        self.assertIn("个 PDF 未归档（论文已有 PDF）：", JS)

    def test_more_than_one_export_file_adds_no_explanatory_line(self):
        self.assertNotIn("找到多个导出文件", JS)

    def test_a_bad_export_does_not_stop_the_pdfs(self):
        self.assertIn("S.sidecarError", JS)

    def test_the_summary_counts_papers_not_placements(self):
        # A paper found in two folders is one paper in two categories: "placed N papers" must count papers.
        self.assertIn("result.changed_papers", JS)
        self.assertNotIn("result.added_memberships", JS)

    def test_an_unidentified_pdf_is_labelled_once(self):
        self.assertRegex(JS, r"paper\.unresolved \? '<span class=\"tag unresolved\">未识别</span>'")
        self.assertNotIn("SOURCE_LABEL", JS)                     # per-row match provenance is not shown (2026-10-22)

    def test_nothing_in_the_script_calls_a_model_or_an_external_service(self):
        self.assertNotRegex(JS, r"https?://")
        self.assertNotIn("/api/gateway", JS)

    def test_dynamic_text_from_files_and_papers_is_escaped_and_not_translated(self):
        # User titles and paths stay raw. Typed errors localize only known system frames, then escape.
        for fragment in ("${esc(item.relative_path", "${esc(paper.title)}", "${esc(p.title)}", "${esc(systemError(item.error"):
            self.assertIn(fragment, JS)
        self.assertNotRegex(JS, r"innerHTML\s*=\s*[^;]*\$\{(?:item|paper|p)\.(?:title|relative_path|error)\}")


class EntryPointTests(unittest.TestCase):
    def test_the_library_toolbar_has_an_import_button_that_carries_the_project(self):
        self.assertIn('data-action="import"', ORG)
        self.assertIn("导入论文</button>", ORG)
        self.assertRegex(ORG, r"case 'import':[^\n]*import\.html\?project_id=")


    def test_project_creation_offers_to_import_an_existing_library_in_every_mode(self):
        self.assertEqual(CREATE_HTML.count('id="importAfter"'), 1)
        self.assertIn("创建后导入我已有的论文库", CREATE_HTML)
        # One shared choice, above the mode forms, so quick, guided and manual all honour it.
        self.assertLess(CREATE_HTML.index('id="importAfter"'), CREATE_HTML.index('id="quickForm"'))

    def test_every_redirect_after_creation_goes_through_the_one_chooser(self):
        self.assertEqual(len(re.findall(r"location\.href = [^;\n]*project_id=", CREATE_JS)), 0)
        self.assertEqual(CREATE_JS.count("afterCreate("), 3)   # the definition and the two creation paths
        self.assertIn("/import.html?project_id=", CREATE_JS)
        self.assertIn("from=creation", CREATE_JS)


class ServedPageTests(unittest.TestCase):
    def test_the_page_and_its_assets_are_served_with_the_language_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            httpd = server.build_server(port=0, root=tmp)
            port = httpd.server_address[1]
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            self.addCleanup(httpd.server_close)
            self.addCleanup(httpd.shutdown)
            for name, marker in (("import.html", "导入已有论文库"), ("import.js", "PTImportFiles"), ("import.css", ".steps"),
                                 ("import-files.js", "walkEntries"), ("pdf-hints.js", "extractHints")):
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/{name}", timeout=5) as response:
                    body = response.read().decode("utf-8")
                self.assertEqual(response.status, 200, name)
                self.assertIn(marker, body, name)
                if name.endswith(".html"):
                    self.assertIn("/i18n/current.js", body)


if __name__ == "__main__":
    unittest.main()
