# 当前工作单元：学习图改成带箭头的图、项目改名/删除、已有项目的 AI 起草（2026-10-05，分支 feature/route-mode）

- **owner 反馈的四件事**：①项目不能编辑/删除；②已有项目不能用 AI 搭学习图；③学习图的结构和界面不对（看起来必须读完上一阶段才能下一阶段，没有节点到节点的关系，AI 给的常常是一条线）；④创建时 AI 生成的图太大，超出页面。
- **项目管理**：新页面 `project.html`（顶栏“管理项目”链接 + 项目总览每张卡上的“管理”按钮）。改名；删除要输入完全一致的项目名，并且先在数据目录写一份数据库备份（`paperdighelper.sqlite.pre-delete-<时间>-<项目前缀>.bak`，只留最近 3 份；备份失败就不删）。论文元数据、PDF、全文保留，别的项目不受影响。关键词不在这里改（它们是画像的钉住词）。
- **已有项目的 AI 起草**：学习图页“让 AI 起草”（有或没有学习图都能用）。显式点击，一次调用；只发送你写的目标（≤250 字）和项目前 5 个关键词；每个项目每个本地日最多 3 次付费尝试（网关拒绝而没发出去的不计）；结果只是草稿，点保存才生效，编辑在调用期间被锁住，草稿会沿用同名概念的旧 id，所以“已掌握/手动解锁”标记按名字保留。**它是单独登记的新操作 `learning_path_plan_project`，`owner_approved: false`**：独立审查指出我不能用自己的理解扩大你已经批准的 `learning_path_plan` 范围（AGENTS 规则 9）。你在 `harness/budget.json` 里把它的 `owner_approved` 改成 `true`（或告诉我“批准”，由我记录原话并改）之前，网关会在发出任何请求前拒绝，页面会写“等待你批准”，用量为 0（已在浏览器里端到端验证）。提示词文件 `prompts/learning-path-plan-project.md` 与会话版系统指令逐字相同。
- **学习图结构与界面**：提示词改为要求“依赖图而不是课程表”（互不依赖的基础方向各自成入口、一个概念可有 2–3 个前置、不要串成一条线），预算里 instructions 份额 500→560、框架余量 150→90（输入总上限 1200、输出上限 900 不变；都是保守字符估算，不是分词器实测）。页面按“最长前置链”分层布局并画出箭头：长边有自己的车道、同层按重心法减少交叉、概念贴在它的前置正下方；点一个概念高亮它的前置和它能解锁的概念，未解锁的概念写明“它只在等 X”；若 AI 给的是单线，页面直说。卡片上不再显示“第 N 层”。
- **大图不再超出页面**：图在可滚动视口里，有 +/−、适应宽度、看全图；创建页图在上详情在下；单列网格用 `minmax(0,1fr)`。
- 检查：Python 857 个测试 OK，node 120 个 OK，预算检查 PASS。变异检查：布局 5 处、后端 6 处（每日上限、退还、备份、设置清理、目标必填、并发锁）都被测试抓到；唯一没被抓到的是“发送全部关键词”，因为 `routeplan.messages` 另有一道截断，属于等价变异。浏览器预览（真实服务、画面里验证）：12 个概念的分支图、点击高亮、标记已掌握后只有对应分支解锁、编辑/添加/重名拒绝/放弃修改、AI 草稿（用拦截的假回复：单线提示、分支图、被拒绝）、创建页、改名、删除（含备份文件）、总览里的“管理”按钮。
- **没做/没验证**：没有调用真实模型，新提示词是否真的产出分支结构未知；Tauri 窗口没点；route-page.js / project-page.js / route-graph.js 的 mount 部分没有自动化 DOM 测试；知识库页（Cytoscape）路径图层、画像页 Route Mode 区块、图的生长界面（切片 7）、治理文件（切片 8）仍未做。预览数据目录里配置了 provider 且 AI 已开启，所以没有点真实的“让 AI 起草”。
- 见[自审](evidence/2026-10-05-route-graph-self-review.md)、[独立审查](evidence/2026-10-05-route-graph-review.md)、[检查证据](evidence/2026-10-05-route-graph-checks.txt)、[变更](../changes/2026-10-05-route-graph.json)。

# 当前工作单元：Route Mode 切片 6b——学习图页面与今日页面板（2026-10-05，分支 feature/route-mode）

- **今日页**：新增“学习图（路径模式）”面板（已读懂 n / 总数、探索约占 x%、现在在读的概念、进入学习图页的链接；学习图被关掉时写“学习图已关闭”，没有学习图时写“还没有学习图”），每张推荐卡带来源标签（路径 / 补基础 / 探索 + 概念名 + 第几层）。
- **学习图页面**（`route.html`）：按层分列，每个概念显示状态（已满足 / 可以读 / 未解锁）和明确计数（收藏、不感兴趣、太难、已展示）；所有手动操作都可撤销（标记已掌握、手动解锁、暂不优先）；编辑概念（改名、检索词、用复选框选前置——名字里有“/”也没问题）、添加、删除，保存带版本检查，冲突时保留未保存的修改；“用公开文献核对”；路径模式开关。创建页的编辑器同样改成复选框选前置。
- 独立审查：没有 XSS，另有 9 处问题全部修复，其中最重要的是：删掉再添加概念会让新概念继承旧概念的“已掌握”标记（现在标记要 id 和名字都一致才保留）；错误或冲突会丢掉未保存的编辑；`/api/home` 对大项目很慢（关掉的图不再匹配论文，开着的图按变化签名缓存）。见[审查记录](evidence/2026-10-05-route-page-review.md)。
- **已有项目（高硼硅、半导体生长等）还没有学习图**：现在只能在学习图页面手动搭建。让 AI 为已有项目生成超出 owner 批准的范围（批准的是“创建会话内”的一次生成），等 owner 另行决定。
- 还没做：知识库页（Cytoscape）的路径图层；画像页的 Route Mode 区块；图的生长界面（切片 7）；治理文件（切片 8）；Tauri 窗口里的点验。
- 见[检查证据](evidence/2026-10-05-route-page-checks.txt)、[自审](evidence/2026-10-05-route-page-self-review.md)、[变更](../changes/2026-10-05-route-page.json)。

# 当前工作单元：Route Mode 切片 6a——学习图驱动刷新和每日推荐（2026-10-05，分支 feature/route-mode）

- 有学习图的项目：刷新改为搜**当前能读的概念**（前置满足、自己还没满足；最多 3 个）的第一个检索词（相关度排序、近 10 年，某页用完就取下一页）；每日一批从这些概念里取论文，**各枝按各自进度推进**，同概念内综述/入门优先；证据少的概念和展示得少的概念分到更多名额，被评为低兴趣的概念名额减半但不会被丢掉；被标“太难”时补一篇前置概念的入门材料（每篇“太难”对应一篇、前置被手动标为已掌握则不补、一批只有一篇时不占位）；探索位随整体进度从约 10% 平滑升到 50%，按批次号确定、可回放，探索位没有可选时还给路径。**可读概念的论文用完时宁可少推并说明原因，也不拿锁定概念的论文凑数**；路径上一篇未展示论文都没有时才退回普通推荐并明确标注。没有学习图的项目完全不变。
- 每张推荐卡带上它的来源：概念名、层数、类型（路径 / 补基础 / 探索），**批次生成时就存进曝光记录**（迁移 008：`route_node/route_kind/route_name/route_layer`），所以之后换掉学习图也不会给旧卡片贴错名字。沉默与“不感兴趣”不改变掌握度，“太难”不当作不感兴趣。零模型 token。
- 迁移 008 在你真实数据库的**副本**上从版本 7 迁到 8 验证过：125 条曝光保留、完整性检查通过；真实数据库没有被动过，首次打开新版本时会自动迁移并沿用迁移前备份。
- 独立审查找到 3 个中等问题（探索位留空且提示错误、换图后旧卡片标签错位、刷新取不到新论文）和一批低级问题，全部修复；修复没有再让审查者复核。见[审查记录](evidence/2026-10-05-route-runtime-review.md)。
- 还没做：Today 页、画像页和知识库页都还看不到这些（切片 6b）；已有项目（高硼硅、半导体生长等）没有学习图，需要一个入口添加。
- 见[检查证据](evidence/2026-10-05-route-runtime-checks.txt)、[自审](evidence/2026-10-05-route-runtime-self-review.md)、[变更](../changes/2026-10-05-route-runtime.json)。

# 当前工作单元：Route Mode 切片 5——从目标生成学习图并在创建页确认（2026-10-05，分支 feature/route-mode）

- **新预算操作 `learning_path_plan`（owner 于 2026-10-05 在会话中批准）**：输入上限 1200 / 输出上限 900 token，单次参考约 $0.00111、上限约 $0.00144；只发送研究目标（≤250 字）和草稿关键词（≤5 个）；每个创建会话共 1 + 2 次付费尝试（回复读不出来或超时费用未知也算，网关在发送前拒绝的不算）。提示词文件 `prompts/learning-path-plan.md`、代码里的系统指令和登记一致。**没有做过任何真实 DeepSeek 调用**，真实回复是否符合这个结构未验证。
- 创建页的**学习图编辑器**（`app/static/route-editor.js` + `project-creation.js`）：按层分列的概念卡片、前置关系、“已掌握”起点、编辑/添加/删除、“用公开文献核对”（每个概念在 OpenAlex 找到多少篇，以及语料对先后顺序的倾向：支持 / 可能反了 / 不足，只发送概念的检索词），无 AI 时可手搭；创建项目时一并保存学习图（`create_project(route=)`，先校验再创建，已掌握的概念会解锁后继）。
- 独立审查找到 1 个严重、4 个重要问题并全部修复：**重新生成的次数上限曾被绕过**（计划和计数器存在会话草稿里，之后每次查找论文都会把它们清掉）；并发请求绕过上限；失败的付费尝试没计数；核对在断网时可能阻塞几分钟；页面与服务端校验不一致。还发现并修了我自己的一处：600 字的目标在全中文最坏情况下会超过 1200 输入上限，现在目标限 250 字。见[审查记录](evidence/2026-10-05-route-plan-review.md)。
- 在真实服务的浏览器预览里走通了创建流程并检查了保存结果；修复审查问题之后的最终状态靠测试覆盖，没有重新点击。
- 见[检查证据](evidence/2026-10-05-route-plan-checks.txt)、[自审](evidence/2026-10-05-route-plan-self-review.md)、[变更](../changes/2026-10-05-route-plan.json)。

# 当前工作单元：Route Mode 切片 4——按项目保存学习图（2026-10-05，分支 feature/route-mode）

- 路径图以**真实项目 ID 为键**存进知识库记录（`Organization(store, project=<项目ID>)`），和分类放在同一份 JSON 里，复用它的版本号、冲突检测、撤销（按名称与普通撤销）和迁移前备份。新增操作 `route-save`（接受 AI/手写的 `plan`，经 `normalize`；或结构化的 `graph`，经新的 `pathgraph.validate`）、`route-manual`（已掌握 / 解锁 / 降级）、`route-start`、`route-mode`；快照在有路径时带 `route`。服务端 `route_get` 由反馈**推导**每个概念的进度（撤销的反馈不算、冻结按 `through_feedback_id` 重放、种子算明确正向、一篇论文只算给最匹配的一个概念、建议中/归档的概念不收集证据也不挡路）；新接口 `GET/POST /api/route`（1 MB 请求上限，冲突返回 409）；删除项目会清掉它的知识库行。
- **有意收窄的一点**：计划里写的是把整个 `Organization` 改成按项目隔离。笔记触发器和语料都写死了全局收藏库与 `default`，整体改风险大，所以这一片只让**路径图**按项目隔离；分类树/知识库页的语料仍是全局的，等需要时单独做。
- 独立审查找到 6 个缺陷和一批低级问题（最严重：一条“建议中”的边会让校验删掉生效的前置边；重新保存计划会让“我已掌握”标记绑到无关概念上），全部修复并补测试，修复没有再让审查者复核。见[审查记录](evidence/2026-10-05-route-store-review.md)。
- 界面还没有用到路径图（切片 5、6）。
- 见[检查证据](evidence/2026-10-05-route-store-checks.txt)、[自审](evidence/2026-10-05-route-store-self-review.md)、[变更](../changes/2026-10-05-route-store.json)。

# 当前工作单元：Route Mode 切片 3——路径算法内核（2026-10-05，分支 feature/route-mode）

- 新增两个纯函数模块，**还没接进应用**：`app/pathgraph.py`（概念图的校验与修复——合并重复、按目标截断、丢悬空/自环/难度倒挂的边、破环、传递约简、入度上限、规范 id；分层；枝路进度：掌握度 m 由收藏提高、“太难”降低、沉默与“不感兴趣”不改变，前置全部满足才解锁，各枝独立推进；兴趣 p 只来自明确评价；探索份额随整体进度平滑上升且按批次号累计取整、可回放）和 `app/pathgrowth.py`（论文归属概念、边的语料支持度、前置缺口词、**新分支候选**：硬门槛 ≥3 篇不同论文、≥2 篇明确正向、≥2 个来源，强度 S·C·(0.5+0.5R)·N；父节点按子集包含、前置按引用不对称；只提议，合并出来的是 proposed 概念，需要人确认）。
- 独立审查（全新上下文的只读审查代理）发现 11 处缺陷，全部修复并补测试，其中最严重的是 AI 漏写 id 时所有概念得到同一个 id、截断到 12 个节点时可能丢掉目标本身。修复没有再让审查者复核。见[审查记录](evidence/2026-10-05-path-algorithm-review.md)。
- 所有阈值（0.6、0.35、探索 0.10–0.50、强度 0.25 等）都是提案，没有数据；评估基线已饱和，不能说“更好”。
- 下一步（切片 4）：按项目隔离的知识图谱——把这张图存进 `Organization`（`concept` 元数据和 `prereqs` 进 `org_projects.data`），并把组织的项目作用域从写死的 `default` 改成真实项目。
- 见[检查证据](evidence/2026-10-05-path-algorithm-checks.txt)、[自审](evidence/2026-10-05-path-algorithm-self-review.md)、[变更](../changes/2026-10-05-path-algorithm.json)。

# 当前工作单元：Route Mode 切片 2——打开应用时自动更新（2026-10-05，分支 feature/route-mode）

- owner 反馈新论文要手动点“抓取”才有。现在打开应用（和切换项目）时调用 `POST /api/maintain`：按设置页已有的“更新频率”（每天 / 每周 / 手动）判断到期才刷新候选池，今天还没有一批且有未展示论文时生成一批。**不补发漏掉的日子、不显示未读数、不触发 AI**；失败可见、30 分钟内不重试、不影响已有论文的那一批。页面显示“更新频率 · 上次刷新时间”。逻辑在 `app/maintenance.py`（可注入时间），状态保存在 `last_refresh_/last_attempt_/last_error_<project>` 设置里，删除项目时一并清理。
- 浏览器预览（真实服务）验证了完整流程：首次打开触发任务，新增 110 篇、生成 5 张卡片；同一天再次调用返回 due=false。检查中发现并修复了一个竞态（页面在后台任务结束前加载完成时状态行过期）。
- 仍未接入后端的设置：时间偏好、推荐数量、衰减窗口、新论文加权。
- 见[检查证据](evidence/2026-10-05-auto-maintenance-checks.txt)、[自审](evidence/2026-10-05-auto-maintenance-self-review.md)、[变更](../changes/2026-10-05-auto-maintenance.json)。

# 当前工作单元：Route Mode 切片 1——非 AI 学科的候选质量（2026-10-05，分支 feature/route-mode）

- owner 反馈其他学科“很旧、没有合法 PDF”。实测（owner 终端）：半导体生长不限年份时 1981–2019、中位 1996；近 10 年后 2017–2026、中位 2021。但合法 PDF 本身稀缺：半导体生长近 10 年 12 篇里只有 2 篇有直链，高硼硅 12 篇里 1 篇，AI 领域 7/9。
- 做了什么：创建候选默认近 10 年，页面加“不限年份”开关；刷新窗口改为相对 5 年（原来写死 2024-01-01）；`pdf_availability`（直链 / 仅原文页 / 无）进入创建候选和每日推荐卡并标注；相关度排序时在每 6 篇一组内把有直链的排前（不跨组、不丢弃）。
- 没做：只看开放获取的过滤（会让材料类候选大幅减少，需要时再做成开关）。
- 见[检查证据](evidence/2026-10-05-candidate-quality-checks.txt)、[自审](evidence/2026-10-05-candidate-quality-self-review.md)、[变更](../changes/2026-10-05-candidate-quality.json)。

# 当前工作单元：路径模式（Route Mode）——总览与切片 0（2026-10-05，分支 feature/route-mode）

- owner 要求：把创建时的学习路径做成画像里的路径模式；路径是**前置知识的拓扑图**（层是拓扑层次，不同枝路进度不同），**可随阅读生长**（强分支并入），并且**与知识图谱本质相同、要复用**。完整方案见计划文件的九个切片：0 修底座，1 候选质量，2 自动更新，3 算法内核 `pathgraph.py`，4 项目作用域的知识图谱，5 生成与创建（新预算操作，需 owner 批准），6 运行时与界面，7 图的生长，8 治理。每个切片通过测试和构建后在本分支本地提交。
- 切片 0（本条）：`build_batch` 的画像向量只用候选池，而候选池排除了已展示和已有反馈的论文，所以收藏/不感兴趣从未影响排序，已展示的种子也丢失；现在 IDF 与画像向量用项目全部论文。`ranking.tokenize` 增加中文字二元组（英文输出逐字节不变，预言测试）；`ranking.words` 保留旧的 ASCII 分词，所有展示给用户的词（引导关键词、画像兴趣词、共同主题）只用它，所以不会出现两字碎片；中文只通过完整的钉死短语出现在推荐理由里。等分时按“最新日期、再按 key”确定性排序。
- 未验证：真实数据上的排序质量（评估基线已饱和，不能说改进）；中文排序质量只有玩具例子。
- 见[检查证据](evidence/2026-10-05-ranking-foundation-checks.txt)、[自审](evidence/2026-10-05-ranking-foundation-self-review.md)、[变更](../changes/2026-10-05-ranking-foundation.json)。

# 当前工作单元：OpenAlex 主题检索——修复创建页搜不到候选（2026-10-04，分支 feature/pdf-acquisition）

- owner 新建“半导体生长”项目，创建页没有候选论文；“古典文学发展史”同样一篇都没有。**不是没接 OpenAlex**：创建页走的是 DATA-01 的配方（只查 arXiv、只匹配标题且每个词都要出现、2024 年起，中文原样发给英文标题索引），实测中文词 0 篇、三个英文词 0 篇。
- 修复（[ADR 0012](decisions/0012-openalex-topic-discovery.md)）：`OpenAlex.discover_topic`（标题+摘要、不限来源、相关度排序、严格匹配不足时用相关度补足、含中文直接走相关度）；检索短语清洗防止改变过滤器；AI 引导提示词加一句要求同时给英文和中文检索式；项目刷新改为搜项目自己的关键词（默认项目仍用 world model 配方）；种子选择器把标题吻合的排前面并去重；缓存加新鲜度和离线兜底；记录并在设置页显示 OpenAlex 剩余额度；有 key 时请求后停顿 0.3 秒。
- 实测（owner 终端）：四种检索式都有 11–12 个候选，每次约 2 秒（之前约 3.7 秒）。见[检查证据](evidence/2026-10-04-openalex-discovery-checks.txt)。
- 还没解决：中文文献在 OpenAlex 里偏旧、质量参差，要覆盖知网等需要 `worktree-channels` 的渠道方案；OpenAlex 对预印本缺引用关系；合并 channels 分支时本改动会与它的 `app/channels/openalex.py`、`app/sources.py` 冲突，需要人工处理。
- 见[变更](../changes/2026-10-04-openalex-topic-discovery.json)。

# 当前工作单元：Unpaywall 评估——结论是这一版不接（2026-10-04，分支 feature/pdf-acquisition）

- owner 要求先量再定。用私有脚本（`.local/unpaywall_compare.py`，不提交）对两个主题各 50 篇非 arXiv 期刊论文，比较 OpenAlex 与 Unpaywall 的 PDF 直链：Unpaywall 独有 0/77，两边都有 41，23 个 DOI 在 Unpaywall 查不到。Unpaywall 没有增量，不接；缺口是“开放获取但只有落地页”（20/100），现有的落地页链接和手动附加就是对应办法。
- 样本只有两个主题、100 篇、2023 年以后，不是 owner 的库；邮箱用的是占位地址，真实邮箱没有外发。证据见[测量记录](evidence/2026-10-04-unpaywall-measurement.txt)，决定写进 [ADR 0011](decisions/0011-pdf-acquisition.md)，变更见[记录](../changes/2026-10-04-unpaywall-decision.json)。

# 当前工作单元：修复迁移编号冲突导致的启动崩溃（2026-10-04，分支 feature/pdf-acquisition）

- 现象：owner 打开新构建的 app，显示“项目加载失败”。
- 原因（已复现）：owner 的真实数据库 `schema_version` 已有 `5`（2026-10-02，来自 `worktree-channels` 分支的 `migrate_005_channels`）。本分支原先的迁移也编号 005，被当作已完成而跳过，列没加；随后的 006 从不存在的 `pdfs.sha256` 读取，启动时抛 `no such column: sha256`。上一个构建（bbcdf2a）在真实数据库副本上稳定复现；此前的构建没有在启动路径上用到这些列，所以没暴露。我之前的测试都用全新临时数据库，没覆盖“另一个分支的迁移已在真实库里”。
- 修复（见 [ADR 0011](decisions/0011-pdf-acquisition.md) 第 10 条）：迁移按编号逐个判断是否已记录；本分支迁移改为 006/007，5 留作 channels 的保留位；每个迁移在事务里执行，失败整体回滚。真实库副本验证：2 个项目能读出、channels 的表原样保留、23 条 PDF 记录补进历史表、完整性检查通过。真实数据库本身没有被我改动（只读副本），重新打开新构建时会自动迁移，并沿用已有的 `.pre-v5.bak` 备份。
- 合并两个分支时：把 `migrate_005_reserved_for_channels` 换成 channels 分支的 `migrate_005_channels`；两边的数据库都不会漏迁移。
- 见[检查证据](evidence/2026-10-04-migration-fix-checks.txt)、[变更](../changes/2026-10-04-migration-collision-fix.json)。

# 当前工作单元：独立审查的修复与移除无效的 mailto（2026-10-04，分支 feature/pdf-acquisition）

- 独立审查（全新上下文的审查代理，只读）对 `1f5ada9..aba281e` 给出 8 条发现，密钥处理被确认安全。已修：**抓取器每个请求都被重建**（桌面服务每次请求新建 `App`），导致间隔、arXiv 15 秒 Crawl-delay、robots 缓存全部失效，现在是进程内共享并加主机级锁；非 OSError 的异常（`InvalidURL`、`UnicodeError`、`IncompleteRead`…）会逃出 `download_pdf`，现已归类；重定向目标没有 robots/间隔/公网检查，现已加上；替换 PDF 丢失旧来源，新增 `pdf_versions`（迁移 006）；只有两条路由检查 Origin，现在所有写入路由都检查；迁移 005 吞掉所有 `OperationalError`，现只忽略重复列；robots 429 被当成“无限制”，现按不可用。没改并说明理由：robots.txt 请求不计入间隔（否则第一次下载要等 15 秒）；附加本地 PDF 仍是一次性上传。
- 实测并移除 `mailto`：OpenAlex 官方弃用页说礼貌通道已被 API 密钥取代，“`mailto` 被忽略”；四种组合实测额度与耗时一致。设置页的“联系邮箱”已删除，不再向 OpenAlex 发送用户邮箱（`settings.json` 里已有的 `contactEmail` 无害，下次保存设置时会被丢掉）。
- 打包版检查：`.app` 内的服务能启动，从零迁移到最新版本，新页面和路由可用，无会话 cookie 返回 403；Tauri 壳能启动并加载页面，但 macOS 权限不允许我截图或点击窗口，所以窗口里的点击没有做过。
- 见[独立审查记录](evidence/2026-10-04-independent-review.md)、[变更](../changes/2026-10-04-review-fixes-and-mailto.json)。

# 当前工作单元：PDF 获取收尾——手动附加、落地页、实测（2026-10-04，分支 feature/pdf-acquisition）

- 把 plan 里剩下的做完：为已有论文手动附加 PDF（`POST /api/pdf/attach`，复用 `/api/seeds/pdf` 上传和 `take_imported_pdf`，以 `source_kind=user_import` 记录，已有下载文件不删）；开放获取但只有落地页的论文报 `landing_page_only` 并显示“打开原文页面”；所有失败都提供“附加本地 PDF”。
- 实测（详见[检查证据](evidence/2026-10-04-pdf-acquisition-checks.txt)）：浏览器里验证了失败框、落地页链接、附加合法 PDF 后阅读器渲染、附加非 PDF 被拒；无网络环境下已归档的 arXiv PDF 哈希一致且经本地 HTTP 原样提供；dl.acm.org 与 sciencedirect.com 返回 403，如实报告、不重试、不绕过。
- E-PDF-ARCHIVE 改为 `passed`（自测，不是独立审查；断点续传没做，按“一次受限重试”解释）；PDF-01 改为 `review`。
- 仍然没做：独立审查；Unpaywall（第二阶段，需要 owner 批准，是否需要取决于更多非 arXiv 样本）；`mailto` 在有密钥时是否仍有作用；Tauri 窗口本身的点验（同一批静态页面在浏览器预览里验证过）。
- 变更见[变更](../changes/2026-10-04-pdf-attach-and-landing.json)。

# 当前工作单元：OpenAlex API 密钥（2026-10-04，分支 feature/pdf-acquisition）

- 起因：owner 申请了 OpenAlex 免费密钥以获得更高额度，并已在设置里填联系邮箱。此前代码没有任何密钥支持。
- 做了什么（见 [ADR 0011](decisions/0011-pdf-acquisition.md) 第 8 条）：新增 `app/openalex_key.py`（独立文件 `openalex.key`、0600、环境变量优先、不回显）；`OpenAlex._request` 只把密钥作为 `Authorization` 请求头发给 `https://api.openalex.org`；设置页新增“OpenAlex API 密钥（可选）”与清除按钮；`/api/settings` 增加 `openalex_key`、`clear_openalex_key` 与状态字段；`tools/data_probe.py` 读环境变量。登记了 `OPENALEX-AUTH` 来源。
- 注意：owner 在对话里贴出了密钥原文，它已出现在会话记录里。密钥没有写入任何仓库文件、测试或命令。免费密钥风险有限，若在意可在 OpenAlex 账号页轮换。
- 实测（2026-10-04，owner 机器上、密钥不外显）：Bearer 请求头被识别（错误密钥返回 401）；额度从无密钥的 1000 credits / $0.10 每天提高到 10000 credits / $1 每天。真实下载：arXiv 论文与 OpenAlex 回退论文都得到有效 PDF，重复请求走缓存，并等待了 arXiv 的 15 秒 Crawl-delay；Nature 的 DreamerV3 只有落地页，报 `no_oa_source`。
- 未验证：`mailto` 在有密钥时是否仍有作用；403 付费论文；在应用阅读器里离线打开下载的文件和失败文案；设置页在运行的应用里的表现。
- 自审与变更见[自审](evidence/2026-10-04-openalex-key-self-review.md)、[变更](../changes/2026-10-04-openalex-api-key.json)。

# 当前工作单元：PDF 获取与开放获取来源（2026-10-04，分支 feature/pdf-acquisition）

- 起因：owner 询问 OpenAlex 能否下载 PDF，并给出“OpenAlex + arXiv + Unpaywall”的建议。现状是 `download_pdf` 只会抓 arXiv，失败原因被吞掉。决定：Unpaywall 留到第二阶段；owner 提供真实联系邮箱并写入设置；不用 embedding（违反 AGENTS 边界 2）。
- 做了什么（详见 [ADR 0011](decisions/0011-pdf-acquisition.md)）：
  - `slim()` 保留 OpenAlex 的开放获取信息（只留 https PDF 链接）；迁移 005 增加 `papers.oa_json` 与 `pdfs` 的 `sha256/bytes/source_kind/license`。
  - 新增 `app/pdf_fetch.py`：来源顺序（arXiv，再 OpenAlex 链接）、robots（含 Crawl-delay）、速率、重试一次、https 限制、60 MB 上限、`%PDF-` 检查、原子写入、sha256。`App.download_pdf` 改用它，失败返回具体原因。
  - 阅读器显示失败原因；设置页新增“联系邮箱（OpenAlex）”。`tools/data_probe.py` 输出 PDF 候选覆盖率。
  - 登记了 `OPENALEX-OA`、`ARXIV-PDF` 两个来源；官方文档页核对了字段名，arXiv robots.txt 当前 Crawl-delay 为 15 秒、允许 /pdf。
- 没有新增模型操作，零 token，不改预算。
- 未验证：真实下载（arXiv、非 arXiv 开放获取、付费论文各一篇）；OpenAlex 开放获取链接在真实记录上的命中率（请运行 `tools/data_probe.py`）；arXiv 批量/自动访问帮助页没读到（超时）；桌面包里实际打开阅读器。E-PDF-ARCHIVE 仍是 `not_run`。
- 缺口：没有为已有论文手动附加 PDF 的入口（计划里提到，本单元未做）。
- 独立审查未做；见[自审](evidence/2026-10-04-pdf-acquisition-self-review.md)和[变更](../changes/2026-10-04-pdf-acquisition.json)。

# 当前工作单元：创建项目流程重做（2026-10-02，分支 feature/project-creation-redesign）

- owner 反馈：AI 参与时没有状态反馈、不知道有没有在请求；候选论文空白后整批突然出现且只有题目；快速创建和 AI 引导几乎一样；手动种子只认标识符，应能拖 PDF 或按名称检索。
- 做了什么（详见 [ADR 0010](decisions/0010-project-creation-flow.md)）：
  - 页面拆成 `project_creation.html` + `project-creation.css` + `project-creation.js` + `creation-pdf.js`（纯函数，有 node 测试）。
  - 每次等待显示动作和已等秒数；每个 AI 回合标明“AI 已回复 · 约 N token · X 秒”或“没有使用 AI + 原因”（无 key、总开关关闭、未批准、预算、HTTP、网络、回复格式），可一键重试；没拿到 AI 回答的回合不占 6 轮名额。
  - 候选论文逐条检索、逐批出现，先有占位；卡片有作者、日期、可展开摘要、原文链接和命中的检索式；不预勾选。
  - 快速创建＝一次 AI（服务端限制 1 次 AI 回合）+ 自动检索 + 审阅；AI 引导＝对话（开始即回应目标，页面上的修改带入下一轮）；手动创建＝关键词 + 种子（DOI/arXiv/链接、名称检索、拖入 PDF）。
  - PDF：浏览器用内置 pdf.js 读前两页，找 arXiv 编号 / DOI / 标题，再向 OpenAlex 核对（相似度 ≥ 0.8 自动采用，否则让用户选）；原文件保存为该论文的 PDF，不上传。Tauri 窗口加了 `disable_drag_drop_handler()`。
  - 后端：新增 `app/creation.py`、路由 `/api/seeds/resolve|search|pdf` 和 `/api/project-guidance/sessions/<id>/search`，`turn` 增加 `retry` 与 `draft`。
- 没有新增模型操作，也没有改预算上限。
- 未验证：桌面包里实际拖放 PDF、OpenAlex 名称检索与 PDF 匹配的真实命中率、真实 DeepSeek 回合；沙盒连不上外网，浏览器检查用的是模拟接口。候选检索本身仍是 arXiv / 2024 起 / 按日期倒序的标题词检索。
- 独立审查未做；见[自审](evidence/2026-10-02-creation-flow-review.md)和[变更](../changes/2026-10-02-creation-flow.json)。

# 当前工作单元：项目创建的 AI 引导接上模型（2026-10-01）

- owner 反馈：创建项目的三种入口测试时都是本地模式，没有接上模型。
- 原因：不是接线错误。`harness/budget.json` 里 `project_guidance` 的 `owner_approved` 一直是 `false`，网关 `admit()` 因此对每一轮都返回“待 owner 批准”，服务退回本地词项解析。手动创建本来就不调用模型；快速创建和 AI 引导走同一个 `guidance_turn`。
- owner 在会话中明确批准后，改为 `owner_approved: true`（单会话最多 6 轮，每轮上限 1200 输入 / 500 输出，沿用全局日/月上限；没有 key、AI 总开关关闭或超预算时仍降级为本地模式）。
- 顺带修复：系统提示里的 JSON 示例缺了 `search_queries` 与 `next_question` 的开头引号（审批前从未真正发送过），加了解析该示例的测试。
- 测试：原来断言“未批准就拒绝”的三个测试改为用关闭审批的网关配置验证机制；新增“已批准则发送一次并按上限预留”和“模型回复生成 mode=ai”的测试。`test_project_chain` 现在整类替换 `urlopen`，因为该操作批准后不再是“没发请求”。
- 未实测：没有对 DeepSeek 做真实调用，回答质量和实际 token 用量都没有测量；沙盒阻止本地端口，HTTP 测试需在终端重跑。创建页仍写“本地优先”“可随时切换本地模式”，降级原因（无 key / 总开关 / 超预算）仍只显示“AI 未参与本轮”。

# 当前工作单元：知识库清空的类别自动删除（2026-10-01）

- owner 反馈：在论文库里「编辑类别」后，某个类别下已经没有论文，但类别还留着，应当删掉。
- 修复：`membership` 操作结束后，本次被移除论文的类别若已没有已收藏论文、也没有子类别，就删除；删除后上级类别如果也随之变空，一并删除。没被这次编辑动过的空类别（例如刚新建、还没放论文的）保留。删除时同步清理排序、折叠和布局，并移除未收藏论文对它的残留归属。`suggest-apply` 的旧清理代码改为复用同一个 `_remove_directions`。
- 编辑类别对话框加了一句提示；整个操作仍是一条「调整分类」，可撤销恢复。
- 回归测试在 `tests/test_organization.py`。沙盒阻止本地端口，24 个 HTTP 测试未能运行，其余全部通过。已构建 `.app`，未在 .app 中人工点验。记录见[变更](../changes/2026-10-01-empty-category.json)。

# 当前工作单元：界面语言切换真正生效（2026-10-01）

- owner 反馈：设置里把语言调成 English，界面依然是中文。
- 原因：`app/static/i18n.js` 和语言包从来没有被任何页面加载，服务端也没有读取语言设置；设置只是存进了 `settings.json`。
- 修复：
  - `app/language.py` 读取 `settings.json` 的 `language`，缺失或无效一律按中文。
  - 服务端给每个页面的 `<head>` 注入 `/i18n/current.js` 与 `/i18n.js`；英文时下发 `app/static/i18n/en-US.json`（642 条，以中文原文为键），语言包损坏时回退中文。
  - `i18n.js` 按原文精确匹配、` · ` 列表逐段、`{0}` 模式三种方式翻译文字节点、提示、对话框；输入框只翻译占位提示，不动用户输入。用户问题、AI 回答、划词翻译结果，以及标题、摘要、AI 速览正文、引用原文都标记 `data-no-i18n`，不会被改写。
  - 模式里的中文片段只有整段是词条、词条列表或另一句模式句才翻译，否则原样保留；量词（篇、页…）旁和「第/共」后的位置只接数字；片段和键里的中文粘连时不套用该模式。这样「收藏夹」「首页」这类词和名字不会被半翻译。
  - 服务端自己写的说明（推荐理由、本地引导、候选不足、周报分析、整理建议的名称与理由）有英文分支。
  - 英文界面下，AI 问答换成英文系统指令，速览、项目引导追加一句「用英文回答」（速览放在画像和候选文本之前），估计多 40–60 token（估算，未实测）；中文界面的提示逐字不变。
  - `scripts/i18n_extract.py` 静态列出所有界面中文字符串，测试要求每条都有英文。
- 独立审查：第一轮未通过（半翻译、数据目录不一致、单复数、指令位置、head 正则、看图提示文档），第二轮发现嵌套句子仍半翻译，修复后第三轮通过；第三轮的三条小意见（嵌套句子粘连、风险措辞、本文件过时）随后也已处理。见[审查](evidence/2026-10-01-i18n-review.md)。
- 限制：论文标题、用户笔记、已存的类别名、缓存的中文 AI 速览等用户数据保持原样，不翻译。
- 预览实测（英文）：主页、论文库、知识库、画像、阅读器、设置、建项目、周报只剩用户数据是中文；切回中文一切照旧。没有发真实的英文 AI 请求。记录见[变更](../changes/2026-10-01-i18n.json)和[审查](evidence/2026-10-01-i18n-review.md)。

# 当前工作单元：阅读助手看图——中文编号与图/表区分（2026-10-01）

- owner 反馈：提问时让它看图，它看不了，怀疑 DeepSeek 接口或连接有问题。
- 结论：不是接口或连接问题。官方 vision 指南确认 `deepseek-flash` 接受 `image_url`（base64 data URL），网关的请求格式也正确。但账本里 `paper_vision_qa` 一次都没调用过：前端只在问题含阿拉伯数字（图2、Figure 2）时才附图，owner 问的是「图二」，于是走了纯文本问答。
- 另一个原有 bug：服务端定位图页不区分图和表，「Figure 2」命中了第 11 页的「Table 2」图注。真正的 Figure 2 图注在第 4 页，被 PDF 文本粘成「RobotwinFigure 2 Data construction」。
- 修复：
  - 新增 `app/static/figure-intent.js`：识别中文数字编号（图二、第三张图、表十二）和不带编号的看图问法（这张图、图中…、上图、this figure）；主题词（图像生成、图神经网络、这表明）不触发。
  - `service.py` 按图/表/公式分别匹配大小写敏感的标签，识别行首、冒号、无冒号首字母大写三种图注。
  - 输入框加「附本页图」开关，只作用于下一个问题。附图时系统指令追加一句看图要求。
  - `image` 只接受本地渲染的 base64 data URL。
- 预算登记不变。预览中拦截 `/api/qa` 验证：owner 原话两条都附了第 4 页；另经 owner 批准发过一次真实看图请求（I-JEPA「图二画的是什么」，自动附第 2 页，$0.0015），回答与 Figure 2 一致；只有一个样本，且文字层也含图注，像素理解效果未系统测量。记录见[变更](../changes/2026-10-01-reader-vision.json)和[审查](evidence/2026-10-01-reader-vision-review.md)。

# 当前工作单元：知识库整理建议按画像细分（2026-10-01）

- owner 反馈：「整理建议」太宽泛、像瞎分；应按画像分类，而且分得太粗（世界模型只是其中一个小类）；建议左边两个按钮没用。
- 建议改由 `app/organization_facets.py` 生成：一级类别 = 当前项目画像的固定关键词；子类 = 类内多篇标题共有的短语（每类最多 6 个）。不再使用 OpenAlex topic 或 Louvain 宽社区。离线、确定性、零模型 token。
- 画像词经 worker stdin 传入，不进命令行。弹窗显示层级和每类依据；没成类或超出 12 个上限的关键词都会写明。
- 工具栏去掉「刷新」；「撤销」写明要撤销的内容，布局保存不占撤销。旧库 `org_events` 加 `label` 列，加列前先备份。
- 独立审查（code-reviewer 子代理）提出的 7 项已修复并加回归测试。2000 篇合成库单次约 3 秒（本机实测）。
- 未测：其他学科真实语料的分组质量；.app 内需 owner 实际看一遍。记录见[变更](../changes/2026-10-01-profile-suggestions.json)和[审查](evidence/2026-10-01-profile-suggestions-review.md)。

# 当前工作单元：阅读助手追问——引用不再占满面板（2026-10-01）

- owner 反馈：追问时引用会占满整个面板，什么都看不见。原因是 UI 重设计时删掉了引用卡片的截断样式。
- 引用改到输入框上方，作为两行卡片（显示页码和字数，可点击展开）；对话区保留最小高度。
- 输入框改为多行：中文输入法选词时的回车不再发送；等待回答时输入内容不会被清空。
- `/api/qa` 不变。引用长度仍无上限，是否加上限待 owner 决定。记录见[变更](../changes/2026-10-01-assistant-composer.json)和[自审](evidence/2026-10-01-assistant-composer-review.md)。

# 当前工作单元：修复 PDF 阅读器捏合误开项目总览（2026-10-01）

- owner 反馈：在 PDF 阅读器里双指捏合缩小，会同时打开项目总览。
- 原因：项目总览在 `window` 上监听捏合，只排除了知识库图谱。
- 修复：阅读器打开期间（`body.reader-open`），以及捏合落在 `#reader`/`.pdfbox` 内时，都不打开总览；阅读器自己的缩放照常。
- 零模型调用。只用合成 ctrl+wheel 事件在预览中验证过；.app 的 WKWebView 手势事件走同一判断，但需要 owner 实机确认。记录见[变更](../changes/2026-10-01-reader-pinch.json)和[自审](evidence/2026-10-01-reader-pinch-review.md)。

# 当前工作单元：画像页改成仪表盘（2026-10-01）

- owner 反馈：画像页满是说明文字，像在“说废话”，希望反馈更直观，做成仪表盘。
- 只改前端 `app/static/profile-ui.js` 与 `profile.css`，全部由现有 `/api/profile/insights` 的本地计数算出，不改后端，零模型调用。
- 页面从上到下：
  - 标题行：主要词项，学习中/已冻结状态。
  - 5 个指标卡：收藏、有用、不相关、太难、本周活动。每张卡有本周新增、上周数量和 12 周迷你走势，点击看来源。
  - 兴趣词项条形图，固定关键词放在图的顶部。
  - 明确反馈环形图：有用率 = 有用 ÷（有用 + 不相关），并显示样本数；样本少于 5 时提示仅供参考；“太难”不计入。
  - 12 周堆叠柱状图，每一列可点开当周记录。
  - 本周动向：本周与上周的对比条，以及升/降词项。两周不可比较时不显示“下降”。
  - 最近反馈（可撤销）。
  - 原来散在各处的免责说明合并为页面底部一句。
- “修正画像”区保留不变。周报页 `weekly_report.html` 继续使用 `weeklyHTML`，也未改动。
- 记录见[变更](../changes/2026-10-01-profile-dashboard.json)和[自审](evidence/2026-10-01-profile-dashboard-review.md)。

# 当前工作单元：知识库论文详情的类别与字号（2026-09-30）

- owner 反馈了两个问题：点开论文后看不到它属于哪一类；右侧详情的字号不合理。
- 类别：
  - 详情标题下新增“所属类别”卡片。胶囊可以点击，点击后定位到该类别；没有类别时显示“未分类”；“编辑类别”放在卡片内。
  - 保存为默认色的类别，现在按目录顺序分配不同色相。图谱节点、目录圆点、列表标签和详情胶囊使用同一套颜色。
- 字号：
  - 原来详情顶栏的 `:first-child` 规则也命中了笔记区：“笔记”只有 12px，编辑/预览按钮却是 21px。现已限定为直接子元素，并重新整理了字号层级。
  - 论文库列表卡片原先横排挤压，现已改为纵向排版。
- 零模型调用。饱和度上调后的观感需要 owner 目测确认。记录见[变更](../changes/2026-09-30-knowledge-detail.json)和[自审](evidence/2026-09-30-knowledge-detail-review.md)。

# 当前工作单元：创建项目功能测试修复 + Mission Control 式项目总览（2026-09-30）

- 逐项测试了创建项目页面，并修复了以下问题：
  - 早期 arXiv 种子解析失败。
  - 重复种子会重复请求。
  - 多个种子的失败状态被合并成一条。
  - 快速创建时第一轮目标被重复记录。
  - 中文目标在本地模式下提取不到词，却没有任何提示。
  - OpenAlex 503/429 显示为多条重复的通用错误。现在归为 `unavailable`：遇到后停止剩余查询，只显示一条错误。
  - 手动创建时，失败的种子状态闪一下就自动跳走。现在会停在结果页。
  - 本地模式下无法编辑学习路径。现在可以手动添加、删除阶段，最多 8 个。
- 项目下拉菜单换成了 macOS Mission Control（调度中心）式的项目总览，代码在 `app/static/project-switcher.js`：
  - 打开时，当前页面缩小成一张窗口卡片，所有项目以窗口缩略图的网格排列；选中的项目会放大回全屏。
  - 四指上推和 ⌃↑ 被系统占用，应用收不到，所以打开方式改为：⌥↑、点击项目名、触控板双指捏合。
  - 双指张开进入当前高亮的项目；Esc 或点击空白处回到当前项目。
  - 本次会话中打开过的项目，显示离开时的页面快照（只存在内存中，最多 8 个）；没打开过的项目显示占位页。
- 验证与已知缺口：
  - 零模型调用。
  - 真实候选导入没有测过（OpenAlex 匿名检索暂停，返回 503）。
  - ⌥↑ 和捏合手势还没有在 .app 中用真实输入验证过。
  - 保存的学习路径目前没有任何页面展示。
  - 记录见[变更](../changes/2026-09-30-project-creation-switcher.json)和[自审](evidence/2026-09-30-project-creation-switcher-review.md)。

# 当前工作单元：整体 UI 改为 logo 配色（2026-09-30）

- owner 反馈原 UI（紫色拟物风 + 五种可选强调色）与书签海狮 logo 不搭、颜色太花。现改为单一纸/墨/红配色：`app/static/theme.css` 为唯一色板来源，四个页面都链接它；红色只用于收藏/书签、当前标签、字标 “Dig”、图谱起点等“标记”位置；标题用衬线字体；强调色选择器已删除。
- 深浅模式统一为 `pdh-mode` 键（无值跟随系统），切换时图谱实时重绘。创建项目页原先是独立的深紫主题，也已并入同一色板；周报页补上了色板与返回按钮样式。
- 零模型调用、零预算影响。`tests/test_ui_contrast.py` 锁定单一色板与对比度；283 + 30 个测试在用户终端通过。自审见 [UI 重设计自审](evidence/2026-09-30-ui-redesign-review.md)，记录见 [变更](../changes/2026-09-30-ui-redesign.json)。审美需 owner 在 .app 中确认。

# 当前工作单元：应用图标替换为书签海狮（2026-09-30）

- owner 选定「书签海狮」为 PaperDig 标志（落选：鼹鼠、寻回犬、瑞吉正面顶书等探索稿，已删除）。唯一生成源：`docs/design/logo/sealion.html`；`python3 docs/design/logo/build_icons.py` 重新导出 SVG 母版、`app/static/{brand-mark,favicon}.svg` 和 `src-tauri/icons/`（手工组装 `icon.icns`，因沙箱内 `iconutil` 失败）。≤32 px 使用简化母版（无腮红、鳍缝加宽、眼睛放大）。
- 接入：`tauri.conf.json` 的 `bundle.icon`；首页品牌标识改为 `/brand-mark.svg`；四个页面加 SVG favicon。`app/static/icons/` 下的功能性线条图标没有改动。零模型调用，零预算影响。
- 验证见 [检查](evidence/2026-09-30-app-icon-checks.txt)：281 个测试在用户终端全部通过（沙箱不允许本地端口绑定），桌面构建成功，.app 内的 `icon.icns` 与源文件一致。Dock/Finder 可能缓存旧图标，需重新启动应用或重建图标缓存后才会显示新图标。

# 当前工作单元：PROJECT-01 依赖链收口（2026-09-30）

- 范围：只收口 `PLAN-02`/`BUDGET-01`/`DATA-01` → `CORE-01`/`REUSE-01` → `PROFILE-01` → `EVAL-01`/`AI-01` → `PROJECT-01`；`PROFILE-02`、`PILOT-01` 状态不变。没有真实模型调用，`project_guidance` 仍 `owner_approved=false`。
- 结果：`BUDGET-01` 为 `done`；其余 8 项为 `review`，逐项缺口见 [链路状态](evidence/2026-09-30-project01-chain-status.md) 与 `harness/tasks.json` 的 `missing_inputs`。最关键的 owner 输入：PLAN-02 的最小有意义差值/样本量/资源目标、owner 盲评标签、是否接受保留现有排序器、`project_guidance` 真实调用批准。
- 新增行为：画像冻结/解冻、恢复默认（可找回原钉死词）；反馈幂等；撤销回放一致（收藏保留，沿用画像重构决定）；“太难”不进入负例；不足五篇给出 `shortfall` 原因；种子逐个报告 resolved/duplicate/not_found/network_error/failed（404 不重试）；迁移前自动备份；删除项目清理曝光/问答/引导记录/项目设置；跨项目加入不会把种子降级；只能取消草稿会话。网关预留账本与 AI 总开关见 [ADR 0009](decisions/0009-gateway-ledger-profile-control.md)。
- 本地基线：[REUSE-01 基线](evidence/2026-09-30-reuse-baseline.md)，SVM 相比现有排序器无实质增益；P@5 饱和，结论只作探索性参考；上游探针未运行。
- 测试：`tests/test_profile_core_chain.py`、`tests/test_project_chain.py`、`tests/test_gateway_budget.py`。本沙箱禁止本地端口绑定，23 个 HTTP 测试无法运行；新增路由用 socketpair 驱动真实 Handler 补测（15/15），详见 [检查](evidence/2026-09-30-project01-chain-checks.txt)。需在允许 `sandbox.network.allowLocalBinding` 的环境重跑全量。`harness.py review changes/2026-09-30-project01-chain.json` 目前只剩这一项未通过（测试检查如实记录 exit 1）。
- 独立审查（结论：修复后通过，无阻断项）：已修复 3 个重要问题：自由文本或异常种子在项目写入后抛出未捕获错误；取消收藏后重复点“有用”仍报告已保存；冻结期间撤销冻结前的反馈不生效。另外已限制客户端设置 seed 关系，并修正了基线表的措辞。其余次要项见 [审查记录](evidence/2026-09-30-project01-chain-review.md)。
- 已知未做：设置页的推荐数量、衰减窗口、新论文加权、来源、更新频率、时间偏好字段仍未接入后端；“探索主题”未成为结构化画像字段。

# 当前工作单元：PROJECT-01 项目引导与跨项目共享（2026-10-01）

已实现本地 `project_guidance_sessions` 草稿会话、六轮结构化引导、候选预览、用户确认和本地降级；手动 DOI/arXiv 种子逐个解析并记录部分失败。新增 `project_papers` 与 `project_library` 迁移，使规范论文事实可跨项目复用，同时反馈、收藏、曝光、推荐、画像和问答历史保持项目隔离。论文详情支持显式加入其他项目，项目删除只清理关系和项目状态，不删除全局论文事实。

新增验证覆盖会话恢复/取消/六轮上限、AI/本地路径、候选确认、共享论文隔离、删除保留、HTTP 路由和创建页静态行为。预算登记了独立的 `project_guidance` 操作；本工作单元完成时它标记为待 owner 批准（此后已批准，见上方“AI 引导接上模型”），当时没有进行真实模型调用。待完成：完整 harness/review 记录、桌面构建及独立审查。

# 当前交接：推荐优先路线、复用调研与行动前 token 预算

## 2026-09-30 画像证据导向重构（Current）

- 画像页正在从重复统计卡和长条图改为“当前判断→证据→活动→本周变化→修正”阅读顺序；固定关键词、收藏、有用、不相关、太难分组展示。
- 新增本地证据接口 `/api/profile/evidence`，项目隔离、分页上限 25 条；反馈撤销保留收藏并即时刷新画像。
- 周报改为复用画像页的 UTC 周期统计，保持零 token；未引入 AI 调用或外发数据。
- 当前 worktree 仍包含此前图谱/详情/画像事实改动；完整测试、harness、预算检查、桌面构建和原生验收已记录在 [画像重构检查](evidence/2026-09-30-profile-redesign-checks.txt) 与 [变更记录](../changes/2026-09-30-profile-redesign.json)。


## 2026-09-30 画像与周报事实数据修订（Current）

- 画像关键词分布改为从当前项目真实论文证据计算：种子、正向反馈和收藏按可解释权重汇总，固定关键词单独标记；不再使用随机字号或无证据的固定示例。
- 兴趣时间线改为记录实际曝光、收藏与反馈的 12 个周桶；正向/负向反馈形成兴趣分数，太难单独统计；没有活动时显示空状态，不把无动作猜成不感兴趣。
- 画像总结改为本地事实摘要，显示关键词证据篇数和有活动的周数；周报关键词变化比较本周与前一周真实收藏/正向反馈论文的词项计数，变化条目带有前后计数。
- 周报统计保持零 token；现有 `weekly_digest` 仍是未批准提案，未新增或触发模型调用。证据：[画像事实检查](evidence/2026-09-30-profile-truth.txt)、[变更记录](../changes/2026-09-30-profile-truth.json)。
- 当前测试覆盖关键词确定性、真实事件时间线、周报前后周期比较和画像 UI 不含随机/示例数据；真实项目的长期兴趣收益仍需 owner 试用确认。

## 2026-09-30 论文详情阅读栏修订（Current）

- 今日推荐的论文详情改为右侧滑入阅读栏：背景保留可见，标题、元数据、阅读/收藏/原文操作、AI 速览与完整摘要按 Connected Papers 的阅读顺序组织，关闭按钮和 Escape 都能返回。
- 论文库/知识图谱沿用同一层级：知识图谱右侧详情保留图谱在左，标题自然换行，摘要默认展开，分类显示为可验证的标签；已有 arXiv、DOI 或落地页时提供真实原文链接，不生成引用数量或作者等缺失字段。
- 证据：[画像事实检查](evidence/2026-09-30-profile-truth.txt)。普通详情与知识库详情的聚焦测试、35 个 Node UI/动效测试、桌面构建和签名校验已完成。
- 已将 `networkx==3.2.1` 补到当前用户 Python 环境，与 `requirements-desktop.txt` 和桌面打包环境一致；全量 Python 测试 205 项通过，图谱聚类与 worker 测试恢复为绿色。

## 2026-09-30 Connected Papers 图谱可读性修订（Current）

- 对照 Dia 中 Connected Papers 的布局重新整理知识图谱：首次进入以当前论文为中心，用受控径向分布显示周边论文；避免 Cytoscape 后台自动排布把节点推到视口外。
- 节点改为紧凑的标题锚点 + 年份，左侧目录在每个类别下直接列出论文，可以直接聚焦节点并同步详情；类别筛选继续定位到对应论文集合。
- 关闭论文详情后，图谱布局切换为“目录 + 全宽画布”，重新计算 Cytoscape 尺寸，避免右侧留下空栏。
- 同一类别使用同一色相，出版年份只改变明暗，越新的论文越深；边改为细实线并按关系权重调透明度，类别补充边明确标注为非引用关系。
- 证据：[图谱修订检查](evidence/2026-09-30-graph-refinement.txt)、[变更记录](../changes/2026-09-29-graph-redesign.json)。35 个 Node UI/动效测试、199 个 Python 测试通过；`budget.py --check`、`harness.py check`、桌面构建和 ad-hoc 签名校验通过。
- 仍未测量大规模混合年份语料的关系质量和密度；当前类别边只表达整理关系，不是引用事实。运行包位于 `src-tauri/target/release/bundle/macos/PaperDigHelper.app`。

## 2026-09-29 Feedback simplification (Phase 4) (Current)

- Implemented Phase 4: simplified feedback options from three to three clearer choices. Removed "later" (稍后看) which users didn't use effectively, replaced with "too_hard" (太难) for papers that are currently too advanced but may be relevant later.
- Three feedback actions now: "useful" (saves to library, never re-recommended), "irrelevant" (大幅降权, needs +50% similarity or 180 days to re-recommend), "too_hard" (小幅降权, can re-recommend after 60 days with >0.65 similarity).
- UI updated: replaced moon icon with brain icon for too_hard button. Stats display shows "太难" count instead of "中性". Profile display updated to show too_hard_feedback list. All buttons use consistent iconography across recommendation cards, library, and detail views.
- Backend changes: `TOO_HARD_ACTIONS` constant replaces `NEUTRAL_ACTIONS`. Profile includes `too_hard_feedback` field. Stats track too_hard count separately. Service layer handles too_hard with lighter weight penalty than irrelevant.
- Evidence: 178 non-HTTP tests passed; 18 HTTP errors due to sandbox (expected). [Change record](../changes/2026-09-29-phase4-feedback-simplification.json). Zero runtime token impact; feedback logic and UI changes only.
- Phase 4 complete. Next: Phase 5 profile visualization (keyword cloud, interest timeline, AI summary), Phase 6 weekly reports, then knowledge graph redesign per approved plan.
- Related: PROFILE-01. Open risk: existing "later" feedback displayed as "too_hard" in stats (acceptable, no migration needed).

## 2026-09-29 Multi-project UI (Phase 2) (Previous)


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

**2026-09-30 PDF 懒加载缩放修复**

- 修复后续 PDF 页面缩小到左上角的问题：页面树建立时固定 `R.renderedScale`，懒加载页面沿用同一比例；缩放手势只做视觉变换，不让后加载页面误用当前缩放值。
- 已在重启后的最新桌面包中打开 23 页论文，滚动到初始、中段和后段页面验证，页面内容保持完整宽度，文字和图表没有缩到左上角。
- `python3 -m unittest discover -s tests -v`：206 项通过；Node 图谱/组织测试 35 项通过；预算、harness、桌面构建和签名校验均通过。

**不开始新的 PDF 阅读器平台，不自动执行整条路线。**
