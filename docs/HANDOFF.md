# 当前交接：推荐优先路线、复用调研与行动前 token 预算

## 2026-09-29 Multi-project UI (Phase 2) (Current)

- Implemented Phase 2 of multi-project support: project selector dropdown UI and project creation flows. Users can now switch between projects and create new ones through the web interface.
- Project selector in header shows current project name with dropdown listing all projects. Click switches active project, reloads data, and persists selection to localStorage. Dropdown closes on outside click or selection.
- Dedicated project creation page (`/project_creation.html`) with three modes: Quick (AI screening, placeholder for Phase 3), Manual (keywords + optional seeds, fully functional), AI-guided (conversational, marked as coming soon).
- Manual creation accepts project name, comma-separated keywords, and optional DOI/arXiv seed list. Quick mode accepts natural language research interests but AI screening unimplemented. Both modes redirect to home with new project selected.
- Evidence: [change record](../changes/2026-09-29-multi-project-phase2.json). Core tests pass; HTTP tests blocked by sandbox (expected). Visual verification in Browser pane. Zero runtime token impact; UI-only changes.
- Phase 2 UI complete and committed (be85506). Server endpoints already support project_id from Phase 1. AI screening for quick mode and full AI-guided flow deferred to Phase 3. Requires non-sandboxed environment for server testing.
- Related: PROFILE-01. Next: Phase 3 AI guidance, Phase 4 recommendation adjustments, Phase 5 profile visualization, Phase 6 weekly reports per approved plan.

## 2026-09-29 Multi-project data layer (Phase 1) (Previous)

- Implemented Phase 1 of multi-project support: database schema migration system, project tables, and project-scoped data isolation. This enables managing multiple research projects with independent profiles, papers, and feedback.
- Migration system tracks schema versions in `schema_version` table. Migration 1 creates `projects`, `profile_snapshots`, `weekly_reports` tables, adds `project_id` foreign keys to `papers` and `feedback`, creates a default project, and migrates existing data.
- `ProjectManager` provides project CRUD: `create_project`, `get_project`, `list_projects`, `update_project`, `delete_project`, plus snapshot/report operations. Service layer updated to accept optional `project_id` parameters with default project fallback for backward compatibility.
- All 178 non-HTTP tests pass. 18 HTTP tests fail with "Operation not permitted" on socket binding (expected sandbox behavior, not a Phase 1 defect). Migration is idempotent and verified through manual testing.
- Evidence: [checks](evidence/2026-09-29-multi-project-phase1-checks.txt), [change record](../changes/2026-09-29-multi-project-phase1.json). Zero runtime token impact; no new model calls. Harness/budget/review checks passed.
- Phase 1 complete and committed (aa2479d). Provides data layer foundation for Phase 2+ UI and features.

## 2026-09-20 Desktop runtime API key wiring (Previous)

- Owner reported the Tauri app had many places not calling the API. Root cause confirmed: the desktop shell stripped `DEEPSEEK_API_KEY` and the gateway only resolved `.local/deepseek.env` from the process CWD (`~/Library/Application Support/PaperDigHelper`), while the key lived in the checkout. `/api/translate` and `/api/qa` returned `no API key`; the desktop DB held 0 summaries and 0 QA rows versus 50/56 in the browser DB. The usage ledger also resolved inside the frozen `.app` bundle.
- Fix: `Gateway` now takes `data_dir`, resolves the key from env/explicit file/data-dir/checkout, and keeps the ledger + `DEV_MODE` in the user data dir. New `GET/POST /api/settings` stores or clears the key at `<data dir>/deepseek.env` with 0600, never returns it, and rejects cross-origin writes. A header settings dialog lets the owner paste/clear the key; `/api/home` reports `provider.configured` without the secret. No key goes to webview storage or Git.
- Nine new tests (`tests/test_provider_settings.py`) cover data-dir/legacy resolution, private save/clear, offline provider-call + local ledger, missing-key degradation, HTTP round trip/no-leak, and cross-origin/length rejection; one UI layout test pins the settings wiring. Full suite 196 passed. No live provider call and no token spend was made in this work unit.
- Evidence: [checks](evidence/2026-09-20-provider-key-checks.txt), [ADR 0004 stays the runtime/eval split](decisions/0004-evaluation-annotator-separation.md). Budget unchanged (`approved_by_owner=true`, `runtime_enforcement_implemented` and `tokenizer_parity_verified` still false). The packaged frontend/backend bundle was regenerated and ad-hoc signed (`codesign --verify --deep --strict` passes); relaunch the app to load it. The running instance keeps the pre-fix code until then.

## 2026-09-16 Selected suggestion application fix (Current)

- Version0.11 fixes silently skipping all already-classified/protected papers. Explicit UI acceptance now adds selected category memberships, preserves existing memberships/notes/labels/parents, shows actual effects or already-present notice, and remains undoable. Legacy automatic protections remain unchanged.
- Browser synthetic fixture with two manually classified/protected papers: real apply added two links and one category, repeat showed no-op, undo restored original category. Native fixture QA uses isolated Tauri shell/source backend; see checks for final result. No real library changed.
- Full Python185 passed; Node23 organization tests passed; independent review passed including added empty-group regression (5 focused tests). Local bundle rebuilt and ad-hoc signature verified; packaged JS equals source. Evidence: [checks](evidence/2026-09-16-suggestion-apply-checks.txt), [review](evidence/2026-09-16-suggestion-apply-review.txt).
- Zero new model tokens/network/dependencies. READ-01/GRAPH-01 remain in_progress for broader acceptance. Local trial only, no notarization/full release certification; prior dirty work preserved.

## 2026-09-16 Category directory and editable memberships (Current)

- Owner requested working existing-category edits/deletion, nested directories and multiple paper memberships, then a compact folder-like sidebar. Version0.10 implements folder icons, one row per category, indent guides/disclosure/counts, per-row more menu and current path.
- Additive parent_id in project JSON: old records remain roots; self/descendant cycles rejected. Move preserves subtree/memberships. Delete promotes direct children, removes only direct links, preserves papers/PDFs/notes/other memberships; undo restores. Parent views deduplicate descendant papers. Single-paper checked-box editing exposes existing links; batch keep/add/remove retained.
- Native/browser synthetic QA confirmed editing already-classified papers and deleting existing categories. Native used isolated QA shell with exact packaged frontend and same source backend; separate frozen worker snapshot smoke passed. No real user database changed.
- Full Python181 passed; final Node28 passed. Budget/harness/diff/record checks and ad-hoc bundle signature passed, final packaged assets equal source. Evidence: [checks](evidence/2026-09-16-category-tree-checks.txt), [independent review](evidence/2026-09-16-category-tree-review.txt), [ADR0007](decisions/0007-category-tree.md). Independent finding on collapsed-leaf recovery fixed/tested.
- READ-01/GRAPH-01 remain in_progress for broader acceptance; no new model tokens/network calls. Old unrelated dirty work preserved; package is local trial, not notarized or full release certified. Large/deep-tree resource limits not measured. Next: owner trial of v0.10 from built bundle, verify usability on actual categories.

## 2026-09-15 Organization suggestion refinement (Current)

- Owner feedback: directions too fragmented and English-only. Implemented broader local communities, majority exact-topic coalescing, Chinese lexical features, Chinese display labels with explicit unnamed fallback, visible source terms and singleton abstention. Graph relation algorithm retains its old default.
- Explicit preview checkbox can regroup selected untouched automatic memberships; manual directions/protected edits remain intact, old emptied automatic directions are cleaned, undo restores prior state. No schema, provider, network or token changes.
- Evidence: [checks](evidence/2026-09-15-organization-refinement-checks.txt), [independent review](evidence/2026-09-15-organization-refinement-review.txt). Full Python175 tests passed in desktop-build-env; base system Python lacks optional NetworkX. Four independent-review findings fixed.
- GRAPH-01/E-ORGANIZATION remain in progress/not_run for broader quality gates. Finite Chinese glossary is not arbitrary translation; unknown topics remain editable, cross-language semantic equivalence and all-discipline real-corpus quality unmeasured.
- Version0.9 local trial build/visual verification results recorded in checks; prior unrelated dirty files preserved and included only for harness coverage. No release approval or broad release certification. Next: owner real-paper trial and domain-specific quality feedback.

## 2026-09-15 Local Elastic Graph Motion (Current)

- Implements owner's linked motion summary for a work-focused graph: no idle drift, bounded
  one-hop drag response, short release easing back to the user's NEW drop point, synchronized straight
  edges/labels, layered fade-in, local expand/collapse and one-shot relationship emphasis.
- Reuses Cytoscape animate, not a new physics engine or model. At most32 responding neighbors,
  18px neighbor offset, 10px release overrun, approximately520ms settling; these are configured caps,
  not measured FPS or physical simulation claims. Reduced motion and direct user input take priority.
- Canonical coordinates stay separate from animations. Constructor input cloned to prevent shared
  snapshot mutation; group drags save once. Relation completion preserves camera and waits for drag.
- Evidence: [motion checks](evidence/2026-09-15-graph-motion-checks.txt),
  [motion review](evidence/2026-09-15-graph-motion-review.txt).
- Python166 tests passed; focused Node25 tests cover motion, actual Cytoscape settling/aliasing,
  multi-select and click/free event order. Browser fixture checks: nonblank graph, focus, drag/drop,
  collapse10->7nodes and expand7->10nodes; no console errors. Native frame timing unmeasured.
- Version0.8 local trial package; earlier dirty PDF/Tauri work preserved. Broader release gates and
  owner release approval remain incomplete. Next: owner trial with real papers, tune amplitudes only
  from feedback; no paid calls, persistent auto-floating or invented directional propagation.
- Final targeted independent review passed; local macOS bundle rebuilt and ad-hoc signature
  verified, packaged frontend byte-for-byte equal to source. Not notarized or native-FPS measured.

## 2026-09-14 Network Graph and Motion (Previous Slice)

- Round-node branched network replaces compound cards. Empty directions hidden in graph only;
  each saved paper has one node, multiple real direction links and bounded lexical similarity links.
- Category/paper focus animates camera for 550ms with neighborhood highlighting; toolbar zoom
  preserves center. Rapid focus replaces queued motion; grabbing cancels it. Reduced motion supported.
- Library title opens PDF directly; notes/classification remain a separate control. PDF internals untouched.
- Graph operation is read-only in the existing bounded local worker. Drag coordinates persist across
  view changes, existing positions survive relation refresh, and full rearrange remains explicit.
- Final evidence: [network checks](evidence/2026-09-14-network-graph-checks.txt),
  [targeted independent review](evidence/2026-09-14-network-graph-review.txt).
  166 Python and 17 Node tests passed, plus budget/harness/diff checks. Browser fixture checked at
  1265x712: category highlight, paper focus/detail, nonblank graph, direct library-to-PDF route.
- App rebuilt, ad-hoc signature verified, bundled frontend matches source; actual frozen graph worker
  returned two similarity edges from six synthetic papers. Footer version 0.7. No paid calls made.
- READ-01/GRAPH-01 remain in progress; no native FPS, large-corpus quality, 8GB resource guarantee,
  notarization or broad release certification. Older dirty PDF/Tauri work remains preserved.
- Next: owner trial of this package on real papers; finish broader graph/read acceptance separately.

## 2026-09-14 Editable Library and Graph (Previous Slice)

- Owner requested implementation of library directions/notes and a local drag-and-drop knowledge graph.
  This supersedes older statements below that all implementation is unapproved; it is not release approval.
- READ-01/GRAPH-01 remain in progress for their broader acceptance scope. New organization modules and
  local Cytoscape/NetworkX dependencies implement the current slice; PDF reader changes are excluded.
- Additive organization schema preserves legacy notes, backs up before migration, versions notes and
  drafts, persists memberships/positions/collapse, and supports undo/export. Suggestions are local,
  bounded, preview-first, and cannot overwrite manual organization. No incremental model calls.
- Evidence: [checks](evidence/2026-09-14-organization-checks.txt),
  [independent review](evidence/2026-09-14-organization-review.txt),
  [ADR 0006](decisions/0006-library-organization.md).
- Current worktree also contains earlier uncommitted UI/PDF/Tauri work. Preserve it; new feature review
  does not certify those older changes or broader recommendation/budget/release gates.
- Final: 164 Python tests, 13 Node behavior tests, budget/harness/diff checks passed. Independent
  source review findings closed. Cross-port browser restart restored an acknowledged DB draft with
  explicit comparison before saving. Not a guarantee for keystrokes before the persistence debounce.
- macOS bundle rebuilt at `src-tauri/target/release/bundle/macos/PaperDigHelper.app`; approximately
  49M, ad-hoc signature verified. All bundled frontend assets match source, and its frozen worker
  classified the six-paper fixture successfully. Footer server version is 0.6. No native app
  crash/restart interaction, notarization, 8 GB performance or human category-quality claim is made.
- Next: owner trial with real saved papers, then address real-corpus grouping quality and remaining
  READ-01/GRAPH-01 gates; do not silently expand into viewpoint inference or paid classification.

## 2026-09-12 UI refresh

- User-requested visual refresh recorded in [change record](../changes/2026-09-12-ui-refresh.json).
- `app/static/index.html` now uses a compact editorial layout inspired by the supplied Dribbble reference: bright canvas, restrained borders, deep accent, icon navigation, responsive card sizing and subtle enter/hover motion.
- Added local Lucide SVG icons under `app/static/icons/`; no CDN or runtime provider dependency was added.
- Manual QA covered normal zoom, dark mode, library/profile/detail views and enlarged browser text. The earlier oversized screenshot was browser zoom, not an app measurement.
- Fresh checks: budget exit 0, harness exit 0, full unittest suite exit 0 (115 tests), `git diff --check` exit 0. Evidence: [UI refresh checks](evidence/2026-09-12-ui-refresh-checks.txt).
- This is presentation-only; recommendation quality, AI budget enforcement and release gates remain unchanged and are not implied by these checks.

2026-09-11。旧 ABCD 已退出执行；本轮完成**复用调研、S0–S6 阶段计划、行动前 token 预算提案、harness 说明**，并继续清理旧应用。**新实现未批准、未开始；推荐质量、画像收益与 AI 成本均未实测。**

## 当前状态

- `PLAN-01` 完成（调研与重规划）。`CLEAN-01`、`BUDGET-01` 处于 `review`（实现完成、等待独立审查）；`PLAN-02` 现为 `in_progress`（领域/种子/首版范围已确认；AI 上限已获 owner 批准；待冻结实验指标）。`REUSE-01`、`DATA-01` 及之后尚未开始。
- owner 已确认 AI 开销上限（`budget.json` `approved_by_owner=true`）、不允许外发私人种子/画像 ID、PDF 默认写本机、允许显式启用的混合大模型重排（[ADR 0003](decisions/0003-hybrid-llm-ranking.md)，`llm_rerank` 默认关且未获批额度）。论文图谱/聚类调研进行中（`GRAPH-01`）。
- 新实施批准为 `false`，预算批准为 `false`；agent 不自批。
- 活跃任务与依赖只在 `harness/tasks.json`（stages: research/benchmark/feedback/reading/assist/delivery/release）。旧 A-01～A-06 不再活跃。

## 本轮交付

- [DOMAIN](DOMAIN.md)：已确认测试领域（英文 AI / world models）与 10 篇正例种子，及外发边界。
- [KNOWLEDGE-GRAPH](KNOWLEDGE-GRAPH.md)：论文图谱/聚类的开源调研与建议栈（sklearn HDBSCAN + networkx/python-louvain + OpenAlex 引用边，零 token）。
- [EVALUATION](EVALUATION.md)：大模型辅助标注 + 人工抽检的评估协议；[ADR 0004](decisions/0004-evaluation-annotator-separation.md) 规定运行时（DeepSeek）与评估裁判（taomu/gpt-6-astra）分离。
- [BRAINSTORM](BRAINSTORM.md)：需求拆解、算法选型、A/B/C 路线、「没空/暂停/督促」语义、第一版形态候选。
- [RESEARCH](RESEARCH.md)：新增 ASReview（Apache-2.0、纯 sklearn、显式相关/不相关、主动学习 querier）为首选画像内核；补齐 txtai/paperetl、Paper-Agent-Zotero、arXivDigest、rank_bm25、抓取库；列出「没人解决好的缺口」。
- [DATA-01 报告](evidence/2026-09-11-data01-openalex-report.md)：种子解析 10/10；裸关键词不是领域过滤器；发现配方 = arXiv源 + title.search + 日期上界；引用边缺失；OpenAlex/arXiv 限流与费用实测。
- [实验 1（排序对照）](evidence/2026-09-11-ranking-experiment-1.md)：评测管线端到端跑通（冻结 318 篇 → 3 系统 → taomu 盲标 26 篇 → P@k），但裁判 96% 判有用、候选池已过滤，**无区分度**；负结果，`E-RANKING` 保持 not_run。
- [ROADMAP](ROADMAP.md)：按风险排的 S0–S6，覆盖推荐/画像/阅读/AI 四类能力，含实验协议与停止条件。
- [BUDGET](BUDGET.md) + `harness/budget.json` + 生成表：**核心零 token**（搜索/去重/排序/画像/归档/DB 维护）；运行时 AI 层已批准额度（后台 26k/交互 35k/合计 55k 每日、150 万每月、$0.15/日、$1.50/月），含 `llm_rerank`（默认关闭）；评估裁判单独走 `evaluation` 段（taomu，只计 token）。除两次探针外均未实测。
- `prompts/`：7 个操作合同（速览、重排、标注、追问、周报、划词、关键词扩展），每个都声明有界上下文与不可信源文本规则。
- Harness：新增「孤儿 evaluation 检查」与技能描述长度预算；`docs/HARNESS.md` 记录吸收的开源做法。

### 检查边界（精确结果见 `docs/evidence/2026-09-11-plan02-decisions-and-graph-checks.txt`）

最终结果：预算检查 exit 0；仓库检查 exit 0；**Python 41 测试通过**；`check --release` exit 1（预期阻断：实现未批准、enforcement/tokenizer 未实现、全部 blocking gate 为 `not_run`）。**没有独立审查，没有运行任何上游候选。** 两次真实模型调用都只是非私密探针（`docs/evidence/2026-09-11-deepseek-probe.txt`、`docs/evidence/2026-09-11-taomu-probe.txt`），不是产品测量，也不代表任何 gate 通过。

```sh
python3 scripts/budget.py --check
python3 scripts/harness.py check
python3 -m unittest discover -s tests -v
python3 scripts/harness.py check --release    # 应阻断
python3 scripts/harness.py review changes/2026-09-11-recommendation-plan-and-budget.json
```

## 预算与安全

- 核心路径 0 模型 token；真实成本是元数据 API 请求、CPU/RSS/磁盘/时间，尚未测量。
- AI 层价格按 DeepSeek peak cache-miss（$0.30/$1.20 per 1M），来源已核查 2026-09-11；未做离线 tokenizer 校准。
- 旧 Key、旧校准、旧批准都不继承；未授权不发起真实调用、不下载模型权重、不外发私人种子/笔记。
- 保留本地优先、低资源、不把没空/难懂当不喜欢、原件/来源保护等边界。

## 工作区与历史

- 按用户要求已删除全部旧 Git 历史并重建仓库，不含旧 A-01～A-06 任何提交。当前历史为：初始基线 + 规划基线 v2（`git log --oneline` 查看）。未配置远程、未 push；用户将自行新建远程仓库。
- 旧历史保险备份在 `.local/git-history-backup-before-reset.bundle`（受 `.gitignore` 忽略，不会提交或推送；确认不再需要可删除）。
- `changes/` 里的记录随对应提交一起进入历史；之后每个新工作单元再新建 `changes/<id>.json`（此时 `harness.py review` 才有可比较的工作树差异）。
- 旧说明与旧任务快照在 `docs/archive/`、`harness/archive/`，不继承完成/批准结论。`.local/` 是本机私有数据，不应提交。

## 下一步

已确认（2026-09-11）：领域 = 英文 AI / world models；10 篇正例种子（无反例，记未知）；首版 = 推荐画像核心 + **PDF 下载归档** + **AI 每日速览与追问**；仅 macOS、本地保存；论文软件 Zotero（只读/导入）。详见 [DOMAIN](DOMAIN.md)。

`PLAN-02` 收尾仍需：

1. 冻结「相关/有用」标签定义、静态与滚动时间切分、正向增益指标/最小有意义差值/样本量。
2. ~~若启用混合重排：批准 `llm_rerank` 的新增每日/每月额度~~ —— **已完成（owner 批准，默认仍关闭）**。
3. 可选的 3–5 篇反例（owner 暂无法提供，保持未知）。

已解决：AI 上限（已接受，含 `llm_rerank`）、数据外发（不允许私人ID外发，只发公开元数据）、PDF 存放（本机文件夹）。
- 新增 `LABEL-01` 大模型辅助评估标注；运行时用 DeepSeek 官方，评估裁判用 taomu/gpt-6-astra（[ADR 0004](decisions/0004-evaluation-annotator-separation.md)）。两个 key 都**仅存于 `.local/`（未入 Git）**，建议实验后轮换；已跑通两次非私密探针（deepseek 122 token；taomu 发现每次注入 ~4.4k 隐藏 token）。
- 随后跑 `REUSE-01`（ASReview/X 受限探针）与 `DATA-01`（领域覆盖），再按 [EVALUATION](EVALUATION.md) 跑 `LABEL-01`。

### 实现（第一切片，2026-09-11）

owner 已批准实现（`harness/tasks.json` `approved_for_implementation=true`）并选定 **Python 核心 + SQLite + 本地网页（Tauri 壳后续）**，第一切片包含 AI 速览。见 [ADR 0005](decisions/0005-implementation-start-tauri-python.md)。

已具备（`app/`，stdlib）：

- `db.py` SQLite：papers / exposures / feedback / profile_versions / pdfs / settings；反馈可撤销、画像版本追加不可变。
- `sources.py` OpenAlex：发现（arXiv源 + title.search + 日期上界，DATA-01 验证的配方）+ 种子解析；响应缓存可回放；限流时容错。
- `ranking.py`：TF-IDF 余弦 + Rocchio 画像 + MMR 多样性。
- `gateway.py`：唯一预算网关（先预留、再发送、记账；超限拒绝；失败降级）。
- `service.py`：每日 5 卡、反馈语义（`busy/confused/later` 不改兴趣）、画像可见可改、PDF 下载、AI 速览。
- `server.py` + `static/index.html`：本地 loopback 网页（单线程，只绑 127.0.0.1）。
- `cli.py`：headless 全流程。

已验证：83 个单测通过；`harness.py check` 通过；真实 AI 速览一次成功（1469 token, $0.00106，ledger 已记）；网页 `GET /` 200、`/api/home` 返回卡片与统计。

UI 第二轮（按 owner 反馈）：

- **主页**：磨砂玻璃顶栏 + 统计（文献/种子/正例/负例/中性/已展示）+ 三个主操作。
- **卡片可点开**→ 详情面板显示**完整摘要**（之前 UI 截断成 420 字，误以为摘要不全）。
- **磨砂玻璃 + 动画**：backdrop-filter、卡片入场/悬浮发光、模态弹入、Toast、进度条；支持 reduced-motion。
- **并发修复**：服务器改 ThreadingHTTPServer + 每请求独立 App；“抓取”改为**后台任务 + 轮询进度**，不再是单线程阻塞（实测抓取进行中 `/api/home` 仍 **3.6ms** 返回）。
- **文案修正**：预演不再显示为“降级为离线”；预演会明确显示预留 token/金额。

UI 第三轮（按 owner 反馈第二轮）：

- **反馈语义改为收藏**：`有用` = 写入 `library` 表（幂等），**卡片不消失**、标为“已收藏”；新增「论文库」标签页与 `/api/library`、`/api/unsave`。
- **生成 5 篇秒出，AI 自动速览**：卡片立即渲染，随后自动调用真实速览（可在页面上关掉）；等待时卡片显示转圈，完成后标「AI 已速览」。
- **详情交互重做**：悬停 0.5s 弹出预览框，移开即消失；**点击进入独立详情页**（不是按钮，而是整页）。
- **配色换成暖色系**（黄铜/玫瑰/青苔），去掉蓝色；按钮改为胶囊样式。
- 修复详情无响应（旧代码在 `document` 上重复绑定、且缩略卡拦截了点击）。

尚未做：Tauri 壳、打包与签名、AI 追问、Zotero 导入、笔记/高亮（后置），以及修标注提示词的种子标题偏差。

### 2026-09-12 应用壳与 macOS 打包

- 已安装 Rust、Tauri CLI、PyInstaller，并完成 Tauri v2 macOS `.app` 构建。
- 产物位于 `src-tauri/target/release/bundle/macos/PaperDigHelper.app`
  （本机 arm64，约 31 MB；构建目录按约定不纳入 Git）。
- Python 后端已随包携带；应用使用随机 loopback 端口和每次启动的本地会话
  token，数据写入 `~/Library/Application Support/PaperDigHelper`。
- 已实际打开应用，窗口和首页可用；关闭后随包 Python 子进程也退出。
- `cargo check`、`cargo tauri build --bundles app`、全量 118 测试、
  `codesign --verify --deep --strict`、`spctl --assess` 均通过。
- 发布仍未批准：推荐质量、持久性/恢复等项目 gate 仍未完成。`PILOT-01`
  保持 `in_progress`，`REL-01` 不标记完成。

### 2026-09-12 PDF 触摸板缩放修复

- 修复 PDF 预览触摸板缩放松手时的跳动：缩放锚点现在同时缩放页面内偏移和
  指针偏移，视觉阶段与重新渲染阶段使用同一套公式。
- 缩放手势期间只变换整组页面，手势结束或 wheel 空闲后才提交高清重绘；
  普通双指滚动不再被缩放监听器拦截。
- 缩小时舞台至少保持可视区宽度，视觉阶段和高清重绘阶段都保持水平居中。
- 已重新生成后端、构建并签名 `.app`，并重启桌面实例。
- 最新检查：全量 121 项测试通过，`harness.py check`、`git diff --check`、
  `cargo tauri build --bundles app`、签名校验均通过。证据见
  [PDF pinch anchor checks](evidence/2026-09-12-pdf-pinch-anchor-checks.txt)。

- **10/10 种子解析成功**（owner 补了两个 arXiv ID）；显式 ID 作权威，标题不符会记录 mismatch。
- **发现配方已确定**：arXiv source（`S4306400194`）+ `title.search` + 日期上界 → 3,226 条且 200/200 全是世界模型；裸关键词 328 万条且被污染。
- **可用候选池**：200 条全来自 arXiv、摘要 0 缺失；但**引用与 related 边 200/200 全缺** → 图谱引用边必须换源。
- **日期必须带 `to_publication_date`**，否则出现 2036 年记录。
- 费用：OpenAlex $0.001/search、1000 credits 与 $0.10/日；arXiv 本机 IP 本次持续 429。
- 下一步：修正测量（加非世界模型干扰项、改分级相关度、标更多低排名样本），再做 `E-LLM-LABEL-VALIDITY` 抽检，然后才可能碰 `E-RANKING`。

### DATA-01 首轮结果（in_progress）

### 实验 1–2 结果（CORE-01 in_progress）

- 管线可复跑：冻结候选（实验2: 1126 篇 = 318 field + 808 distractor，哈希 `5c27c2aa8bfbf91c`）→ 3 个系统 → taomu 盲标 → 分级 P@k。
- **实验 1（无干扰项、二值标签）**：全部 P@5≈1.00，裁判 96% 判有用 → **无区分度**（负结果，已保留为教训）。
- **实验 2（加干扰项 + 0–3 分级）**：标签分布 {1:18, 2:5, 3:22}。
- **标签验证与阈值冻结**：owner 盲评 20 篇（15 + 5 边界样本）；annotator 从不输出 0、整体上移（exact 45%），但二值一致 95%。冻结 **`useful = annotator >= 2`**（95% vs `>=3` 的 80%，零漏判）。
- **修正后的实验 2 读法**：`>=2` 口径下 P@5 全部 1.00（饱和）；**P@10 有区分**：`recency` 0.60 vs `keyword+date`/`tfidf` 1.00 → **画像排序优于纯时间基线**，但两法并列，方法间无差异。详见 [阈值冻结](evidence/2026-09-11-label-threshold-freeze.md)。
- n=45、P@5 仅 5 样本，不具统计意义；干扰项构造有循环性；**不能宣称推荐有效**。
- `E-LLM-LABEL-VALIDITY` 仍 `not_run`（n=20、阈值事后选定）；发布前需在新候选池上做 ≥40 篇抽检。`E-RANKING` 仍 `not_run`。
- **实验 3（反馈价值，单次切分）**：AUC：`recency` 0.52 < `frozen_seed` 0.94 < `+正反馈` 0.96 < `+负反馈` 0.99。
- **实验 4（滚动 10 批，跨 12 个月）**：重建 754 篇候选、累计 268 条标签；9 个评估批 mean AUC rolling **0.910** vs frozen **0.891**（delta **+0.018**，wins 4 / ties 3 / losses 2）。→ **实验 3 高估了反馈收益**；正确说法是“小幅、不稳定”。见 [滚动反馈 1](evidence/2026-09-11-rolling-feedback-1.md)。
- **重要方法学缺陷**：标注提示词里包含了种子标题 → 种子相似论文被构造性地判为有用，frozen/rolling 的 AUC 都偏高。**修好提示词（不再给种子标题）前，排序与反馈评估都不可信。** `E-RANKING`、`E-FEEDBACK-VALUE` 保持 `not_run`。
- taomu 网关实测：屏蔽无 UA / `Python-urllib` UA；每次调用含 ~4,224 cached 隐藏前缀。两次标注共 15 次调用约 82k token。

**不开始新的 PDF 阅读器平台，不自动执行整条路线。**
