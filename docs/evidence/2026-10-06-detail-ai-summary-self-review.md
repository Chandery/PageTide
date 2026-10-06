# Self-review: 2026-10-06-detail-ai-summary

Front-end only, zero model tokens (reads stored summaries). Staged as hunks and gated in a clean worktree because another session has unfinished suggestion-review edits in the shared tree. Weak spots: the fetch-on-demand path has no automated test (checked in a browser); a summary written after the pane was first opened appears on the next open (cached per paper for the page's lifetime); the pane still lacks the save toggle and add-to-project controls.
