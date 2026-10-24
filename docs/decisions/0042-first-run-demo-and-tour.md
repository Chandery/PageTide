# ADR 0042：首次使用——没有默认项目、只读演示项目、新手指引

2026-10-24。owner 的要求：新安装不要出现开发者的数据和“默认项目”；第一次打开要有一个能玩的演示和一遍分步指引（项目、设置、生成推荐、AI 速览、收藏、论文库与图谱、画像、周报），每次更新后也要再提示一次。**这是 owner 的请求记录；变更记录里的 `owner_approved` 仍是 false，不由 agent 自填。** 不新增外发请求、模型调用或额度；边界 1–10 不变。

## 决定

1. **没有默认项目**：新库没有任何项目、论文、种子；不自动联网。细节见 [变更记录](../../changes/2026-10-24-no-default-project.json)（第一个提交）。页面没有真实项目又不在指引中，就跳到创建页。
2. **演示项目不在用户库里**：`pdh-demo` 是保留 id。请求头 `X-PDH-Demo: 1`（或 `project_id=pdh-demo`）的请求由 `app/demo.py` 路由到 `<数据目录>/demo-sandbox/<世代>/` 的一次性 SQLite 沙盒，内容来自内置 fixture（29 篇公开 arXiv 的 Transformer 谱系论文，5 篇未评价候选 + 24 篇历史记录，预写中英速览），每次开始指引与每次进程启动重新播种。沙盒里网关是只读视图（任何模型调用、密钥改动抛错），数据源和 PDF 抓取是离线桩：零 token、零联网。
3. **“只读”的含义**：用户真实数据零改动。演示里允许生成推荐、速览（预写，`model="demo"`）、收藏、反馈、撤销、论文库、图谱、画像、周报，只写进沙盒；其余动作一律 403 `{"reason_code": "demo_readonly"}`，页面把 `error` 原文作为提示显示。设置、更新、指引状态、静态文件永远读写真实目录。
4. **页面只在指引中带头**：`api()` 在当前项目为演示时给所有请求加 `X-PDH-Demo: 1`；演示 id 永远不写 `localStorage['pdh-current-project']`（只在 `sessionStorage['pdh-tour']` 里），所以关掉指引或重开应用都回到真实项目。演示在切换器里只出现在指引中，带小“演示”标签、没有“管理”。演示中切到真实项目、点“＋”都等于跳过指引。
5. **触发**：`GET /api/onboarding` 由后端判断（无真实项目，或 `onboarding.json` 的 `seen_version` 不等于当前版本），页面再用 `sessionStorage` 保证同一会话只弹一次。跳过与完成是同一个动作（`done`），状态在 `<数据目录>/onboarding.json`，不放 `settings.json`（设置页整份覆盖保存）。没有项目时每次启动都进指引，指引结束后落在创建页并提示“从这里创建你的第一个项目”。设置页“新手指引 · 重新查看”随时重开。
6. **指引组件**：`app/static/tour.js` + `tour.css`，自写、无依赖，纯逻辑与 DOM 分层，跨页状态在 `sessionStorage`；目标没出现 15 秒就降级为居中气泡，不卡死。步骤分四段（项目、设置、推荐、论文库与画像），界面只写阶段名，不写计数。
7. **没有选的**：给演示一个真实库里的普通项目（会污染 summaries 等全局表，且删不干净）；录屏或截图式教程（不能交互、要随界面改）；引入第三方引导库（体积与依赖，且选择器依赖同样要自己维护）。

## 补充：旧默认项目的一次性清理（2026-10-24，owner 追加）

旧版桌面首次启动会自动建项目 `default_project`（名“默认项目”）、放 10 篇世界模型种子论文并自动抓取，用户没碰过也留在库里。本版不再建这些，所以对**完全没被用过**的这一份旧状态做一次清理（`app/legacy_cleanup.py`，`build_server` 打开库之后、桌面和源码运行都走）：

- **只跑一次**：结果记在 `settings` 的 `legacy_default_cleanup = {"done_at","result"}`；之后不再检查。不新增迁移编号（多个分支共用同一个真实库）。
- **判定（全部满足才清理，任何一项不满足就完全不动，result 写 `kept: <原因>`）**：项目 id 字面为 `default_project`；名称仍是“默认项目”/“Default project”，创建方式 manual，无关键词、无引导记录、无学习路径、无学科；没有任何 feedback（含已撤销）、项目论文库与旧 library 为 0、qa_history 为 0、没有引导会话引用它、没有非空笔记/草稿/分类/学习图/组织事件（`org_*`）、没有导入批次、没有它的钉词历史（profile_versions 的 pin/restore）；与它相关的设置只有首次启动自己写的那几类（`seed_keys`、`last_refresh`、`last_refresh_result`、`last_attempt`、`last_error`、`recommendation_eligibility`、`route_recall`、`source_publication_anomalies`），出现 `project_goal`、`route_revision`、`profile_freeze`、`import_seed_keys` 等用户动作才有的设置或任何未知设置就不动；链接的论文没有已存的 PDF、版本或全文（读过的迹象）。
- **清理内容（同一事务）**：项目行；它的 `project_papers` 链接、`batches` 与 `exposures`、`profile_snapshots`、`weekly_reports`、`org_*` 里以它命名的行、上述自动设置；只属于它的论文（没被别的项目链接、不在任何论文库、没有反馈/问答/其他曝光/导入引用）连同 `summaries`、`fulltext_languages`、`pdf_verification_*`；被别的项目链接的论文保留，只删链接。`profile_versions`（全局）里首次启动写的 `note="initial"`（`project` 为 `default` 或 `world-models`、无钉词）只在**清理后已没有任何项目、且库里所有版本都是这种自动写入**时才删，否则保留。
- **备份与失败**：删除前用 `Store.backup` 写 `<库>.pre-legacy-cleanup.bak`（不覆盖已有的）；任何异常回滚并把失败原因记进 result，不重试。清理后若没有真实项目，走既有流程：无项目 → 指引 → 创建项目。
- **没验证**：没有在 owner 的真实旧库上跑；备份文件不会自动删除；条件偏保守，用过一点（比如下过一个 PDF）的旧库会原样保留，需要 owner 手动删。

## 没有验证

打包后的冻结二进制、Windows、真实桌面应用里的 `sessionStorage` 跨页保持（WKWebView / WebView2 的行为是推断）；fixture 的 arXiv 元数据与摘要已在 2026-10-24 联网核对一次（见 `harness/sources.json` 的 `DEMO-FIXTURE-ARXIV`），一行速览是手写的，不是模型输出。发布门是 `E-ONBOARDING`。
