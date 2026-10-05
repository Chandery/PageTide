# Self-review: 2026-10-06-project-tabs

Owner direction after the first stage-3 build: no "current project / all projects" switch; put the projects as the outermost level of the left directory, as a panel of tabs (全部 + one per project), for both the library and the knowledge base, so choosing a project tab isolates it. Done that way. The category tree and notes remain one shared set (view-level isolation, chosen by the owner earlier), so categories that exist in several projects are marked 跨项目 with per-project counts, and categories holding only other projects' papers are folded behind a note in a project tab.

Judgement calls: the tab starts on the current project and then stays where the person put it; picking a tab resets the category filter and the graph focus (a category from another tab may not exist there); a partial view never saves or overrides layout positions (this is the main safety rule); the graph focus modes (全貌 / 当前类别 / 论文·1 跳 / 论文·2 跳) and the 60-paper overview guard from the first design are kept.

Weak spots: renderGraph and the reset/reopen path have no DOM test; the final design was not re-reviewed; the panel has no dark-mode or large-screen check; notes are still per paper across projects, which the page does not yet say.
