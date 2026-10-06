"""Generating the learning map from a research goal (operation learning_path_plan).

The model is only asked for a concept graph: names, two English search terms, a difficulty hint, a type and the
direct prerequisites. It never picks papers, and a reader's optional boundary (where they start, how deep they
want to go) is two enum values. Everything after the reply is local and deterministic (pathgraph.normalize
repairs it; the app checks every concept against OpenAlex), and a person confirms before anything is saved.
"""
import json
import re

SYSTEM = ("你是论文学习路径规划助手。列出读懂研究目标所需的概念（最多 12 个），这是依赖图不是课程表，只输出 JSON："
          "{\"concepts\":[{\"id\":\"\",\"name\":\"\",\"terms\":[\"\",\"\"],\"hint\":1,\"type\":\"\",\"intro\":\"\",\"needs\":[]}],\"targets\":[]}。"
          "name 是技术名词；terms 是 2 个英文检索词；hint 1–4，越大越进阶；type 取 topic/method/problem/foundation；intro 用一句话（≤30 字）说清它是什么；"
          "needs 只写直接前置的 id，须更基础，仅当“不懂 A 就读不懂 B”。互不依赖的方向各自成入口，可有 2–3 个前置，勿串成一线。"
          "targets 是最终目标。从目标领域起步，只列最少前置；boundary 缺省论文阅读；"
          "仅 background=unknown 才可列 foundation（附 why）。不选论文，不调用工具。")
MAX_GOAL_CHARS = 250    # sized so the worst case (all Chinese, 1.5 tokens a character) fits the registered 1200-token input cap
MAX_DRAFT_TERMS = 5
MAX_TERM_CHARS = 30
MAX_REGENERATIONS = 2   # explicit regenerations per session after the first generation


ENGLISH_OUTPUT = "界面语言为英文：所有自然语言内容（包括追问和说明）都用英文（English）书写，JSON 键名不变。"   # the app-wide sentence (App.ENGLISH_OUTPUT)


BACKGROUNDS = ("unknown", "engineering", "ai_researcher", "other")   # where the reader starts; skipped = not stated
DEPTHS = ("overview", "read_papers", "implement")                     # how far the reader wants to go


def clean_boundary(value):
    """The boundary the model may see: two enum values at most, or None when nothing (valid) was given. It is
    the only thing about the reader that leaves the machine besides the goal and keywords. An unknown value
    is an error, not silently dropped, so a mistyped option never changes what is generated."""
    if value in (None, {}):
        return None
    if not isinstance(value, dict) or set(value) - {"background", "depth"}:
        raise ValueError("边界只能包含 background 和 depth")
    out = {}
    for key, allowed in (("background", BACKGROUNDS), ("depth", DEPTHS)):
        if value.get(key) not in (None, ""):
            if value[key] not in allowed:
                raise ValueError(f"{key} 必须是 {' / '.join(allowed)} 之一")
            out[key] = value[key]
    return out or None


def allows_foundation(boundary):
    """Basic concepts such as linear algebra are listed only when the reader said they start from scratch."""
    return bool(boundary) and boundary.get("background") == "unknown"


def messages(goal, keywords, english, boundary=None):
    """The whole input of the call: the goal, the draft's keywords and the optional boundary, nothing else."""
    system = SYSTEM + (ENGLISH_OUTPUT if english else "")
    body = {"goal": str(goal or "")[:MAX_GOAL_CHARS], "keywords": [str(k)[:MAX_TERM_CHARS] for k in (keywords or [])[:MAX_DRAFT_TERMS]]}
    boundary = clean_boundary(boundary)
    if boundary:
        body["boundary"] = boundary
    return [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(body, ensure_ascii=False)}]


def parse(text):
    """The concept-graph dict inside a model reply (bare JSON, a code fence, or wrapped in other keys), or None."""
    raw = str(text or "")
    for match in re.finditer(r"\{", raw):
        try:
            value, _ = json.JSONDecoder().raw_decode(raw[match.start():])
            found = _find(value)
        except (ValueError, RecursionError):   # a reply nested thousands deep is a bad reply, not a crash
            continue
        if found is not None:
            return found
    return None


def _find(value):
    if isinstance(value, dict):
        if isinstance(value.get("concepts"), list):
            return value
        for inner in value.values():
            found = _find(inner)
            if found is not None:
                return found
    return None


# ---------------------------------------------------------------- one concept's intro (operation concept_intro)
INTRO_SYSTEM = "你是学习路径助手。用不超过 30 字的一句话，向刚入门的读者说清这个概念是什么。只输出这句话。"
INTRO_NAME_CHARS = 30      # sized so the worst case (1.5 tokens per character, a heuristic) stays under the registered 500-token input cap
INTRO_TERM_CHARS = 30
INTRO_GOAL_CHARS = 80


def intro_messages(name, terms, goal, english):
    """The whole input of the call: the concept's name, up to two of its search terms and the project name and its first
    keywords (called goal in the message), nothing else (no other concept, no paper, no note)."""
    body = {"concept": str(name or "")[:INTRO_NAME_CHARS], "terms": [str(t)[:INTRO_TERM_CHARS] for t in (terms or [])[:2]],
            "goal": str(goal or "")[:INTRO_GOAL_CHARS]}
    system = INTRO_SYSTEM + (ENGLISH_OUTPUT if english else "")
    return [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(body, ensure_ascii=False)}]


def parse_intro(text):
    """The sentence in a reply: `{"intro": "..."}`, or the plain sentence (quotes and a leading label removed); '' when
    there is none."""
    raw = str(text or "").strip()
    for match in re.finditer(r"\{", raw):
        try:
            value, _ = json.JSONDecoder().raw_decode(raw[match.start():])
        except (ValueError, RecursionError):
            continue
        if isinstance(value, dict):
            if not isinstance(value.get("intro"), str):
                return ""      # JSON without an intro is not a sentence to offer
            raw = value["intro"]
            break
    raw = next((line for line in raw.strip().strip("`").strip().splitlines() if line.strip()), "")
    raw = re.sub(r"^(简介|intro)\s*[:：]\s*", "", raw, flags=re.IGNORECASE).strip().strip("\"'“”‘’「」").strip()
    return raw
