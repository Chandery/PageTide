# 分类标准与完整 AI 审阅：独立审查记录

日期：2026-10-07。工作单元：`2026-10-07-category-standards`。审查者：协作代理 `category_audit`。

## 审查范围与独立性

本代理未编写本次后端分类身份、候选生成、合并/应用、AI 合同、批处理服务或异步作业，也未编写 AI 预览、取消及迟到结果保护。对以下范围进行了独立源码、调用链、失败路径及离线合成审查：

- `app/organization_terms.py`、`app/organization_facets.py`、`app/organization.py`。
- `app/category_review.py`、`app/category_review_service.py`、`app/server.py` 分类审阅入口。
- `app/static/organization.js` 中新增 AI 预览、`suggest()`、取消、迟到响应及作用于审阅提交的 `mutate()` 保护。
- 新操作注册、提示词与 cap 一致性、`owner_approved=false` 准入拒绝。

本代理编写了整理分类的标准说明、合并原名展示、周报归并说明及其 UI 测试；这些自身实现仅作常规验证，不声称独立审查。本代理编写 `tests/test_category_review_async.cjs`，被测产品函数由其他代理实现。后端主体和 AI 合同/服务仍由其作者维护；该作者的自测不替代这里的独立审查。

未读取真实私有论文库、笔记、画像、密钥或账本，未执行付费模型请求。实际 SQLite 探针全部位于临时目录；VM 探针只使用合成资料和假 API。

## 发现与修复闭合

| 发现 | 初始证据 | 复核结果 |
| --- | --- | --- |
| 双语 pinned 子方向可重复；父目录双语重复后的子类不能在同一预览完整合并 | 独立源码/合成分类探针 | `accepted_terms`、完整祖先身份路径、父先子后的依赖及后代范围检查已加入；10 项标准回归通过。临时 Store 子合并不选父时拒绝且不写入，完整父子合并及撤销可恢复。 |
| 新子类 parent 尚未解析时可能错误复用同名顶层目录；选子不选父或 source 快路可使子方向/方法变成根 | 独立源码/合成分类探针 | 去除 source 绕过，先解决父级，再仅复用同父身份；缺少需要的父级拒绝；标准回归覆盖。 |
| 论文覆盖重叠可把独立的机器人方向自动嵌入世界模型 | 独立源码/合成分类探针 | 仅声明的子方向或方法候选可自动嵌套；不同方向身份和显式自定义 pinned 保持可用。 |
| Gateway `ok=true, usage_unknown=true` 可被当作有实测用量的成功回复，继续批次并存方案 | 独立读取真实 Gateway 返回合同发现；修复前未运行该失败探针 | 服务在解析及下一次请求前先检查 `usage_unknown`。独立 fake Gateway 复核仅 1 次请求、总 token 为 `None`、`tokens_known=false`、不存方案；对应 service 回归通过。 |
| 迟到的 initial AI 响应在切项目/重置后打开旧预览 | 实际 `suggest()` VM 交错探针曾出现 2 个弹窗及旧预览 | 捕获 epoch、scope、currentProject、reviewToken，响应/poll/展示均检查。持久实际函数回归覆盖三种变化，无旧预览、旧 snapshot 或重绘。 |
| 关闭弹窗只停止 UI 轮询，后台可能继续发送后续付费批次 | 独立读取入口和服务调用链 | UI 取消端点、server Event 及 service 批次前后/存方案前取消检查已加入。初始 job ID 尚未返回时关闭也能在 ID 到达后取消。已发一次请求的实际已知 usage 保留，后续停止、未完整方案不保存。 |
| `_apply_ai_review` 最终写入边界只依赖 parser，直接合法 shape 的新 JEPA 根或无支持新类别可被接受 | 修复前临时真实 Store 探针接受了方法根 | 最终边界同时校验新/改名方法不能无父及所有新类别必须得到本次论文或已分配后代支持；真实临时 Store 回归通过。 |
| parser 接受世界模型→机器人这类不同已知概念的 merge | 修复前纯 parse 合成探针接受 | parser 和最终写入边界均按最终改名后的目标身份拒绝不同已知概念；严格论文 refs 测试改用真正双语同义 fixture，以继续验证被删/合并 ref 拒绝。 |
| apply 回调 await 后仅检查 epoch 不足以保护同 epoch 的 scope 切换；内部 mutate 仍可能先接受/重绘旧响应 | 独立源码检查指出回调 guard 前内部 repaint/accept 路径 | 两分支 `mutate(..., false, current)`，`mutate` 接受及错误/重绘也验证 scope-current。6 个持久交错回归验证 AI/local × scope/project/reset 后新 snapshot/filter/notice 不变、不重绘、不 toast。 |

最后复核未发现上述独立范围内未闭合的 P1/P2。已知标准词不是通用学科推断器：未知类别身份仍为 custom，用户显式 pinned 词可用；未知未固定标题残片保留待分类。父类、子类和不同祖先路径的同名类保持层级差异。固定词表覆盖与模型的主观合理性仍未实测。

## 原子性、失败和隐私边界

完整共享目录与当前范围所有论文在请求前冻结，每批都有完整目录；60 类、每批 12 篇和完整 wire UTF-8 bytes + 256 的上限会明确拒绝，不能静默裁目录。请求只有临时 c/p 引用、类别名称、父级以及公开标题/摘要片段；非空 profile 在合同层拒绝。source 文本作为不可信输入；没有工具调用、profile/PDF/私有 ID 暴露路径。

每批一次请求且无重试；已有分类意见须跨批一致，新增类别按规范祖先路径稳定映射。完整 reply/覆盖/父依赖/循环/目标/usage 未确认等失败均停止。失败本地结果 `stored=false`、不含 `ai_plan/ai_token`，UI 显示失败后需明确另点本地检查；失败结果没有被伪装成可应用 AI 方案。

`store_ai_review` 先验证 revision、完整 paper key 集合、corpus 和 structure，然后对数据副本运行完整应用校验；成功仅存预览。确认时再次检查 token、corpus、structure，分类 delete/rename/merge/new 与每篇最终归属在同一事务内完成，并产生一个撤销事件。其他项目或已归档论文仍持有待删类时拒绝，不发生部分删除。论文/笔记保留；merge 保留其他成员及子类；重复应用不新增撤销事件。未知或旧方法类可 keep，不能因证据片段不足直接判为不合理。

## 已执行检查

以下均为本代理实际执行，退出码 0：

1. `python3 -m unittest tests.test_ai_category_review tests.test_category_review_service tests.test_category_review_apply tests.test_category_standards tests.test_organization_review tests.test_organization_facets tests.test_weekly_categories tests.test_weekly_detail -v`：165 项通过；另以同一套测试安静复跑计数，0 failure / 0 error / 0 skipped。
2. `node --test tests/test_category_review_async.cjs tests/test_organization_ui.cjs tests/test_weekly_ui.cjs`：117 项通过；异步独立实际函数回归单独为 10/10。
3. `git diff --check`：通过。`python3 scripts/harness.py impact`：退出 0，最低分类 critical；该命令不证明产品正确性。
4. 实际 `Gateway('.', dev=False, data_dir=<temporary>)`，将 `_load_key` 与 provider `urlopen` 替换成禁止触达断言：新操作 `owner_approved=false`，`ok=false`，原因 `operation awaiting owner approval: category_review`，密钥读取 0、provider 调用 0、临时 ledger 未创建。没有读取真实账本或密钥。

目标回归同时包含严格 JSON/字段白名单/完整覆盖、同义与不同身份、支持新父级、新方法根、预算拒绝、未知 usage、截断、跨批一致/冲突、并发作业/目录变化、取消、scope 外/归档 holder、真实 Store preview/apply/undo/CAS、周报归并与反馈口径。自身编写 UI 的通过仅为自测。

## 当前未测与后续门槛

- 真实模型分类质量、tokenizer/实际账单与真实论文库效果：`not_run`。新操作 cap/privacy 批准在本次检查时仍待用户答复，不能借其他操作批准或由代理自行变 true。
- 全产品完整测试、记录覆盖/harness check/review、后端打包/Tauri `.app` 构建：由 root 在审查后执行；本记录当前不宣称这些尚未执行的检查通过。
- 原生 macOS 新分类流程验收、8GB 资源测量：`not_run`。VM 交错和临时 Store 恢复不等同原生验收或通用学科准确性。
- 不改变原全产品的已知 release 阻断项；离线确定性标准部分可工作且核心每天最低 0 模型 token，新 AI 操作注册上限不增加原全局日/月 token 或 USD 额度。

## 全量首跑后旧合同 fixture 与登记复核

root 报告全量首跑发现三项旧合同期望。独立 diff 复核：`test_organization_undo.py` 把 child-only JEPA 升 root 的旧期望改为缺父拒绝，并新增失败前后 snapshot 完全相等，原来先应用父再复用父的成功断言仍保留；`test_i18n.py` 仅把原始小写 pinned 名改为标准英文 `World Model`，中文期望和每组 name/reason 无汉字断言仍保留；`test_library_entry.py` 标题一致性计数由 2 改为 3，分别对应等待、完整预览、明确 AI 失败弹窗。三项均未删除行为覆盖或放宽断言。

本代理以加入 `tests` import 路径的 unittest loader 实际复跑上述三个模块：34/34 passed，0 failures/errors/skipped。首次直接 `python3 -m unittest tests.test_organization_undo tests.test_i18n tests.test_library_entry -q` 因 `test_i18n` 的既有 `recommendation_fixtures` 同目录 import 路径而失败，属该定向调用方式问题；修正调用路径后通过，未改测试来隐藏错误。

当前 change record 已从原纯本地预算叙述更新为 `runtime=changed`：新 optional operation 每批 8000/2000、最高 10000 token/$0.0048，仅 ceiling arithmetic，非产品实测。record/PRODUCT/BUDGET/ADR/prompt 明示用户授权 AI 审阅实现范围，但 cap/privacy 回复仍待答复。实际比较 `HEAD:harness/budget.json` 与当前 registry：既有操作 `owner_approved` 变更 0；新 `category_review.owner_approved=false`。`python3 scripts/budget.py --check` 退出 0，算术和生成文档一致；这不证明模型质量、账单或新授权已取得。完整记录文件覆盖、全量最终复跑、构建结果仍待 root 后续提供，不在此预先标 passed。

## 最终记录、构建产物与恢复复核

本节更新以上早期时点中“待 root 后续提供”的全量检查及构建状态；真实模型、真实论文库和原生窗口验收仍为 `not_run`。

本代理读取并核对 root 的最终日志：`.local/category-full-python.txt` 明确为 1546 tests / 323.881s / OK；`.local/category-full-node.txt` 为 298 tests / 298 pass / 0 failure；`.local/category-backend-build.txt` 为 PyInstaller complete 并准备 backend；`.local/category-tauri-build.txt` 为 arm64 release、14.44s、成功生成当前 `PaperDigHelper.app`。这些完整测试及两次构建由 root 执行，本代理没有把日志审阅描述为自己重跑全量或构建。签名后 route/类别包探针日志均为 PASS，checks 诚实保留首次签名失败及产物 adhoc 修复，不声称 notarization 或发布批准。

本代理实际再次执行：

- `python3 scripts/harness.py check`、`python3 scripts/budget.py --check`、`python3 scripts/harness.py review changes/2026-10-07-category-standards.json`、`git diff --check`：均退出 0。
- `codesign --verify --deep --strict --verbose=2 src-tauri/target/release/bundle/macos/PaperDigHelper.app`：退出 0，当前产物 valid on disk / satisfies Designated Requirement。
- 实际函数异步 VM 回归：10/10 passed。`python3 scripts/i18n_extract.py --check`：退出 0，0 missing / 1178。
- 读取 root 的 `.local/category-packaged-smoke.py`，在内存增加两个精确断言：应用后两篇 `directions=['new-world']`；重启后的 undo 两篇 `directions=[old]`。执行该加强后的合成探针退出 0，当前签名包 HTTP 实际完成未经批准 AI 拒绝、完整 fixture 预览应用、旧标签删除、新归属、笔记保留、重启及精确原归属恢复。未修改产品文件或原脚本，未使用真实模型/用户资料。原脚本输出曾声称 both memberships restored 却仅断言旧标签/篇数/笔记，本次增强消除这一证据不足；不是发现恢复产品错误。

独立比较 Git 当前 tracked diff 与 nonignored untracked 全集和 change record：36 actual files = 36 registered files，missing/stale 均 0。最终产品差异与此前已复核修复一致；标准/AI UI/失败统计、翻译与文档未引入新未闭合 P1/P2。PRODUCT、ADR0027、BUDGET、prompt、HANDOFF、checks 与 record 明确实现授权和新操作 cap/privacy 待答复的区别；task acceptance 已覆盖全部现有分类、已分类/未分类、完整批次、delete/reassign、失败/取消/usage/stale 与包恢复，task 为 `review`。

新 `category_review.owner_approved=false`；既有操作批准变化 0。实际检查 `policy.runtime_enforcement_implemented=false` 和 `policy.tokenizer_parity_verified=false`，与 HEAD 相同；`harness/evaluations.json` 无 diff。再次执行 `python3 scripts/harness.py check --release` 实际退出 1，保留原 19 项 `not_run` 阻断及上述两个 false flags。因此本工作单元的离线实现/记录/当前产物审查通过，不等同新付费操作授权或全产品 release。独立审查结论限于本文声明的范围；本代理自写 UI helper 的独立资格不能由这些自测替代。

## 最后任务 evidence 登记修正

root 随后补查发现，在上述全量通过后添加到 task evidence 的 6 个新 test 路径，使 `tests.test_harness` 的隔离临时仓库校验失败；该 fixture 复制注册和文档等资料，跳过 `scripts/changes`，且 tests 中只复制既有唯一 route test，不复制本次新 tests。独立复核本次修正只移除 task evidence 的 6 个 test 路径，保留 ADR、完整 checks 和本 review 三项文档；7 条 acceptance、需求引用、task `review` 状态、新测试实现与 exact change record 文件清单均未放宽。`tests/test_harness.py`、`scripts/harness.py` 没有 diff，未修改 validator 或失败测试以隐藏错误。

本代理实际执行 `python3 -m unittest tests.test_harness.HarnessTests.test_declared_stages_are_not_tied_to_legacy_abcd -v`：退出 0，1 test / 11.461s / OK。随后实际 `python3 scripts/harness.py check` 和 `python3 scripts/harness.py review changes/2026-10-07-category-standards.json` 均退出 0。root 的首次 41 项补查失败已在 checks 保留；本次产品代码无变，先前当前签名包验证仍适用。新登记后的 41 项及全量 fresh rerun 由 root 进行，本节不预先将尚未返回的新全量结果标 passed。

最终补充：本代理已读取 root 登记修正后的 `.local/category-full-python-final.txt`，实际记录 1546 tests / 184.401s / OK（root 执行 exit 0）；checks/HANDOFF 已保留首次补查失败并同步这次通过，Git actual 36 文件与 record 36 文件再次一致、missing/stale 均 0，最后登记及全量证据闭合，未重复运行检查或改产品，新 cap/privacy 仍待批准、真实 AI/原生验收及原 release 阻断状态不变。

## 人类批准后的授权登记与单次真实失败探针

本节更新上文待批准状态：用户随后明确回复“批准”前一轮呈现的 `category_review` 范围和 cap。独立读取当前登记及同期 PRODUCT/BUDGET/ADR/prompt：本操作 `owner_approved=true`，approval_note 明确记录本轮原话、60 类/12 篇、标题80/摘要160、临时 c/p、8000输入/2000输出、不发私有ID/画像/反馈/笔记/PDF/历史、每批一次无重试。`enabled_by_default=false`、interactive 和原全局 policy 全部保留；相对 HEAD 既有其他操作批准变化 0、整个 policy 变化 0。人类批准不等同全产品发布许可、自动后台运行或开启 AI 总开关。

本代理仅编写 `tests/test_budget.py`、`tests/test_gateway_budget.py` 的 4 项授权回归：本轮 grant/cap/default、实际 Gateway mocked provider 一次发送及请求前 reserved→同 ID reconciled、临时 revoked fixture 在 key/network 前拒绝、AI-off normal/dry-run 在 key/network 前拒绝。首次当前 registry 仍 false 时 2 fail/2 pass；root 登记 human grant 后无需修改断言，两个完整模块实际 45/45 passed，0 failure/error/skipped。它们为本代理自写自测，明确不声称对自己的测试独立审查；没有真实网络、真实密钥或真实账本访问。此前 1546/298 和旧包验收发生在授权登记前，不能自动覆盖随后修改。

root 已执行且本代理独立读取 `.local/category-approved-20261007/receipt.json`、`summary.json`、`result.json` 和 probe 源码/输出：仅 1 次真实 Gateway 请求，非 dev，合成 7 类/6 篇，无真实论文库外发；完整 wire UTF-8 bytes + 256 = 4691，官方本地 tokenizer 对本次完整 wire 的结果 1137。provider 报告 prompt 943 + completion 301 = 1244 tokens、finish_reason=stop；Gateway 按登记峰值费率计算/记账 USD 0.0006441，不等同 provider 发票或全面 tokenizer/billing 校准。

真实回复删除 c1/c3，但最后一篇的归属仍引用已删除 c1；服务严格拒绝：status=failed、processed=0、remaining=6、completed_batches=0、calls=1、stored=false、无 ai_plan/ai_token。实际脚本已断言合成目录、6 篇原归属和合成笔记不变，再以 `Review did not complete` 退出；未生成可应用完整 AI 方案。本次是模型输出质量失败和安全拒绝证据，不能称真实整理方案/AI 质量验收通过；不自动重试，也不将失败回复转成伪 AI 本地方案。

主目录协调接管要求到达后，root 停止进一步产品修改、模型请求和 build；本代理本阶段只读审查和追加本记录。已授权 registry 尚未重新打包，先前绿签名包仍内含旧 false 授权，不能宣称当前包已完成此 grant 的发布或新 AI 能用。暂停前正在准备的 context 强化及其他随后差异，需由接管者另行评估，不纳入旧全量/旧包 passed；此审查不预先通过它们。root 将更新最终 change/HANDOFF/integration-ready 记录以反映授权 true、单次真实失败及未重建。原 release 19 gates/2 flags、真实库/原生窗口/普遍质量/8GB 未测边界不变。


## 独立补充审查：标准说明、合并原名与周报归并提示

日期：2026-10-07。独立审查者：协作代理 `weekly_categories`。本次仅追加记录，不改产品或测试；以下 UI 实现与对应测试由 `category_audit` 编写，本审查者未参与编写。该代理明确排除的自身 UI 范围在本节得到独立复核。本审查者此前编写的 `app/profile_insights.py`、周报后端回归、`app/category_review_service.py` 及其测试不在本节独立审查结论内；其作者自测不能被本节改称独立审查。

最终实际审查范围：`app/static/organization.js` 的 `suggestionsHTML()` 标准说明和 merge-card 原始别名展示；`app/static/weekly-ui.js` 的 `directions()` 归并提示；`tests/test_organization_ui.cjs`、`tests/test_weekly_ui.cjs` 相应覆盖及两段标准说明的英文翻译。辅助只读核对后端 `organization_facets.review()` 的 `copies` 输出与排序，以确认界面所说“保留第一个”的来源一致，未修改该后端。

结论：本范围未发现未闭合 P1/P2。说明保持研究方向/子方向/方法的层级区别，明确沿用已有类别和证据不足留待分类；没有把父子等同为同义词，也不承诺未知术语自动得到正确学科分类。说明位于本地建议结果及空结果之前，不改变已有勾选、手动修正或撤销行为。中英文原名按真实 `copies[].name` 显示；缺少该字段的旧预览才回退到实际类别路径。名称、旧路径、建议 ID、理由及计数字段均经过既有 HTML 文本/属性转义，原名带 `data-no-i18n`，不会被语言层再次替换。后端 `copies` 的排序与 `keep` 使用同一个 order，界面“第一个”确为保留项。

周报新增提示仅呈现服务器的字符串 `category_normalization.message`；为空、缺失或错误类型时不输出提示；非空字符串经过 `esc()`，并位于方向卡片或空结果之前。没有在 UI 重新合并类别、重算篇数或改写反馈次数；同义方向在后端归并与真实不同方向分别计数的口径保持分开。显示“原类别与归属保留”是对统计层只读行为的描述，不冒称已修复真实库，也不把安静、未读或太难当成兴趣负例。

本审查者实际执行的证据（均退出码 0）：

- `node --test tests/test_organization_ui.cjs tests/test_weekly_ui.cjs`：107/107 passed，0 failed/cancelled/skipped/todo，实际运行 238.885667 ms。包含标准说明的空/非空结果顺序、英文翻译、真实别名/旧字段回退、恶意原名与提示转义、方向/反馈数字、沉默和太难语义的现有回归。
- 独立 Node VM/生产函数探针：直接载入最终 `organization.js` 的 `suggestionsHTML()`，用中英文别名、恶意 SVG 名称/ID/script 理由和缺少 name 的旧记录验证全部以转义文本展示、原名及论文/子类计数邻接、标准说明先于结果；无 HTML 注入或丢失旧类名称。
- 同一独立生产函数探针直接调用最终 `weekly-ui.js` 的 `directions()`：带归并提示的 HTML 删除新增提示段后，与无提示版本逐字符完全相等；输入 report 的 JSON 前后完全相等。用同一篇论文的 `positive=2`、`understood=3`、`papers=1` 验证真实事件次数和去重篇数原样展示；恶意 SVG 提示被转义，空/null/undefined/object/number 提示与无提示输出完全一致。探针未写库、未调用模型或实际 API。

全量测试、桌面新包构建和原生流程属于 root 的另行证据，本节不将其报告等同为本审查者执行。真实 AI 分类质量、tokenizer/账单、真实库清理及原生界面验收仍未因这些合成/函数测试获得 passed；新 category_review cap/privacy 尚未批准的状态不被本节改变。

独立追加审查（2026-10-07，协作代理 ai_category_review）：本审查者未编写 category_audit 本轮新增的四项授权回归，仅只读核对 tests/test_budget.py、tests/test_gateway_budget.py 的实际 Git diff，以及当前 category_review 预算登记。四项均为新增，没有删除或弱化既有 false 拒绝分支。独立结论：本次 owner_approved=true 与 enabled_by_default=false 的区别有明确覆盖——预算测试断言本操作自己的“批准”记录、interactive 触发及 8000/2000 cap；显式 Gateway mock 测试核对仅一次发送、输出上限 2000、关闭 thinking、临时别名无私有 ID、发出前完整 8000/2000/$0.0048 预留，以及同一 reservation ID 按合成 200+100=300 实际 usage reconcile；单独把本操作改为 owner_approved=false 的夹具仍断言密钥读取 0、网络 0、ledger 不存在；AI 总开关关闭时普通调用与 dry-run 都同样 0 密钥/网络/账本。当前 approval_note 明确指向本会话 owner 的“批准”和本操作范围，未借用 Route 旧 grant；默认关闭的登记不代表显式授权调用应被拒绝，也没有因此移除未授权拒绝能力。本范围未发现未闭合 P1/P2。45/45 passed 为测试作者/root 本轮报告，本审查者按交接要求没有重跑测试或构建，亦未发送模型请求或修改产品源码。本追加仅确认上述测试设计及当前登记，不把 mock 当真实模型质量、计费校准或联合构建证据；首次真实合成探针的严格回复失败和1244token/$0.0006441证据仍保留，新上下文强化未实施。
