# Route Mode 方案完成审计

2026-10-07；基线 f0f000c，功能分支 codex/route-discovery-rework。本审计针对 docs/ROUTE_MODE_REWORK.md 的 ROUTE-V2-00–08 实施与验收，不是全产品发布批准。harness/tasks.json 是唯一任务状态；不新建竞争任务表。

## 本轮剩余原生验收实际完成

使用此前隔离运行的同一 Tauri .app，PID49668、后端127.0.0.1:49446；数据仍在 .local/route-native-20261007/data，AI_DISABLED、无key、隔离 HOME 和失败代理保持。本轮没有新的模型请求或真实库数据修改。

1. 真实原生设置页选文科、勾选英文和中文、保存，显示“论文语言已保存，下次生成推荐时使用”。返回今日，再进入设置，文科和两项勾选均保留。
2. 在原生设置页取消英文，保留中文并保存。今日点生成，实际显示1篇 epitaxy native language fixture，元数据语言中文、全文语言未核验；显示语言不符合设置18篇。AI提示“AI已关闭，保持本地模式”。证明文科策略可允许中文，不把英文标题当英文全文，也没有默认要求所有学科英文。该论文是合成元数据，不能证明真实全文语言准确率。
3. 真实原生项目总览→新建→手动创建；填写 Native project creation acceptance、关键词epitaxy、选择理工科。点创建后进入新项目862c05e7-e7a5-4d3e-a8b9-1fd0c4a7e681，0篇推荐。进入设置核对名称、关键词、手动方式和“理工科只推荐英文”。只读隔离 SQLite 再核对 stem/[en] 与主fixture humanities/[zh]，一致。自动来源刷新因失败代理被拒，旧内容保留；不把这次当真实召回实验。
4. 在这个原生新建项目里打开学习图→自己搭一张，填写五字段中的目标、已知基础和结构意见。手动建立 Lattice basis→Epitaxy goal，Epitaxy为明确目标；Lattice人工简介“Crystal structure needed before epitaxy.”保存。保存后显示当前目标学习中0/2、Lattice可以读、Epitaxy未解锁；已知基础没有自动授予掌握。新项目创建与建图是真实原生点击，没有通过service替代这两步。

此前主fixture的native3+1+1、反馈/撤销保留收藏、关注/掌握、完成后每日发现、双图同纸导航、409/输入保留、新预览确认、重启持久撤销、普通模式见[原生证据](2026-10-07-route-v2-08-native-acceptance.md)。并发变更和手工预览由受控service准备，明确区别于native显示/确认和真实AI生成。单项目完整离线流程另外由 tests/test_route_full_flow.py 和新包后端验收覆盖；不把原生新项目与前一主fixture描述成同一个项目。

## 按原方案核对要求和证据

| 方案要求 | 当前证据与实际范围 |
|---|---|
| 00 分支、默认/测试数据隔离、认证、父退出、兼容启动 | test_desktop_isolation.py、阶段00 checks/review及当前原生隔离进程；main基线850f9fc未变，本地功能分支，无推送合并 |
| 01 旧库迁移、备份/恢复、旧项目待选择、项目隔离、语言/PDF绑定 | test_project_language.py、test_profile_core_chain.MigrationBackupTests、test_organization的schema失败恢复与backup失败回归；阶段01a/02 checks/review；旧批次不删除、元数据/全文分开，PDF替换旧核验失效。native本轮文科多语言保存与仅中文推荐、STEM/en新建已实测 |
| 02 摘要或当前正文、链接不等于正文、各入口一致 | test_recommendation_eligibility.py实际检查链接/空正文/旧PDF/摘要/策略并发、哈希读取上限；build_batch和maintenance共用资格入口；native普通/STEM过滤与文科资格分别实测 |
| 03 目标及前置、旁支、多目标、无前沿、不把已知当掌握 | test_route_goal.py/test_route_store.py；native前置解锁、完成2/2、关闭保图，新项目known仍0/2；watch独立持久化和撤销有证据 |
| 04 三类有界召回与轮转 | test_route_recall.py实际调用计划与固定Source请求验证三主题/最多六请求、失败不加应用重试、跨主题去重、来源/语言/图失效、重启轮转、公开检索词；阶段04独立审查。固定返回不是实测召回收益 |
| 05 3+1+1、发现补位最多2、路径少推、未回答轮转、回答退出、每日发现 | test_route_batches.py验证缺候选/补位/曝光轮转/关注日期/跨日并发/原子失败/手动维护共用限制；native3+1+1、完成后1篇、普通无Route标签 |
| 06 证据不局限探索、仅有用/选种子、五类提议、预览确认 | test_growth_evidence.py/test_growth_proposals.py/test_route_growth.py、阶段06review；完整Map别名/预算/过期/人工编辑合同。实际一次growth covered正常归一，其他分支仅离线合同，不称整体AI质量 |
| 07 固定五字段、12初始/40修改/120边/3前置、补丁、稳定身份、进度截止点 | test_route_revision.py/test_route_revision_service.py/test_route_map_model.py；明确目标删除、显式边/环/数量/冲突/拆分合并/人工简介/旧证据隔离/重新确认幂等/反馈撤销签名/原子恢复。native五字段创建与409/确认/重启撤销，真实revision新增Evaluation成功 |
| 07 完整输入预算、length拒绝、默认关闭、唯一网关 | 相关model/gateway/budget回归和阶段07review；三次实际Gateway.dev=False既有正式账本探针；严格创建超长拒存，保留原图，没有自动修短或重试。授权和既定日/月上限保持，全面tokenizer/账单校准未通过 |
| 08 分类/学习用途分开、共享论文身份、未匹配入口、Routeoff兼容、迟到回复/正文更新 | test_route_detail.py、test_paper_context.cjs、test_organization_ui.cjs、test_route_detail.cjs与阶段08导航/正文review；native x0在两图保持身份、未匹配入口、普通模式保图。正文当前版本校验与缓存交错有独立探针 |
| 08 完整临时库链条与原生验收 | 单项目完整本地回归、新包后端；主nativefixture完成核心链条，原生项目创建/文科保存本轮补齐，明确fixture边界；独立审计和绿色构建以收尾checks/review记实际结果 |
| 记录、阶段提交、回退和隐私 | 连贯change records、各阶段独立review、HANDOFF、本地提交；迁移/恢复在隔离目录回归，不覆盖真实库；正文/私有ID/笔记不扩外发，默认不推送不合并 |

最终全量1462 Python/281 Node通过及f0f000c新backend/Tauri/signature/package检查见[native-checks](2026-10-07-route-v2-08-native-checks.txt)。本轮只新增原生验收和状态/文档记录，不改产品代码；相关记录检查与重建结果见[收尾checks](2026-10-07-route-v2-close-checks.txt)。

## 未被本次变更证明的全产品发布事项

保留原19项全产品阻断评估和2个预算登记字段。E-RANKING/反馈增益/用户试用需要预先约定真实数据与人的判断；全面模型质量、全文语言准确率、资源/8GB、账单/tokenizer、完整隐私/恢复/供应链等原范围不能靠上述合成测试替代。E-ROUTE-V2-08通过只说明本方案规定的实现和测试，不使这些原门槛自动通过。

真实创建收到有效JSON但why超120/intro超140，严格拒存；这是明确的质量失败记录。真实revision/growth各一个场景可用，均不证明模型整体质量。growth重复nearest同值被当前parser接受，未声称严格重复字段合规。原功能最低模型token仍0，真实付费合计1885token/$0.0010254峰费率本地计算，全面校准字段仍false。没有增加或重新消耗额度。

撤销页读取完整组织快照的大库成本未测；实际推荐价值、全文核验准确率、全面模型质量与发布资格仍是独立产品评估。不能把“Route方案实施完成”写成“全产品可发布”。
