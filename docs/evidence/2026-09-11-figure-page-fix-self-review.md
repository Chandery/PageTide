# Self-review: figure page location fix + hover preview fix

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## Bug 1: the assistant kept sending the wrong page

The owner asked about Figure 9 and received a picture of Figure 8, labelled
"图注未定位，发送的是当前页". Two separate faults:

1. **Client never had the page texts.** `extractFulltext()` returned early when
   the server already had the full text cached — which is the normal case after
   the first open — and only populated `R.pageTexts` on the *extraction* path. So
   the local figure locator always had nothing to search and always fell back to
   the current page.
2. **Scoring was wrong even with text.** I scored pages by counting references and
   gave captions only +5. A body page referencing eight figures out-scores the one
   page that actually defines the figure, so Figure 8 resolved to page 11 (a
   reference) instead of page 11's caption elsewhere / page 16.

Fixes:

- **The server decides the page** (`GET /api/figure-page`), because it holds the
  cached full text: caption at line start wins outright, then a mid-line caption
  followed by a colon, and only then reference counting. The client just renders
  the page it is told; the local locator is only a fallback when there is no
  cached text, and the current page remains the last resort.
- `/api/fulltext?text=1` now also returns the page texts, and the client stores
  them, so the fallback is not blind either.

## Bug 2: hover preview sometimes did nothing

`renderCards()` rebuilds the card DOM after every feedback, triage or generation,
but `hoverKey` kept its old value. The `mouseover` handler returns early when the
hovered card equals `hoverKey`, so hovering that same card again never started the
500ms timer and no preview appeared — "根本没有交互". Re-rendering now clears the
hover timer, `hoverKey` and any open preview.

## Verified

- **27 caption pages across two real cached papers** were computed independently
  in the test (regex over the stored text) and compared with the endpoint:
  **0 mismatches** for `arxiv.2510.19430` (20 captions) and `arxiv.2608.27033`
  (7 captions). A missing figure (`Figure 42`, `Figure 99`) returns `None`.
- 105 tests pass, including caption-over-reference preference, mid-line captions,
  and `None` for unknown numbers and questions without a figure number.
- Both inline scripts pass `node --check`; `harness.py check` and
  `budget.py --check` pass.

## Honest limits

- A page whose caption is not in the PDF text layer at all (scanned pages) still
  cannot be anchored; the current-page image fallback is the remaining option.
- The hover fix is logic-level; the visual result is still the owner's to confirm.
- Recommendation quality remains unproven; quality gates stay `not_run`.
