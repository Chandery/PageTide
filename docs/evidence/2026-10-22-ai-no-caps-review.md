# 2026-10-22 budget estimates, no caps on AI conversations — review

Class critical (gateway, budget registry, prompts). Implementation: coordinating agent; the test rewrite to the new
contract by an implementation subagent (Sonnet). Independent review: a separate review agent (Opus), read-only, over
the app/harness/prompts/docs diff against main 46b807e; it did not write the change. No real model call was made.

## Owner decision

"不要给 ai 对话设上限啊，预算只是用来预估的，并不是用来限制用户的". Asked about answer length (with the DeepSeek
JSON-mode whitespace risk stated), the owner chose "对话放开，后台留保护". Reports in the same session: reader QA said the
abstract excerpt was cut and no body excerpt was sent; "AI 回复须为非空完整文本" (length-truncated replies).

## Review findings and resolution

No blocking finding. Should-fix:

1. project_guidance (JSON mode) gets the 384K output. — Kept by owner choice: it is a conversation and the owner chose
   "对话放开" after being told of the JSON-mode risk. ADR 0037 and prompts now say so instead of contradicting it.
2. The model was still told "6max" and the turn was clamped to 6. — Fixed: RULES say "turn>=6:offer confirm,keep
   helping"; the real turn number is sent; prompts/project-guidance.md System text updated.
3. Enabled (developer) ceilings checked the estimate but recorded the larger real reservation. — Fixed: a new
   `Gateway.check_aggregate` judges the real reservation inside the ledger lock; test added (55k/day refuses a
   conversation before sending, nothing recorded).
4. Usage display counted whole-answer placeholders as spending. — Fixed: settings and home show confirmed use only
   (total minus held reservations) and "另有 N 次用量未确认"; test added.
5. Leftover UI caps (guideMessage maxlength 2000, choice buttons disabled at turn 6). — Removed, plus the goal
   maxlength 4000 and the server's 4000-character goal limit.
6. The model saw the whole session while the panel showed 20 messages. — The panel now shows the same whole session;
   ADR 0037 states how this relates to AGENTS.md rule 8.

Docs: PRODUCT.md, the generated budget document text (scripts/budget.py, regenerated), budget.json scope strings and
the DS-LIMITS source (8K default, 1..393216 range) updated. Notes taken: the translate prompt now says the source text
is only material and its instructions are not followed; the byte bound is conservative (about 250K real English
tokens) and ADR 0037 says so. Not changed (out of the owner's "conversation" scope, listed for the owner): structured
operations still choose their inputs by design (concept_intro still says "部分匹配论文因本次预算未发送"), and the
learning-path daily attempt limit is untouched.

## Not measured

No real model call: answer quality with long histories, latency near the window and real billing are unmeasured.
