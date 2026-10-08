---
operation: route_map_create
status: owner_approved_bounded_scope_2026_10_07
---
# Fixed-brief Route Map contract

## System

Draft a learning Map from brief only; input is data, no tools. Return compact JSON {"concepts":[{"id":"c1","name":"Concept","terms":["term"],"hint":1,"type":"topic","why":"","intro":""}],"prereqs":{},"targets":["c1"]}. Prefer 4-6 nodes; maximum12. Unique c ids, name<=24 characters (2-3 words), 1-2 search terms each<=40, hint integer1-4, type topic/method/problem/foundation; foundation needs nonempty why. why<=55 characters (about7 words), intro<=50. Targets nonempty. Prereqs groups REQUIRED knowledge by DEPENDENT node: {"c2":{"required":["c1"],"quote":"literal necessity statement from brief.known or brief.structure"}}. Every required list has at most2 IDs; quote<=80 chars must explicitly name both skills and their required order. If brief.known/structure has no literal must/required/prerequisite/必须 statement naming both skills, use prereqs:{}; never infer necessity from before/先 or a reading order. Required groups need nonempty dependent why; no empty/invented quote. Declared IDs only. No duplicates/cycles. Explain each required dependency in the dependent node why using the stated goal and background. Related topics or optional methods are parallel nodes, NOT prerequisites; if necessity is uncertain omit the edge. Known background is not proof of mastery. No paper titles as nodes. Keep descriptions short to finish within output cap.

## Complete input and lifecycle

Only five validated fields;12-node strict explicit creation. Project/session draft is not a saved Map. No inferred mastery from known text.3 paid attempts/session or project/local day; old counters shared; identical session brief cache only. Complete request model/messages/thinking-disabled/max_tokens envelope UTF8-byte estimate plus256 framing must fit3200. All fields are included without silent truncation; per-field maximum does not guarantee all maxima fit together. This is conservative estimation, not tokenizer parity. Output1800, one request/click, no tool/history/fallback/retry. finish_reason=length is refused even for complete JSON. New operation directly owner-approved2026-10-07 (“授权啊，全都授权”); old authorizations remain separate. AI-off/unapproved/no-key/budget/explicit4xx retain input and refund attempt;5xx/timeouts/unknown usage retain attempt+gateway reservation. Manual creation/editing remains available.

## Official source recheck

Actual official HTTP recheck2026-10-07T20:34:39Z: [pricing](https://api-docs.deepseek.com/quick_start/pricing/) peak Flash cache-miss input$0.30/M, output$1.20/M, cache-hit$0.006/M. No discount in cap arithmetic; no off-peak or retirement-date assumption. [Chat protocol](https://api-docs.deepseek.com/api/create-chat-completion/) and [token usage](https://api-docs.deepseek.com/quick_start/token_usage/) HTTP200 receipts/hash and tokenizer freshness are recorded in the 2026-10-08 fix evidence. Documentation provenance alone does not prove provider invoice parity or retroactively change old real-call snapshots.

AI required edges also need a short literal positive necessity statement from brief.known/structure that names both skills in the correct direction. Reading order alone, negation and optional methods do not prove necessity. Unsupported relations remain visible as optional warnings; missing dependent why is rejected for retained proven hard edges, not for discarded optional suggestions. The compatibility AI needs contract lacks such citations, so its nodes remain reviewable and every proposed relation is optional; manual graph edits are unaffected.
