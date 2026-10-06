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
INTRO_SYSTEM = ("你是学习路径助手。依据给出的论文标题和摘要节选，写一段不超过 120 字的话：先说这个概念在这些论文里指什么，"
                "再写学习它的门槛：要先懂什么、难在哪。不要只解释名词，不要重复概念名，不要编造论文里没有的内容。"
                "没有论文时只依据概念名和检索词。只输出这段话。")
INTRO_NAME_CHARS = 30      # sized so the worst case (1.5 tokens per character, a heuristic) stays under the registered input cap
INTRO_TERM_CHARS = 30
INTRO_GOAL_CHARS = 40
INTRO_PAPERS = 3           # the concept's own matching papers the model may see
PAPER_TITLE_CHARS = 80
INTRO_ABSTRACT_CHARS = 200


def _paper_for_model(paper, abstract_chars):
    return {"title": str(paper.get("title") or "")[:PAPER_TITLE_CHARS], "abstract": str(paper.get("abstract") or "").strip()[:abstract_chars]}


def intro_messages(name, terms, goal, english, papers=()):
    """The whole input of the call: the concept's name, up to two of its search terms, the project name and its first
    keywords (called goal in the message) and up to INTRO_PAPERS of the project's own papers that match the concept
    (title and the start of the abstract). Nothing else: no other concept, no note, no profile, no paper id."""
    body = {"concept": str(name or "")[:INTRO_NAME_CHARS], "terms": [str(t)[:INTRO_TERM_CHARS] for t in (terms or [])[:2]],
            "goal": str(goal or "")[:INTRO_GOAL_CHARS],
            "papers": [_paper_for_model(p, INTRO_ABSTRACT_CHARS) for p in list(papers or [])[:INTRO_PAPERS]]}
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
    raw = " ".join(line.strip() for line in raw.strip().strip("`").strip().splitlines() if line.strip())   # the barrier is often on a second line
    raw = re.sub(r"^(简介|intro)\s*[:：]\s*", "", raw, flags=re.IGNORECASE).strip().strip("\"'“”‘’「」").strip()
    return raw


# -------------------------------------------- is a collected exploration paper a new direction? (operation direction_judge)
JUDGE_SYSTEM = ("你是学习路径助手。给出读者收藏的几篇探索论文（p1…）、学习图里已有的概念（c1…）和已有的潜在方向（d1…），"
                "判断每组论文是否构成一个新的学习方向。只输出 JSON：{\"results\":[{\"papers\":[\"p1\"],\"verdict\":\"\",\"direction\":\"\","
                "\"nearest\":\"\",\"name\":\"\",\"terms\":[\"\",\"\"],\"intro\":\"\",\"barrier\":\"\",\"needs\":[]}]}。"
                "verdict 取 new/join/covered/unclear：只有明显区别于所有已有概念的方向才是 new；是已有概念的子话题、近邻或更细的说法就是 covered，"
                "nearest 写最接近的概念名；能并入已有潜在方向的是 join，direction 写它的 id；看不出来是 unclear。"
                "new 时才写 name（≤20 字）、terms（2 个英文检索词）、intro（≤60 字，依据这些论文说这是什么）、barrier（≤60 字，先要懂什么、难在哪）、"
                "needs（至多 3 个已有概念名，须是读懂它的直接前置）。不要编造论文里没有的内容，不调用工具。")
JUDGE_PAPERS = 3
JUDGE_CONCEPTS = 10
JUDGE_CONCEPT_CHARS = 20
JUDGE_DIRECTIONS = 3
JUDGE_DIRECTION_CHARS = 24
JUDGE_ABSTRACT_CHARS = 180


def judge_messages(papers, concepts, directions, english):
    """The whole input of the call. papers: [{title, abstract}] (at most JUDGE_PAPERS, sent as p1…), concepts: names of the map's
    concepts (c1…), directions: [{name, intro}] already proposed (d1…). No paper id, note, profile, feedback or other project."""
    body = {"papers": {f"p{i + 1}": _paper_for_model(p, JUDGE_ABSTRACT_CHARS) for i, p in enumerate(list(papers or [])[:JUDGE_PAPERS])},
            "concepts": {f"c{i + 1}": str(n or "")[:JUDGE_CONCEPT_CHARS] for i, n in enumerate(list(concepts or [])[:JUDGE_CONCEPTS])},
            "directions": {f"d{i + 1}": f"{str(d.get('name') or '')[:JUDGE_CONCEPT_CHARS]}：{str(d.get('intro') or '')[:JUDGE_DIRECTION_CHARS]}"
                           for i, d in enumerate(list(directions or [])[:JUDGE_DIRECTIONS])}}
    system = JUDGE_SYSTEM + (ENGLISH_OUTPUT if english else "")
    return [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(body, ensure_ascii=False)}]


def parse_judge(text):
    """The list of result dicts in a reply (bare JSON, a code fence or wrapped), [] when there is none."""
    raw = str(text or "")
    for match in re.finditer(r"\{", raw):
        try:
            value, _ = json.JSONDecoder().raw_decode(raw[match.start():])
        except (ValueError, RecursionError):
            continue
        found = value.get("results") if isinstance(value, dict) else None
        if isinstance(found, list):
            return [r for r in found if isinstance(r, dict)]
    return []
