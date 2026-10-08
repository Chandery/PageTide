# 审计问题修复的独立复核

2026-10-08；工作树 `audit-bug-fixes`，基线 `8e5cfd7`。业主已授权逐项修复 B01–B29/I01–I12。本代理独立于实施者，只读产品、测试、设计与分组记录，仅写本文及忽略的私有探针；没有写原审计数据、主检出或正式用户资料，没有构建、操作原生窗口或运行真实模型。

**本阶段的有界独立复核已封存，不是最终发布批准。** 下文保留修前反例与多轮修后证据；末节记载恢复余额后的 R19 核账、实际包的指纹差异和新出现的原生缺陷。实施者正继续修复这些原生问题，最终源、包、HTML、完整科学盲评及发布记录需随后复核。确定性回归、代理审查、科学质量及真人价值门槛分别记录，不能互相代替。

## 方法与资源

已读 review-change 技能、ADR 0030、当前逐项矩阵及阅读/发现分组证据，并检查真实 diff 和调用者。反例直接调用原 LibraryImport/Store，数据库、锁、暂存和归档在 throwaway 目录；时序门有明确等待上限。阅读附件探针提取原 `showPdfFailure` 函数，以 DOM/transport 替身执行其原逻辑，不冒充原生操作。PDF 构造具有真实对象、索引与页面，另以 pypdf strict 解析页数、注释和文字，不能只凭 `%PDF` 头认为合法。

私有证据保存在 `.local/audit-fixes-independent-20261008/`。本代理产品/探针的真实外发和模型请求均为 0；socket 外发被拒绝。另只读访问官方 DeepSeek Vision 文档核对图片协议，这类官方文档浏览不能记作网络 0。读取前轮四份公开 PDF 仅作兼容性回归，没有重写前轮文件。探针退出 0 只表示检查器正常完成，JSON 中的问题状态仍须逐项判断。

证据收尾时发现三个 AI 私有运行器的默认输出名仍是 initial，后续复跑改写了这个 JSON；最初完整 stdout 日志一直保留。已从原始日志逐字复制 `ai-prerequisite-first-failure.json`（4 组）、`ai-scope-first-failure.json`（2 组）、`ai-reply-first-failure.json`（5 组），原日志不改；默认输出已改 current，后续带明确轮次名。这是探针留档错误，不能把被复跑覆盖的 initial JSON 再用作修前证据。本文修前结论以 first-failure 文件及原日志为准。

## 审阅中发现与处置

| 独立项 | 发现与影响 | 当前处置与证据边界 |
|---|---|---|
| R-F01：classic xref 的 64 KiB 错误格式限制 | 最初实现从 startxref 仅读 64 KiB，并要求 trailer/Root 都位于其中，按源码必然拒绝较大的合法索引。 | 实施者已拆开扫描索引与字典。本代理构造 431,326 字节、3,500 个实际页面注释、70,132 字节索引；strict 解析 1 页/3,500 注释/正文均正常，当前接受。初始版本的判断来自源码，未声称在修正前执行该反例。 |
| R-F02：xref stream 的 4 KiB 错误格式限制 | 409,256 字节合法文件，Index 为 3,507 个连续单项范围、字典 23,513 字节；Root 在 Index 后，初次产品实际拒绝。独立 strict 解析正文、1 页及3,500注释正常。 | 已改为分块读至 stream 边界、不解压内容；复跑后接受。`pdf-advanced-initial.json` 保留失败，`pdf-advanced-r2.json` 保留三组通过（常规 xref stream、长 Index、增量 Prev/Root 继承）。 |
| R-F03：B28 附加 PDF 后丢失阅读项目 | 在顶部项目为医学、所选阅读项目为计算机时，失败页附加成功调用两参数 openReader，默认切回医学，随后 QA 归属拒绝。 | 源码发现后已显式携带原项目及 epoch。独立原函数 VM 三组收据：同对象重开仍为计算机；上传期间切对象不 attach；attach 期间切对象不重开旧阅读器。源码发现与修后执行证据分开记录，没有声称原生复现。 |
| R-F04：I03/I04 人工冲突决议被继续匹配覆盖 | 两份矛盾 BibTeX 引同一 PDF；用户选择第二 DOI 后为 matched。再上传另一个 PDF 并 resolve，原条目回到 needs_choice、paper=null。明确排除原 PDF 后 resolve，也会复活成 needs_choice。 | 已以来源身份/规范题名记录决议。独立 `import-lifecycle-r3.json` 确认再 resolve 仍 matched/所选第二 DOI，明确排除仍 excluded。initial/r2 原失败保留。新身份触发新冲突的完整实施回归仍须联合核对。 |
| R-F05：本地 join 在提交后删除追溯来源 | 原 entry UPDATE 前暂停 resolve，另一 controller 对 excluded 来源人工查找并提交；旧 join 继续后删来源行，把已排除旧题录写入已提交 PDF.entry。两分支无异常，canonical 库论文未删，提交计数与追溯行不一致。 | 已给本地阶段共享短编辑锁及 committed/状态守卫，明确排除来源不再自动 join。`import-join-race-r2.json` 确认原两个显式排除分支跳过 UPDATE/保留两行，人工查找也保留；pending join 的实际 SQL 门前 commit/lookup 均被拒，释放后提交前后 IDs 一致。初次失败保留。 |
| R-F06：网络等待中重传导致 PDF 跨论文错绑定 | resolve 等待旧视觉规划 DOI，同路径重发材料 PDF（同 size/mtime，不同 SHA/DOI/题名）；旧结果用旧 hints 审核后把新 bytes 绑定旧 DOI，commit 成功。 | 已用请求起点 SHA/hints/entry 及当前状态核对迟到写入。独立 `import-resend-race-r5.json` 确认旧结果不写，paused/content_changed、pending/paper=null，提前 commit 拒绝；用户继续后新 DOI 与新归档 SHA 一致。r5 将 r4 中歧义的 final 字段名改为 after_late，行为没有更改。r2 原 P1 保留；首轮 fake client 缺方法、r3 旧探针未捕获现在正确的 commit 拒绝均是探针失败，不计产品错误。 |
| R-F07：内部快照恢复写失败留下不可重试目标 | 初次写 100 bytes 后模拟故障，restore helper 留下 partial 数据库，目标已存在使同路径重试被拒；此 helper 没有用户恢复入口。 | 已改独占新目录、0600 临时文件、flush/fsync/replace，失败只清本次新目录。`snapshot-probes-r2.json` 对 fsync/replace 故障确认清理及同路径重试，预存 sentinel 不改，坏 SHA 不建目标。初次失败保留，不能外推 GUI 恢复或所有文件系统故障。 |
| R-F08：坏回复与未知计费组合遗漏 | numeric/list 回复加坏 usage，translate 初次抛 AttributeError；QA 数组/标量初次被当答案写两行历史。未知账本原本保持 reservation，没有发现预算释放问题。 | `ai-reply-r4.json` 5 组及 `ai-reply-boundaries-current.json` 22 组独立通过：坏类型/空白/截断/非法 Unicode 稳定拒绝，未知计费仍占用；坏结构拒写，完整 fence/兼容 prose 正常。首轮 effective/raw 账本的探针读法已更正并保留初版，不伪造原计费缺陷。 |
| R-F09：B21 否定和可选语句被当硬前置证明 | 用户原文为 `Representation is not required before Planning.` 或 `Representation before Planning is optional.`，AI 引用同句时建图/修改仍各保留 1 条硬前置；修改无警告。后续扩大反例仍发现 isn't、never、no prerequisite 被保留。 | 已补否定/可选与方向守卫。`ai-prerequisite-r8.json` 独立 7 组：肯定必要关系保留；not、optional、反向、isn't、never、no prerequisite 在创建和修改均不写硬关系，并给可选提示。first-failure/r3 原失败保留。有限字面防护不是通用必要性证明，人工控制性样本不是自然模型失败率。 |
| R-F10：B20 作用域矛盾/证据缺失仍标 covered | NSCLC PD-1 任务对明确 melanoma in vitro 引文仍 covered；Cathode sulfide interface 对仅 bulk ionic conductivity 引文也 covered。后续还发现包含“mice; no clinical trial”的短引以 trial 标注时可传播临床获益。 | 已补固定对象及研究类型冲突守卫。`ai-scope-r10.json` 独立 7 组：正确 NSCLC 基础实验和明确 cathode/interface 两肯定控制仍 covered；错癌种、仅体相、mice 冒充 trial 均 unclear，并保留 R-F14 的明确治疗正反控制。first-failure/r4 原失败及源码 SHA 保留。引用真实不独自证明科学相关，不能声称彻底验证科学语义。 |
| R-F11：引导的未发送目标限制不可核对 | 输入完整目标仍保存本地，但预算合同只发短节选；若回复仅显示 AI 模式，用户无法判断尾部排除条件未被模型看见。随后实际快速创建函数中英 live/cold 四组也没有 notice/excerpt/details。 | 服务端已补 context_limits/context_excerpt/scope_notice 并持久化，完整引导及快速创建共用提示函数。`guidance-excerpts-current.json` 两语言确认真实 wire 节选与展示收据相同、完整本地目标保留、冷启仍保留。`guidance-bubble-current.json` 和 `guidance-quick-r2.json` 以实际函数确认完整引导及快速创建 live/cold 均显示并转义；快速创建初次失败见 `guidance-quick-initial.json`。初次 bubble VM 误断言必有 message 字段已保留并更正：首轮同目标不重复发送 message。函数 VM 不替代真实像素/可读性验收。 |
| R-F12：学习短语匹配跨空段拼词 | `Visual\n\nrepresentation theory is a topic of algebra.` 对 visual representation 返回 true；两个 matcher 都把任意空白视为短语分隔符，空段也会组合词组。 | 已限制为常规词间分隔或单折行。`learning-match-initial.json` 保留失败，`learning-match-current.json` 确认空段拒绝、正常单折行肯定控制保留；句号和任意非白名单词 gap 均拒。此是格式边界反例，不估计真实论文发生率，也不将全部词法匹配视为科学语义错误。 |
| R-F13：兼容建图入口与旧缓存绕过 B21 必要性防护 | 新界面使用固定 brief，但仍服务的无 brief 会话 route 和项目 action=plan 走旧 parse/normalize。目标明确 `Representation before Planning is optional.` 时仍保留一条 active 硬边。旧 learning_path_plan 及同 brief/正确 operation 的旧 route_map_create 未确认缓存的 kept/cold 也仍有硬边、无警告。 | 新生成旧契约与两类缓存均修复。`legacy-map-r2.json`、`legacy-cached-map-r3.json`、`brief-cached-map-r3.json` 均0无证明硬边、有警告、原setting不改、0重新调用。`cached-proof-controls-current.json` 确认混合草稿保留1条原文肯定必要边、另一条转可选；手工已确认2边仍2，提示没有把保留硬边说成全部可选。两个缓存初次失败均保留，没有把兼容 API 当死代码。 |
| R-F14：B20 按单个关键词一票否决正控制 | 固定 NSCLC PD1 耐药目标，原文明确 `NSCLC PD-1 resistance was induced by KRAS mutation in vitro.`，对象、治疗及 basic 标签均字面支持，但 KRAS 未出现在图中就被 scope_conflict 判为 contrary，结果 unclear。 | 已移除单词一票否决。`ai-scope-r6.json` 保留错误收窄，`ai-scope-r10.json` 确认固定目标不改，明确 NSCLC/PD-1 的 KRAS 基础实验控制 covered，而铂耐药无 PD-1 的邻近控制仍 unclear。这是人工教学文字，不是新发表医学结论或自然库发生率。 |
| R-F15：排除对象反被提取为目标对象 | 固定目标 `Study melanoma. Exclude treatment-response reports from NSCLC.` 和中文“研究黑色素瘤。排除使用PD-1治疗获得的非小细胞肺癌相关材料。”，否定距离窗太短，均把被排除 NSCLC 加进允许对象。扩大检查又发现“NSCLC is excluded.” / “非小细胞肺癌不纳入。”后置排除仍被提取为目标。 | 长前置排除与明确后置谓词已修。`learning-scope-current.json` 核前置、实际 App 流程；`learning-scope-final-boundaries-r2.json` 确认后置中英拒绝，反向 NSCLC 目标及多癌种比较保留。前置和后置初次失败分别保留。无标签或目标的事后修改；明确句式防护不能描述为任意复杂自然语言逻辑已理解。 |
| R-F16：不合目标的心理学论文继续占探索槽 | `replay-precision` 计算机最后60学习推荐真实returned=2：一篇视觉 latent/planning，另 `Dissociating Reasoning and Planning through Markov and Quantum Metacognitive Dynamics` 为人类response/confidence心理研究，以 explore、node=null、explanation=null 进入，未说明如何帮助固定视觉世界模型任务。旧正文只写前沿1/1还隐藏了这次曝光。 | 论文/目标/旧结果保留，新增明确环境冲突守卫。`learning-scope-final-boundaries-r2.json` 确认原公开心理论文拒绝；人工人类控制也拒，真正机器人比较及 vision-based 正控制保留。最终 `replay-purpose-final` 计算机两个目标均只实推1篇/1篇有用；固定P@5仍为0.2，不能以有用/实推=1宣称足量覆盖或整目标质量通过。 |
| R-F17：新证据窗口跨段/跨句拼接身份 | 新片段选择后，`term_match('lithium metal interface', 'lithium. Metal interface')` 和空段形式都 true；直接 canon 分支先于同句分支返回。实际短引接受 `NSCLC\n\nPD-1 resistance`。后续还发现 CRLF 空段/换页/U2029及128断点后的 remainder 可跨段。 | 已统一段落边界、直接与换序匹配同句、40匹配 islice、128段/20k可选扫描上限，保留连续80/180片段和原文offset。`ai-window-boundaries-r6.json` 独立14组通过，初次/r2实际失败保留。r3最后一项探针错把选定窗口外的完整basic短引当正例，产品正确拒绝，原r3保留；r4请求实际可见unknown短引核原文位置，不把窗口外内容冒充模型证据。最新7 scope/7 necessity/5坏回复控制再次维持预期。`ai-long-citation-r2.json` 另核128/160字符的实际可见引文接受、161拒绝、普通单折行保留而90空格跨度拒绝；窗口仍80/180，没有拼接或自动缩写。`ai-interfacial-current.json` 七组进一步核同句interfacial与Li metal/lithium metal肯定控制保留，液态锂、体相、纯正极、跨句和跨段均不授予covered。不声称自然有用率、完整科学语义或内存基准通过。 |
| R-F18：学习图页的原生退出绕过已有未保存保护 | route-page.js 的图草稿/briefDirty有beforeunload防丢提示，却没有PDHPrepareQuit。原生prepare_quit fallback直接complete_quit/app.exit。 | `route-quit-initial.json` 执行原beforeunload handler及原Rust eval脚本：图/brief dirty都preventDefault=true，而fallback仍发complete_quit；clean正常退出。已补页面hook及明确退出决议。`route-quit-r2.json` 执行完整原页面脚本+原native eval，9组确认graph/brief/编辑/未确认AI不自动保存或退出、取消/返回保留、提示后新任务阻退、IPC失败保留可重试、实际主Save不确认AI且保留请求期间晚编辑、clean退出去重。两次路径/DOM fixture不足均留痕后纠正，不计产品失败。未声称锁屏下实际Cmd+Q/WebKit或像素验收。 |
| R-F19：周报使用裸匹配使对象冲突成为“进展” | Reader/主代理发现NSCLC目标中肝癌论文understood仍在周报显示current1/advanced，而route.done为0；修前证据由主代理保存，不冒称本代理独立首次发现。 | `weekly-scope-current.json` 独立实际create/route-save/收藏/understood/weekly入口五库：错误肝癌、他治疗、关键词不扩大固定melanoma目标均0；正确NSCLC及明确多癌种比较保留1；weekly.done均与route_get一致。正例一篇事件1而done0的掌握阈值边界保留。0外发/AI，不代替科学有效性或原生周报验收。 |


| R-F20：取消导出被当作已保存 | `PDHSaveFile` 返回 `{status:'cancelled'}`，设置导出 handler 却检查 `result.cancelled`。独立提取实际 onclick 的三分支 VM 中，取消分支产生“导出已保存”，成功/异常分支正确。 | `settings-export-receipt-initial.json` 保留实际合同反例；VM 的 fake alert 只截取拟展示文字，不证明 WebKit 显示成功。后续已按status分支改为DOM回执；`native-software-independent-current.json`四分支取消/保存/失败/无效收据独立符合，重复保存局部回归通过。新原生包的可见回执仍待主代理重验。 |
| R-F21：原生 JS 对话框不出现，明确放弃等操作被阻断 | 独立源码检查锁定的 wry 0.55.1 WKUIDelegate 没有 runJavaScriptAlert/Confirm/Prompt 委托；界面多处仍调用原生 alert/confirm。主代理实际点击导入放弃后 AX/截图均无确认框、仍停审阅，实际导出成功/取消也没有 alert 回执。 | 源码推断与主代理原生证据相互一致，不能拿普通浏览器 VM 替代平台验收。后续已共享DOM反馈/异步确认并转换调用者await；独立真实脚本VM核可见后scope改变不得审批、队列串行、默认取消/焦点恢复和showModal不可用时false。未默认为同意；全部调用者的原生操作仍未逐一重验。 |
| R-F22：上传前失败收据冷重启丢失 | 主代理原生选择4个PDF，坏PDF未上传；冷重启端口50770→52461后继续恢复同2个去重候选、3个已上传文件、online OFF，却不再显示原坏PDF失败原因。 | 明确属于用户可解释性/恢复信息缺失（建议P2），不是已上传文件丢失或库损坏。本代理核分类，首次操作证据来自主代理。后续本地表保留有界相对路径/原因，快照与UI合并；独立迁移及迟到/过期检查又发现R-F24–26，不能仅以四项初回归通过关闭生命周期。实际冷重启提示仍待主代理重验。 |
| R-F23：Escape 先关下层阅读器，留下助手 | 主代理原生阅读DeepMPCVS→打开论文助手→中文输入→Tab→Escape；AX显示阅读器已关，而助手和相同输入仍留在Library。 | 建议P2：退出层级与焦点不一致。预期先关闭顶部助手、保存草稿、回到阅读器焦点，随后Escape才关阅读器。首次证据来自主代理，本代理未操作原生；后续捕获阶段按translation/selection/assistant/reader层级退出，独立运行真实handler局部回归通过、中文组合输入不关层。afterPaints等待有250ms上限，画布/文本仍要真正完成；新包的渲染与Escape原生复测仍待执行，不能据10页识别就认定可读或PDF损坏。 |


| R-F24：旧上传失败迟到重建新成功文件的错误收据 | 两个独立controller：A坏PDF停在失败登记前，同路径B合法PDF成功保存正确SHA并清错误；A继续后当前合法条目仍被列“不是PDF/未上传”。 | `import-receipt-independent-initial.json`真实失败保留；后续增加per-path attempt与成功tombstone。`import-receipt-independent-r2.json`独立原时序重跑，迟到错误不写，合法条目SHA保持。无外发；不估计自然发生率。 |
| R-F25：新失败活动没有刷新批次寿命 | 旧open batch刚记录新的失败receipt时间，batch.updated_at仍旧；list_batches立即purge_stale删除有当前用户活动的整批。 | initial真实反例保留，新增开始attempt/持久失败_touch。r2重新失败后批次时间为当前、仍列出、receipt保留。原状态/标签未改。 |
| R-F26：旧receipt字段迁移检查与ALTER可竞争 | 两个真实SQLite连接构造LibraryImport，都先读四列PRAGMA，再执行实际ALTER；一成功，另一OperationalError duplicate column name: attempt。 | `import-receipt-migration-race-initial.json`保留；原失败row仍在、integrity ok，不能报为库损坏。后续已用已有跨进程serial锁包住完整schema检查/ALTER/commit；第三阶段独立真实SQLite探针确认第二构造器在锁内等待，两者成功且只一条ALTER，四个旧字段逐字保留。实际ALTER故障不被吞掉，后续同路径可重试，详见`import-receipt-migration-r2.json`。 |
| R-F27：创建页仍走直接退出fallback | 新菜单在prepare_quit中调页面hook，但创建页原无PDHPrepareQuit/beforeunload；人工map/brief/keywords/path/input修改只在内存，原Rust eval直接complete_quit。 | `native-software-independent-current.json`保留源码可达及原eval，无原生冒称。后续creation-quit helper及实际DOM签名adapter已接线；`creation-quit-independent-current.json`组合原Rust eval/当前adapter/helper核中文dirty弹默认Cancel、不退出，Cancel保留字段焦点，提示后新APIbusy阻退，IPC失败恢复按钮/字段，明确重试只complete_quit、不finalize/DELETE/AI。原生菜单仍待主代理重验。 |

PDF 验证当前是有界、不执行内容的封装检查。通过不能外推所有页面可渲染、OCR、密码解锁或全面 PDF 格式验收；对正常增量索引、压缩索引和较大索引的兼容性则不能用这个限制作为错误拒绝的理由。四份前轮真实公开 PDF（最大 17,312,286 字节）当前全部接受，非自然个人库命中率。

## 当前独立确认的导入边界

`import-lifecycle-probes.py` 独立执行了这些路径，使用完整 synthetic PDF，不依赖实施者测试断言：

- I01：A 归档后暂停、B 提交成功，再令 A SQL 失败；B 保持 committed，文件存在且内容 SHA 正确，A 回 review。保留已校验但未引用的复制品是当前明确恢复政策，不等于已有自动垃圾回收。
- I02：矛盾本地 DOI/题名返回 needs_choice，未自动入库或写 PDF。未据此声称所有首页 DOI 误识别已解决或缺题名时能够判断身份。
- I05：一个暂存文件丢失时整批未入 project_library，失败条目可见；补传后 pending，再 resolve/commit，两个 PDF 全入库。恢复不依赖覆盖原始文件。
- I06：上传流结束后放弃批次，再登记迟到上传被拒；discarded、0 条目、无暂存目录。没有把旧路径/大小/mtime 当内容身份。

批次互斥、终态条件、数据库读快照及显式重传的整体策略已核源码；其余并发点与完整旧回归仍须最终同源检查。调度门说明状态交错可达，不估计自然发生率。

## 阅读、导出与发现的审查边界

已读 reader_context/local_snapshot、QA 会话与 SHA 绑定、Tauri 两条 IPC 的精确 origin/窗口校验、原生保存/退出及组织阅读路由。原生能力仅注册 save_export/complete_quit，运行期限定随机 loopback origin 和 main，并由命令再次核对实际窗口 URL；没有新增广泛 shell/任意目录权限。实际 NSSavePanel、写文件收据与快速退出仍由主代理原生包验证，本代理没有代为标通过。

SQLite 导出使用一致性 backup，转 DELETE journal 只作用于临时副本；所有表及行数包含在快照中。PDF/暂存 bytes 与凭据文件明示不在结构化快照里；恢复 helper 只写新目录，不跟随旧 PDF 路径，也没有新增用户恢复入口。这个范围不能被描述为所有 PDF 已可完整迁移。独立故障、未来 BLOB 表和权限检查见 R-F07；完整联合记录与原生保存仍待最终核对。

发现分组的 `work_type` 添加前一致性备份、类型保存、日期/来源二次过滤、明确科学词别名、库存与兴趣分离、零值设置及衰减时钟已核实际实现和调用者。独立 `discovery-boundaries-r2.json` 9 组进一步核对：真正 SQLite backup 首页中断保留原 schema/题名/BLOB、清本次 partial、既存备份不覆盖、重试新备份；忽略过滤的上游返回仍拒 conference-abstract/未来文；三个细方向各两新库，以真实 create_project 入口显式选种子后验证数量、近 7 日、种子不重推、库存/兴趣、有用/撤销、来源全关零请求；另外核对明确科学别名。两副本的目标标签未进入这项软件边界判断，**不是六用户目标的推荐收益测试**。

独立首轮探针和 B07 实施回归原先都只设置 relation_kind，漏配 seed_keys，因而 profile 无主动种子，单篇排序可能碰巧通过。已保留失败日志并改走真实创建入口；实施者也补配并先断言正种子存在。这个前提错误是测试覆盖缺口，不计产品推荐缺陷。发现分组的通过未包含自然来源全集、医学专家审阅或真人满意度；归一词典有明确边界，不能称通用语义理解。最终冻结源码和联合记录仍待验收。

学习修复另由 `learning-match-probes.py` 调用实际 matcher/choose 和 App._route_inputs 验证：白名单 graph 修饰词正常，任意 metacognitive gap 和句号分隔拒绝；psychological latent states、没有视觉语境的 language latent space 不进入视觉单元；视觉编码别名有原文字面引文。双匹配论文可供未掌握 primary 的 secondary 前沿阅读，但显式 understood 只记 primary；primary 已满足时不能用 secondary 填常规学习槽。四线程 300 段归一输入后缓存为 128 条、计入 1,925,632 bytes，小于 4 MiB，上限以两串及条目开销计，超长来源不驻留。初次探针漏收藏导致 understood 被正确拒绝，已保留 fixture 失败并补真实收藏入口，非产品失败。这些软件合同与缓存边界不能证明六目标推荐收益或学习匹配全域质量。

用途保存由 `exploration-transaction-r4.json` 四组独立调用实际 App 验证：五候选只发三路径/一个具原文字面hit的侧枝，无用途protein论文不填第五槽，API说明少推缘由；关闭App再新建App实例后卡片及持久用途收据一致（仅后端冷态，非原生重启）。实际用途settings INSERT时故障使batches、exposures和用途settings均0、无残事务。未知key、40k证据、NaN在写前拒，原无route_evidence的默认调用兼容且不补造历史理由。第一轮SQL proxy漏Python context-manager、第二轮fixture未设必须的语言政策，均在故障门前停止，原记录保留；它们不是产品事务失败。侧枝quote来自当前本地题名+摘要的检索串，不能冒充AI的单字段严格短引；来源身份正确不单独证明侧枝有个人价值。

## 历史核账与中间复核状态

以下保留各轮当时的状态，不作为后续余额恢复及原生验收的最新状态。当时仍在进行。AI 冻结后的实际调用与账本、新探索用途/事务保存和回放、全量回归、实际桌面包、构建指纹、逐项矩阵和变更登记均须收尾后再核，不提前写独立 passed；旧 E-LIBRARY-IMPORT、个人价值/标签有效性及发布门槛不自行关闭。锁屏导致主代理原生操作仍受阻，不能以本代理函数 VM 代替原生通过。

只读逐请求账本交叉核验已完成一轮，见 `ai-receipt-crosscheck-current.json`：2158原始行按请求ID取最终项为1079次reconciled、1,059,026 token、$0.357643410；五轮327/360/162/212/18发送回执与有效账本的operation/model/input/output/cache_hit/total/usd多重集精确一致，逐项Decimal峰值单价重算也相等。R7为108例91格式通过/17拒绝，R8建图18/18格式通过。未知计费为0，拒绝后的已付回包没有从金额中扣掉。这是Gateway估值核对，不是供应商发票。随后本地源及新证据窗口仍变动，当前最终指纹不能提前当同源收尾通过，新增真实轮次也须重新核账。

新增有界窗口后R9增长18案例/117实际请求，16格式完成、2拒绝；R10修改18/18完成、18实际请求。`ai-receipt-crosscheck-r10.json` 重新核七轮全部回执，1214次最终reconciled、1,252,721 token、$0.405537246，回执多重集与账本、逐项价格仍精确一致。第一次只纳入至R9时发现18项额外修改账单，实际来自已完成R10；已保留差异记录并动态纳入全部完成轮次，不误称漏账或未知计费。最新源指纹仍待更新，科学审查不能由这些格式及计费数值代替。

最终六目标表格以 `replay-purpose-final/comparison.json` 为准，先前 `replay-precision` 保留为中间版本。普通推荐连续十批的有用/实推为计算机入门44/50、研究38/50，材料38/50、34/50，医学44/50、37/50；学习推荐则为22/40、17/50、40/50、21/50、33/50、28/50，未知不计有用，重复分别11、21、0、14、13、12。全部当前–冻结差值区间仍包含0，材料入门普通推荐不及关键词，裸assign仍有大量假阴性。计算机最后60已从旧中间版本实推2/有用1改为最终实推1/有用1，固定P@5=0.2；旧矛盾已更正，没有从历史证据删除。不能把软件修正、少推高精度或四项确定FP减少描述为反馈收益、完整学习匹配质量或整产品发布通过。

独立 `learning-replay-source-r3.json` 最新重算：29个原始输入/旧结果SHA、45份冻结模块SHA及11个App实际排序入口AST全匹配；用固定原persona和当前make/check重新核1830条公开候选/种子scope收据，0差。它们是确定性一致性收据，不能称1830条科学有效性盲评。当前相对冻结源另有service首增长请求新增fixed_scope、growthproposal顶层生成提示及可用verdict、ai_evidence最后界面语法修正、profile_insights周报scope接线四模块漂移；11排序入口AST仍相同；R18新增可用verdicts后growthproposal只有messages函数AST漂移，早先仅提示常量不同的核验作为历史保留，不能宣称所有当前模块或函数相同。最终回放未运行模型、无生成方向，仅核上述冻结本地推荐路径。已曝光的最后60是回归集，不能升级为新盲留出。

最新直接运行两个私有窗口探针时，因探针sys.path漏工作树而报ModuleNotFoundError；没有执行产品调用或产出新JSON。已留 `ai-window-r6-first-run-import-error.txt`、仅补私有runner后复跑，非产品故障。

最终 `ai-receipt-crosscheck-final-r18.json` 独立十轮核验1467次请求：1466已核计费、1明确HTTP402并零token/$0释放，合1,655,997 token/$0.491924286，无reserved/unknown。所有paid回执多重集与最终ID账本精确一致，逐项Decimal价格重算一致；402零占用拒绝单独核对，不要求它伪装reconciled。最新8项AI源码及预算SHA全为当前。含前轮280/338321/$0.172496328的算术总为1747请求、1,994,318 token/$0.664420614；不替代供应商发票。R18仅7完整parser通过、1在15/20论文后HTTP402中止、10未执行，保留R16的18例12格式通过/6拒绝，未覆盖失败或绕过供应商拒绝。第一次终态预检时新R18还在途，正确拒绝；后来source receipt从flat改包装字段使私有checker报错，均保留并纠正，非产品漏账。科学审查和最终构建仍须分别收尾。

## AI 协议只读核对

只读核对 [DeepSeek Vision 官方文档](https://api-docs.deepseek.com/guides/vision/)（2026-10-08）。官方当前支持 chat completions 用户消息中的 base64 图片，并规定图片与请求大小边界；应用只发送一张有界图片，文本输入在网关预检。协议兼容阅读不能代替实际模型看图验收、金额核对或论文证据判断，也不代表所有大尺寸图片都能成功。两个其他官方接口页面访问超时没有当产品失败或协议核验通过。


## 本阶段封存结论（2026-10-08，原生修复继续中）

余额由用户恢复后，R19确实完成了十个此前未执行案例及原部分材料案例剩余5篇；早先R18中断不是当前仍有10例未执行。`ai-receipt-crosscheck-final-r19.json` 逐请求独立核十二轮：**1539实际发送=1538 reconciled+1旧HTTP402 released，1,771,317 token、$0.515083590**；0未知、0在途。paid回执的operation/model/input/output/cache-hit/total/USD多重集与最终请求ID账本精确相等，Decimal单价重算相同，8项AI源码及budget SHA匹配。包含前轮280/338321/$0.172496328的算术合计为1819请求、2,109,638 token、$0.687579918；仍是Gateway估值核对，不是供应商发票。R19新70请求与resume新2请求都纳入，未遗漏失败后的已付费用。

`ai-resume-preservation-current.json` 只读SQLite核对原R18仍15条、恢复副本20条，原15条已判断字段逐字段相同、项目状态键相同，原SQLite SHA仍与恢复起点一致。最终machine receipt已经将材料研究该例正确列为8调用（原6+恢复2）、历史failed/原原因单列，当前reason=null。18个最终增长案例均完成格式合同，不能因此把360篇内容全部标为有用。新冷态wire/normalized一致性收据由实施者提供，本阶段未独立重新计算R19全部冷态记录，不扩大独立结论。

另以独立上下文、仅R18盲包委派科学审查B，未传其他评审、排名、标签或本代理结论。其完整记录见[独立内容盲审B](2026-10-08-fixes-blind-b.md)：167实际审查项=155论文判断+12方向提案，19内容未知，另5无AI输出不评；记录6条具体推断错误。包未覆盖完整医学，不能替代新R19全18案例盲审，也没有汇总未读取的A判断或把分歧强行计为有用。最终R19包SHA为`cdc53d964fd4d7f89bec96bac44198951c046cf783d88e1bb4264da95cfaff68`，其完整独立科学盲评仍待另一阶段。代理标签与人类反馈/个人价值门槛保持区别。

`build-fixture-current.json` 独立比较303文件清单：全套r6指纹`09eab02855ddc0091f1b04aed02e2db0622feb74c679cddf1d980c5cd4b3e74e`与五步实际构建/签名/包route全exit0的`ce2fc275403e8ebde98a7e57d5dd723d37be3399a5ffc805c73194e47108b152`只差`scripts/verify_packaged_route.py`。已只读审实际脚本diff：HOME保留、DATA隔离/AI_DISABLED/明确缺key路径及proxy；探索正例有公开query/source收据，增长正例有用户intro的肯定必要短引，原3+1+1/重启/撤销/重开goal/过期断言保留，没有通过放宽负例绕过新合同。直接record_pdf假PDF仅作内部版本失效fixture，明确不是入口验证。首次包route旧fixture StopIteration仍留档。产品/提示/测试在这两清单相同，不把ce2fc冒写为09ea完全同一全源；脚本变更后的实际包验收已经重跑。全套1978 Python/368 Node通过来自主代理实际检查，本代理未自行运行全套或构建。

Mac后续已解锁，早先锁屏blocked是历史事实。主代理实际NSSavePanel取消/保存成功，12.2MB JSON含32表并restore验证；原生暗色/英文设置及导入批次冷恢复也有实际观察。上述原生能力不能关闭R-F20–23：取消回执合同错误、JS对话框不出现、上传前错误丢失和Escape层级均仍未修复；英文动态过滤/坏PDF错误还出现中文，阅读渲染现象仍待调查。源继续因这些问题修改后，需要新的最终回归/构建/原生复测及本工作单元记录复核。

本阶段完成的是有界独立审阅与反例留档，不是全部B/I已修完、功能最终验收或发布批准。未代签业主字段，未关闭E-LIBRARY-IMPORT、标签有效性、人类个人价值及其他发布门槛；主代理最终HTML/新变更登记/结束保护证据尚未作为终稿交付，本阶段也未审查它们。下一轮应以新的冻结源为起点，只重跑受原生修复影响的合同及已有反例，再审最终记录；不能覆盖本阶段失败和中间质量结果。


## 第二阶段：原生修复后的有界软件复核

继续受同一只读边界约束。本次只读审 shared DOM dialogs/调用者、settings可见回执、reader Escape/paint/render、创建页退出、Rust菜单路由及新增本地失败表的实际代码；没有操作原生、构建、付费请求或全量测试。AI科学守卫正在另一分组修改，本阶段不根据其未盲审内容结论评价真实论文。

`native-software-independent-current.json`真实shared helper与实际settings.onclick的隔离VM确认：显示后的目标已改变时即使点击审批也false；第一个取消、第二个必须单独审批；字面script字符串仅textContent；showModal异常不留active且false。settings取消、保存、写失败、未知回执均有持久DOM结果、按钮恢复，未知回执不报保存成功。它们不是WebKit像素、键盘候选输入法或真实系统对话框验收。

新增receipt表最初采用四字段，独立两个时间交错失败已由R-F24/25记录；其补修为开始上传先记录attempt、注册和失败写入均核当前attempt，成功留下空message tombstone，读取只返非空message。路径经原clean_path限制，每段200字符、最多40段；message最多512字符，内部token不出现在失败API，不参与兴趣/模型输入。总行数目标上限2×MAX_FILES，实际错误最多MAX_FILES。放弃已带receipt的批次后错误仍保留，记录为保留策略观察；现有文案只承诺暂存文件删除，未有足够明确策略据此直接判隐私泄漏。缺路径/已关闭批次等无法有效登记的请求、客户端预先跳过的超大/空文件不应被报告为已具永久receipt。新增字段迁移出现R-F26并发缺口，不能通过新数据库绿测试掩盖已有四列schema场景。

独立运行局部7 Python receipt回归和37 Node dialog/reader/settings/route/note/creation退出回归均通过，详见`native-software-focused-current.json`及两份stdout日志。11个所选产品源文件运行前后SHA一致；这是有界模块复核，不是全工作树冻结证明，也不替代随后全量及包检查。独立时序r2另外确认R-F24/25实际问题修复；构造迁移中旧batch行保留、integrity ok。当时两个旧schema构造器竞争仍失败，相应门槛当时不能记passed；第三阶段补修和独立复验结果见下节，原失败不覆盖。

Rust当前仅新增菜单调度，没有扩大两条IPC权限：保留Menu::default中的其他菜单，验证并替换macOS原Quit为自定义CmdQ事件；save_export/complete_quit仍核main窗口与当次随机loopback精确origin，完整退出须由页面明确ack。原muda0.19.3 Quit调用terminate:，Tao0.35.3 applicationWillTerminate调用AppState::exit/LoopDestroyed；新菜单避免原CmdQ直终止路径，cargo check不能替代实际菜单行为。Dock Quit/OS普通terminate不一定经过自定义菜单，仍需原生验证或明确保护边界，尚未作为本代理实际缺陷复现。强制终止不能声称被页面guard阻止。创建页原缺hook已补软件合同，但新包CmdQ、菜单Quit、窗口关闭/取消和数据恢复仍由主代理实测。

正式资料的旧baseline7文件/6表变化已有用户直接确认来自正常正式使用；没有回滚或隐藏差异。只读读取新增owner-use checkpoint元数据，并对其199稳定文件流式SHA/size核验，2026-10-08 02:30:17 UTC全部相同，见`owner-checkpoint-files-current.json`。没有提取/输出文件内容或凭据，未在正式库打开连接或写文件；业务表/integrity及副本78引用的结果仍来自主代理，不冒称本探针独立重查。初次把checkpoint相对key误当cwd路径的运行器错误已保留并纠正，不报为198个真实文件丢失。新checkpoint只增加后续测试归因起点，不重写旧baseline。

本阶段范围再次封存（历史）：已有软件合同改善有实际独立证据，当时R-F26字段迁移仍需补修复测；第三阶段已经独立复验。原生退出/对话框/冷错误恢复/渲染仍待新包验收；最终科学双盲分歧、全量构建/记录/HTML也未在这阶段审为终稿。不得将37+7局部绿、元数据保护或已修复软件反例当作全部流程/个人价值/发布通过。

## 第三阶段：迁移串行与新科学输入合同的窄复核

本节是后续补修的有界独立证据，第二阶段失败及当时结论保留。没有产品改动、付费请求、原生操作、桌面构建或全量测试。后续仅编译了提取原policy的stdlib微探针，不链接或启动桌面应用。

R-F26 已完成独立修后复验。`import-receipt-migration-r2.json` 冻结首个真实旧四字段PRAGMA视图，第二个独立SQLite连接构造器的真实线程栈显示在 `operation_lock.serial` 等待，尚未读PRAGMA；放行后两者成功，只有首个连接执行ALTER，原四字段记录准确保留、integrity ok。另真实注入ALTER失败：OperationalError透传、attempt列仍缺失、旧行保留；下一次构造器成功重试，没有锁泄漏。源码SHA锁定为 `c3638cefefc29a9931f239ec630208f77d541619f400dc7fdd3e077fa2cb9554`。这验证具体迁移竞争和故障恢复，不冒称所有并发/迁移路径已验证。

新公开源窗口保持完整Map和每请求8000/1000上限，最多三篇同类标题/摘要；根据完整encoded envelope的剩余空间可选择连续标题200/摘要480字符。`scientific-wire-independent-current.json` 12项独立实际messages/envelope/source_evidence控制符合：1篇摘要478字符、bound5538；3篇bound6840；Map不裁、临时别名和私有canary隔离；准确原始引文offset、未发原文不能作证、伪造context/错alias/跨段拒绝、普通单折行保留、超字段与超大完整Map拒绝。registry组件算术和仍为8000。输入窗口变大可能增加实际成本，不能说费用完全不变；这些是预检合同，不是新付费运行或发票。初次探针误用registry顶层键导致cap=null，已保留 `scientific-wire-independent-first-registry-schema-error.json` 并修正探针，不计产品错误。

新增 R-F28：有限关系守卫最初对三条明确否定仍标covered——“Action-conditioned video prediction is not used by this model.”、“No experiments or planning evaluations were performed.”、“The lithium metal interface used a sulfide coating; a sulfide electrolyte was not used.”。实际messages→sent_papers→validate_result的13项初始记录中只有这三项与预期不符；它们是合成教学反例，不冒称自然论文错误率。实施者补修后，`scientific-relations-independent-current.json` 原13项全部符合：明确否定unclear，未识别电解质保持missing_scope_evidence，明确排除保持explicit_scope_conflict；动作输入预测、规划实验、明确硫化物电解质和明确NSCLC/PD-1的KRAS/铂比较肯定控制保留。正否控制均固定任务、原引文和预期，未事后移动目标。任务关系守卫仍是有限字面规则，不能代替科学盲评、人类标签或个人价值测量；当前新轮AI实发、科学内容与最终包仍待下一阶段。

## 第三阶段：原生系统退出 callback 的独立源码与异常复核

只读检查 pinned Tao0.35.3、Tauri2.11.5、runtime-wry2.11.4、objc2 0.6.4及AppKit bindings0.3.2实际源码。Tao的现有delegate由EventLoop的IdRef保留，具有auxState ivar及launch/openURL/reopen/willTerminate回调。新guard严格限定现有类，instance_method同时检查继承链，class_addMethod只增加缺失selector；没有替换类、对象、ivars或其他callback。获取delegate为Retained，弱setDelegate先清再登记期间仍有局部强引用与Tao的原保留。安装要求MainThreadMarker，callback和CString为进程寿命；返回类型由AppKit repr-transparent NSUInteger及Encode导出，receiver/selector/argument类型与`@:@`一致。未知类/已有method/注册失败拒绝setup继续，局部PythonProcess错误退出仍走Drop清理。没有新增IPC、外发或预算。

未确认时同步Cancel，没有TerminateLater挂起状态；只有原精确origin授权的complete_quit设置ack后才Now。正常确认由app.exit→RequestExit→ExitRequested→ControlFlow Exit→LoopDestroyed→RunEvent Exit→PythonProcess.stop；Tauri proxy派发失败的framework cleanup/process::exit是另一条路径，不能据源码称也交付自定义Exit callback。源码审查未发现该委托接线另一个确定错误，但不能据此通过AppKit缓存刷新、真实Dock/System/CmdQ/窗口关闭、对话框像素或子进程实际终止验收，强制结束也不属于页面确认保护。

新增 R-F29：原内catch结果 `.is_err()` 与外catch `.unwrap_or()` 在catch外释放panic payload；payload的Drop自身再panic可以再次展开。`native-panic-payload-initial.json` 提取实际policy和相同outer模式，只替换AppKit枚举为stdlib替身，独立微探针记录escaped=true、两次payload Drop。首次替身use alias写错编译失败已另留存并纠正，不计产品错误。这是人工极端异常健壮性反例，未声称实际用户崩溃。实施者改为内外Err都forget payload并Cancel；外最终边界没有后续日志/destructor。`native-panic-payload-current.json` 提取修后真实两个函数，五个独立控制符合：inner/outer/combined异常均Cancel、不逃逸；ack为Now且不派发，失败后可重试且只派发一次，payload Drop为0。代价是在这一异常路径保留payload分配，不能说无任何资源代价；不将该控制扩大成所有Rust/ObjC异常或强杀都能恢复。

第三阶段有界软件证据已完成，R-F26/28/29均有具体失败与独立修后证据。当前新AI实发、内容盲评、原生新包、最终全量构建、保护核对、工作单元登记和HTML仍由主代理继续，不能用本节控制绿代替整产品发布通过。

## 后续窄审：测试包隔离 fixture 合同

独立只读审 `tests/test_packaged_route_isolation.py` 与实际 `launch` diff。原Gateway加载合成继承key的肯定控制、捕获启动env后无key的控制、私有DATA与代理断言仍保留；新增合成parent HOME且保持、KEY_FILE替换为不存在路径并不同于继承路径的检查，符合此前已经修改的verifier合同。独立运行单项Python回归1/1通过；另 `packaged-isolation-independent-current.json` 用真实launch捕获（Popen前停止、没有启动包）及仅临时目录的Gateway执行13项控制，全符合：四个代理闭端口、NO_PROXY仅loopback、AI_DISABLED、HOME保持、环境key清空、空隔离root/data无key等。没有改Gateway、原产品或测试，没有读正式key、出站或付费调用。

特别用合成data/root key验证：显式不存在的KEY_FILE不会停止 `_key_candidates` 后续候选，data及root的合法key仍可加载；隔离成立还依赖私有包/root/data没有key及AI_DISABLED，而非此env值把所有fallback关闭。建议将现有注释/docstring中宽泛“prevents host key fallback”改成仅覆盖继承KEY_FILE的准确表述，不据此改Gateway行为。完整r7的旧Python/Node失败由主代理保留，本单项通过不将那轮全量升级为通过。

本附录不重新批准第三阶段旧源：13关系/12wire的结果仅对应私有收据记录的当时源码SHA。主代理已通知R22真实运行出现受保护拒绝并继续修论文分组合同；本代理未根据这些未盲审内容判断科学有效性，也没有通过其随后修改的新源、实际实发或最终发布。新轮科学合同、实际包和最终记录仍需独立收尾。

## 后续窄审：R23 学习任务去重与复数论文合同

只读审实际task_relations、growthproposal validator与真实wire；没有读取其他盲评标签、排名或真实输出来建立预期。`task-duplicate-independent-initial.json` 是14项固定合成阴阳控制：12符合、2发现限定条件被错误去重。40节点完整Map保留全部临时别名与目标，private canary未发，完整Gateway bound6900≤8000；SYSTEM显式使用papers数组，singular paper拒unexpected_fields，坏c99 parent/needs仍拒、退役能力不合并、两篇同能力可以合组。每项图对象不变，covered不生成硬边；没有授予掌握或静默改Map。

新增 R-F30（初次失败，后续独立修后复验已通过）：第一，proposal的普通动作预测名称、intro及实际sent引文都明确“under contact constraints”，qualifiers只认contact-aware等后缀，漏名词条件，把应保留的可选条件任务改covered。第二，现有节点intro明确Contact-aware/contact constraints，普通无contact的动作输入材料也被改covered；原因是单向proposed−existing集合判断，把泛能力错误吸入受限定能力。第三，补充肯定控制只将相同proposal intro改为“Predict future video conditioned on control inputs.”，却返回new_branch；把“video conditioned”误当新条件，漏去重同一动作输入预测能力。`task-duplicate-independent-r2.json` 保留15项及这3项差异，正否预期没有修改。最初第一条件控制未在引用中写contact，随后已用实际sent含contact的引文复验同一错误；不足的首fixture另保留 `task-duplicate-independent-first-contact-fixture-insufficient.json`，不拿它证明原文支持接触条件。

补修过程中，`task-duplicate-independent-r4.json` 又保留一条真实sent控制：intro与原引文都写“conditioned on actions and contact forces”，却把额外接触力输入合并成普通动作输入预测；此前r3该控制引用未包含contact forces，已明确修正fixture，不以不足引用证明来源支持。最终输入条件提取、名词条件及双向等价补修后，`task-duplicate-independent-r6.json`（R26）及`task-duplicate-independent-r7-r28.json`（R28）的同15项固定阴阳控制全符合：普通动作输入预测及同义重述covered、contact constraints/contact forces/受限现有能力保留new_branch，错parent/needs、singular字段仍拒，缺失/假引用unclear；原图对象均未变，covered无新增边。旧失败记录没有删除或改写。

R28当前源另重跑原13关系及12wire控制，见`scientific-relations-r28-recheck.json`、`scientific-wire-r28-recheck.json`：肯定控制保留、明确否定及错癌种/错治疗拒绝；40节点完整Map与targets c1保留，私有canary未发，完整bound6951≤8000；1篇摘要478字符/bound5551、3篇bound6853。准确原文offset、未发原文/假上下文/错别名/跨空段拒绝、正常单折行保留；标题201/摘要481及超大Map拒绝，registry仍8000/1000。冻结源SHA为task_relations `71a8a01a999ab0333d88ffa9e0d94dddeb47e8c24d33e18390ba1258be7a0d04`、growthproposal `b913e9e0d255c436583f86c95b4606bf0ebfd5ba98dd0c42d86ba5be634b8d57`；service、ai_evidence、budget与私有收据一致。

这些是限定能力等价、集合方向和有界输入的软件控制，不能报告自然科学误差率、用户满意度或最新真实AI质量通过。R23/R24及后续真实调用失败、已付费用和模型缺引用仍应独立保留；本代理没有读取其他评审/排名/真实结果来移动这些预期，没有改产品、tests或预算，0模型/出站。

## 后续窄审：英文系统文字与用户材料保护

新增 R-F31（初次失败，后续窄软件修后复验已通过）：`english-system-independent-initial.json` 用实际project render、route/import/creation helper和实际i18n MutationObserver在隔离VM中复现四类系统中文残留，所读7源文件运行前后SHA相同。项目页的“创建方式”可译，但值“快速创建”和空关键词“（还没有）”被统一data-no-i18n保护；前置chip把用户概念名和系统title同放受保护节点，title“语料支持这个先后顺序”仍中文，虽然字典已有准确英文。导入failed的默认“匹配失败”同样被跳过；真实后端身份矛盾警告和RIS缺标题/缺ER动态错误还缺字典。route简介和已存guidance的scope_notice是软件生成的系统说明，却与原文输入同样保护；保存中文draft后切英文，旧说明仍中文。后端新请求可按英文生成notice，不解决旧draft显示；该问题不涉及将AI原回答改写为英文。

复现明确区分两类材料：项目名、非空关键词、概念名、论文题名/摘要、用户笔记/输入片段与真实引用保持原文；固定模式值、空态、前置判断tooltip、已知软件错误及软件scope说明应按界面语言展示。建议只在已知系统字段显示处翻译，补动态错误模板；不移除整块原文保护，也不把任意模型reason都当系统文本翻译。创建页item.error另有相同保护路径，已交给实施者核对。本次没有操作浏览器像素或原生输入法，也没有读取用户私有材料或调用模型。

实际route countsText/summaryText及weekly kpis生成的8个数字复合统计全部译为英文，没有在这些控制中发现数字统计失败。静态提取器忽略data-no-i18n块，0missing不能覆盖上述DOM路径；本次也不能据8项控制声称全部统计、所有页面或完整英文体验通过。

修后`english-system-independent-fixed-r3.json`重复原四路径：固定模式/空态、前置tooltip、默认匹配失败/保存的身份警告、两处旧中文scope_notice均显示英文，RIS两种动态系统错误也译出，用户概念名仍原文。新PDHi18n.system只用于typed软件错误；命名slot先译固定frame，再原样插入bibkey/snippet，不能将任意标题、笔记或模型prose传入格式器。本代理另用`english-raw-frames-independent-r2.json`实际organization renderList/projectTags/detailCategories和真实observer复验7项：项目“有用/收藏”、题名“种子”、分类“收藏”碰巧等于UI字典key时，名称、selector aria与tooltip的原始值均保留；系统frame按英文呈现。parser raw片段包括`<title>`和`{reason}`仍原样，未被二次模板替换；未知diagnostic保持原始文字，不伪称全都已翻译。程序调用者仍esc后入HTML，没有因formatter改为执行markup。

私有扩展首轮transport漏提供实际生成的data-select-all checkbox，renderBulk报null；已保留`english-raw-frames-first-runner-error.txt`及当轮四路径记录，只补DOM transport后复跑，不计产品缺陷。实施者新增系统render回归由本代理直接运行最新15/15通过，见`english-system-focused-independent-r2.json`：画像全部明确反馈/空态/冻结、英→中重绘、library用户命名及undo、动态题录/seed错误、旧scope说明均包括；真实校验失败回执显示未保存为导入条目，不再误称文件从未传输。所选9份产品/测试SHA运行前后全同。英文源随后由实施者明确冻结，本节只通过这些软件显示与原文保护路径；原生语言/输入法、所有未知provider错误、全产品英文和最新AI科学质量仍须分别验收。

## 后续窄审：问题草稿归属与后台 PDF 绘制等待

新增 R-F32（初始P2建议，后续软件修后复验已通过）：主代理实际原生切换DeepMPC至G-DOOM后观察到标题/项目和附件状态已更新，旧未发送问题却仍留在框中。本代理不操作原生，用`reader-draft-context-independent-r2.json`提取实际PDHSetContext、loadReadingSession、sendInput、ask，在隔离VM分别验证换论文和同论文换项目：旧中文草稿未保存/切换或标记迁移，点击发送会直接构造新key/project/session_id的请求。API是本地stub，没有发往服务器或模型，不能称已经发生真实跨论文回答或泄漏。首轮同论文换项目fixture还把展示title改成另一论文，保留原记录，r2只纠正该展示title后同一问题仍复现。

既有“Escape关闭助手保留中文草稿”测试覆盖同上下文关闭，不能证明切换对象后的归属正确；PRODUCT的问答身份绑定也没有明确逐论文草稿存储方案。因此本项区分确定的静默跨上下文携带行为与建议的产品合同：可以按论文/项目保留草稿，切回恢复；或者明确告知原草稿来自何处，再由用户决定迁移。不能直接清空而丢掉原问题，也不能用正确清引用、附件和会话的测试掩盖输入框归属。

主代理补为窗口内Map，JSON二元组键区分论文/项目，切换前保存/删除原上下文草稿、切后恢复目标草稿，同上下文不变。独立首轮`reader-draft-scope-independent-current.json`的11项中10项符合；另发现原sendInput先清框、ask才检查未选论文，孤立草稿发送被阻止却丢失。该旧缺口已保持输入并先提示；最终`reader-draft-scope-independent-fixed.json`同11项全部符合：原A/B精确保留与恢复、两项目隔离、手动及发送后清空不复活、JSON键无碰撞、同上下文及异步history不替换输入、无论文草稿独立且发送不丢。只有当前草稿进入本地stub QA payload，未携带其他草稿。index源码SHA `8cb150bd9f4a9ac1936fafc8ade08c6b2ce3ae13910784e543f5d2f9a421d472`运行前后相同。

Map仅在本窗口模块内存，没有写DB、模型输入或history；冷重启不持久、没有总entry/字节上限，不宣称新增持久保存或有界缓存。当前选择保留输入而不静默淘汰用户草稿，这个资源观察不单独计已发生缺陷。软件控制不替代主代理修后原生跨论文与退出验收。

`reader-background-schedule-independent.json`提取实际pinned PDF.js 4.6.82的InternalRenderTask及应用renderPage/afterPaints；只将canvas/text APIs替换为合成对象。暂停requestAnimationFrame时，presentation fallback已结束，但canvas/text仍未执行、renderPage promise尚未完成；恢复真实scheduler登记的帧后两者完成并返回true。源码中await renderPage位于afterPaints之前，因此250ms等待上限只覆盖展示交换，不覆盖PDF.js内部显示渲染帧；页面数已读到也不等于页面像素已完成。

这项解释一个可达后台等待边界，不直接计正常前台阅读缺陷。主代理冷启动后台时AX/旧Library截图不一致、Raise未刷新而native windowZoom后恢复；随后前台G-DOOM立即绘制。上述结果可能同时涉及后台调度、WebKit绘制刷新或控制工具可见性；本代理没有原生像素、线程及事件证据，不能断言唯一原因或用该合成探针关闭原生验收。实际前台/重开/后台回前台需分别记录真正页面绘制，无法重现的部分保留未知。

此轮有界源码/函数复核再次结束，已独立核旧科学软件合同R-F30、英文系统显示R-F31和草稿归属R-F32对应修复。没有重跑全量、构建、原生或付费轮，也没有根据其他盲评标签授予科学质量通过；后续应以新的冻结源继续新片段合同、最终工作单元记录与实际包复核。

## 实施前设计窄审：片段编号合同

已只读审`2026-10-08-fixes-snippet-contract.md`，尚未据设计定义通过实施/运行/科学门槛。沿用3篇公开题摘、200/480字符、160字符连续短引、完整Map及8000/1000的范围可继续；已向实施者指出四个需实际验证的边界：现有source_evidence强制非空object，故空值展开需只在已验证本次冻结编号/原文offset的新路径使用，不能让任意旧JSON或伪造声明通行；多块实际sent文本独立验证与展示，不能拼接后补造引用或visible_scope；合同和冻结编号表须与实际请求/输入快照、迟到校验及缓存/重放指纹绑定，不能回复后重新选择；ID有效仍须经过原对象/治疗/任务关系/证据类型/必要性保护，信息缺失保持unclear。

前置R28的15/13/12控制与失败先行记录是旧合同基线，不自动移交为新编号合同通过。新代码、新raw响应及账本仍待另一次独立检验；不以预计减少抄写错误当实测稳定性或费用收益。

实施者在编辑代码前改为保留每篇原有单段连续sent题名/摘要，仅在该实际字段内部提供若干不可变snippet选项。该修订解决多块拼接来源的问题：没有新增distinct原文，scope只用真实连续字段；重复选项及编号/offset开销仍计入整协议预算。已要求双重核对选项与冻结字段/原文偏移、相同文字重复位置、当前paper/请求身份，以及周边实际sent否定/基础实验对类型宣称的否决。本节仍只审修订设计，不作为随后实现或付费运行通过。

## 后续窄审：实际片段编号合同与临床证据否决

2026-10-08 06:25 UTC继续同一只读边界，检查实际snippet_contract、messages/validator、service冻结与提交、Gateway序列化、注册预算及开发capture工具。没有使用模型、原生窗口、构建或正式资料；没有读取其他科学盲评结论来移动合成控制预期。以下通过只限软件合同，不等于本次真实论文AI质量、个人价值或发布通过。

新增 R-F33（临床类型与获益宣称的否决范围，初始失败、后续窄软件修后已通过）：实际messages生成的两个合法编号覆盖同一146字符题摘。“NSCLC PD-1 resistance was assessed in a randomized clinical trial.”后面明确写“All reported findings are simulations in mice; no human patients were enrolled.”。选择第一句的真实编号、type=trial，并写Clinical benefit improves survival，原实现仍归covered并保存trial；周边基础实验声明已实际发送，不能因它不在所选短引中就忽略。补修类型守卫后，又独立复现“improved survival was not observed”及“improved survival was absent”仍允许上述获益理由；前置否定模式没有覆盖结果短语后面的否定。第三个补修中，“All reported findings are simulations in mice, informed by prior clinical studies.”又因句中prior被整句当成背景豁免，仍允许trial。后者完整冻结探针`snippet-reference-independent-r2-global-bypass.json`保留42项中的1个失败及相同的前后源码SHA。

前三次直接工具输出的真实输入、选择短引与covered结果已转存`snippet-clinical-initial-tooltrace.json`；它明确说明是本会话工具输出的事后落盘，前三次未记录各自精确旧源码SHA，不能把后来源码SHA冒充初始版本证明。旧42项失败文件与初始15/13成功文件均保留，没有覆盖。实施者最终将当前研究/全部结果的明确声明优先于后续背景词，背景动物比较按局部子句区分；临床获益还需要所选真实trial短引有肯定获益关系，并拒绝否定或假设表达。它仍是有限规则，不是对任意科学语言的正确性保证。

`snippet-reference-independent-r3.json`的44项固定控制全部符合：实际生成的编号、错论文/未知/重复/额外字段、偏移和原文篡改、跨空段、重复文字第二位置、缺证据不授覆盖；选择短引后仍核实际sent范围及上下文，旧自由引文空object仍拒绝。当前研究模拟、上述两种后置否定、prior不能掩盖当前模拟均unclear；真正患者试验加独立/既往小鼠研究，以及明确“human participants, not simulations in mice”保留covered。肯定临床获益保留，trial标记本身、basic或unknown类型不能证明获益。必要先修仍需当前Map内肯定有序引文，optional/not required保持可选任务；原图对象没有被修改。

旧15项条件去重和13项关系控制已改用本次实际messages生成的snippet编号，再在最终冻结源码下重跑，分别见`snippet-duplicate-independent-final.json`、`snippet-relations-independent-final.json`，均符合。没有把旧quote格式的通过直接沿用到新协议：虚构自由引文的旧unclear控制，在新合同中对应未知编号的protected failure；改的是传输预期，不是论文/任务的有用标签。接触条件、额外接触力、受限现有能力保留可选；普通同能力合并、坏拓扑拒绝；明确对象/治疗/动作否定、材料未识别和KRAS/铂的正否控制均保留。

`snippet-lifecycle-independent-r2.json`用实际App.route_direction_judge、独立临时数据库与fake Gateway执行8项控制，全部符合：表在Gateway前冻结，即使测试替身随后改变调用参数对象也只展开原表；结果属于起始项目；保存引用包含VERSION与冻结整个sent_papers的SHA；读取pending不会重新选择原片段。VERSION改变使旧判断stale并重新pending；题摘真正改变保留原引用并重新pending；调用中更改题摘、Map或VERSION会Conflict且不写judgement，错编号也不写并保留pending。首轮`snippet-lifecycle-independent-r1.json`的两个“更改来源”fixture误用upsert，其合同保留既有非空摘要，实际没有改变来源；该运行器失误已保留，r2只在隔离合成库显式UPDATE并验证真实变化，没有改产品或拿首次结果判产品失败。

源码中runtime没有新的provider回复缓存；已存引文直接保留展开后的字面范围，不在以后对p1.a1重新求值。growth_context包含合同VERSION、完整任务/固定scope及明确反馈所涉题摘指纹，提交再次核对上下文和旧proposal状态；开发capture保存全部app模块SHA和实际wire编号表。上述8项证明具体运行路径，不声称任意篡改本地数据库或未来实现变更都自动失效；新真实AI轮的冷重放尚由主代理和实施者执行，本代理未把它标已测。

新`snippet-wire-independent-current.json`的12项实际wire控制全部符合：1篇原文摘要窗口478字符、完整bound5613；3篇完整bound7803≤8000。所选编号都在实际连续字段之内，重复提供片段未增加distinct原文；未发原文、伪造上下文、错别名和跨空段不能作为证据，普通单折行保留；标题201/摘要481及过大完整Map拒绝。44项另一完整40节点Map的bound7077，15项去重图的bound6934，全部节点和目标保留，私有key/note/profile/node canary不在请求。output仍1000，注册input各组件和仍8000。开销按重复片段、编号、偏移及完整JSON计入；不能推断新增协议必然降低真实费用。直接运行实施者的snippet/public关系两个模块27项回归通过，用时0.170秒；没有重跑长全套。

最终窄审SHA：snippet_contract `e5f0516e46b50aa44a84dfd386014d6420fa56b46b73f6540e14a8091444bd1e`，growthproposal `f1b961eea19ed0459d7743b2b35281ab43cf56ef19a7ed5116d522ed16e46215`，ai_evidence `18c56cb1e56712c6c1dabb8e996cfe52008858234de2b6aaba00de2272d21f37`，task_relations `5b2312041667d751aa62d4fcb80bcb7bfb58b224092661b32ea72367dcd3d2c6`，service `6f4ef452252964360e125eeefd374cae2923418105fa4f4084f84bb4fad183af`，budget `65cb391da2102e6c82c4a3dcc959192174f19ad0b24a362171ddc06d919f43f0`。prompt文件和新增英文错误目录项SHA另随最终私有manifest封存；新增目录项只描述未知/未发编号，未据这一字典添加重做或通过全产品英文。44/8/12记录所审产品源码与最终文件相同；各组控制存在覆盖重叠，不把加总数冒称独立论文样本数。

此有界新协议软件复核结束：当前检查范围内R-F33具体反例已修复，不留下已知未修的同一软件反例。必须另行验收新真实AI重复运行、科学内容分歧/未知、实际账本、最终全量和桌面包、原生关键流程及正式资料保护。合法编号只证明引用来自本次实际发送的材料，不证明它足以帮助任务、科学正确或用户认可。

## 后续窄审：R-F34 固定材料身份在手动改图后丢失

在实发前，实施者另发现固定需求的正向硫化物电解质身份未被learning_scope保存。本代理随后独立复现：goal明确“Study the lithium metal interface with sulfide electrolyte.”且关键词也是sulfide electrolyte，make→as_text却仅输出lithium metal interface；Map仅保留界面节点时，实际发送“The lithium metal interface used a sulfide coating.”的合法编号仍被covered。`snippet-fixed-electrolyte-scope-initial.json`保存真实输入、输出与当时learning_scope SHA `c0a8a8d582d207fe713faf0148c75c3f5b4d1c174ded22e76e06f0c8897adc08`，不是根据盲评标签猜测材料。用户删去一个学习节点没有改变已存固定目标，不能借此丢掉目标的材料组成条件。

第一层补修保留正向身份后，独立14项发现3个反向边界：goal、include或后置studies are excluded明确排除sulfide electrolyte，宽关键词仍被采为正向固定身份。它们保留于`snippet-fixed-scope-independent-initial.json`，前后源码SHA一致。修正fixed字段优先之后，另一正向边界又过严：goal仅泛指“with an electrolyte”，明确的sulfide electrolyte关键词也被禁止补充组成；实际coating再次covered。`snippet-fixed-scope-independent-r3-generic-omission.json`及扩展r4保留此失败，不能把已知的泛电解质对象误当已有或相反的化学组成。仅在明确固定组成或排除时阻止宽关键词反转，在组成确实未指定时允许明确正向关键词补充。

主代理要求再核通常的all-solid-state词形；固定goal只有“sulfide all-solid-state electrolyte”、没有关键词和对应Map节点时仍丢身份；真正候选相同字面材料也被当成未识别。`snippet-fixed-scope-independent-r5-all-solid-omission.json`的19项中保留这2个失败及相同前后SHA。随后仅补连续、规定修饰词顺序的all-solid-state同义结构，不采用任意间隔匹配，不推断coating加另一个oxide electrolyte就是硫化物电解质。

最终`snippet-fixed-scope-independent-r6-final19.json`的19项全部符合，SHA `77acb7bba1309d0ae1527401fa42d0a6260425a6369e64249b7d5f963db8790b`：goal/include/正向关键词、泛组成的合法关键词补充、英语based/solid-state/all-solid-state和中文固态身份保留；三种排除、non-sulfide和明确oxide组成不会被宽关键词反转；单独sulfide及coating+oxide不被拼成身份；真正electrolyte和all-solid-state候选covered，明确未使用electrolyte保留unclear。所有来源trace的matched_text都能回到本次原始用户字段，未借Map或候选反推用户偏好。

同一探针还通过实际App保存brief和两个节点，再由真实route_save删除电解质节点，随后以隔离fake Gateway调用真实route_direction_judge：固定目标精确保留，coating判断unclear，分类过程没有修改用户Map。没有调用模型或操作真实应用/资料。最终四个既有snippet边界/临床模拟/获益/基础实验针对性回归另由本代理运行4/4通过、0.017秒；依主代理要求没有重跑此前44/8等全部组。前面的R-F33整组证据仍对应各自历史SHA，不伪称是在本次新材料词法源码下重跑。

本阶段只新增正向材料trace与局部引用身份判定，没有新增外发字段、私有资料、请求、预算、模型或任意化学ontology。固定scope与完整题摘指纹仍进入growth_context，实际源对象变化使旧判断重新pending；新增constraint不是新的全领域材料召回或推荐有用性证明。旧直接局部科学规则、相邻领域资料的个人价值和缺资料的未知状态仍须独立评价。

最终增量SHA：learning_scope `68106a99359bb2fa1c610da4c5aebba2821606e14f06da532bfc879e7f897a2f`，ai_evidence `2d7f19d230951983795abc4f3214213b984e0a6b87b33100b2faa0d03f44d4d5`。snippet_contract、growthproposal、service及budget与R-F33封存值相同，19项运行前后及随后核对均一致。R-F34具体软件反例在该增量范围内已修复；新实发、来源标签/科学质量、最终全量/包/原生和工作单元登记仍待主代理收尾，不把中间r9绿测试、合法编号或本19项软件通过升级成整产品发布通过。

## 后续窄审：v2 按论文编号取证与原始重复字段

本节对应 `public-snippet-ref-v2`，此前R-F33/R-F34的v1结果及失败记录均原样保留。变化是回复的evidence改为以p编号为键、每篇恰好一个仅含snippet/type的对象；不存在数组、重复证据合并、自由引文补写或带v1标记的降级转换。读取实际snippet_contract、growthproposal、service、共享strict_json、提示、预算登记和验收脚本后，独立执行了下列软件控制；没有读取盲评标签或让模型判断软件预期。

- 44项引用/科学否定/临床模拟及获益/必需与可选边界、8项真实App冻结与迟到响应、12项完整发送与范围、15项动作任务去重、13项对象/关系、19项固定电解质身份，共111项全部符合。本次只将已知阳性的证据传输编码换为v2；未知编号、篡改表/偏移、跨论文、旧自由引文和科学阴性没有通过转换补成阳性。重复数组故意保留为非法数组，空的合法对象仍为unclear。它们是固定的软件回归控制，含复用及重叠案例，不是111个独立科学评审或实际模型请求。
- 另39项新合同控制全部符合：数组/多选/标量/空值/额外字段/缺字段/错误类型/不完整别名集合拒绝；v1或未知版本的冻结表不能退回自由引文；顶层、结果组、evidence及更深层重复JSON键均在归一化前拒绝。还测试了转义后同名的p/type字段和非有限数值。这11个原始JSON阴性均可被普通json.loads接受，严格解码器拒绝，避免把语法损坏当成重复键证据。合法原始JSON阳性通过。
- 新的三个产品结构回归另由本代理实际运行3/3通过，0.006秒。首轮误用了两个不存在的方法名，导致runner的2个AttributeError；`snippet-v2-focused-initial-runner-error.json`如实保留，随后只改本次调用的名称，不改产品或测试。这个执行器错误不列为产品bug。

39项中还从真实verify_packaged_route源码提取其嵌套public_fixture_reply及字面fixture，不执行main、服务、构建或原生验收。函数从本次实际messages取当前abstract选项，严格解析并通过真实validator后得到有必要性原文的missing_prerequisite；required_by保持原节点、引用内容/原始偏移/表SHA正确。删去实际选项时函数明确失败，没有猜编号或补写引文。该合成验收fixture只能证明本地结构/恢复流程，不能证明真实AI的科学判断。

实际App探针确认发送前冻结题摘及表：测试侧在fake Gateway内更改messages对象，已冻结引用不受影响；切活动项目不会把结果写入新项目；保存后pending消失，VERSION改成真实旧v1后判断变stale并重新pending；随后修改公开原文不会重解释原来已保存的引文。原文、Map或VERSION在响应途中变化均触发Conflict且不保存；非法引用也不落库。VERSION和固定用户scope/Map/题摘参与本地growth_context，citation另保存整张本次冻结表的SHA；这个SHA不发送给模型。未把旧引用在另一张新窗口表上重新展开。

完整40节点阳性保持所有节点、目标和边，实际完整请求上界7096，输出1000；另一个40节点控制6953。超限完整图明确拒绝，不裁图。三个公开论文仍仅使用连续title≤200/abstract≤480，各表≤3个、每个8–160字的原文选项；每个字段和选项均校验本次原文偏移，不用段落拼接或额外源上下文补证。私人ID/笔记/画像canary没有进入测试wire，8000/1000和现有全局上限没有扩大；登记的灵活分项算术不是每个字段必定能达到上限的承诺。

独立只读重算R36六份真实零发送capture：完整上界依次7942、7863、7839、7957、7955、7958，均≤8000，scope_issues为空且sent=false。核对所有选项连续存在于该请求实际发送字段。最初219文件冻结SHA `297166b0aa95907e19fdb09a80064f86591abe41dd67f75ee29c56af2a9e8e6d`随后只有主代理下面R-F36的index改动；新最终冻结SHA `61a6f9c4c2f60c689c53398bca467ba17ca15b59a2b0cea2bda73b88f0ddd870`的219个文件与当前源全部一致。新增capture-r38六份messages和上界与原R36逐项相同，仍零发送；不计作又六次模型稳定性试验。

最终关键源码SHA：snippet_contract `311fa7023939f981e6b43669ee5357d0e7432bd1ad95611e55695f643c0872fd`，growthproposal `d224c2aa71f5bc69f3484005b965f865188966dccb49e98bae6346bf63b580d7`，budget `88de4ce2aa4851d50c4ec5a729d68e7940f6be79c2fb041bbeefc5e13dea39ea`。ai_evidence、learning_scope及service仍与前节R-F34封存值一致。新证据见私有`snippet-*-independent-v2.json`、`snippet-v2-keyed-independent.json`、`snippet-v2-r36-capture-readonly.json`及`snippet-v2-final-freeze-readonly.json`，运行前后未改产品。v2有界软件控制通过；科学真伪、个人有用性、真实模型稳定性、最终全套/包/原生及工作单元收尾不由它们通过。

## 后续窄审：R-F35/R-F36 助手恢复草稿与PDF即时重排

R-F35主代理恢复草稿高度的改动经实际setPetOpen/openPet/growInput函数VM独立核验：助手隐藏时scrollHeight=0，打开后84px；多行中文和科学术语不变；关闭再打开、PDF可见时同样恢复高度，没有API请求或新持久化。这个测量是DOM替身的软件控制，不是原生像素验收。

附加PDF布局控制发现真实函数的另一反例：原代码切open class之后才读取before宽度。模拟CSS同步将PDF区域900变为500时，before已是500，下一帧仍500，layoutPages调用为0；宽度下一帧才变化时调用为1。`reader-visible-draft-independent-initial.json`保留4/5及index SHA `e185dc967badec5e6280a216ef3821395df4e16e9f74b4f744a8092021e6a68b`。确定的是原函数漏过即时宽度变化，实际原生视觉影响未测，未把背景绘制未知归到它。

主代理最小修复将PDF可重排状态和before宽度移到class切换/输入测量之前。本代理重跑原5项，再加即时关闭变宽及保持关闭宽度不变，共7/7符合；打开900→500调用一次、关闭500→900再调用一次、不变时不重排，多行输入原文不变。最终index SHA `2b51be3e6166c5a5cf04d3a59a83c621de9e27f2e8f007f5f28ea92d91734ffc`，私有`reader-visible-draft-independent-fixed.json`运行前后同源。R-F36这一软件反例已修；原生前台PDF像素、背景rAF限制及整体UX仍由后续实机证据判定。

## 后续窄审：R-F37 整队列的可选片段挤占发送上限

真实R39诊断的18种运行中，9种队列在中途安全拒绝下一批完整输入；这个失败原样保留，不写成完整通过或科学验收。三次计算机入门分别已处理3篇、剩17篇；计算机研究已处理12篇、剩8篇；材料研究已处理9篇、剩11篇。入门计算机的下批有3个已有方向；后两类实际选定方向为空。因此不能把九次超限都归因于新增方向，可选片段表加上题摘本身也能超过上限。

本代理对九个实际失败数据库只读一致性备份，在自己的临时App副本取正确useful反馈项目的下批、完整Map、固定scope及实际选定方向。修前完整growthproposal和snippet_contract源码在私有目录重建，分别精确核对R39记录的SHA `d224c2aa71f5bc69f3484005b965f865188966dccb49e98bae6346bf63b580d7`、`311fa7023939f981e6b43669ee5357d0e7432bd1ad95611e55695f643c0872fd`后调用原函数；不是用实施者测试fixture代替原现场。九个旧函数输入均拒绝，初始完整上界分别8344/8323/8344、8005×3、8070×3。

新函数仅在初始完整wire超限时，把同一连续原文字段的可选引用数由3降2、再降1，每一步重算完整请求；保留当时已有评分最高的可用选项，不裁Map/目标/边/选定方向，不删连续题摘上下文，不放宽输入8000、输出1000或科学守卫。九种修后上界7899/7981/7899、7920×3、7994×3，全部符合。初次入限的packing阶段逐字段与旧baseline一致；后续仍只在既有余量内执行原来的连续窗口扩展。每个选项能回到该篇本次原文偏移，旧已移除编号及篡改偏移明确拒绝，不补写引用。

`snippet-packing-independent-r3.json`共27/27符合，除九个现场，还覆盖强制2选项/1选项、同一原始动作关系仍在最高分选项、仍超大的完整Map保持完整并拒绝、非法0/4/布尔/负数/空的option上限及一选项下的临床控制。模拟鼠实验的整项研究、没有字面获益却宣称临床获益仍unclear，真实临床试验与独立既往鼠实验对比的肯定控制保持covered；合法编号未变成科学授予权限。用户缺失或不足8字的元数据可以自然没有可用选项，不能为了满足数量制造文字；最终登记明确是“不移除最后可用的字面选项”，不是声称任何数据必有一个。这一自然缺资料分支是既存合同，本次未增加实际短元数据测试。

另`snippet-packing-endpoint-independent.json`的5/5直接调用实际App：三种旧卡队列的17/8/11篇，分别以6/3/4次fake Gateway完成持久化，旧judgement和Map保持原样；新引用仍使用Gateway调用前冻结的表及正确原始偏移。fake回复可以由守卫归为unclear，完成仅指软件流程，不代表有用。另两种在packed响应中途改原文或改VERSION均Conflict，原判断不被覆盖。fake用量是合成字段，全部不是实际token或付费测量，本代理此阶段真实模型请求0。

初始探针曾把默认项目当成实际useful项目，随后固定读取真实反馈项目；强制范围只到2800字符时仅到2选项，扩到4000才覆盖1选项。最初保存消息函数时实施者已改源，那个文件不作为旧代码证据，另保存并验证上述完整旧文件。首轮相对Path.as_uri也在连接前失败。所有runner失败日志、22/23的中间范围缺口与最终结果分开保留，不能列为产品bug或覆盖历史R39失败。

用户要求结束后，本代理停止新增R-F37实验，仅封存已完成的27+5项；新的真实AI整队列、付费窗口捕获或独立科学盲评未执行，记录not_run。科学守卫文件及VERSION未变，新packing不会重解释原已存引文；最终registry SHA `d891b33cbf9f22df8b870e8a25218fd95448604328d9c0641efe3b3bd9cf6b1a`只澄清last available的表述、数字与原批准边界未扩大。R-F37在此有界软件范围内修复，允许据实进入本地工作单元收尾；不授权整产品发布，不替代新的原生、真实模型稳定性或个人价值门槛。

## 最后窄审：R-F38 所选文件全部失败时的恢复入口

在用户要求停止扩测和本地合并之后，只复核实施者冻结的最后导入恢复切片。本代理读取完整实际import脚本、HTML、翻译和共享确认对话框，独立执行`tests/test_import_failure_recovery.cjs`，8/8通过、0跳过、退出0，68.401292ms。该测试在真实闭包内仅注入可调用函数出口，执行实际上传、恢复、审阅和按钮处理；网络、DOM和PDF提示解析是替身，不是最终包原生实机验收，也不是另八个独立用户情境。本代理不再新增付费、原生或广泛实验。

全失败时，startImport回读实际条目计数，空计数进入审阅恢复页；startResolve也在调用resolve前检查空计数。页面保留本地及持久失败原因，隐藏提交/空分类，提供重新选择文件和明确放弃。重选仍用原批次，原online等选项锁定，不能靠失败恢复悄悄开启联网；可返回查看原因，修复后补传才进入正常匹配。暂停和原文件保持边界没有由本次切片改写。共享DOM确认在弹出与接受时均复核valid条件；取消放弃不发discard，确认才使用捕获的原batch ID。

生命周期审查确认上传提示提取、上传结束、匹配回读和审阅回读均核当前batch/stage；reviewToken另防同一审阅被较早回读覆盖，rowsToken防返回选择后旧行重画。实际回归涵盖重复开始、切批次时迟到提示不得上传、迟到审阅不得覆盖新批次/选择页。没有把合法空恢复当成提交成功，也没有额外模型调用或资料外发入口。新系统文字有精确英文映射，真实中文文件名仍按用户数据保留；本代理没有据此宣称所有任意错误消息或全产品英文完成。

修前日志`import-failure-recovery-before.log`保留0/8及实际空计数throw、冷恢复错误页和迟到覆盖；实施者先修软件后曾出现7/8、缺一条英文key，该中间失败不归并为最终通过。本代理最终独立运行未发现此有界切片的新确定缺陷。最终源码SHA：import.js `e532287e0e825c09d194230cafe2bfb1705aaa9125c0b1952a2c0d188fd695b6`，import.html `35f6ecbbf47cc3ffb1041a9cc0ef48337a0b9bb96074ba3950eb16e79970899f`，en-US `782ea811e5813b4f29a1a3b114870c10a3e51e8c48d175ebdffea3fe49262250`，新回归 `d3b3a69cef19528c9008e5a5acfe4f0904d243d8d80d3db4e49d9e5b07f47df3`。独立收据仅记录这一软件范围；最后新包的原生全失败→重选/放弃仍为not_run，最终全套/包和记录一致性由工作单元收尾证据另核。

## 用户要求收尾时的独立追溯核对

本节只读核对最终记录与已经完成的证据，不重跑长全套、构建、原生或模型。变更登记171个路径与实际tracked diff及非忽略untracked集合完全一致，无遗漏、额外或重复；critical分类、任务仍in_progress、release owner_approved=false均符合当前边界。本地main合并是用户明确授权的当前快照操作，不能据此记任务全部完成或发布批准。

最终r13记录的Python2021项、203.989s、OK与Node425项全通过/0跳过、774.208417ms均与实际日志末尾一致。r7五个构建/签名/包后端步骤各exit0，日志表明产生实际.app并严格验签；包内backend、主执行文件与Info.plist的SHA重新核对均一致。全套前后和构建前后的320个源码/提示/测试/脚本/预算文件与当前字节全部一致，指纹均`4764f88b512b50fa2748bc045769a45b79b842bed2a8770c13135358be4a9e17`。这是源和检查的追溯核对，不是本代理另做一次实机验收；ad-hoc签名不等于notarization，包路由使用隔离合成Gateway。

本代理独立按最后一条记录归并专用开发账本，1782尝试中1781reconciled、1历史402released，2,216,743token/$0.610460442，与本次逐项请求收据的operation/input/output/cache-hit/USD multiset完全相同，差异0、unknown/reserved0。含先前已独立核对的原审计280次为2062尝试、2,555,064token/$0.782956770。金额仍为网关记录，不声称供应商发票一致；失败费用不剔除。当前AI13文件manifest与最后软件切片对应，真实诊断源码和修后源码分开记载，用户停止后的新付费队列没有偷记通过。

详细HTML只读静态核对8面板、13表、无重复ID、失效锚点/本地文件链接或远程脚本/样式资源；内嵌am-source逐字等于冻结Markdown草稿。2021/425、R-F38和未测项在页面中可追溯。HTML SHA `a4d0b78a1ec4bf2f3615ab5b8e3a3607c2cb210babbbe3c090b3e31a3cd4e3d6`，草稿SHA `681632f29b8ef69a3f8b1a439583d9bb93c5fd678978cda136212a8909f32269`。像素预览not_run，没有绕过file协议工具限制。

发现原生文档残留“最终包仍待完成”的过时一句，主代理已改为最终r13/r7软件/包通过、最终包原生复测未执行（用户停止）；复读确认已改。原生r6是中间包，只覆盖记录的有限动作；正式资料后续14文件/19表差异仍标归因未知并保留，不拿更早用户确认的7文件/6表覆盖新时段。收尾记录、检查、总矩阵和HTML的主要状态一致，本代理未发现阻止用户授权本地合并的新的追溯问题。有界软件及本次记录一致性复核通过；推荐/科学/个人价值、人类标签有效性、最终原生未测和整产品发布门槛继续开放。
