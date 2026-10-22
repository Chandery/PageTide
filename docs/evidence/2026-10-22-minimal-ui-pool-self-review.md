# 2026-10-22 whitespace-first UI and recommendation-pool rules — self-review

Reviewer: coordinating agent, not independent. Class critical because the unit edits `harness/tasks.json` (wording of the
hotspot default). No independent review has been done; one is required before any release. Baseline: preview merge
`a6f45b7` (restyle + learning-map beta switch). Decisions: ADR 0036 (and the correction recorded in ADR 0035).

## What was done and how

- UI text: the coordinator simplified the home page, paper drawer and profile by hand; implementation subagents (Sonnet)
  simplified the library, import, learning map, creation/project, settings/weekly and the reader/assistant, each on its own
  files, under one rule sheet. A first batch launched on the wrong model was stopped and its half-finished files restored
  from the checkpoint commit before relaunch.
- 133 tests failed after the text pass. Four Sonnet agents sorted them: wording-only assertions were updated (120);
  behaviour changes were reported, not papered over. The coordinator restored four behaviours rather than accept the
  removal: the "重新匹配" action, the "另带上了 N 项" notice, an honest "AI 回复不可用 · 用量未确认" instead of "未使用 AI"
  for a paid unusable reply, and a one-line folded "AI 只看到部分内容" receipt. Removals that stand: judgment history,
  import match-source labels, card status pills.
- Settings keeps short cost honesty: test result "本次 N token" or "用量未确认", usage line "含未确认的用量".
- Pool rules: failing tests first for `no_pdf_source` (9 cases), recency-as-weight (5 cases) and the English-abstract
  fallback (6 cases: detector, reported language never overridden, Chinese title still held, nothing written back).
- Root cause of the owner's "没有符合条件的候选论文": measured on a private copy of the owner's data (API keys not copied):
  all 46 papers inside the owner's 7-day window were `language_unknown` (OpenAlex reports no language for arXiv
  preprints). After the fix the same copy gives 405 / 299 recommendable papers in the two projects and a real 5-paper
  batch from the button.

## Limits

- Pages seen in a browser: home, drawer, profile, library, settings, creation, weekly (synthetic and real-copy data).
  Learning-map page (beta on) and import steps were checked by tests only.
- The English-abstract check is a heuristic; recommendation quality was not evaluated.
- The owner's real settings still say "最近 1 周"; only the preview copy was changed.
- No native window check before the build below.
