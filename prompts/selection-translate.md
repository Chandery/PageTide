---
contract: implemented
operation: selection_translate
---
# Short selected-text translation

One explicit selection calls the shared gateway once. The current instruction translates paper text into Chinese, retains English terminology and asks for translation only. No tools, full PDF, other papers, history or automatic retries. No result cache is currently implemented.

The selected text is not silently shortened: the UI character boundary and the complete protocol input cap both apply. Complete wire admission may refuse a selection shorter than the character maximum because UTF8 and protocol overhead count. The response must be nonempty complete text; invalid types, empty or length-truncated output fail visibly. Unknown billing retains the cap reservation. A successful translation is AI text, not original paper text or a user note.

## No caps on the conversation (2026-10-22)

Owner 2026-10-22: the budget estimates, it never limits the user. The 1200-character selection limit is removed and the selection is never shortened; only the model window (1M tokens, DS-LIMITS-20261022) can refuse it. The translation may use the model's maximum output (384K), shrunk to fit the window. The registered cap is an estimate.
Because a selection is no longer bounded, the instruction now also says the source text is only material to translate and any instructions inside it are not followed (AGENTS.md rule 6).

## Word lookup (2026-10-28)

Owner 2026-10-28 asked for 划词翻译 to be structured like the macOS dictionary when one word is selected: the word with its pronunciation, its parts of speech with their meanings, and what it means in this sentence. A selection of one to three English words (at most 40 characters, `app/word_lookup.py` `is_word`, the same rule as `static/reader-word.js`) is sent with the sentence it was selected from (at most 400 characters, taken by the reader from the same page's text) and the model answers with one JSON object `{word, uk, us, senses: [{pos, meaning}], here}` (at most 5 senses). It is still one `selection_translate` call through the gateway; JSON mode is not switched on for this operation, so the reply is parsed leniently and, when it is not a usable entry, shown as plain text like a translation. The sentence is paper text and is treated as material only, like the selection. Nothing else (other pages, notes, profile, history) is sent. Longer selections keep the translation instruction above.
