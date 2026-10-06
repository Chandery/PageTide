"""One place for the papers: the top bar has a single "论文库" entry, the page is called 论文库, and it switches
between a list and a graph (the graph between paper relations and the learning map). The old names for the same
page (论文整理, 知识库, 知识图谱, 整理建议, "学习图 + 论文") are gone from what the person reads."""
import re
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
ORG = (STATIC / "organization.js").read_text(encoding="utf-8")
RETIRED = ("论文整理", "知识库", "知识图谱", "整理建议", "学习图 + 论文")


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$|\s//\s.*$", "", text)


class LibraryEntryTests(unittest.TestCase):
    def test_the_top_bar_has_one_library_entry_and_no_knowledge_entry(self):
        nav = INDEX[INDEX.index('<nav class="tabs"'):INDEX.index("</nav>", INDEX.index('<nav class="tabs"'))]
        self.assertEqual(re.findall(r'data-view="(\w+)"', nav), ["today", "library", "profile"])
        self.assertNotIn("knowledge", nav)

    def test_the_page_is_called_the_library_and_switches_between_a_list_and_a_graph(self):
        self.assertIn("<h2>论文库</h2>", ORG)
        self.assertIn('data-action="library">列表</button>', ORG)
        self.assertIn('data-action="graph">图谱</button>', ORG)
        self.assertIn("['route', '学习图',", ORG)

    def test_the_old_names_do_not_appear_in_text_the_person_reads(self):
        for name, text in (("index.html", INDEX), ("organization.js", ORG)):
            body = strip_comments(text)
            for old in RETIRED:
                self.assertNotIn(old, body, f"{old} in {name}")

    def test_the_old_hidden_library_section_is_gone_with_its_code_and_styles(self):
        for leftover in ("view-library", "我的论文库", "loadLibrary", "renderLibrary", "lib-item", "library-copy", "library-title", "#library", "libraryCount", "data-unsave"):
            self.assertNotIn(leftover, INDEX, leftover)
        self.assertIn("async function refreshStats()", INDEX)   # the top-bar counts still follow a save made on the library page

    def test_no_source_file_calls_the_page_a_knowledge_base_or_knowledge_graph(self):
        root = STATIC.parent
        for path in sorted(root.rglob("*.py")) + sorted(root.rglob("*.js")) + sorted(root.rglob("*.html")) + sorted(root.rglob("*.css")):
            if "vendor" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?i)knowledge[ -](base|graph)", str(path.relative_to(root)))

    def test_coming_back_to_the_page_returns_to_the_view_the_person_left(self):
        self.assertIn("S.modeKept = S.mode;", ORG)
        self.assertIn("(S.modeKept || 'library')", ORG)

    def test_the_category_review_button_and_its_dialogs_say_the_same_thing(self):
        self.assertIn("整理分类</button>", ORG)
        self.assertEqual(ORG.count("dialog('整理分类',"), 2)


if __name__ == "__main__":
    unittest.main()
