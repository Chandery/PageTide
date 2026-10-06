# Route 阶段05独立审查（2026-10-07）

审查者：`/root/route_logic`，与实现者不同的agent；最终结论：当前阶段没有剩余P1/P2阻断。临时库、公开/假元数据和loopback，无模型调用，不访问真实库。独立没有保存日志文件，以下证据来自审查agent工具输出及最终消息，不能冒充本地日志。

## 发现与修复

- 日期在选中watch后变旧仍保存：事务快照增加published。
- 冻结后的新标签遮住旧有用反馈撤销：签名增加冻结through范围有效反馈。
- 探索抢唯一watch、路径抢唯一探索：五位置增广匹配，存在不同纸可行组合时保留3+1+1。
- 第一匹配已满足、第二匹配未满足却标成第二节点路径：路径与进度都采用第一匹配。
- 正文论文卡片有节点、理解却不推动节点：对有种子/反馈/曝光的论文复用当前版本有界正文；语言规则变化不撤销既有理解。
- 拒绝方向后仍保存旧explore_new：签名加入方向与拒绝状态。
- 英文翻译误在根层、组合文本无法翻译：放进messages，句子按既有分段规则组合；实际动态句与标签测试。
- 首页缓存部分正文进度：签名含有关文件身份及单纸有界正文hash，延期不缓存。
- 部分核验误认完成且消费日额度：未完成核验直接pending，不写批次；事务含延期状态，UI显示核验中。
- 多次扫描放大物理读量：整次build及维护可用性各共享256MiB预算，来源解释复用当前route，卡片核验也用同预算。
- 工作集超过LRU时永久pending：每篇当前PDF仅一份本地实际SHA+file identity凭据，变更/重新登记失效，保护外层事务。原极小LRU/预算夹具恢复pending→completed→daily_limit，只有一批次；独立验证共享项目、重启和0预算复用。

## 最终实际执行

`PYTHONPATH=tests python3 -m unittest test_route_batches test_explore_new test_route_runtime test_recommendation_eligibility test_route_goal test_route_store test_pathgraph test_pathgrowth -q`：322通过、exit0。

`node --test tests/test_route_batch_ui.cjs tests/test_explore_ui.cjs tests/test_route_editor.cjs tests/test_i18n.cjs`：针对当前最终代码74通过、exit0。另执行10组实际完整句翻译（含核验中）、内联脚本编译、diff检查，全部通过。

先前独立配额子审查纯函数穷举3003种0–6篇角色组合，独立回溯认定可行的1021种完整配额全部分配正确，无重复、总数不超过5、发现不超过2。此证据只有工具输出，没有本地日志，也不是推荐价值测量。

新包由主线程另行验证，见[检查](2026-10-07-route-v2-05-checks.txt)。本审查不证明原生窗口全流程、真实推荐收益、8GB资源或AI质量，原发布gates保持。
