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

## 补充：旧默认项目的一次性清理（2026-10-24，owner 追加；独立审查后修订）

旧版桌面首次启动会自动建项目 `default_project`（名“默认项目”）、放 10 篇世界模型种子论文并自动抓取，用户没碰过也留在库里。本版不再建这些，所以对**完全没被用过**的这一份旧状态做一次清理（`app/legacy_cleanup.py`）。原则：有疑问一律保留。

- **何时跑**：只在桌面应用启动时（`app/desktop.py`：拿到实例锁之后、`build_server` 之前，仅当设置了 `PDH_APP_VERSION`）；源码运行需显式 `PDH_LEGACY_CLEANUP=1`（`serve()`）。`build_server` 本身不打开库，和之前一样。只跑一次：结果记在 `settings.legacy_default_cleanup = {"done_at","result"}`，有记录就不再检查。不新增迁移编号（多个分支共用同一个真实库）。
- **判定（全部满足才清理，任何一项不满足就完全不动，result 写 `kept: <原因>`）**：
  - 项目：id 字面为 `default_project`；名称仍是“默认项目”/“Default project”；manual；无关键词、引导记录、学习路径、学科；`language_policy_revision` 为 0 且 `allowed_languages` 为空。
  - 用户动作：无任何 feedback（含已撤销）；项目论文库与旧 library 为 0；qa_history 为 0；无引导会话引用；无非空笔记/草稿、分类、学习图、组织事件；无导入批次；没有 `project_papers.source_project_id='default_project'`（分享出去过）。
  - 使用迹象：批次只在一个日期（首启当天）；链接论文没有任何非 `demo` 的速览；周报没有 AI 分析；链接论文没有已存的 PDF、PDF 版本或全文。
  - 画像：`profile_versions` 里除 `note="initial"` 外，凡属于本项目（`project_id` 为 `default_project` 或缺失）的版本（pin / restore / freeze / unfreeze…）一律保留整个库。
  - 设置：与它相关的只能是首启自己写的 `seed_keys`、`last_refresh`、`last_refresh_result`、`last_attempt`、`last_error`、`recommendation_eligibility`、`route_recall`、`source_publication_anomalies`；`project_goal`、`route_revision`、`profile_freeze`、`import_seed_keys` 等或任何未知设置都不动。
- **顺序与备份**：(1) 先单独提交标记 `in_progress`，让备份里也带标记（从备份恢复后不会再清理）；(2) `Store.backup` 写到唯一临时名，用另一个连接做 `PRAGMA quick_check` 并核对 projects/papers 行数和标记，通过后改名为唯一最终名 `<库>.pre-legacy-cleanup-<时间>-<id>.bak`（不信任也不覆盖任何已有文件；失败删残片、不删任何数据、记 `failed: backup…`）；(3) 在一个事务里再判定一遍、删除、把标记改成最终结果；任何异常回滚并记 `failed: …`，不重试。
- **删除清单**：项目行；它的 `project_papers` 链接、`batches` 和 `exposures`、`profile_snapshots`、`weekly_reports`、`org_*` 里以它命名的行、上述自动设置与 `route_exploration_evidence_<批次>`；只属于它的论文（没被别的项目链接、不在任何论文库、没有反馈/问答/其他曝光/导入引用）连同 `summaries`、`fulltext_languages`、`pdf_verification_*`；别的项目的 `org_projects` 里指向被删论文的 memberships/positions/protected 条目；被别的项目链接的论文保留，只删链接。全局的 `initial` 画像版本只在清理后已没有任何项目、且库里所有版本都是这种自动写入时才删。清理后若没有真实项目，走既有流程：无项目 → 指引 → 创建项目。
- **恢复**：退出应用，把 `<库>.pre-legacy-cleanup-….bak` 复制回 `paperdighelper.sqlite`（备份带 `in_progress` 标记，恢复后不会再清理；同目录的 `-wal`/`-shm` 文件要一起删掉）。备份不会自动删除。
- **中断与异常（复审后补充）**：标记停在 `in_progress`（清理途中进程被杀）等于永久不清理，下次启动只删除同名前缀的 `*.pre-legacy-cleanup.<uuid>.tmp` 残片，不重试；判定时遇到形状异常的存储数据按“用过”处理并记 `kept: unreadable`；项目里批次多于 1 个（另一天或同一天“再来一批”）即视为用过（`used_batches`）。备份是整库副本，库大时备份也大，不会自动删除。
- **跨分支风险**：清理之后若用旧 main / v0.1.0 的构建打开同一个真实库，它会新建 UUID 默认项目并再塞种子论文；新旧构建不要混用同一个数据目录。

## 没有验证

打包后的冻结二进制、Windows、真实桌面应用里的 `sessionStorage` 跨页保持（WKWebView / WebView2 的行为是推断）；fixture 的 arXiv 元数据与摘要已在 2026-10-24 联网核对一次（见 `harness/sources.json` 的 `DEMO-FIXTURE-ARXIV`），一行速览是手写的，不是模型输出。发布门是 `E-ONBOARDING`。
