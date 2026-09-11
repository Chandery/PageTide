# Self-review: whole-paper context and vision for figure/table questions

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## Why

The owner showed a real failure: asked about Fig. 2, the assistant could only
see title + abstract and had to refuse. Abstract-only context makes detailed
questions meaningless.

## What was built

1. **Whole-paper context (zero token).** When the reader opens, the browser
   extracts each page's text with pdf.js and posts it to `POST /api/fulltext`;
   the server caches it in a new `fulltext` table. For every question the server
   picks the most relevant passages with local TF-IDF (`passages()`), labels each
   with its page number, and includes them — 8 chunks normally, 14 with the new
   「更多上下文」toggle.
2. **Vision for figure/table questions.** A figure/table pattern in the question
   (`fig`, `figure`, `table`, `eq`, 图, 表, 公式) triggers a local caption search
   across the extracted page texts; the matched page is rendered to a JPEG in the
   browser and sent as an OpenAI-compatible `image_url` content part through the
   same gateway. DeepSeek's own docs confirm `deepseek-flash` accepts vision, so
   this is a **payload-mode switch, not a model switch**.
3. **Registered, not silent.** New operation `paper_vision_qa` with its own
   envelope in `budget.json`, its own prompt contract
   (`prompts/paper-vision-qa.md`), a `DS-VISION` source entry, and a
   `vision_qa_starter` scenario. Answers are labelled
   `视觉 · 第 N 页` or `全文检索 · 命中第 N 页`, and the toast shows the tokens
   and cost.
4. A full-text status chip in the panel (`全文已缓存 · N 页 / Mk 字符`).

## Verified live (not just unit tests)

- Extracted a real 25-page paper with pdf.js in Node and cached it:
  `{"pages":25,"chars":72200}`; `GET /api/fulltext` agreed.
- Text-mode question 「这篇论文的 Figure 2 展示的是什么？」 retrieved 7 passages
  (6,241 chars) and answered correctly that the paper has **no** Figure 2, listing
  the figures that do exist (4, 7, 9, 10, 11–16, 18, 19) instead of inventing one.
- Vision-mode call accepted the content-part request shape: `ok: true`,
  `mode: vision`, 2,839 tokens, $0.00102, and the answer referenced the page text
  as well as the (deliberately unreadable) test image.
- 101 tests pass, including new ones for the full-text cache, passage retrieval,
  empty-retrieval handling, and that a vision question uses the
  `paper_vision_qa` operation with a proper `image_url` part.
  `harness.py check` and `budget.py --check` pass.

## Honest limits

- The vision call was verified with a 1×1 test JPEG to prove the request shape
  and cost path, **not** with a real rendered figure, so vision accuracy on an
  actual plot is unverified.
- Image tokens are an estimate (~1,500 per page at JPEG scale 1.7); a dense page
  may cost more.
- Extraction happens in the background after the reader opens; a question asked
  before it finishes falls back to the abstract for that answer.
- Sending a rendered page means that page leaves the machine; it is public
  arXiv content and only happens when the question or the route asks for it.
- Retrieval is lexical, so a question whose wording does not overlap the paper's
  wording can still miss the right passage.
