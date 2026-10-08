---
contract: implemented
operation: selection_translate
---
# Short selected-text translation

One explicit selection calls the shared gateway once. The current instruction translates paper text into Chinese, retains English terminology and asks for translation only. No tools, full PDF, other papers, history or automatic retries. No result cache is currently implemented.

The selected text is not silently shortened: the UI character boundary and the complete protocol input cap both apply. Complete wire admission may refuse a selection shorter than the character maximum because UTF8 and protocol overhead count. The response must be nonempty complete text; invalid types, empty or length-truncated output fail visibly. Unknown billing retains the cap reservation. A successful translation is AI text, not original paper text or a user note.
