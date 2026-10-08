---
contract: implemented
operation: daily_triage
---
# operation: daily_triage

Optional summaries for up to5 locally selected current-project cards, including an explicit subset selected on a card. Input: pinned terms, count of positive seeds, public paper key, title fragment<=120 characters, abstract fragment<=400 and truncation/missing flags. No PDF, full text, notes, other projects or QA history. Complete wire UTF8+256 is checked by Gateway against input4200/output1300, aggregate daily/monthly caps unchanged. One call per trigger, no retry/fallback/thinking. Explicit JSON-object mode and temperature0.

Output strict JSON object `{"items":[{"paper_id":"...","one_liner":"...","why_relevant":"...","caution":"..."}]}`; legacy bare arrays may still parse under the identical item contract. Every requested ID exactly once; all four fields text, one_liner and why_relevant nonempty. No foreign, duplicate or missing IDs, duplicate JSON keys, unknown fields or length-truncated reply. Source text is data, no tools; reasoning must cite real pinned/source material and state insufficient fragments as unknown. UI language instruction precedes candidates.

Before atomic summary writes, recheck current project membership, complete public metadata and PDF-version snapshot. Any identity/coverage/source conflict or invalid result writes no summaries and keeps local cards. Format/coverage/source failure is distinct from model usage: charges/unknown reservation remain in the gateway ledger. This contract is not proof of scientific correctness or provider tokenizer parity.
