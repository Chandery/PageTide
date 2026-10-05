# Self-review: 2026-10-05-route-graph (the learning map as a graph, project management, AI draft for existing projects)

Implementing agent's own review; not independent (see 2026-10-05-route-graph-review.md for the independent one).

What the owner reported, and what changed
1. Projects could not be edited or deleted: there was no endpoint and no page, only a method nobody called. Now: rename and delete (page `project.html`, reachable from a "管理项目" link in the top bar and a "管理" button on each card of the project overview). Delete asks for the exact project name, writes a consistent database copy first (newest 3 kept) and says what is removed and what stays. Keywords are not edited here (they are the profile's pinned terms).
2. Existing projects could not use the AI to draft a map: the map page now has "让 AI 起草" for projects with and without a map. One explicit click, at most 3 paid attempts per project per local day, the draft is only a proposal until saved. The owner's wording ("不需要对已有的进行生成" together with listing the missing capability as a problem) was read as: build the capability, do not run it for me now. The first version of this change extended the approved `learning_path_plan` scope on that reading; the independent review rightly called that self-approval. It is now a separate operation `learning_path_plan_project` with `owner_approved: false` that only the owner can switch on.
3. The structure/UI was wrong: (a) the prompt asked for "concepts from beginner to goal", which invites one line; it now asks for a dependency graph (independent entry points, 2-3 prerequisites, no chain) and the page says so when a draft is a single line; (b) the page showed columns "第 N 层 / 越靠左越基础" with prerequisites as text: replaced by a drawn graph with arrows (route-graph.js) where selecting a concept highlights what it needs and what it opens and a locked concept says which prerequisites it is waiting for; the layer number is no longer shown on recommendation cards either.
4. A big AI map overflowed the page: the graph lives in a scrollable viewport with zoom (fit width / fit whole / +/-), the creation page stacks graph over detail, and a grid track no longer grows with its content.

Judgement calls
- The instruction budget share of `learning_path_plan` was raised from 500 to 560 tokens and the framing margin lowered from 150 to 90 to fit the longer prompt; the 1200 input cap, the 900 output cap and the price ceiling are unchanged. All sizes are the existing pessimistic character estimates (1.5 tokens per Chinese character), not tokenizer measurements, and the new prompt has never been sent to a real model.
- `delete_project` makes the backup before deleting and refuses to delete when the backup fails; ids for delete, rename and the paid call must be explicit (no default-project fallback).
- Not done: the knowledge-base (Cytoscape) path layer, the profile-page Route Mode block, growing the map from exploration (slice 7), governance documents (slice 8).

Weak spots
- No real provider call was made; whether the new prompt yields branched maps is unmeasured. The single-line warning exists because it may not.
- route-page.js, project-page.js and the mount() half of route-graph.js have no automated DOM tests; they were exercised by hand in a browser preview (select/mark/edit/add/discard/AI draft with canned replies/rename/delete/switcher button). The layout half has 15 node tests with mutation checks.
- The Tauri window was not clicked through.
