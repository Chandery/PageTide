"""AI-guided project creation helpers.

Simplified version: generates prompts for AI keyword/paper suggestions
and provides basic parsing. Full conversational UI is deferred.
"""


def create_guided_prompt(user_input):
    """Create a prompt for AI to suggest keywords/papers/learning paths.

    Args:
        user_input: User's description of their research interests

    Returns:
        str: Prompt to send to AI model
    """
    return f"""你是一位学术研究助手。用户想要开始一个新的研究项目，他们的兴趣描述如下：

"{user_input}"

请提供：
1. 5-10个相关的学术关键词（英文）
2. 3-5篇推荐的论文标题和作者
3. 一个简短的学习路径建议

请用 JSON 格式回复：
{{
  "keywords": ["keyword1", "keyword2", ...],
  "papers": [
    {{"title": "Paper Title", "authors": "Author Names"}},
    ...
  ],
  "learning_path": "简短的学习路径描述"
}}"""


def parse_guided_response(ai_response):
    """Parse AI response for guided project creation.

    Args:
        ai_response: Raw AI response text

    Returns:
        dict with keywords, papers, and learning_path, or None if parsing fails
    """
    import json
    import re

    # Try to extract JSON from response
    # Look for JSON block between ```json and ``` or just raw JSON
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', ai_response, re.DOTALL)
    if not json_match:
        json_match = re.search(r'(\{.*?\})', ai_response, re.DOTALL)

    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Fallback: return empty structure
    return {
        "keywords": [],
        "papers": [],
        "learning_path": "请手动输入关键词以开始。",
    }
