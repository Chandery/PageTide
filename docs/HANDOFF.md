# 当前工作单元：界面换肤，冷灰底 + 白卡片 + 蓝色强调（2026-10-22）

分支 `ui-elavatine`，隔离 worktree `.claude/worktrees/ui-elavatine`，基线 main `0c288b3`，未推送、未合并、未构建 `.app`（另有 agent 可能在测主目录的构建）。owner 嫌原来的米色/衬线/书签红风格像某个助手产品，给了另一款 app 的截图作参照，要求简约、有质感；试过靛紫、青碧、森绿、石墨、玫红后选回蓝色。[变更记录](../changes/2026-10-22-ui-restyle.json)，任务 `PILOT-01`。

改动：`theme.css` 的浅色/深色色板、`--display` 代替 `--serif`、大圆角、扁平阴影；`index.html` 的视觉层（页签、按钮、卡片、输入、开关、详情抽屉、聊天、提示、项目总览背景）。其余样式表只把 `--serif` 改名，随 token 变化。[检查证据](evidence/2026-10-22-ui-restyle-checks.txt)，[自审](evidence/2026-10-22-ui-restyle-self-review.md)（非独立审查）。

未验证：学习图图形、导入批次、周报、项目总览浮层没有用真实内容看过；logo 与 favicon 仍是米色+红色，待 owner 决定是否换；没有原生窗口检查。

---

# 当前工作单元：整理分类范围 / 顺序 / 逐项选择修复（2026-10-09）

分支 `organize-scope-select`，隔离 worktree `.claude/worktrees/organize-scope-select`，基线 main `9fdae25`，未推送。owner 于 2026-10-10 授权合并到 main 并构建最终 release：合并与桌面构建（`build_desktop.py` + `cargo tauri build --bundles app`）的实际结果以[检查证据](evidence/2026-10-09-organize-scope-checks.txt)末尾的“构建记录”为准，没有记录就是没做。`FIX-ORGANIZE-SCOPE-SELECT` 状态 review；[变更记录](../changes/2026-10-09-organize-scope-selection.json)、[ADR0034](decisions/0034-organize-scope-priority-selection.md)、[检查证据](evidence/2026-10-09-organize-scope-checks.txt)、[独立审查](evidence/2026-10-09-organize-scope-review.md)。

owner 反馈三点：整理分类的对象应是左边目录显示的内容；先处理未分类、整理完不能还有未分类、然后才是调整/合并；预览只有一堆列表，“应用所选”却没有地方选。现已：(1) 项目标签只审阅该项目论文和左侧目录实际显示的类别，只在其他项目里的类别不发送也不改，共用类别（及其上级）只接收论文；“全部项目”仍整库。(2) 未分类论文排在最前，提示词第一优先；模型没给归属的，有原类别的保持原类别，否则由本地归入顶层“其他”并标明依据不足，所以整理完不会还有未分类（用户在预览里自己取消的除外，提示会写“仍有 N 篇未分类”）。(3) 预览按“先归类未分类 → 再调整现有分类 → 最后重新归类已分类”三段列出，每项有勾选框，带依赖的联动（服务端存预览时用试应用找出依赖，保证任何勾选组合都能应用），按钮写“应用所选（N 项）”，应用后可一次撤销。

验证（真实数字见检查证据）：Python 全量与 Node 全量通过；范围规则与页面规则共用一份用例；4000 个随机有效方案×全部子集 0 失败；用合成数据在真实浏览器里走完整流程（只桩住模型任务，应用走真实服务端；含部分勾选、父子联动、撤销、英文界面、报错可见）。独立审查共四轮（同一只读审查者）：第一轮 7 项 major / 9 项 minor；第二、三轮各发现“修复自己引入的” 2 项 major（探测成本与错放；为提速所做取舍造成的失败与过度绑定）；第四轮结论“可以交付”，留 3 个小项已修（这三处小修发生在最终复核之后，只有作者先写失败测试再修的验证）。逐条处置见审查记录。未调用任何真实模型；真实模型质量、真实库、原生窗口、8GB 资源未测。

预算：单批 8000 输入 / 2000 输出、每批一次无重试、不新增外发字段（只有匿名 `"lock":1`）均不变，未提高任何额度。提示词变长 269 字节，靠压缩措辞保住极限用例（7900/8000）；常见规模下每批少放 0–1 篇（20 类 9→8、60 类 2→1），类名很长的 53 类以上目录会被拒绝（此前 56）——这是预检算术，不是账单实测。**需要 owner 知悉**：`prompts/category-review.md` 文字改了而 `status: owner_approved` 与批准语未动（授权范围/上限/隐私口径未变，agent 不能自改批准字段）。

已知限制：本地（无 AI）检查路径未改；类别结构意见仍由第一批冻结（后批看不到前批新建的类别，近义不同名的新类别可能并存）；方案一次性，部分应用后（或撤销后）未勾选项需重新整理；少数高阶组合在应用时会由服务端自动补上最少的类别变更并在提示里说明“另带上了 N 项”（可撤销）；被丢弃的越权合并/删除所涉论文的移动仍留在预览里（默认勾选，可取消）；旧版留下的、没有可选单元的预览不补算，页面提示重新整理。合并提示：主目录有另一单元未提交的 `docs/HANDOFF.md`、`harness/tasks.json` 等改动，合并时这两处会有文本冲突，保留双方即可。

---

# 当前工作单元：项目引导回复截断与本地兜底误标修复（2026-10-09）

用户提供截图并要求修改、真实测试和交付。截图中的短句是 `finish_reason=length` 后的本地降级文案，原始半截 JSON 未保存；旧提示还把输出上限误说成应缩短输入。当前修复记录见 [变更记录](../changes/2026-10-09-guidance-output-bounds.json)、[ADR0033](decisions/0033-guidance-output-bounds.md) 与 [检查证据](evidence/2026-10-09-guidance-truncation-checks.txt)。

引导 system 示例移除容易被模型照抄的占位 graph，明确 `k/q/c` 为字符串数组及小上限，图只在有具体内容时输出；完整但略超关键词、检索式或选项显示边界的字符串响应由本地有界裁剪接纳，错误对象、坏图和 `finish_reason=length` 仍失败关闭。输出合同保持 1200 输入 / 500 输出、每次点击一次、无自动重试、模型和外发范围不变。引导失败的本地气泡显示“本地整理”，输出上限原因说明结构化草稿未完成。

已在 `PDH_DEV=1`、隔离临时数据目录和现有单一 Gateway 中真实调用 DeepSeek：中文/英文短目标与约束目标重复三轮，加一轮两回合对话，共14次；14/14完整解析为 AI 回合，正常停止，最大实际总用量426 token，开发账本4225 token/$0.0029838，正式账本和正式数据未动。离线49项相关回归、UI Node语法、预算/harness检查均通过；全量测试、桌面重建、独立审查与最终 `review` 仍待本工作单元收尾，未宣称一般产品发布通过。

---

# 当前工作单元：项目引导 JSON 协议修复（2026-10-09）

基线 main `06b23be`，上一单元 AI 设置/题目初筛已本地提交隔离，无推送。本单元 `FIX-GUIDANCE-JSON-PROTOCOL` 已完成，改动保留未提交；[变更记录](../changes/2026-10-09-guidance-json-protocol.json)。用户报告设置测试成功、引导HTTP400；引导system漏JSON字样，违反本日核验的服务合同，而设置测试仅固定普通文本。已增加明确JSON声明，保持1200/500和单次尝试；新增安全有界400分类与同处失败原因，草稿保留。

离线协议感知失败先行与36项针对回归已通过；最终Python2127（295.453秒）、Node461通过。独立主审查102Python/22Node及4个App/真实显示函数回放通过，另Gateway/creation独审12项回归+8合成回放通过。桌面prepare/build、签名、编译合同常量和隔离API包验证均通过，以[检查证据](evidence/2026-10-09-guidance-json-checks.txt)最终记录为准。本次没有真实付费调用、正式库或正式密钥访问；不能声称现网引导质量成功，历史截图未保留provider响应体。

本地日常核心最低0模型token，1200/500峰时未命中单次上界算术 $0.00096 不变；新增12字节不是实测token。用户aggregate帽仍取消且总量未知，开发限额与账本保留；编码agent用量未知。完整目标/回答留本地；长BMP中文请求适配至下限36字符，更高转义成本仍可安全拒绝，非全Unicode准入保证。全部产品blocking gates/人工发布批准保留原状态。新版输出 `src-tauri/target/release/bundle/macos/PaperDigHelper.app`；source165文件SHA256 `6def5810a5418d143cc9d5e6b42486689e133e94c058380f2880fc8711bbe838`，打包后端SHA256 `32b0bfd9e9f7b238bea80bf5c4df30898cce1f4eb70ab81e51ab5306d2c41928`，构建时间 `2026-10-09T11:14:16.798711+08:00`。旧应用备份位于 `.local/app-backups/PaperDigHelper-before-guidance-json-20261009.app`。下一个动作：用户退出旧版并打开新版，在保留草稿上显式重试；若仍有400，依据新的安全原因进一步调查，不自动付费复测。

---

# 当前工作单元：AI 设置与推荐题目初筛（2026-10-09）

本地 main 基线 `f745009`（上一创建/brainstorm修复单元已本地提交隔离）；本单元修改保留在 main 工作树，未提交/推送。`FIX-AI-SETTINGS-TITLE` done，仅表示本单元软件验收；一般发布批准和既有质量门槛不自行通过。见 [变更记录](../changes/2026-10-09-owner-ai-settings.json)、[ADR0031](decisions/0031-owner-ai-settings-title-screen.md)、[检查证据](evidence/2026-10-09-owner-ai-settings-checks.txt)。

按业主明确指令取消运行时每日/月 token/USD 总帽，保留账本/未确认预留/单次合同/原次数和独立开发限额。设置新增“测试 AI”：固定短请求，支持临时或已有密钥，AI 关闭也可显式测试，不保存临时密钥、不改开关、无重试。具体失败及耗时就地显示，晚回复受输入版本保护。发送前本地锁/记账失败明确未发送，发送后写入错误保留真实预留；锁退出错误保留已确认计量。未知或缺 total 不伪称已知/预留。

推荐先检查当前原题。明显非Latin多数题名与来源英文报告冲突、正文未核验时，不进仅英文推荐；已核验当前正文优先，PDF变化失效，原题/来源语言/旧批次保留并分开说明。数学英文字体按计数字形兼容，不改原题。该本地启发式不能证明正文语言或通用科学筛选质量。

最终源代码165文件指纹 `4fc80141f57399564031730197a1c60fa18af34cc2def15d9be3488ee0f35010`。完整2107Python/361.672s、461Node、预算/traceability/i18n0缺漏/diff均绿。独立API、gateway/UI、title/backend审查均完成，发现的P2均修复复验。旧包在新策略夹具失败，新包实际隔离接口/资产/题名筛选/历史/重启及既有Route夹具通过。backend+Tauri构建与adhoc严格签名绿，常用 `src-tauri/target/release/bundle/macos/PaperDigHelper.app` mtime2026-10-09 01:24:54+0800；打包backend SHA256 `f86440c82cf943840e3e6e9218c7526ac904b015d5867734d204c82527b30203`。

旧包备份 `.local/app-backups/PaperDigHelper-before-owner-ai-settings-20261009.app`；私有测试/截图/manifest/包验证器在 `.local/owner-ai-settings-verification/`。正式数据/密钥/账本未读取或修改；本单元paid/provider调用0，coding-agent用量未知。原先单元345token事故仍在原记录，不覆盖。新固定测试768/16峰时未命中 $0.0002496/次仅注册算术，取消总帽后累计可选花费没有App上界。官方HTML已重新读取、原价格/model版本不改。

20全产品评估not_run、2计量/enforcement标记和人工发布批准保持原状，`check --release` 与 `review --release` 应失败；此单元不是全产品发布。未实测当前正式密钥、真实连接/科学收益/tokenizer/invoice、原生窗口或8GB。下一步退出旧实例并从常用路径重开，设置中由用户显式点测试AI核对自己的连接；不自动代发付费调用。后续新单元先提交或隔离当前工作，保留旧记录/恢复包。

以下交接记录按当时状态保留，上文是当前状态。

# 当前工作单元：创建学习图与 brainstorm 引导体验修复（2026-10-08）

基线 main `48bfc63`，初始工作树干净；当前修改保留在本地 main 工作树，未提交/推送。用户四项问题及追加“轻量 brainstorm skill”“确认细节后输出右侧结构”已实现，`FIX-CREATION-AI-UX` review，待用户体验复核；不自行批准整产品发布。记录见 [工作单元](../changes/2026-10-08-creation-ai-ux.json)，脱敏检查与限制见 [检查证据](evidence/2026-10-08-creation-ai-ux-checks.txt)。

快速/引导创建均显示并保存真实可编辑图；同次引导可输出最多3概念/3前置/明确目标，路径行绑定实际节点，不推断掌握或凭行序造前置。轻量规则主动建议/取舍、确认一个缺口、给选项，允许早确认，原1200/500、quick1/guided6上限不变。人工改图受保护，提交需明确确认图或放弃。学科等字段就地报错；分类空目录/未分类可提新类、预览/确认/撤销；AI失败原因与未知计费分开显示，未知/预留保留尝试与预算。独立审查P1计数及P2图/界面/作者/输入缺陷均已修复并复验。

最终源码串行全量 Python 2057 passed（370.819s），含最后分类已确认用量统计修复；最终 Node 445 passed、受影响 Python 51 passed、独立创建复验22 passed、独立分类复验25 passed。一次并行构建导致harness复制被替换target文件的setup错误，串行重跑通过，未弱化断言；后续全量测试不要与cargo构建并行。budget/harness/i18n（0/1457缺漏）/diff检查通过。新 backend + Tauri 构建、ad-hoc签名深度验证、原有包内Route链路与新增quick/guided创建/重启持久链路全绿。可打开 `src-tauri/target/release/bundle/macos/PaperDigHelper.app`；未替换正式运行进程或正式用户数据，旧bundle备份在私有 `.local/app-backups/`。最终app/prompts/budget源hash `3f11d479a53990e604fbdb7239fe990ae6727307c21306c96e77900a84724e83`，包内backendhash见检查证据。原生最终窗口、真实brainstorm/分类科学质量、500输出充分性仍未测，ad-hoc签名不代表公证或整产品发布通过。

每日本地搜索/去重/排序/画像/归档/维护最低0模型token；原请求/全局预算与次数不提高，图兜底不新增AI。界面测试曾因临时data仍读取checkout key意外调用1次project_guidance，provider报告345token（157/188），本地费率算术$0.0002727，原临时runtime账本reconciled且私有留档，没有改正式账本；不得称为developer模式或充分质量验收。随后停止server，独立root、显式AI关闭且阻断外网，全量回归保护实际DeepSeek传输。真实模型测试没有追加授权。下一步用户重开新bundle体验该闭环；需要真实模型/原生质量验收时单独确认范围，保持现有预算与发布门槛。

# 当前交付：按用户要求收拢修复并合入本地 main（2026-10-08）

用户先授权逐项修复 B01–B29 / I01–I12 和系统英文遗漏，随后明确要求“结束吧，把现在的合并到 main 我看看”。已停止新增付费 AI、扩展原生与科学实验；本次提交交付当前修复快照，不宣称全部学科/个人价值或整产品发布通过。

实现分支 `codex/audit-bug-fixes-20261008`，工作树 `/Users/chandery/.codex/worktrees/audit-bug-fixes/PaperDigHelper`，基线 `8e5cfd7`。本地 main 合并属于本次明确授权范围；实际最终提交和干净状态从 Git 读取。未推送远端、未安装或替换正式应用、未修改正式账本。`FIX-MULTIDISCIPLINE-AUDIT` 仍 in_progress；release owner_approved=false，不将本地合并授权冒充发布/预算批准。

英文系统标签与用户原文已分开：画像反馈/收藏/周报/来源/撤销框架翻译，项目名、论文名、分类、笔记和人工理由保留原文；任意模型/来源自由文本不自动翻译。R-F32 按项目和论文隔离窗口内草稿；R-F35 多行草稿显示及 R-F36 PDF 打开助手后适配已由 r6 原生实际复验。真正输入法、最小窗口、精确焦点、后台 PDF 首次绘制原因未完成。

R-F37 仅在完整输入超限时减少可选不可变引用 3→2→1，保留连续题摘、完整 Map、全部已选提议和原 cap。258 回归、独立27+5有界控制通过；真实后续整队列18例未重跑，用户停止时标 not_run。R-F38 全部 PDF 被拒绝后的重选/明确放弃恢复：8函数/64相关Node/27Python及独立8项通过；最终软件检查状态以检查证据为准，停止后不补充原生验收。

r12/r6 是修前最后中间同源证据：2019 Python / 417 Node、五步实际包验证绿；原生英文/分论文两行草稿/141%-205%适配及结构导出通过。导出12,412,961字节/33表，本地新目录恢复计数一致、integrity ok、无凭据。最终 r13 2021 Python/425 Node全绿（203.989s/774.208417ms），r7五步包验证全绿，二者前后同源 `4764f88b512b50fa2748bc045769a45b79b842bed2a8770c13135358be4a9e17`；结果看 `docs/evidence/2026-10-08-fixes-checks.txt`。

模型实际累计 2,555,064 token / $0.782956770：修复开发1782尝试（1781核账、1历史402释放0）、2,216,743/$0.610460442，加旧审计280、338,321/$0.172496328。pending/unknown 0；软监控3m/$2，既有硬限额不增。R39十八诊断9完整/9安全输入拒绝保留，不能拿新回归覆盖；新真实轮与新盲审未运行，科学正确/来源覆盖/推荐收益/真人标签和满意度门槛仍开放。

正式库旧7文件/6表变化由用户确认是正常使用。09:32 UTC后续核对又有14文件/19表变化（新增10，无删除），完整性ok、测试项目不存在；时间约北京时间17:09–17:26，单独归因询问未答复，保留差异/快照，不回滚、不假称仍199文件完全不变。私有原生副本AI始终关闭，无key且HOME不替换；主库仅只读检查。

新包、逐项矩阵、独立软件审阅与可视报告均按当前快照留档。下一步由用户检查 main 后决定继续修复哪些开放项；不得自行重启付费实验、降低门槛或替换正式应用。

# 历史工作单元：导入已有论文库已合并到本地 main 并重建正式包（2026-10-08）

业主说“现在可以合并到正式的构建里了”。worktree 的改动提交为 `27a2fbe`（无 co-author 行），已在本地 `main` 上 `--ff-only` 快进（main 此前仍是 `93d3ecd`，无冲突）；**没有 push/fetch**。主检出上重跑全量：Python 1871、全部 Node 文件 fail 0、预算和 harness check 通过；随后 `build_desktop.py` 与 `cargo tauri build --bundles app` 均退出 0，新包 `src-tauri/target/release/bundle/macos/PaperDigHelper.app`（目录时间 2026-10-08 02:36）。构建后的 Tauri 包只有链接器签名、严格校验失败，已按既有做法 `codesign --force --deep --sign -` 重签，`--verify --deep --strict` 退出 0（ad-hoc，不是公证）。旧包备份在 `.local/app-backups/PaperDigHelper-before-library-import.app`（git 忽略）。证据：[合并与构建证据](evidence/2026-10-08-library-import-merge-checks.txt)、[变更记录](../changes/2026-10-08-library-import-merge.json)。IMPORT-01 仍 `in_progress`，E-LIBRARY-IMPORT 仍 `not_run`。

打包后的验证：项目自带的 `scripts/verify_packaged_route.py` 通过（隔离 HOME、外网屏蔽，原有路线/增长/重启行为未被破坏）；另用打包后的后端在隔离临时数据目录里跑通一次完整导入（登录、5 个导入资源 200、建批次、上传、同内容副本合并、离线匹配、提交、分类、论文库）。**我没有启动原生窗口**（沙箱禁止 `open`），所以“在 .app 里点选文件夹/拖入文件夹”仍未实测：请你启动新包后试一次，这是 E-LIBRARY-IMPORT 的第一项。正在运行的旧进程需要退出重开才会用新包。

以下是功能本身的原始交接记录（合并前写的，“未构建/未合并”已过时，以上文为准）：

做了什么（ADR [0029](decisions/0029-library-import.md)）：论文库工具栏「导入论文」和新建项目页「创建后导入我已有的论文库」进入 `import.html`；选 PDF/选文件夹/拖入文件夹/Zotero 导出文件夹（BibTeX、RIS、CSL-JSON）。页面用 pdf.js 读首页线索并逐个流式上传到暂存批次；服务端后台线程按节奏匹配 OpenAlex（进度写库，额度不足/断网时暂停，可“不再联网，按原样导入剩下的”）；审阅（选候选、手动查找、排除）后一次事务提交；文件夹结构成为分类（一条可撤销事件）；完成页可把已识别论文设为种子（20/40）。已在本项目论文库的论文不再是今日/路线候选。运行期模型 token 为 0；新增文件 `app/library_import.py`、`app/reference_files.py`、`app/static/import*.{html,js,css}`、`pdf-hints.js`，新表惰性创建（不占迁移号）。

验证（开发证据，非 gate）：Python 1871、全部 Node 文件 fail 0，预算/i18n/harness check 通过；失败先行 + 变异检查；浏览器里用真实 pdf.js 走过离线、断网暂停、候选、Zotero 导出、英文界面、暂停/补传。独立审查（只读 agent）无 P1，P2 全部修复，修复未再独立复审：[审查与处置](evidence/2026-10-07-library-import-review.md)、[检查证据](evidence/2026-10-07-library-import-checks.txt)、[自审](evidence/2026-10-07-library-import-self-review.md)、[变更记录](../changes/2026-10-07-library-import.json)。

**待业主决定/确认**：(1) 导入来源的种子也不推进学习地图进度（我对 ROUTE-V2-06 的延伸）；(2) E-LIBRARY-IMPORT 是否阻断发布（暂按阻断）；(3) 种子仍会用其公开标题/主题词做路线召回检索；(4) 何时合并并重建正式包。

**未做/未验证**：原生 `.app` 内选文件夹/拖入（wry 源码核对过 `NSOpenPanel` 可选目录，未实测）；真实网络命中率与 OpenAlex 额度消耗（沙箱连不上 API）；业主 Zotero 版本的真实导出 fixture（格式按公开资料+合成样例）；未识别 PDF 的重新匹配、撤销整次导入、AI 复审前预算预检。

**事故（已修复）**：用 `preview_start` 的 `app-ui` 配置起服务时，它在**主检出**目录运行，把 `.local/ui-redesign-data`（git 忽略的 UI 测试库）迁到 v9 并多了个测试项目；已用应用自己写的 `pre-v8.bak` 还原并核对（5 个原项目、schema v8、完整性 ok）。之后改用 worktree 里自己的服务器和临时数据目录。后来者：不要用预览配置测 worktree 代码。

# 当前交接：已合并到本地 main（2026-10-07）

用户明确要求合并。原main `850f9fc` 是已验收 `11969c5` 的祖先，没有独有提交；已 `--ff-only` 快进，原main历史完整保留，无冲突。合并当下tree `148c073cfe24719930e7c5a8d297c75d848fd86f` 与已审源码完全一致。本轮后续只补本记录/证据/HANDOFF三路径文档，最终main commit/dirty以Git核对。原工作分支保留，本次未fetch或push；origin/main只是本地缓存。

沿用相同源码的1599Python、314Node及两轮真实AI副本语义证据，没有冒充本轮重跑。main下新跑backend/Tauri构建、adhoc严格签名及实际包隔离Route/重启/撤销/整队列AI-off检查均通过；常用app目录时间18:21:17+0800。原生已从常用路径重新启动，新backend63396；本轮未代点付费判断、确认提议或重置用户数据。预算/模型/权限/默认设置不变，原分类review质量失败、19全产品gates与2false标记保留，不宣称整产品发布通过。

[合并记录](../changes/2026-10-07-main-merge.json)、[合并与新包证据](evidence/2026-10-07-main-merge-checks.txt)。以下原分支验收记录作为历史保留。

# 当前工作单元：完整生长回复与学习任务粒度已验收（2026-10-07）

分支 `codex/growth-reply-validation`，基线 `053b7f9`；最终 commit/dirty 以 Git 核对。FIX-GROWTH-REPLY-VALIDATION done，E-GROWTH-REPLY-VALIDATION passed，仅代表本单元验收。

已修回复字段歧义、严格 JSON/UTF8、12条提议阻断和具体错误诊断；unclear 合法相关节点仅校验，不保存为覆盖；两项实际观察到的空说明仅允许字面空字符串。潜在方向按任务动词、核心对象和明确方法约束归并；应用综述补充已有能力，不推断必需前置，独立能力无确证依赖先提无硬边分支。确认保留原目标和原边，历史提议不自动删除。仅本操作使用温度0/JSON模式；原 Flash、关闭思考、额度、公开字段及单网关/无重试不变，其他15操作 wire 与旧版一致。开发原则已按人类要求写入 AGENTS/BUDGET：日常使用节约预算；获得明确授权的开发测试充分验证，并独立记账。

真实 v1–v7 格式/结构/语义失败保留。最终 v8 两轮两实际项目快照共22调用/62判断均完成、pending0；独立逐组审查未见剩余确定P1/P2，仍有空简介下范围/命名P3，不声称普适模型质量。所有148开发调用237029tokens/$0.070480680及1正式诊断1611tokens/$0.000670776均为峰费率账本算术，非invoice；测试只改私有数据库副本，不消耗真实项目次数、不改真实图。最终源码全量1599Python/451.480s和314Node通过，独立代码/语义/保留审查通过。

常用 `/Users/chandery/PaperDigHelper/src-tauri/target/release/bundle/macos/PaperDigHelper.app` fresh重建，目录时间2026-10-07 18:08:38+0800。backend/Tauri构建、adhoc严格签名、实际包隔离Route及分类合成应用/重启撤销通过。用户解锁后CUA实际从同路径启动，两个项目均显示新粒度说明和“判断全部待判断论文”；A待判断16/剩余6次、B15/3保留。退出确认进程消失，再从同路径启动并见新入口。未代点真实付费判断或确认提议，应用留在新版A学习图。旧13:26包可恢复备份在.local；原Loadfail未在本次启动/重启复现。

原19全产品gates、2 false budget flags、分类task review及其真实质量失败保留，整产品release不宣称通过。未验证providerinvoice/tokenizer、notarization、8GB和全产品推荐收益。单元记录验收与全产品发布批准保持区分。

[本单元记录](../changes/2026-10-07-growth-reply-validation.json)、[分版本和最终包证据](evidence/2026-10-07-growth-reply-validation-checks.txt)、[独立审查](evidence/2026-10-07-growth-reply-validation-review.md)、[ADR0028](decisions/0028-growth-reply-validation.md)。以下历史阶段记录原样保留。

# 当前工作单元：主入口整队列判断持久交付完成（2026-10-07）

分支 `codex/route-growth-delivery`，基线 `1327828` 原样保存 38 路径分类工作；原分支保留。合并已审查 `cefc5fe` 的完整待判断队列修复到主目录，解决常用 12:50 应用仍每次处理 3 篇的交付遗漏。最终 commit/dirty 以 Git 核对。FIX-GROWTH-PRIMARY-DELIVERY done，E-ROUTE-GROWTH-DELIVERY passed，仅表示本单元交付验收。

常用唯一交付路径 `/Users/chandery/PaperDigHelper/src-tauri/target/release/bundle/macos/PaperDigHelper.app` 已 fresh 重建，应用目录时间 2026-10-07 13:26:10 +0800。旧包在新接口验收中实际失败（缺 requested）；新包构建、adhoc 严格签名、实际包后端、分类合成应用/重启撤销均通过。原生从同一路径启动、退出并再次启动，均实际看到“判断全部待判断论文”和全队列提示；原 pending17/剩余4次保留，第二次窗口停在新按钮。未代点付费判断，不声称真实17篇已完成。

联合完整 1577 Python（308.655s）和 314 Node 全通过；独立审查核对38哈希、30非共享分类路径、授权/预算/登记/翻译，108目标与合成并发预算准入通过，无剩余已发现P1/P2。用户明确授权跨任务协调，分类任务已安全停止写入。现有分类人类单独“批准”的8000/2000 scope原样保留，FIX-CATEGORY-STANDARDS仍review；其真实模型方案被严格拒绝的质量失败保留。原 provider/default-off/总额度、19全产品阻断评估和2预算flags不降低。

无数据迁移、库或计数重置；本单元模型/付费请求0，核心强制每日模型最低0，developer用量未知。未核验真实多批AI质量、账单/tokenizer、notarization、8GB或全部产品收益。旧包可恢复备份在.local。原全产品release仍应失败；本单元record验收不等于全产品发布批准。

[联合检查证据](evidence/2026-10-07-growth-primary-delivery-checks.txt)、[独立审查](evidence/2026-10-07-growth-primary-delivery-review.md)、[同单元记录](../changes/2026-10-07-growth-primary-delivery.json)。后续从常用路径使用新版；若实际预算/服务拒绝，保留已完成判断并提示剩余和原因，不自动重试。历史各单元记录以下原样保留。

# 当前交接：分类范围已批准，联合验收接管（2026-10-07）

用户本轮明确回复“批准”，已登记仅 `category_review.owner_approved=true`；保持8000/2000、60类/12篇标题80摘要160、显式触发/默认off、原总额度/其他授权不变。源码/SYSTEM未新增强化，prompt header和预算/文档授权已更新。`FIX-CATEGORY-STANDARDS`仍review，不能称最新包或模型质量完成。

批准后新增4个授权回归，两模块45/45通过；最新全量1550、重建内含true预算的新包、原生分类点击尚未运行。此前全1546/298和旧包构建/签名/合成恢复通过，仅证明批准前版本，旧包中category_review仍false。实际仅一次非dev正式网关合成7类/6纸：1244token（943/301）、$0.0006441峰费率本地计费、reconciled；wire4691bytes+256、固定官方tokenizer1137，计数对象不同不宣称parity。AI把已删c1留在paper归属，严格拒绝方案，classes/memberships/笔记未改，single-model质量failed、拒绝防线passed，无重试。真实用户库未改，只有已批准正式模型账本新增此usage。

接管任务要求本目录源文件/切分支/重建/新模型请求在安全边界后停止，本任务按要求收尾；所有子代理均停止产品源码写入。加强同义组/term-kind/最终ref上下文仅建议，未实施、无第二模型调用。原生AI_OFF隔离资料 `.local/category-native-20261007`准备完、应用未启动；第一次真实receipt/fixture/marker留 `.local/category-approved-20261007`，不得自动重复付费。

[同工作单元记录](../changes/2026-10-07-category-standards.json)、[最终检查及真实失败](evidence/2026-10-07-category-standards-checks.txt)、[独立审查](evidence/2026-10-07-category-standards-review.md)。稳定交接标记 `.local/category-integration-ready.json`；接收任务原样保存全部分类源改动与本轮人类批准，再负责联合完整测试、构建、签名和原生入口。原19gates/2flags不降；不继承授权为全产品release/无限预算。

# 上一阶段：完整分类审阅已实现，新增 AI 范围待批准（2026-10-07）

分支 `codex/route-discovery-rework`，实现基线 `ac814ca`；最终 commit/dirty 以 Git 核对。`FIX-CATEGORY-STANDARDS` 为 review：用户授权完整 AI 审阅实现，但新增 `category_review` 范围/上限提问尚未答复，`owner_approved=false` 保留。未执行模型请求或修改真实论文库；不能借其他操作已有批准。初始其他 growth 工作未被本任务重置、丢弃或覆盖。

默认“整理分类”审阅完整共享目录和当前范围全部已收藏论文，已分类/未分类都检查。AI 提 keep/rename/merge/delete、新类及每篇最终归属，完整预览确认后原子应用、单事件可撤销和重启恢复。中英文明确别名统一身份；同路径双语父子有依赖，方向不按共现错误嵌套，未知标题残片不自动立类。周报只读归并别名及论文归属，保留真实反馈事件次数。失败不能存部分/假 AI 方案，另点本地检查；跨项目迟到、取消、未知用量停后续批次，scope 外或归档持有者阻止删除标签。

最终 1546 Python（登记修正后 fresh 184.401s）/298 Node 全通过；独立审查发现并复核未知用量、缺父复用、方法根、跨 scope 迟到应用等防线，无剩余已发现 P1/P2。fresh backend/Tauri `.app` 构建通过；初次严格签名失败后对产物 adhoc 签名，严格验证与签名后包后端复验通过。实际隔离新包 HTTP 合成 fixture 完成未批准 AI 拒绝、完整预览应用、标签删除、论文笔记保留、重启撤销。不是原生窗口验收、模型质量或 notarization。

[ADR0027](decisions/0027-category-standards-review.md)、[检查证据](evidence/2026-10-07-category-standards-checks.txt)、[独立审查](evidence/2026-10-07-category-standards-review.md)。预算/harness/i18n/diff 检查均通过；首跑旧合同 fixture 的 2fail/1error 及修正保留；末次登记补查41项的1fail来自临时仓库未复制test证据路径，改用3份完整docs evidence后全1546再次通过，未改validator/test或降低验收。单批 8000/2000、60 类/12 篇，公开标题80/摘要160与临时引用，完整目录过大拒绝，无重试；单批最高 $0.0048 为峰费率算术，原总额度不增，核心最低0token，developer 用量未知。

下一步只等待人类对已呈现的新 cap/privacy 选项答复；获得批准后登记本操作授权、重建内含预算的包，再做有界真实模型/原生验收。用户不批准则保持 AI 拒绝和显式本地检查；不得自设 true。原全产品19阻断评估和两个 budget flags 保留，`check --release` 实际仍 exit1。真实模型/真实库/账单/tokenizer/原生窗口/8GB 未测，不称整个产品发布通过。

# Current work unit: whole-queue growth jobs completed (2026-10-07)

Branch `codex/growth-whole-queue`, isolated managed worktree `/Users/chandery/.codex/worktrees/growth-whole-queue/PaperDigHelper`, baseline `ac814ca`; final commit/dirty state must be read from Git. The original checkout's concurrent owner category changes were preserved and excluded. FIX-GROWTH-WHOLE-QUEUE and E-ROUTE-GROWTH-BATCH are complete only for their synthetic contract/package acceptance.

One click freezes all currently pending selected papers and runs sequential distinct batches of at most three, charging one daily job. Each request retains the full Map, bounded relevant proposal context and the existing 8000-input/1000-output ceiling. No retries or background continuation. Partial refusal/invalid/unknown/stale evidence stops further requests, retains completed opinions, and reports processed/requested/current pending plus the reason. New interest and renewed prompts wait for the next click. Directions still need explicit confirmation before Map growth. Canonical cross-process ledger admission locks close the independently reproduced reservation race; network calls remain outside the admission lock.

Final full Python: 1492 tests/196.004s/exit0; Node:297 passed/0 skipped/exit0. Independent stable targets:142 Python,39 Python UI,100 Node passed; nine P2 findings reproduced and closed, including verifier host key-file inheritance. CUA served-page fixture with synthetic papers/mock Gateway: one click20/20,pending0,two directions,quota10→9. Fresh backend/Tauri .app, ad-hoc strict signature and actual frozen packaged-backend verification all exit0. Expanded packaged acceptance checks20 pending/AI-off/no charge/current served UI assets; rerun with inherited temporary fake-key override passes in isolated HOME with outbound network blocked. This is not a native-window AI run or real model quality evidence.

Built app: `/Users/chandery/.codex/worktrees/growth-whole-queue/PaperDigHelper/src-tauri/target/release/bundle/macos/PaperDigHelper.app`. Existing build runtime/dependencies reused; no global installation. No real library/key/ledger access or model/paid request. Direct owner instruction authorizes whole-queue public metadata; global55k/day1.5M/month and $0.15/day/$1.50/month/default-off remain unchanged. Twenty papers need seven bounded requests: theoretical maximum63k tokens/$0.0252 is a demand estimate, not an admission guarantee or measured billing. Mandatory core model tokens remain0.

[ADR0026](decisions/0026-whole-queue-growth-jobs.md), [checks](evidence/2026-10-07-growth-whole-queue-checks.txt), [independent review](evidence/2026-10-07-growth-whole-queue-review.md). Prior19 whole-product gates and two budget flags remain unchanged; product release audit remains blocked. Do not infer tokenizer parity, real AI quality, recommendation benefit or notarization from this unit. Final30-file record/diff review passed with no remaining P1/P2; final local commit/dirty state comes from Git. Keep this attached worktree/app for delivery; no push/merge and no edits to the owner category work.

# 当前工作单元：实际旧库启动失败修复完成（2026-10-07）

分支codex/route-discovery-rework，基线a0cb9e2，最终commit/dirty以git核对。用户原生Load failed已实际复现并修复：v8旧discipline列重复添加失败，保留列/旧值/NOTNULL默认cs_ai，未指定策略创建省略列，revision0pending不冒充选择语言。FIX-LEGACY-LANGUAGE-START完成；新增nullable/回滚和真实历史NOTNULL回归，之前干净v8验收未覆盖此结构，不隐藏遗漏。

最终1465Python/281Node通过；独立129Python/三类旧结构/3个实际源码desktop启动反例闭合，无剩余P1/P2；freshbackend/Tauri/sign/package全0。真实默认原生首页已加载项目和文献数量，无Load failed，旧项目提示明确语言选择。实际默认库自动升级9，既有论文/反馈/收藏/笔记/归属原行不删改；私有一致性备份.local/load-fix-20261007。运行期有新增记录和显式语言设置/组织变化，保留不回滚；不能虚称整库冻结不变。未按按钮生成/修改用户设置，无新增模型/付费请求。原全产品19gates和2budgetflags保留，releasecheck仍exit1。

[ADR0025](decisions/0025-legacy-discipline-migration.md)、[checks](evidence/2026-10-07-legacy-language-launch-checks.txt)、[review](evidence/2026-10-07-legacy-language-launch-review.md)。最终11文件record/diff独立复核已通过，无剩余P1/P2；本地提交后commit/dirty以git核对，不推送不合并。10854/69038/1194都已terminal；1464run在P2前通过，1465首次仅验收引用在harness测试夹具中缺失，修正引用后最终全量通过，未改validator或降低gate。真实数据/备份/日志不入Git。

# 当前工作单元：Route 方案最终实施验收（2026-10-07）

- 分支 codex/route-discovery-rework，基线 f0f000c；本轮只更改验收证据/文档/ROUTE-V2-08和E08状态，无产品代码/提示/模型/预算改动；最终commit/dirty以git核对。00–08实现与验收完成，唯一任务表见harness/tasks.json。
- Mac已解锁。native完成文科en+zh保存/离开再读、仅zh生成1篇并过滤18英文、STEM/en手动项目创建和同新项目五字段两节点图保存；known仍0/2，人工简介与前置/目标正确。此前native主fixture与本轮新项目区别明确，单项目完整回归另有证据；不声称所有native点击都是同一项目。隔离app/backend原生quit后PID消失，没有CUA默认重开。
- 最终全量1462Python通过（311.503s/exit0）、281Node通过；独立315Python/129Node及4项真实恢复回归通过，未见剩余P1/P2。新增状态只凭实际覆盖，不改原验收标准。fresh backend/Tauri .app构建、adhoc严格签名和新包隔离后端通过。不是notarization/分发批准。
- 三项已授权Route AI和原global/day/month/default-off不变；本轮新增模型token/费用0。此前3次真实1885token/$0.0010254峰费率本地计算保留，创建超长拒存的质量失败保留；不能称总体模型质量通过或提供商账单校准。
- 本方案执行完成与全产品发布分开。原19项全产品阻断评估not_run、PDF archive已passed、runtime enforcement/tokenizer parity两个false及blocks_release全保留；check --release仍应失败。真实推荐/反馈增益、AI总体质量、全文语言准确率、资源8GB、全面隐私/恢复/安全与预算测量不能靠本次合成测试替代。
- [逐项审计](evidence/2026-10-07-route-v2-completion-audit.md)、[收尾checks](evidence/2026-10-07-route-v2-close-checks.txt)、[独立审查](evidence/2026-10-07-route-v2-close-review.md)。独立最终9文件diff已通过；本单元record review --release通过，本地提交以git核对，不推送不合并。无在运行测试session，之前19609已经exit0完成。后续全产品发布须独立落实原gates，不继承本次Route完成为全产品done。

# 当前工作单元：Route 阶段08原生与真实网关验收（2026-10-07）

- 分支codex/route-discovery-rework，基线f20e2f4。人类本轮明确“授权啊，全都授权”，登记三项新增Route scope/caps；不再等待访问/付费范围批准。原global55k日/150万月/$0.15日/$1.50月、default-off、核心日最低0不变。
- 实际新Tauri原生窗口验收：手工五字段图、前置/显式掌握/关注、3+1+1、Useful/撤销收藏保留、同纸双图定位、完成后1发现、409保留/禁旧确认、AI-off保留、修改确认/旧掌握隔离、普通模式质量入口通过。手工预览和并发fixture由local service准备，不冒充AI或全部native生成。
- 原生发现P2：确认修改重启后撤销入口丢失，已修GET page读取持久且revision绑定undo、loader恢复/清除；core事务route_get不变。新增失败回归并freshbackend/Tauri后，实际原生重启→按钮出现→点击恢复原名及2/2完成通过。独立146Python/71Node及双连接/HTTP/loader交错探针通过，无剩余P1/P2。
- 3次真实DeepSeek网关各1次、非dev、串行、同既有正式账本合计1885token/$0.0010254峰费率本地计算，均reconciled。创建返回why/intro超长被拒，无自动重试；另手工4节点fallback后修改新增Evaluation/目标正确，growthcovered定位DreamerV3。不能称3项质量全通过或invoice校准。官方tokenizer仅校验3完整wire+中英fixture，全面parity/runtime评估false保留。
- native有意修改均隔离data/HOME、AI关/无key/出站代理；初次quit后CUA观察自动重开默认路径load failed，立即终止并隔离重启，未操作默认库UI；真实账本含付费探针。秘密/原始响应留.local/App Support。
- 文科选项可见，但最后保存及额外native项目创建未完成：Mac验收中自动锁定，已发手动解锁请求；不是授权缺失，不重问批准。08/E08仍in_progress/not_run，goal active不提前complete。可继续独立证据/检查；下一步只需解锁后实际完成这两项。
- 首次全1461的2fail是授权后dry-run旧断言，已更正并保留false授权fixture；第二全1462遇构建并行删除target文件的复制竞态，代码目标通过但整run失败。最终停止构建后串行全量1462Python通过（317.353s/exit0），281Node通过。无运行session；budget/harness/i18n/strict签名/实际新包后端过。原release仍20not_run和2预算登记阻断，不降gates。
- [ADR0024](decisions/0024-route-native-approval-and-undo.md)、[实际原生/付费证据](evidence/2026-10-07-route-v2-08-native-acceptance.md)。全量与实际新包检查已完成；[独立脱敏审查](evidence/2026-10-07-route-v2-08-native-review.md)通过，创建失败/修改/覆盖解析与用量数学复核一致，无新增P1/P2。最终record review --release通过（只审本单元记录，不代表整体release通过）；最终dirty/commit以git核对。

# 当前工作单元：Route Mode 阶段08正文匹配一致性（2026-10-07）

- 分支codex/route-discovery-rework，基线deec31a；最终commit/dirty用git核对。00–07done，08in_progress/E08not_run，整个goal未完成。
- 学习图与今日/库详情共用标题+可用摘要，缺摘要用当前PDF有界正文。最多2关联；进度仍最强单元。语言变更/Routeoff不清学习证据，待核验与未匹配分开；摘要可用时语言延期不隐藏匹配。
- 图与进度共享captured rows和256MiB物理核验预算，响应返回前比对当前identity/version/有界正文，变更拒绝旧结果；详情同guard，无第二hash。hover说明标题或正文，不虚构命中。正文不上卡片/context/外发。
- 所有Map详情/图可显式重核验同时清图/context缓存。保存全文/reader返回更新视图，Today读前关drawer、重开重读；visible失效重发当前scope，迟到旧保存不让新图/context永久loading，hidden只清缓存，无轮询。独立6P2全部修并原探针闭合，无剩余P1/P2。
- 最终1461Python/280Node通过；独立最终103Python/128Node及生产函数交错probe通过。freshbackend/TauriApp/实际新包临时后端通过。初次签名资源校验失败，构建输出本地adhoc签名后strictverify和签名后包后端复验通过；未改签名配置/证书，不等于notarization/发布批准。
- 临时HOME/data、AI关闭、出站封锁、默认库未动。无模型/真实来源/真实库调用，核心每日token0，新AI未批准；agent本单元成本未知。releasecheck仍exit1（20原评估含E08not_run及预算登记阻断），不降低gates。
- 之前browserpolicy因用户拒绝访问权限阻断，此前Maclocked；人类解锁/授权请求仍待答复，不重试/绕过、不以时间当许可。下一步获人类许可后做原生全流程，按计划补实际验收；不得提前08done/goalcomplete。真实AI质量、推荐价值、全文语言准确率、账单/tokenizer、8GB资源未测。
- [ADR0023](decisions/0023-route-current-body-matches.md)、[checks](evidence/2026-10-07-route-v2-08-body-matches-checks.txt)、[review](evidence/2026-10-07-route-v2-08-body-matches-review.md)。任务唯一状态仍harness/tasks.json。

# 上一工作单元：Route Mode 阶段08双图导航与本地完整流程（2026-10-07）

- 分支codex/route-discovery-rework，基线6302862；最终commit/dirty用git核对。ROUTE-V2-00–07 done；08 in_progress，E08 not_run，原生验收与完整目标未完成。
- 今日与论文库详情分别说明收藏类别、项目学习单元和当前批次用途；同paper双图定位与单元定位，未收藏先收藏，本项目120图上限内确保选中纸可达。未匹配显式入口及总数/省略说明；Routeoff保留Map。语义匹配只派生，不改分类/掌握。
- reset使旧快照/关系/context/Map回复失效，同项目同语料亦失效。新选择/关闭/离开视图取消晚导航，失败/无Map先清旧未匹配名单。独立找到并复核修复这两项P2，无剩余P1/P2。
- 最终1455Python/269Node通过，独立73Python104Node+最终1条全流程复核通过；新backend/Tauri .app和实际新包隔离后端通过。一个临时项目完成语言/手工图/3+1+1/Useful撤销/watch/完成/发现/409保留/重新预览确认/重启/undo恢复/当日额度复用/普通资格。证明本地合同，不等于原生点击或建议价值。
- 无模型/来源/真实库调用，核心模型token0、新AI仍未批准；假HOME/出站封锁，默认库未改。之前browserpolicy因访问权限拒绝，Mac锁定，没有绕过；本轮人类解锁/授权请求待答复。不能以等待时间当许可。
- 发布检查exit1：20个原有阻断评估含E08仍not_run，预算执行与校准登记仍未通过；不降gates。真实收益/全文语言/AI质量/tokenizer账单/8GB资源未测。
- [ADR0022](decisions/0022-route-paper-navigation.md)、[checks](evidence/2026-10-07-route-v2-08-navigation-checks.txt)、[review](evidence/2026-10-07-route-v2-08-navigation-review.md)。下一步：人类解锁/许可后验证实际native页面与全流程、必要时修UI；按ROUTE_MODE_REWORK逐条审计最终gates。08不得提前done，goal不得complete；任务状态仅harness/tasks.json。

# 上一工作单元：Route Mode 阶段07共享需求与模型/UI合同完成（2026-10-07）

- 分支codex/route-discovery-rework，基线3ec94c0；最终commit/dirty用git核对。ROUTE-V2-00–07 done，E07 passed仅本地合同与新包后端；08 planned，完整目标未完成。
- 创建/修改共用五字段，老师文字或MD只作需求。创建12，修改完整40/120/3紧凑Map与白名单补丁；预检完整请求、超预算不截图、length拒绝。新操作route_map_create3200/1800、route_map_revision8000/4000独立未批准；原全局额度保持，核心每日必需token0，无真实库/来源/模型调用。
- UI区分创建和修改；现有图先预览结构/目标/掌握影响，再draft_id确认。重启恢复/409保留/需求更改禁旧确认/迟到session回复忽略；人工简介/稳定关注/兴趣历史保留，known不授予掌握。手动建图、明确目标、难度警告保持可用。
- 新旧创建共享flock/计数。取消原子、生命周期核对、短事务退款不复活删除key、确认拒绝同连接重入、reservation failure可重试。Gateway编码先于预留，非法Unicode不留账；未知5xx保留次数与预算。Route raw请求仍1000000字节，131072只限session/model回应，不阻断合法大身份图保存。
- 最终1450Python/257Node全过；独立最终70Python/90Node及实际探针过，无剩余P1/P2。新backend/Tauri .app和实际新包隔离后端验收过，默认HOME未改、出站网络封锁；不等同原生窗口/真实AI质量/推荐收益/全文语言准确率/账单tokenizer/8GB资源测量。
- 实际浏览器被policy明确拒绝（用户拒绝访问权限），Mac锁定；没有绕过。原生与实际浏览器点击验收未完成，留在08及原发布gates。当前新AI范围不借旧批准，不做实付调用。
- [ADR0021](decisions/0021-route-shared-brief-model-ui.md)、[checks](evidence/2026-10-07-route-v2-07-model-ui-checks.txt)、[review](evidence/2026-10-07-route-v2-07-model-ui-review.md)。下一步08：类别与学习任务共享paper身份、双向导航/未匹配入口、Routeoff保留Map、多项目/视图迟到回复；隔离全链条+原生完整验收和发布gates审计。任务唯一状态在harness/tasks.json。

# 当前工作单元：Route Mode 阶段07后端修改预览（2026-10-07）

- 分支 `codex/route-discovery-rework`，本单元基线 `d78d589`；ROUTE-V2-07仍in_progress，E07 not_run，08未开始。实际最终commit和dirty用git核对；完整方案未完成。
- 本地API revision-preview/draft/confirm接完整Map白名单补丁与五字段，新增alias固定UUID；预览不改图，事务内核对图revision+有效反馈（含撤销）/冻结/种子/内容身份。409保留草稿；图、brief、服务权威cutoff、组织事件与确认marker一起保存/失败回滚，重复确认无第二event，undo恢复且禁止重放。
- 语义改变隔离旧熟悉度，保留兴趣/历史/人工简介；watch跟稳定ID。cutoff不低于project最大ID/冻结globalID/旧cutoff。冻结兴趣保持，显式重置后重新读懂或太难可产生一次新熟悉度；双击幂等。旧结构save保持显式边/活动明确目标、不可伪造cutoff；旧plan12限制不裁40图，保留身份/人工简介。旧编辑器删后新增不复用ID。
- 独立审查修复跨项目冻结编号、too_hard重复、共享连接undo/freeze/restore提前commit、原始HTTP重复JSON与旧editor身份复用；228Python+75Node和26weekly夹具复核通过，无剩余P1/P2。最终1418Python/242Node、新backend/Tauri .app及实际新包隔离预览/确认/撤销/重启/409与前期兼容通过；包后端不等于原生窗口或整阶段验收。
- 无新增模型操作/提示/外发/真实来源/真实库；AI扩展仍未批准，不借旧授权。原生窗口、推荐收益/全文语言准确率、AI质量/tokenizer/账单和8GB资源gates不降低。
- [ADR0020](decisions/0020-route-revision-transaction.md)、[检查](evidence/2026-10-07-route-v2-07-preview-checks.txt)、[独立审查](evidence/2026-10-07-route-v2-07-preview-review.md)。下一单元继续07：注册未批准AI新合同，完整消息预算与length拒绝，创建/修改共享五字段、前端预览/409/迟到响应/手动fallback。之后08双图同paper导航与完整隔离+原生验收。任务唯一状态仍在harness/tasks.json。

# 当前工作单元：Route Mode 阶段07本地合同基础（2026-10-07）

- 分支 `codex/route-discovery-rework`，本单元基线 `4937ad1`。ROUTE-V2-07 in_progress，E07 not_run；07整项与08仍未完成。实际commit和dirty用git核对。
- 新 `app/route_revision.py` 固定五字段、完整40/120/3图上下文及本地白名单补丁；旧节点c#、新节点n#，新UUID身份，不截成12节点。保护人工简介，名称/词/类型变化列reset，hint/简介/词顺序不reset；只计算预览cutoff，无服务持久化/AI/API/UI。
- 显式校验模式保留冗余前置、难度倒置列警告、不猜目标。源图允许已归档/空目标进入显式修复，合并结果必须活动明确目标。最终120目标、1384全量Python、241Node通过；独立184相关+506探针通过，无剩余P1/P2。新backend/Tauri .app与实际新包隔离后端兼容通过，不证明尚未接入的revision功能。
- 解析有400ops/131072 UTF8bytes限制；重复JSON字段、未知/冲突操作、截断、深层畸形标量、非法UTF8拒绝。旧公共save不接纳客户端cutoff；新cutoff只在explicit模式保留，未来必须服务端计算。
- 独立审查发现源图目标修复阻断、坏concepts类型、深层copy RecursionError与surrogate响应故障；修复并加回归，独立最终复核通过。无模型/网络/新预算变化，原AI扩展授权保持false。
- 检查与审查见 [checks](evidence/2026-10-07-route-v2-07-contract-checks.txt) 和 [review](evidence/2026-10-07-route-v2-07-contract-review.md)，[ADR0019](decisions/0019-route-revision-contract.md)。下一单元接service/API/UI：保存五字段；预览冻结新增alias→UUID映射（重算随机UUID不能当CAS）；确认内重算权威feedback cutoff+图revision+有效撤销签名，原子graph+brief+cutoffs/undo；只隔离旧熟悉度，兴趣和冻结兼容/读懂重新确认幂等。然后新提示/网关未批准操作、完整消息预算、前端预览/409保留及创建共享字段。最后08双图/原生全链条。

# 当前工作单元：Route Mode 阶段06完成（2026-10-07）

- 分支 `codex/route-discovery-rework`，基线 `a7abf94`，本单元本地提交哈希以git log核对。唯一任务状态在 `harness/tasks.json`：00–06 done，07–08 planned；完整目标未完成。
- 完整有界Map/临时别名、新route_growth_judge、已有任务附近深化/前置缺口/新分支/已覆盖/不确定/补证据、过期签名、活动目标预览、原子确认、跨进程claim及中英文UI已实现。图或相关有效证据变化拒绝旧意见，布局/无关兴趣不误伤。相似度/计数只解释，低证据可主动确认，手动入口保持。
- 修复重复发送、过期遮挡、撤销拒绝不重开、目标预览误算proposed边。失败/409刷新次数和过期，保留编辑草稿；未知5xx保留次数/预算预留，4xx已释放才退。缺口两个方向均未确认虚线。原始提议保留支持接受/拒绝后的撤销，不为清理破坏undo；12仅当前有效意见，页面5、模型3，历史大规模资源未知。
- 最终1354 Python、241 Node、153目标通过；独立核心247、追加80Node/20Python通过，无剩余P1/P2。新后端/Tauri .app和实际新包隔离后端确认/目标重开/撤销/过期/重启/AI-off及前期兼容通过。[检查](evidence/2026-10-07-route-v2-06-proposals-checks.txt)、[审查](evidence/2026-10-07-route-v2-06-proposals-review.md)、[ADR](decisions/0018-route-growth-proposals.md)。
- 新操作仍owner_approved=false，真实模型token/外发0、真实库/源未调用；临时假模型/缓存来源，出站代理封锁。参考3000/700、上限8000/1000、每项目本地日10尝试；全局额度不变，官方价格/协议UTC2026-10-06（本地07）HTTP200复核，旧记录保留。原授权不扩用。E06 passed仅离线合同+新包后端，不证明AI质量/tokenizer/账单/原生窗口/推荐价值/全文语言准确率/8GB资源；原发布gates保留。
- 下一步07固定五字段需求（goal250/known150/include150/exclude150/structure500，仅goal必填）、完整紧凑Map+allowlist patch预览、严格引用/目标/冲突/循环/容量、保留显式边、身份与掌握cutoff、revision+有效反馈CAS、原子graph+brief+cutoffs及undo。之后08共享paper双图导航/Routeoff/迟到响应、隔离全链条及原生完整流程；新AI范围/预算仍需独立审批，不借旧授权。

# 当前工作单元：Route Mode 阶段06进行中（2026-10-07）

- 分支 `codex/route-discovery-rework`，基线 `b752d63`。证据基础本地提交后的最新哈希用git log核对，阶段06未完成；07–08继续保留 planned。任务状态以 `harness/tasks.json` 为准。
- 已修复有效生长兴趣：明确有用或用户选定种子，已读懂不再充当兴趣。方向显示、探索引导与旧判断的方向上下文统一过滤有效证据；撤销有用后不能靠收藏/读懂残留继续引导，冻结反馈仍遵守有效撤销。
- 新 `_pending_growth` 是不限历史曝光类型的本地证据队列，覆盖路径、有用但未曝光和选定种子。尚未接入新的AI合同或页面；旧 direction_judge 仍只发送原批准的探索论文范围，不借用旧授权扩大种子/Map外发。
- 新增12项行为回归；修改前3 failures、8 errors、1 passed，修复后137项相关回归通过。全量1326项Python、231项Node通过；独立80项通过，无剩余P1/P2。新后端和Tauri桌面构建通过，实际新包隔离兼容验收通过，未验证新判断合同或原生窗口全流程。实际结果见 [阶段06检查](evidence/2026-10-07-route-v2-06-checks.txt)。
- 还需完整有界Map与五种提议合同、图/有效证据快照及过期提示、近邻深化/前置插入、原子确认、手动入口和UI，再验收阶段06。E-ROUTE-V2-06保持not_run；不能将这次基础回归当阶段完成。
- 新模型token和外发范围0，真实库/源/模型未调用。AI扩展预算仍未批准。完整目标继续按 [方案](ROUTE_MODE_REWORK.md)执行。

# 当前工作单元：Route Mode 阶段05完成（2026-10-07）

- 沿用 `codex/route-discovery-rework`，本单元在 `f3f2c14` 后本地提交，最新哈希用git log核对。唯一任务状态在 `harness/tasks.json`：00–05 done，06–08 planned；完整目标未完成。
- 本地五位置匹配实现3路径+1探索+1关注，兼任用途的论文在可行时保留不同纸的完整配额。发现互补后路径补位，路径不足少推，发现仍最多2。未回答路径轮转，已回答退出；已满足常规前置不再自动补学习任务。Route无候选不普通回退。
- 完成后每项目每本地日最多1发现，探索优先；手动与维护共用原子batch/exposure和日检查。重复返回当天历史、不新增曝光/自动速览，重启/并发/客户端日期不能绕过。上下文包含当前/冻结有效反馈撤销、方向拒绝和实际论文日期/正文/PDF身份，变化拒绝旧结果。
- 路径与进度一致采用第一匹配。证据论文复用有界当前正文，语言推荐规则不撤销旧理解。延期核验阻止新批次并不缓存为最终进度；生成各环节共256MiB物理核验预算。每篇当前PDF仅一份实际核验凭据，跨LRU/请求/重启可完成核验，身份/版本变化和重新登记失效，不提前提交外层事务。中英文UI区分配额、缺候选、核验和日复用。
- 最终1314 Python、231 Node、261目标通过；独立322+74通过、无剩余P1/P2。新后端/Tauri .app重新构建通过，实际新bundle隔离HTTP的3+1+1/完成限制/重复/重启、召回和前期语言质量兼容通过。[检查](evidence/2026-10-07-route-v2-05-checks.txt)、[审查](evidence/2026-10-07-route-v2-05-review.md)、[ADR](decisions/0017-route-batch-quota.md)。
- 新增模型token和外发范围0；全部临时库，真实源/模型未调用。包请求预置缓存且出站代理封锁。原生全流程、真实推荐收益、大库8GB、全文语言准确率和AI质量/tokenizer/账单仍未测；原发布gates不降低。
- 下一步06有效有用/种子证据与生长提议；07固定五字段与原子修改预览；08双图导航/原生完整流程，按[方案](ROUTE_MODE_REWORK.md)依赖继续。新模型范围/预算仍未批准，先完成离线合同与手动入口。

# 当前工作单元：Route Mode 阶段04完成（2026-10-07）

- 分支 `codex/route-discovery-rework`，本单元在 `62aa5e6` 后本地提交；最新哈希用 `git log -1` 核对。唯一状态在 `harness/tasks.json`：00–04 done，05–08 planned。目标仍是执行完整 [方案](ROUTE_MODE_REWORK.md)，不能把本单元当完整重构。
- 每刷新最多3主题，分路径相关性分页、探索近期分页、已满足且持续关注的最新第一页；单主题最多50篇，实际页码不再从本地匹配数量猜测。多概念轮转，正常严格/补充请求最多6，沿用单HTTP两尝试，来源不可用/网络错误停止剩余主题，无应用额外重试。
- 临时来源七天、最多600论文/每篇3条；分页最多160键（合法40节点最多129），latest不占页缓存。来源与分页签名分别保存，实际路线/语言/窗口/页大小变化失效；无关布局或笔记不重置，新兴趣不重置未变路径页。游标随重启保持。
- 同进程重复刷新拦截；跨进程事务比较最初状态和当前输入，防止后提交覆盖先提交。论文事实与来源原子保存，失败回滚、删除不复活，不改变种子或分类永久归属。公开标题/主题只来自明确有用与用户选种子；导入、收藏、读懂和沉默不自动声明兴趣。
- 页面区分实际抓取结果和仍运行状态，不再把所有失败说成限流。独立审查发现并复核上述分页、缓存、并发与UI问题，最终无阻断。最终1283 Python、226 Node、188目标及独立211+17通过；新后端和Tauri重新构建通过，实际新bundle缓存刷新/轮转/分页/来源/重启及前期资格/关注兼容通过。[检查](evidence/2026-10-07-route-v2-04-checks.txt)、[审查](evidence/2026-10-07-route-v2-04-review.md)、[ADR](decisions/0016-bounded-route-recall.md)。
- 新增模型token和外发范围0，AI扩展仍未批准，未真实调用。所有测试用临时库；新包来源请求由预置缓存提供，出站代理封锁。未验证原生窗口全流程、真实召回收益、大库/8GB资源、全文语言准确率、AI质量/账单；原发布gates保留。
- 下一步 ROUTE-V2-05：替换旧探索比例与普通回退，3路径+1探索+1关注，发现互补再路径补位，路径不足发现仍最多2；未回答路径继续轮转无冷却，已满足未关注不推任务。目标完成后本地日最多1发现，手动与maintenance共用原子额度。之后06有效证据生长、07固定五字段/原子改图、08双图导航与原生全流程继续按依赖执行。

# 当前工作单元：Route Mode 阶段 03 完成（2026-10-07）

- 分支 `codex/route-discovery-rework`，在 `024aa44` 后本地提交；最新哈希用 `git log -1` 核对。唯一状态在 `harness/tasks.json`：00–03 done，04–08 planned。完整目标仍是执行 [方案](ROUTE_MODE_REWORK.md)，本单元不能当完整重构完成。
- 目标范围为活动目标及活动前置祖先；旁支不阻止完成，多目标共享前置只计一次。`goal_status` 区分 learning/completed/needs_review，缺目标、目标范围悬空前置或循环不当完成。`goal_done/goal_total` 为目标口径，旧 `done/total` 保留全图兼容；候选不足不改完成状态。前沿只取目标范围内可学节点，排序与解锁都用有效活动边。
- `watch` 与掌握独立，显式布尔操作可提前关注；仅当前满足节点进入 `watched_satisfied`。关注经组织 revision/undo、保存身份映射、模式开关及重启保留；删除或复用身份不转移。旧图读取默认空关注但不自动写入。页面未保存编辑不允许关注操作。
- 修复冻结范围内反馈撤销不使首页缓存失效，以及409后旧图搭配新版本号的问题；干净页面同步新图，脏草稿单独保留。元数据变化也失效缓存，缓存读取/序列化的大库耗时仍未实测。
- 最终1251 Python、225 Node通过；独立208算法/存储/运行时、68编辑器/翻译、4恢复及94边排序/图算法复核通过，无本阶段剩余阻断。重新后端和Tauri构建通过，实际新bundle后端在临时HOME/库验证资格、目标范围、旁支、关注/掌握、撤销、模式、重启通过。[检查](evidence/2026-10-07-route-v2-03-checks.txt)、[审查](evidence/2026-10-07-route-v2-03-review.md)、[ADR](decisions/0015-route-goal-watch.md)。
- 新增模型token/外发范围0，未调用真实模型；AI新范围仍未批准。E-ROUTE-V2-03 passed仅代表离线合同夹具，原有发布质量/资源/预算等gates保持原状态。原生窗口全流程和真实资料库性能仍未验证。
- 下一步 ROUTE-V2-04：每刷新最多3主题的有界路径/探索/新进展召回、轮转、有限来源记录与去重，不扩大来源调用配额。随后05实现3+1+1、完成每日最多1发现、无普通回退与未回答路径继续轮转。当前旧探索配额和普通回退仍未被新规则替换，勿当已完成。06生长、07固定五字段/原子改图、08双图导航与原生全链条继续按依赖执行。

# 当前工作单元：Route Mode 阶段 01、02 完成（2026-10-07）

- 分支 `codex/route-discovery-rework`，在 `f823138` 之后本地提交；最新提交用 `git log -1` 核对。唯一状态在 `harness/tasks.json`：00/01/02 done，03–08 planned。完整目标仍是执行 [方案](ROUTE_MODE_REWORK.md)，本单元不能当整个重构完成。
- 项目创建和管理页显式选学科/语言，旧项目 pending 时阻止新批次并提示，历史仍可读。STEM 英文，文科多选；元数据与当前全文核验分别显示，替换或修改文件不沿用旧核验。
- 普通、Route、维护共用资格：可用摘要或当前 PDF 对应的有效本地正文。链接、占位摘要、纯标点及无来源/旧来源正文不能充数。统一语料、候选、反馈向量和 Route 的本地文本选择，不改变模型外发。
- 阅读器捕获实际加载字节 hash，提交/缓存查询带来源；项目或文档切换的迟到响应不覆盖当前页面。来源/策略在选取期间改变或项目删除，本轮明确拒绝，无批次/曝光；缓存条件写不能复活删除项目。
- 正文取实际 PDF 第1–6页、每页2000字符；最低200字母数字字符是保守策略，非质量测量。文件最多128MiB、扫描新读取最多256MiB，有界digest/游标缓存并公平轮转；增长文件不超预留读取。最终写入只比较捕获身份，不再全读。
- 最终1231 Python、218 Node测试通过；62项边界/资格/语言/维护/词条目标通过。独立评审发现并复核修复，最后无阻断。重新构建后端和 Tauri .app 通过；实际新bundle后端验证认证、隔离、历史、STEM/文科、正文边界、文件变更和重启通过。[检查](evidence/2026-10-07-route-v2-02-checks.txt)、[审查](evidence/2026-10-07-route-v2-02-review.md)、[ADR](decisions/0014-shared-recommendation-eligibility.md)。
- 新增模型token/外发范围0，AI新范围仍未批准，未真实调用。未操作原生窗口，未测真实资料库、推荐收益、语言准确率或8GB性能；旧发布gates保持原状态。
- 下一步 ROUTE-V2-03：目标及活动前置祖先范围、goal_frontier/complete/needs_review分开；持续关注与掌握独立保存，route-save/组织事件/撤销/身份变化都保留或明确清除，不能只添加字段后保存就丢失。随后按依赖执行有界召回、3+1+1与完成每日1发现、有效证据生长、固定五字段/原子改图、双图导航与原生全链条验收。未回答路径仍轮转、无冷却；当前旧探索与普通回退规则暂留到05，勿当新行为已落地。

# 当前工作单元：Route Mode 阶段 01 数据基础（2026-10-07）

- 分支 `codex/route-discovery-rework`；阶段 00 已提交 `cc6bcaf`。本切片在其后本地提交，最新哈希用 `git log -1` 核对。唯一状态源仍为 `harness/tasks.json`，ROUTE-V2-01 为 in_progress，E-ROUTE-V2-01 为 not_run。目标仍是执行完整 [方案](ROUTE_MODE_REWORK.md)，不能把此切片当重构完成。
- 已实现数据基础：迁移 009 保存显式学科/允许语言/revision，旧项目保持 pending；STEM 只接受英文，文科13种固定选项可多选。OpenAlex语言单独保存，不从英文标题猜全文。全文语言核验绑定 PDF hash，替换失效且历史证据保留。
- 正文保存可明确传来源 hash；缺失保持 NULL，过期版本被拒绝，分页失败原子回滚，HTTP透传并返回400。旧阅读器目前仍提交未绑定正文，尚未作为当前文件证据；后续必须接入来源版本与当前版本读取。
- 最终全量1205 Python测试通过；独立审查实际21项基础/迁移/备份及1项HTTP测试通过，发现误绑定和迁移夹具问题已修复复查。后端与 Tauri .app 重新构建成功；打包后端从v8夹具升级v9、pending策略、备份、隔离认证、退出重启通过。原生窗口未操作。[检查](evidence/2026-10-07-route-v2-01a-checks.txt)、[审查](evidence/2026-10-07-route-v2-01a-review.md)、[ADR](decisions/0013-project-paper-language.md)。
- 模型预算和外发范围不变，新增本地逻辑0模型token。AI扩展仍未批准、未真实调用，旧发布门槛不改为 passed。
- 下一步继续 ROUTE-V2-01：项目设置/创建UI与API接入、旧项目生成新批次前的语言策略检查、策略变化的资格失效和元数据/全文状态显示。随后 ROUTE-V2-02 共用资格函数，并把阅读器实际抽取文件的hash传到正文保存、过滤过期缓存。资格规则只有摘要或当前有效本地正文；链接不能代替正文。调整既有推荐测试时显式补语言策略与元数据夹具，不在生产默认猜英文，不用全局测试补丁绕过门槛。

# 当前工作单元：Route Mode 重构阶段 00（2026-10-07）

- 分支 `codex/route-discovery-rework`，基线 `850f9fc`。完整设计见 [方案](ROUTE_MODE_REWORK.md)；唯一阶段状态在 `harness/tasks.json`（ROUTE-V2-00 至 08）。
- 阶段 00 已实现：桌面启动尊重显式测试目录，默认启动兼容；临时库认证/退出/重启验证通过。基线 1191、阶段全量 1193 Python 测试通过；前端基线通过。后续测试加强项单独重跑通过；后端和 Tauri .app 构建通过，打包后端隔离验证通过。
- [检查证据](evidence/2026-10-07-route-v2-00-checks.txt)、[审查](evidence/2026-10-07-route-v2-00-review.md)。独立静态复查无阻断；独立执行受其 sandbox 禁止 loopback 限制，记 not_run。未操作原生窗口，不把后端检查当完整 UI 验收。
- 预算不变：日常核心最低模型开销 0；新创建/修改/方向判断范围只在方案中提议，未登记为批准、未实际调用。AI 质量、tokenizer/账单和旧发布 gates 保持未验证。
- 下一步 ROUTE-V2-01：项目语言策略与备份迁移。理工科英文、文科显式允许语言；旧项目待选择，不凭关键词自动判学科。先写迁移和项目隔离回归，再动 API/UI。不要用真实资料库。

# 当前工作单元：没有摘要又没有 PDF 的论文不推送（2026-10-07，直接在 main 上，在 91fee72 之后）

- **规则**：每日推荐只考虑“有摘要，或本地已存 PDF，或已知能拿到 PDF（直链或开放获取原文页）”的论文；三样都没有的论文留在项目里、仍然参与画像和学习图，只是不推送。有学习图和没有学习图都一样。
- “无 PDF”我按“没有任何 PDF 来源”理解：只有开放获取原文页的论文仍然算能读。如果你想连“仅原文页”也不推，告诉我。
- **没验证**：没读你的真实库，不知道会过滤掉多少；所有没看过的论文都不可读时就没有批次；没做独立评审。见[变更](../changes/2026-10-07-unreadable-papers.json)。

# 当前工作单元：探索的标准改严、没回答的路径论文可以反复推（2026-10-07，直接在 main 上，在合并 c83ab62 之后）

- **探索 = 没展示过、并且不匹配学习图里任何概念的论文**（已读懂的概念和还没解锁的概念都不算）。之前凡是不在“现在能读的概念”里的没看过的论文都能当探索，按和你兴趣的相似度排，所以最像你已知内容的 3DGS 综述排第一。
- **没回答的路径论文可以反复推**：属于你现在能读的概念、你还没收藏 / 不感兴趣 / 太难 / 已读懂的论文一直是候选，展示得最少的先出，所以先把没展示过的推完，再轮到展示过的。回答过就不再出现。
- **去掉上一轮的“路径外”标签和补位**。路径上没有可推的论文又没有探索候选时才退回普通推荐；批次不够 5 篇时写明原因（“没凑够”）。原来所有论文都展示过时直接不出批次的提前返回也去掉了（在有学习图时）。
- **没验证**：没读你的真实库，“不匹配任何概念”的论文可能很少，那样一批就没有探索位（面板会写）；一直不回答的路径论文会反复出现，你只能回答它或把概念标成已掌握；没做独立评审；Tauri 窗口没点。见[变更](../changes/2026-10-07-explore-standard.json)。

# 当前工作单元：今日推荐不再丢掉路径标签、探索标更醒目（2026-10-06，分支 feature/route-growth-visible，在 b151002 之后）

- **问题**：点“生成今日 5 篇”有时候卡片上没有任何路径信息。原因（用夹具连续生成三批复现）：你现在能读的概念的论文都被展示过之后，`build_batch` 把路径选出来的论文全丢掉，退回普通推荐，卡片没有标签，原因也从来没显示给你。
- **现在**：这一批仍然是路径批。探索位的论文保留探索标，其余按普通排序（兴趣）补上，标“路径外”，标签里写它最像的概念（有的话）；今日页路径面板那一行会写“今天有 N 篇是路径外的补充：你现在能读的概念暂时没有未展示的论文了，点‘抓取新论文’回到路径上”。不增加 AI 调用，也不需要迁移。
- **探索标**：实心加粗的标签加 ✦，探索卡片左边加一条竖线。
- **没验证**：没有读你的真实库，不知道多久会发生一次；补充的论文只是普通排序加标签，不会自己去抓新论文；没有做独立评审；Tauri 窗口没点。见[变更](../changes/2026-10-06-today-path-labels.json)。

# 当前工作单元：潜在方向和探索合成一个闭环（2026-10-06，分支 feature/route-growth-visible，在 9e6f150 之后）

- **流程**：今日推荐里带“探索”标的论文 → 你点“有用”收藏 → 卡片上出现“让 AI 判断”（学习图页的潜在方向里也有同一个按钮）→ AI 判断这些论文是不是一个**明显不同于学习图里已有概念**的新方向（是已有概念的近邻或更细的话题就答“已覆盖”）→ 是的话放进潜在方向（中文名、介绍、门槛、前置）→ 探索位优先推和这个方向的论文读起来像的论文 → 你再收藏，再判断（通常并入该方向）。原来本地从标题切英文词对的做法已删除。
- **页面**：学习图下面的“潜在方向”只列方向（名字、进度条、论文数）；**点哪个，图上才出现哪个**（虚线进度框、与现有概念的虚线箭头；全满变实线），右侧是介绍、门槛（标“AI 的判断，不是事实”）、四项门槛、依据的论文、拓扑；再点一次或点别的节点就收起。加入需要四项门槛全满再点“加入学习图”。待判断的探索论文单独一块，按钮点了才调用 AI。
- **本地只数不发现**：论文数（AI 并入的）、仍然明确正向的篇数（之后被你点“不感兴趣”或撤销的不再算）、来源数、强度；AI 说是新方向时本地再兜底（前置只能是已有概念；名字/检索词已在地图上，或论文文字和某个现有概念太像，余弦 ≥ 0.40，就改判“已覆盖”）。
- **节点简介**：`concept_intro` 现在还会发该概念匹配到的最多 3 篇本项目论文（标题 + 摘要前 200 字），让 AI 说清“在这些论文里指什么、门槛在哪（先要懂什么、难在哪）”，上限 140 字；点“让 AI 写简介”后编辑框里仍然能看到“你的项目里的论文”（之前会消失）。
- **预算（owner 批准“简介 + 方向解释两项上调”）**：`concept_intro` 输入 500→2000、输出 250→400（每项目每天 20 次）；新增 `direction_judge` 输入 3000、输出 500（每项目每天 10 次，`App.DIRECTION_JUDGES_PER_DAY`）。摘要节选比议案说的 250 字短（200 / 180 字），为了不超过上限。最坏输入按每字 1.5 token 的启发式约 1950 / 2930。
- **没做/没验证**：两条提示词没有真实调用过，AI 是否守 JSON、是否把近邻误判成新方向未知；`T_NEAR`、`T_TOWARD`、强度阈值没有数据；不是通过探索收藏的论文不会触发方向；离线时不会出现新方向（已存的仍可看）；被判为“看不出来”的论文不会再被问；尚未合并 main；Tauri 窗口没点。见[变更](../changes/2026-10-06-growth-direction-loop.json)。

# 当前工作单元：学习图的“生长”不再是黑盒（2026-10-06，分支 feature/route-growth-visible，基于 0d65548）

- **探索标看得见**：之前探索占比 10%，批大小 5 时第 1 批 0 个、第 2 批才有 1 个，所以一直看不到。现在起始占比 20%（每批至少 1 个，最多约 60%）；探索位**先给“正在形成的新方向”里的论文**，卡片标“探索 · 新方向 X”（`route_kind=explore_new`，存在原有的曝光列里，没有迁移），Today 页写明本批探索位和原因。生长靠什么没变：只看你对论文的明确反馈（有用 / 已读懂 / 种子），和这篇论文是怎么推给你的无关；被推荐、被展示都不是证据。
- **潜在方向一进页面就列出**：学习图页自动读取，最多 5 个，两篇明确点过的论文共享一个学习图没覆盖的短语就出现（“证据不足”）。每个方向在图上是虚线边框的“幽灵节点”，边框随四项门槛（论文数、明确点过的篇数、来源数、强度）变满，**全满才变实线、才能点“加入学习图”**；点开能看每项门槛、还差什么、哪几篇论文（标出你点过的）、加入后和哪些概念相连。幽灵节点只用于显示，不会进入草稿和保存。
- **节点看得懂**：每个概念可以有一句简介（≤90 字）：自己写、AI 起草学习图时顺带写（≤30 字）、或点“让 AI 写简介”单独写；AI 写的标“AI 写的”，改过就算你写的，**AI 重新起草不会覆盖你写的简介**。详情里还有角色（入口 / 中间 / 目标 / 旁支）、难度含义、项目里匹配到这个节点的论文，以及“看公开文献里的代表论文”（只发第一个检索词去 OpenAlex，不保存）。
- **预算（owner 在会话里批准了这两项）**：`learning_path_plan(_project)` 输入 1400→1460、输出 900→1500；新操作 `concept_intro` 输入 500 / 输出 250，每项目每天最多 20 次（代码常量 `CONCEPT_INTROS_PER_DAY`）。独立评审发现披露文字写“项目目标”而实际发送的是项目名称和前 3 个关键词，已全部改正并把上限收紧到 30/80 字（最坏 471 token，每字 1.5 的启发式估算）。**请 owner 确认改正后的 budget.json scope 文字。**
- **独立评审**（只读 agent，不是人）：1 个会让就绪方向消失的真问题（两篇阈值把 60 个短语名额挤满），已修；3 个重要问题和若干小问题都已修，见[评审记录](evidence/2026-10-06-growth-visible-review.md)。修复没有再让评审重读。
- **没做/没验证**：两条提示词都没有做过真实调用，简介质量和长度未知；20% 探索占比没有数据支撑；尚未合并 main（另一个会话的“已读懂必须先收藏”规则合并后，这里把未收藏论文标“已读懂”的测试夹具要改）；Tauri 窗口没点。见[变更](../changes/2026-10-06-growth-visible.json)。

# 当前工作单元：周报显示方向的详细变动（2026-10-06，分支 feature/route-layers）

- **周报不再只是数字表**：页面（画像 → 本周动向 → 周报）现在依次是：一句话概览（本周涉及几个方向、几篇论文，比上周多/少多少）→ 五张数字卡（收藏、有用、已读懂、不相关、太难，带上周对比，点开看来源）→ 这一周每天的堆叠柱状图 → **方向的变动**（按论文库类别，一篇论文在两个类别里两边都算：本周/上周的横条、各类记录数、状态词“新出现 / 比上周多 / 与上周持平 / 比上周少 / 本周没有记录 / 本周没有收藏或已读懂”、点开看涉及的论文）→ **学习图进度**（已读懂 N / M、本周有“已读懂”记录的概念、每个概念本周的记录；学习图关闭时会说明）→ 本周留下的论文（带方向和概念标签）→ 曝光与有用率 → 词项变化。
- **口径**：全部是本地明确记录的计数。没有记录只写“本周没有记录”，不写成兴趣下降；被推荐露出的论文只算“看到”，不算拒绝；收藏不推进学习进度，只有“已读懂”才会让概念出现在“本周有已读懂记录”里。有用率按每篇论文本周最后一次评价算一次。
- **实现**：`profile_insights.weekly()` 在原有字段外新增 `daily / directions / more_directions / units / highlights / picks`（旧字段不变）；`weekly-ui.js` 是纯函数渲染，文字都转义；旧的 `PDHProfile.weeklyHTML` 表格已删除。路线匹配只在周报里做、只匹配本周有记录的论文。
- **独立审查**找到 1 个严重问题（删旧函数后 `PDHProfile.create` 还引用它，会让画像页打不开，之前没有测试会发现）和 5 个重要问题，均已修复并加测试，修复没有再让评审重读，见[审查记录](evidence/2026-10-06-weekly-report-review.md)。
- 没做/没验证：`/api/weekly_report/analysis` 的文字总结没改；Tauri 窗口没点；很多论文都没归类的项目会得到一个很大的“未分类”卡。见[变更](../changes/2026-10-06-weekly-report.json)。

# 当前工作单元：论文库入口与命名整理、学习图视图的左侧定位（2026-10-06，分支 feature/route-layers）

- **一个入口、一个名字**：顶栏只剩 今日 / 论文库 / 画像（原来“论文库”和“知识库”打开同一个页面）。页面标题叫“论文库”（原“论文整理”），页内切换“列表 | 图谱”（原“论文库 | 知识图谱”），图谱里再分“论文关系 | 学习图”（后者原叫“学习图 + 论文”，按 owner 要求改名）；“整理建议”按钮和弹窗叫“整理分类”，导出叫“导出论文库”。回到这个页面时记住上次停在列表还是图谱。
- **学习图视图的左侧定位**：在“学习图”视图里点左边目录的论文，会定位到它的节点（相连的保持亮，其余变淡，镜头居中）；点类别则点亮该类别的论文和它们对应的单元。另外把图上两个切换条画成真正的胶囊（页面通用按钮样式不再透进里面），并修了“切回论文关系后还留着学习图提示行”的问题。
- 没做：docs/*.md 和代码注释里还有旧名字；index.html 里一段从不显示的旧“我的论文库”区块还在；桌面 .app 已重建但没启动。见[变更](../changes/2026-10-06-library-entry.json)、[定位变更](../changes/2026-10-06-route-view-focus.json)。

# 当前工作单元：学习图与论文知识图谱分层（2026-10-06，分支 feature/route-layers，基于 main 6c0e575）

- **反馈语义**：新增显式动作 `understood`（已读懂）。收藏/有用只增加兴趣，**不推进掌握度**；只有“已读懂”推进学习进度，“太难”降低掌握度，二者都不改变兴趣。每篇论文分两个维度各保留最新一条（兴趣：有用/不感兴趣；熟悉度：已读懂/太难），所以先点“有用”再点“已读懂”不会互相覆盖，“太难”也不再把已有的“有用”挤出画像（`db.collapse_feedback`）。种子论文仍算一次兴趣（选定的方向），**不算读懂**。沉默、没选、没空、没打开都不改变任何东西。旧反馈不回填，旧项目按新语义重算，学习图页写明“收藏不等于已读懂”。推荐卡和论文详情都有“已读懂”按钮。
- **节点类型与边界**：学习图节点可带 `type`（主题/方法/问题/基础）和 `why`；论文形状的节点（DOI、arXiv 号、网址、et al.、论文字段）在 AI 回复修复时被丢掉并报告，在保存校验时被拒绝，AI 回复里的论文列表被忽略。基础概念只在用户选了“背景：未知”时保留，且必须有一句理由。创建页和学习图页新增可跳过的“你的背景 / 想学到”两个枚举；跳过 = 能读论文 + 最少前置。只发送这两个枚举值。
- **预算（owner 已批准）**：加入 type 和 boundary 后，保守估算的输入超出原 1200 上限，`learning_path_plan` / `learning_path_plan_project` 的输入上限登记为 **1400**（输出 900 不变）；agent 先标为未批准，**owner 于 2026-10-06 在会话中批准**（“AI 起草的输入上限我批准了”），现为 `owner_approved: true`。真实调用还没有做过。次数上限（1+2 / 每项目每天 3）在代码里，不在 budget.json，已写进 BUDGET.md 并有测试固定。
- **图谱的第二视图**：论文库的“图谱”页在“某个项目标签且该项目有学习图”时多出“论文关系 | 学习图”切换。`POST /api/organization {action:"route-detail", project_id}` 只读、不存任何东西：学习单元按前置层数分行，论文挂在检索词匹配的单元下（边上写着匹配到的词），没有对应单元的论文放最后一行并说明，库太大时最多 120 篇并写出另有多少篇；相似边复用离线结果。布局只在内存里，不动论文图的保存布局。**本次没有引用边**（OpenAlex 对近期 arXiv 论文几乎没有引用数据；owner 2026-10-06 决定不做；曾试过给论文挂 Connected Papers 搜索链接，owner 觉得没用（免费额度太少）已回滚，提交 ca6b552 / 801ff2c）。
- **增量生长**：学习图页新增“新方向”：点“查找新方向”才计算。证据只有“有用”“已读懂”和种子；“不感兴趣”不创建分支，“太难”只算难度，沉默无证据；冻结后不再计入新反馈。每个提议显示论文数、你明确点过几篇、来源数、与现有概念的重叠、建议的父节点和前置。点“加入学习图”才加入（走 route-save，带版本号，冲突返回 409），“不再提示”把候选记进路线数据；两者都能马上撤销。不会自动加入。`pathgrowth.branch_candidates` 之前只有测试调用，现在接了线。
- **独立审查**（一个只读的代码审查 agent，同一模型家族，不是人）找出 7 处真实问题，已全部修复并各加了测试：①“不感兴趣”后又点“已读懂”的论文仍被算作增长证据；②“不再提示”按论文集合的哈希记，论文一增加就失效——现在按归一化的短语记，已在地图上的方向也按短语识别；③“撤销”可能撤销别的步骤——现在页面带上它提供撤销的那一步的编号，之后又有别的改动就拒绝并隐藏按钮；④未保存修改时“撤销”没有锁；⑤第二视图的慢请求可能画在已经切回的论文图上——现在每次重绘都作废在途请求，并核对视图、项目标签和模式；⑥旧地图里本来就有的“论文形状”名字会让之后的保存失败——现在只拒绝新出现的，报错带上概念名；⑦读第二视图会建表/写行/做备份——现在是纯读取。修复**没有**再让评审重读。另有：详情面板点“已读懂”后现在会重画；预算最坏情况估算比登记值高的缺口写进了 BUDGET.md。
- **没做/没验证**：没有调用真实模型（新提示词是否产出带 type 的结构未知）；Tauri 窗口没点；增长的强度阈值（0.25 等）是没有数据支撑的提案，真实库上可能很少出现“ready”（测试里需要 3 篇明确正向且文本很一致）；第二视图的点击交互只在浏览器里点过按钮，没有自动化的画布点击测试；知识图谱里没有显示“建议中的新方向”节点（只在学习图页）。工作树里还有另一个单元（`changes/2026-10-06-text-wrap-layout.json`）未提交的改动，和本单元混在 `index.html`、`project-creation.css` 里。

# 当前工作单元：学习图改成带箭头的图、项目改名/删除、已有项目的 AI 起草（2026-10-05，分支 feature/route-mode）

- **owner 反馈的四件事**：①项目不能编辑/删除；②已有项目不能用 AI 搭学习图；③学习图的结构和界面不对（看起来必须读完上一阶段才能下一阶段，没有节点到节点的关系，AI 给的常常是一条线）；④创建时 AI 生成的图太大，超出页面。
- **项目管理**：新页面 `project.html`（顶栏“管理项目”链接 + 项目总览每张卡上的“管理”按钮）。改名；删除要输入完全一致的项目名，并且先在数据目录写一份数据库备份（`paperdighelper.sqlite.pre-delete-<时间>-<项目前缀>.bak`，只留最近 3 份；备份失败就不删）。论文元数据、PDF、全文保留，别的项目不受影响。关键词不在这里改（它们是画像的钉住词）。
- **已有项目的 AI 起草**：学习图页“让 AI 起草”（有或没有学习图都能用）。显式点击，一次调用；只发送你写的目标（≤250 字）和项目前 5 个关键词；每个项目每个本地日最多 3 次付费尝试（网关拒绝而没发出去的不计）；结果只是草稿，点保存才生效，编辑在调用期间被锁住，草稿会沿用同名概念的旧 id，所以“已掌握/手动解锁”标记按名字保留。**它是单独登记的新操作 `learning_path_plan_project`。独立审查指出我不能自行扩大 `learning_path_plan` 的批准范围（AGENTS 规则 9），所以先登记为未批准；owner 随后在会话里明确回答“批准”，已把 `owner_approved` 改为 `true` 并记下原话（2026-10-05）。** 仍然只在点击时调用，仍受全局日/月额度和 AI 总开关约束；若以后被改回 `false`，网关会在发出请求前拒绝，页面写“等待你批准”。提示词文件 `prompts/learning-path-plan-project.md` 与会话版系统指令逐字相同。
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
