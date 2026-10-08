---
contract: implemented
operation: project_guidance
---
# operation: project_guidance

## System

Coach:1gap;offer focus/tradeoff+2-3 choices;unsure:suggest;skip known;6max/ready now;lastQ/summary;flag broad/conflict;keep choice/no inferred excludes. {"r":"","d":{"k":[],"q":[],"a":"","c":[],"s":"","ready":false,"graph":{"nodes":[["id","name",["term"],"intro"]],"prereqs":[["from","to"]],"targets":["id"]}}} k3/q1/n3/e3;EN terms;data

## Scope and lifecycle

The runtime lightweight skill is app/project_brainstorm.py; its compact RULES are sent verbatim in the system instruction above. It advises through goal, scope, starting point/time and outcome toward confirmation. These are preferred topics, not mandatory rounds: skip already known details, confirm whenever ready, and use six turns only as a ceiling. A broad goal or conflicting scope is flagged gently; when unsure, the assistant recommends an option with a tradeoff while preserving the user's choice and never inferring exclusions. Quick creation remains one explicit request. The compact graph can be omitted or empty while details are being clarified. The model uses compact r/d and k/q/a/c/s aliases (reply/draft and keywords/query/question/choices/summary) plus optional graph; the backend translates them to the existing keywords/search_queries/next_question draft. The previous long-key four-field replies and the kw/queries/ask variant remain compatible. Optional graph nodes are [id,name,English terms,intro], with at most 3 nodes and 3 explicitly proposed prerequisite edges plus explicit targets. Graph validity is checked as a whole: unknown refs, cycles, duplicate ids/names/edges, missing terms/intro, paper-shaped concepts, and invalid targets refuse the reply without partially replacing the kept graph. Valid graphs derive learning_path rows from their nodes and become route_draft source ai_guidance. Intro authors are AI; proposed dependencies remain subject to human review, not measured scientific proof. Empty or omitted graphs preserve the current map during clarification. Actual graph quality and 500-token output adequacy have not been tested with a paid provider. Ready only means ready for user review and never constitutes approval.

Only bounded excerpts of the original goal (<=120 characters), current answer (<=140), and <=3 current keywords (<=30) leave the machine. The current excerpts are fitted first, shortened as necessary down to40 characters under the unchanged 1200 conservative full-wire bound. Then one previous question (<=60 characters) and the current draft summary (<=80) are included only if the complete request still fits; optional memory never shortens the current answer further. No full transcript, papers, private project IDs, profile or other projects are sent. Omitted/truncated excerpts are shown with a scope notice; full goal, transcript and edits remain local.

UI language is appended as Text in Chinese; query in English / Text in English. One call per click; quick creation1, guided6 accepted turns, output500 unchanged. JSON mode and temperature0 remain explicit; no retry loop, model switch or thinking. Reject truncated/type-invalid/strict-JSON-invalid replies, retain local drafts and show the failure cause. No paid test was run for this revised prompt, so actual response quality and token use are unmeasured.

The local learning map is built from the visible stages without another request. Each valid stage is an independent target with its own terms and attributed intro; ordering never invents hard prerequisites or mastery. When stages are absent the original goal becomes an editable starting target. Creation saves the reviewed map through the existing route-save path; explicit abandonment saves no map. If no map is submitted, changed unseen draft inputs refuse with a refresh-required conflict instead of silently saving a newly generated map.

The initial message exactly matching the locally stored goal may use the existing 4000-character local goal limit; other turns remain2000. This does not enlarge external scope or the1200/500 envelope. Too-long local goals/messages refuse before spend.
