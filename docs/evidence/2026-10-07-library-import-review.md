# Independent review: library import (2026-10-07)

Reviewer: a separate read-only subagent (superpowers:code-reviewer) given the diff, the decisions and the invariants; it ran the suites and probed some cases itself. It did not see this session's reasoning. It is independent of the implementing context but is **not** the owner's or a human review, and it did not run the packaged app, a real network or a real Zotero export. It does not replace the release review E-LIBRARY-IMPORT asks for.

Result: no P1 (no data loss, privacy breach or broken core flow found). 10 P2 and a list of P3. Each finding was checked against the code before acting; all P2 were real or at least a documentation overstatement.

## P2

| # | Finding | Disposition |
|---|---|---|
| 1 | Two different PDFs matched to one paper replaced each other; `already_in_library` counted the batch's own paper | Fixed. One current PDF per paper per commit; extra files are not archived (originals untouched) and named in the result and on the done page; with "replace" every file is recorded in order and the history keeps them. Test: `test_two_different_pdfs_of_one_paper_do_not_replace_each_other` and two more |
| 2 | An identifier read off the first pages was trusted without checking the title (could be a cited paper) | Fixed. A PDF-sourced match whose title shares almost nothing (<0.25, titles of ≥3 words) with the title read from the same PDF becomes "needs a choice". Export-sourced matches are never questioned. `IdentifierSanityTests` |
| 3 | The pause button did nothing during upload | Fixed (one handler bound once, works in both stages). Verified in the browser: pause during upload took effect |
| 4 | Files that failed to upload vanished from the review | Fixed. Listed on the confirm step with "send these files again". Verified in the browser |
| 5 | Resuming an interrupted upload could not upload the missing files | Fixed. "补传并继续" returns to step 1 with the batch's options fixed; only missing files are sent (browser: `1 / 1`) |
| 6 | Quota exhaustion blocked the commit | Fixed. `settle_rest` / `/settle` ("stop looking up, import the rest as they are"), nothing is sent; refused while a resolver runs |
| 7 | A "poison" DOI could pause the batch for ever (HTTP 4xx treated as no network) | Fixed. 4xx other than 429 is `invalid_input`, not `network_error`; a refused batch is retried one DOI at a time so only the offender fails; export entries fall back to the export's record. Not verified against the live API |
| 8 | "Online off = zero network" was false for a typed lookup | Resolved by wording, not by disabling: a lookup the person types is their own query (as on the creation page). Page text, ADR and ARCHITECTURE now say so; a test pins the behaviour |
| 9 | A batch stuck in `committing` was invisible and could not be removed | Fixed. Listed with "重试提交" |
| 10 | Docs said "unique best" but ties were decided by the first | Fixed in code: best must beat the runner-up by 0.05 and the title needs ≥2 words, otherwise a choice is offered |

## P3

Fixed: seed consumer `_route_recall_interest` documented in the ADR (import seeds steer discovery queries by design; they are still not growth evidence or map progress); regex quadratic on `\'` + spaces (linear now); RIS wrapped lines (linear); CSL-JSON hostile shapes (never an exception), list-valued `container-title`/`title`, odd `date-parts`; BibTeX DOI `\_`; docstring escape warning (compile with warnings as errors is tested); an entry naming an identical copy now finds its PDF; discard while a resolver runs (server refuses; the resolver can no longer bring a closed batch back); UI polling overlap and stale rows (tokens); a `resolving` batch with a dead worker is treated as paused; `files/<n>` rule scoped to Zotero batches so a real `files/2023` folder is kept; an export entry whose lookup fails falls back to the export's record; more than one export file says which one was read; one-word titles never auto-match.

Not fixed, recorded: two names that differ only in the number of spaces collapse to one path (the second replaces the first in the batch; ADR "failure paths"); a lock file per committed batch accumulates in `operation-locks/`; no automated DOM-level tests of the page (structure tests plus manual browser runs only).

## Not verified by the reviewer or by me
Live OpenAlex behaviour (400 handling, OR-filter, credit cost), WKWebView folder pick/drop, real Zotero/Better BibTeX output, a 2000-file upload under real concurrency.
