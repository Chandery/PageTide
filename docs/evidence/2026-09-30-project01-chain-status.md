# PROJECT-01 依赖链收口：逐任务状态与缺失输入

2026-09-30。owner 选择“工程 + review”：只有证据完整的任务标 `done`；需要 owner 标签或决定的任务进入 `review` 并列出缺口。本工作单元**没有真实模型调用**，`project_guidance` 保持 `owner_approved=false`。
PROFILE-02、PILOT-01 不在本次收口范围，状态不变。

| 任务 | 新状态 | 工程证据 | 仍缺（需要 owner） |
|---|---|---|---|
| BUDGET-01 | done | [预算检查](2026-09-11-plan-budget-checks.txt)、[owner 决定](2026-09-11-plan02-decisions-and-graph-self-review.md)、本次 `budget.py --check` | 无；数值仍是规划包络，非运行实测（`measurement_status`） |
| PLAN-02 | review | 领域/种子/首版范围/AI 上限/PDF 本地/Zotero 只读/仅公开元数据出站已确认；有用阈值 ≥2 已冻结 | “优于关键词基线”与“更新画像优于冻结画像”的**最小有意义差值、样本量与资源目标**未由 owner 确认 |
| DATA-01 | review | [OpenAlex 报告](2026-09-11-data01-openalex-report.md)、种子逐个解析状态测试（resolved/duplicate/not_found/network_error/failed，404 不重试） | 依赖 PLAN-02；owner 对数据源覆盖结论的确认 |
| REUSE-01 | review | [本地基线](2026-09-30-reuse-baseline.md)：SVM 相比现有排序器无实质增益 | 上游 arxiv-sanity-lite 探针**未运行**（owner 选择）；是否接受“保留现有排序器”的决定 |
| CORE-01 | review | `tests/test_profile_core_chain.py`：同池可回放且不依赖 PDF/LLM、重复曝光排除、已反馈不再推荐、不足五篇原因（`shortfall`）、标签分离 | 依赖 PLAN-02/REUSE-01；owner 标签下的排序质量 |
| PROFILE-01 | review | 反馈幂等、撤销回放一致（画像/向量/统计/证据/周报）、冻结/解冻、恢复默认可逆、双项目隔离、删除项目保留全局事实、迁移前备份与恢复 | **“探索主题”未作为结构化画像字段实现**；熟悉度目前仅由“太难”事件表达 |
| EVAL-01 | review | 冻结协议与阈值、[本地基线](2026-09-30-reuse-baseline.md)、no-op/撤销不变量测试通过 | owner 盲评标签；现有结果 P@5 饱和，不能判定 E-RANKING / E-FEEDBACK-VALUE 通过 |
| AI-01 | review | `tests/test_gateway_budget.py`：预留先于发送并对账、日/月/USD 上限拒绝且不发请求、并发预留、未知 usage 持续预留、网络失败不重试、无 Key/关闭 AI 时 0 请求、速览解析失败降级 | 未做真实调用（未授权）；tokenizer 对齐与运行时实测仍缺 |
| PROJECT-01 | review | `tests/test_project_chain.py`：草稿重启恢复、只能取消草稿、六轮后仍可编辑/预览/确认、未勾选不加入、无 Key/AI 关闭/断网仍可创建、预算拒绝保持本地、删除项目清除其引导记录；跨项目共享不降级种子、项目内隔离、移除关系保留全局事实；URL project_id 优先 | 依赖链未全部 done；`project_guidance` 需 owner 单独批准才可真实调用；HTTP 测试在本沙箱无法绑定端口（见检查文件） |
