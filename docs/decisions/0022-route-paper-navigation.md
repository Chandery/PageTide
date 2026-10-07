# ADR 0022 — Shared paper identity and separate graph meanings

2026-10-07. R-ROUTE-V2-08 continues on the approved Route rework branch. No AI, source calls, schema change or new external sharing is needed.

Category membership stays in the shared library's manual organization data. Learning-unit matches are derived from the selected project's live Map and title/abstract terms, with at most two matches per paper. They never write categories or grant mastery. The same paper key drives both graph views and the Today/library detail panels. Each detail shows categories, units and the current project batch's recommendation purpose separately; an earlier exposure is not called the current recommendation. Exposure names remain their historical batch names when the Map changes.

Graph navigation requires the paper to be saved in the selected project. Unsaved recommendation papers can show matching units but first require saving for graph navigation. Route off retains the Map and navigation. A graph draws at most120 papers; a requested focus_key replaces the last displayed paper if it is saved in this project, rather than increasing the cap or importing a foreign paper. An explicit unmatched entry shows the drawn unmatched papers and the complete unmatched count; omitted papers remain reachable through library search and focus navigation.

Library reset invalidates snapshot, relations, Map and detail responses by generation. Same-project/same-corpus resets still invalidate earlier requests. View changes invalidate pending Map renders. Today detail also checks project, paper request generation and closing, so a late reply cannot reopen a closed drawer or overwrite a newer paper. Read-only context requests do not mutate Map, notes, categories, exposure or familiarity.

Automated handler/HTTP/package fixtures provide local contract evidence. Full isolated flow and actual native-window acceptance remain separate requirements. The earlier actual browser permission denial and locked Mac are not bypassed. E08 stays not_run and the task stays in_progress until its full acceptance is evidenced; existing real quality/AI/billing/resource gates remain unchanged.
