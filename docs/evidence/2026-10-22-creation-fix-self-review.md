# Self-review: creation page guidance fields and language check boxes (2026-10-22)

Self-review by the implementing agent. It is not independent; an independent review is still to come (critical class).

## Specification pass

| owner item | where it is handled | evidence |
|---|---|---|
| AI replies land in the search box | named wire fields and descriptions (`app/guidance_contract.py` SYSTEM); parser drops questions and echoes; service never copies prose into queries | `tests/test_guidance_fields.py` (checks what is in each field, including a matrix of goals x reply shapes x modes) |
| paper language as check boxes 中文/英文 | `app/static/paper-policy.js`, `app/paper_language.py`, `app/project.py`, creation and project pages | `tests/test_paper_policy.cjs`, `tests/test_paper_language_choice.py`, `tests/test_app_server.py` |
| first impression: test thoroughly | red-first runs against the unchanged code (checks file), full Python and Node suites | `docs/evidence/2026-10-22-creation-fix-checks.txt` |

Root causes A-D from the investigation are each reproduced by a test that fails on the old code: A question in the query slot (parser and service), B `q` as a string / more than 3 choices / long summary (reply no longer refused), C Chinese-only fallback input (no query, user queries kept), D new sessions starting with the goal as the query (now empty; legacy sessions cleaned on read). The "model is never sent the current queries" and "empty list wipes the user's list" defects have their own tests.

ADR 0037 is respected: no input-size loop, no turn or length cap, `max_tokens` request unchanged (`tests/test_guidance_json_protocol.py` still asserts 384000 and whole-input sending). The beta map (ADR 0035): with it off the prompt does not ask for a map, a map that arrives is ignored, hints do not name the map, create needs no map; with it on the old map tests pass (they now switch the setting on explicitly).

## Quality pass

- Privacy and scope: new outbound fields are the current search phrases (already the person's on-screen draft) and the zh/en choice. No profile, seed id or library data. Recorded in ADR 0038 and the change record.
- Failure paths: a reply with wrong types or unknown keys is still refused whole and falls back to the local draft (tested). A bad map no longer refuses the reply (tested both ways).
- Data: no migration. `discipline` is never written when only languages are chosen, so a historical `NOT NULL DEFAULT 'cs_ai'` column keeps working (tested). Legacy languages survive a save (tested in Python and in the editor).
- Dead code: `context_limits`/`scope_notice`/`context_excerpt` for the creation conversation and `guidanceScopeHTML` are removed. The same names in `routeplan`/`route_concept_intro` are still live (papers are still omitted to fit that request) and were left alone.
- Wording: i18n extractor reports 0 of 1124 missing; unused entries for the dropdown and the removed receipt were deleted.

## Defects found and fixed while working

- My first service-level "no prose query" matrix compared against the wrong message in quick mode (test bug, fixed).
- The first version of `test_creation_page_fixes.cjs` stubbed `finalize` incompletely for `resume()` (test bug, fixed).
- Two existing tests hard-coded the old 1200 input estimate for `project_guidance`; they now read the registry.

## Limits and doubts

- No real model was called. Whether the new wording makes the model put its question in `ask` and phrases in `queries`, how often a non-question sentence still lands in `queries`, and real token use are unmeasured.
- The parser cannot recognise a statement written as a query ("建议先读综述") unless it equals `ask`/`reply`/the goal/the message.
- The keyword limit 5 and query limit 2 are judgement calls.
- Not checked in a browser or WebKit: the check boxes, the error under them, the keyword hint line and the restored-quick-draft note were verified only through vm-executed production source and static markup tests.
- A keyword-derived query can equal a very short English goal; that is kept on purpose.

## Second round (after the independent review and the coordinator's real-model run)

Each finding was re-verified against the code before fixing, with a test that failed on the round-one code (counts in the checks file).

- R1/B1 (blocking) the person's added phrases were replaced by the model's list: confirmed (parser cut to 5/2, service replaced). Now the page's lists stay in order and the model appends new items only; per-turn limits apply to additions.
- R2 the reply repeated the question: prompt now says the reply is never a question; the last question sentence is removed when `ask` carries it, an emptied reply is kept as it was.
- S1 goal/message could reach keywords and then keyword-built queries: confirmed; the parser and the service now take them as an avoid list.
- S2 the legacy goal-only query returned on the next turn of a resumed draft: confirmed; the cleanup runs in `guidance_turn` too.
- S3 `languages` was described like an output field and an echo refused the reply: now described as input; echoed input keys are ignored.
- S4 quick call/retry lost the person's edits: it now sends `draft`, and the review shows the session draft before the first call.
- S5 language not enforced: Chinese phrases added by the model need zh ticked and are limited to one; the person's own phrases are never judged; the UI suffix no longer contradicts it.
- Smaller: non-string `languages` entries ignored; preview no longer falls back to the goal; a learning path is ignored with the map off and beside any map the reply sent; the saved goal is labelled as coming from the creation conversation; dead i18n entry removed; approval note rewritten factually (owner_approved untouched); English filler words filtered in the local fallback; the language heading is a normal heading inside the card.

Doubts: only-append means stale model phrases pile up until the person deletes them; the filler list is a fixed short list; the second-round prompt was not run against a real model; browser look not checked by me.

## Third round

The "stale model phrases pile up" doubt from round two was real. The draft now keeps internal origin sets (person's items, deleted model items), derived each turn from the page's lists against the stored draft. Model turn: person's items in page order, then the model's current suggestions (5/2), replacing its earlier ones; deleted items are not re-added; an empty/unusable list keeps the page. The local fallback changes no list, adds no goal terms and no removed term. Legacy sessions without sets count everything on the page as the person's (conservative). The sets are hidden from the page's session view, not sent to the model, ignored when a client sends them, and kept by the preview. Doubts: matching is by text, so rewording a model item counts as delete + new user item; the prompt wording is not run against a real model.

## Fourth round (second independent review, fixes)

The second independent review found no blocking issue. Each finding was re-verified and fixed test-first:
F1 deleted keyword-built query returned (the built phrase was never checked against the removed list); F2 goal/message exact-match was too broad (now only sentence-like text); F3 reply splitter garbled abbreviations/quotes and left repeated questions (rewritten; a reply that is only the question is replaced by the neutral text); prompt consistency (the model now gets its own items apart from the person's); N1 deleted person items are remembered as removed; N2 case/spacing-only edits adopt a model item; N3 a draft revision (`base`) keeps a page that missed a turn from flipping authorship; N4 Chinese keywords need 中文; N5 preview cleans the legacy goal query; N6 removed items up to 200; N7 grammar of the approval note.
Doubts: the stale-page rule needs the replaced-items memory to avoid mistaking old model items for the person's, and still cannot tell a person's newly typed copy of such an item; sentence detection is rules, not understanding; the round-4 wording was re-run by the coordinator afterwards (see the checks file).
