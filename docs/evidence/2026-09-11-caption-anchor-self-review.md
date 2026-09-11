# Self-review: figure captions are now found deterministically; reader no longer jumps

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## Diagnosis

The owner asked about Figure 3 and still got "no caption in the material". Extracting
the cached full text and listing every figure mention showed the caption **was**
there (page 6): `Figure 3: GigaBrain-0's self-collected real-world robot data...`.
The failure was my retrieval: a Chinese question shares only the word "figure"
with an English caption, its IDF is low, so the caption chunk never reached the
top 8. Lexical similarity is the wrong tool for an exact anchor like a figure
number.

## Fixes

1. **`caption_passages()`** — extracts the figure/table/equation number from the
   question and pulls the passages that literally define it, placing them first in
   the prompt as "直接命中用户所问图/表的图注或定义". Deterministic, zero token,
   independent of question language.
2. **Client page locator hardened** — the previous comparison kept the dot
   ("figure3" vs "fig.3"), so `Fig. 3` never matched. It now matches by kind +
   number across pages, **prefers the page whose line starts with a caption**, and
   falls back to the page the user is currently viewing (labelled
   "图注未定位，发送的是当前页").
3. **Reader no longer jumps** — `layoutPages()` recorded the page but restored it
   with `scrollIntoView`, which lands arbitrarily. It now records the page *and*
   the offset inside it (`currentAnchor`) and restores `scrollTop` exactly; and
   the panel only triggers a re-fit when the available width actually changed.

## Verified live

- `Figure 3 展示了什么？` now answers with the page-6 caption verbatim.
- `Figure 13 讲的是什么？` answers with the page-14 caption and the ten-step
  sequence, also citing page 12.
- 101 tests pass (a new one asserts the caption anchor returns page 6 and returns
  nothing when the question has no figure number); `harness.py check` and
  `budget.py --check` pass.

## Honest limits

- The scroll-restore logic is arithmetic I cannot verify visually; it is exact
  (page offset + intra-page offset) rather than an approximation, but a real
  check on the rendered page is still the owner's.
- If a figure is never mentioned in the extracted text (e.g. a scanned page with
  no text layer) the caption anchor cannot help; the current-page image fallback
  is the remaining option.
- Recommendation quality remains unproven; quality gates stay `not_run`.
