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

## 补充：设置页收尾，演示里加入“论文库导入”和“划词提问”（2026-10-24，owner 追加）

owner 原话：“百度学术接口现在是没有的，只有百度搜索接口，把百度学术那个复选框删掉”“DeepSeek 的 key 那里也要做一个‘获取’的按钮”“演示里加入论文库导入演示和 AI 辅助读论文（提问）演示……提问要做成划词提问，划词很重要”。**这是 owner 的请求记录，`owner_approved` 仍是 false。** 不新增外发请求、模型调用或额度。

- **百度学术复选框删除**：设置页“数据源”里百度只剩一行：开关“百度搜索”，下面一行密钥（同一把千帆密钥）、状态词、测试、清除、获取（`#baiduScholarKey` 等 id 不变，指引 s4 的目标仍是这一行）。后端 `user_settings.baidu_scholar()` 由常量 `BAIDU_SCHOLAR_OFFERED = False` 关死：旧 `settings.json` 里残留的 `sourceBaiduScholar: true` 不再启用百度学术来源（刷新、创建检索、来源策略都读这个函数），数据不删、不改迁移；下一次在设置页保存时这个字段自然消失。适配器代码和 `/api/source-test` 保留（测试用模块级补丁打开）。
- **DeepSeek 密钥旁的“获取”**：`#apiKeyLink`，固定指向 `https://platform.deepseek.com/api_keys`（提供商只有一个，不像来源行那样由后端 `key_url` 给出），样式和打开方式与来源行的“获取”相同（`target=_blank`，桌面端同一个外链处理）。地址登记在 `harness/sources.json` 的 `DS-KEY-PAGE`（官方文档页链到它；页面本身要登录，没有核对登录后的内容）。
- **划词提问演示**：演示不带论文原文 PDF（arXiv 默认许可不允许转发）。`app/static/demo/reading-material.pdf` 是**本仓库自己写的**演示阅读材料（把 Attention Is All You Need 的改写摘要扩成一页英文笔记，首行“Demo reading material, not the paper's original text”，不引用原文），由 `scripts/make_demo_reading_pdf.py` 从 `app/demo_fixture.READING` 生成（纯标准库、确定性、测试会重新生成并逐字节比较）；Helvetica 标准字体、有真实文本层，高亮句子是 PDF 里的一块淡黄色矩形。只做英文 PDF：中文文本层需要内嵌 CJK 字体，纯标准库做不到可靠嵌入；回答、翻译和追问按界面语言。沙盒播种时把它登记为这篇论文的本地 PDF（`source_kind=user_import`），所以真实阅读器（`/api/pdf/prepare`、`/api/pdf/view`、pdf.js 文本层、`#selbar`、阅读助手）原样工作。pdf.js 自己取 PDF 不带演示请求头，所以演示里阅读器的地址带 `&project_id=pdh-demo`。只有这一篇的“阅读 PDF”在演示里显示（今日卡片和详情按钮用属性选择器），其余仍隐藏；失败面板里“选择或拖入 PDF”（会写真实库）在演示里不画。
- **问答与翻译是预写的，零 token**：`DemoApp.qa()` / `DemoApp.translate()` 覆盖真实方法（沙盒网关的 `call` 本来就抛错，这里根本不碰）。`/api/qa`、`/api/translate`、`/api/qa/session`、`/api/pdf/prepare`、`/api/fulltext` 加入演示白名单；真实路由里的项目归属、会话、PDF 版本校验照常，问答与回答写进沙盒的 `qa_history`。**匹配逻辑**（`demo.match_selection`）：把选中文字和每条预写句子都切成小写字母数字词，用最长公共连续片段判断；至少 4 个词，且片段占选区 ≥ 60%（选区是句子的一部分）或占句子 ≥ 80%（句子带着前后文被选中）；跨行、大小写、多余空白都无妨。翻译要求几乎整句（≥ 90%）。问题优先：问题恰好是某条预写的追问时按问题答，否则按选区答，都不是就给一条通用回答（说明这是预写的、真实使用时 AI 会针对选中内容回答，并提示选高亮的那句）。三条预写问答（自注意力、位置信息、多头注意力）各有中英回答、中文译文、两个互相引用的追问；回答带“演示 · 预先写好的回答”，翻译浮层标“划词翻译 · 演示”。点“追问”时演示里自动填好问题“这句话是什么意思？”，下一步只要点发送；演示里隐藏“附本页图”“更多上下文”（没有东西会被发送）和通用起始问题。
- **论文库导入演示**：真实导入页（`import.html`）和真实导入代码在沙盒里离线跑通：随包的 `app/static/demo/sample-library.bib`（3 条 arXiv 题录，元数据已于 2026-10-24 核对，摘要是为演示写的改写）经 `add_sidecar` → `resolve`（`online=false`，只做本地匹配）→ `commit`，3 篇出现在演示论文库。演示里服务端把批次选项强制成“不联网、导入没有 PDF 的题录”（`demo.import_options`），`resolve` 在请求里同步执行（后台线程会打开真实库）；白名单只放行 `/api/import/batches` 及 `sidecar/resolve/cancel/commit/discard/settle/categories/items/<n>`，PDF 上传和设为种子仍是 403。导入页在演示里隐藏文件选择、拖放区、Zotero 说明、选项、种子卡、分类卡和题录的“查找”，只留“使用示例文件”（取 `/demo/sample-library.bib`，交给原来的 `pick()`）。`import.js` 的 `api()` 在 `project_id=pdh-demo` 时带演示头，`/api/projects` 的 demo 描述用来显示项目名；导入页加载 `tour.js` 并 `boot('import')`。
- **指引步骤**：收藏之后加“阅读”一段 k1 打开演示阅读材料（今日卡片的“阅读 PDF”）→ k2 选中高亮句并点“追问”（新增 `clickOn`：这一步靠 `#selbar` 的追问按钮完成，而不是页面里的任何点击，聚光框是整个阅读区且不挡点击）→ k3 点发送 → k4 看预写回答 → k5 返回；论文库列表之后加导入 i1（库里的“导入论文”）→ i2 示例文件 → i3 开始导入 → i4 导入到论文库 → i5 回论文库（这三步在导入页）→ i6 列表里的新论文，然后图谱、画像、周报。阅读放在收藏之后、而不是图谱之后，是因为 Attention 是今日推荐的卡片而不是已收藏论文，这样不必来回切标签。机制照旧：15 秒目标没出现就降级为居中气泡，跳过、跨页恢复沿用。s2 加“点获取去申请”，s4 改说百度搜索。
- **没有选的**：做中文 PDF（要内嵌字体）；演示里放真实论文 PDF（许可）；导入演示只做讲解文字、不真的导入（真实流程可以安全离线，所以没有退到这一步）；用线程跑演示的解析（会打开真实库）。
- **没有验证**：真实 WKWebView 里的划词（用 `preview_eval` 在文本层创建 Selection 并派发 `mouseup` 代替鼠标拖选）；冻结二进制、Windows；独立审查；阅读步骤中途刷新页面时，阅读器已关闭，k2–k4 会因目标不存在 15 秒后降级为居中气泡（可以“下一步”继续）。

## 没有验证

打包后的冻结二进制、Windows、真实桌面应用里的 `sessionStorage` 跨页保持（WKWebView / WebView2 的行为是推断）；fixture 的 arXiv 元数据与摘要已在 2026-10-24 联网核对一次（见 `harness/sources.json` 的 `DEMO-FIXTURE-ARXIV`），一行速览是手写的，不是模型输出。发布门是 `E-ONBOARDING`。
