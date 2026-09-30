# PROJECT-01 依赖链收口：独立审查

2026-09-30。审查者：独立子代理（superpowers:code-reviewer），不参与实现，只读，未改文件，无网络/模型调用。
审查范围：本工作区未提交改动中与依赖链相关的代码、测试、证据与任务状态。

## 审查者自行运行的检查
- `python3 -m unittest tests.test_profile_core_chain tests.test_project_chain tests.test_gateway_budget`：40 个 OK。
- `python3 scripts/budget.py --check`：PASS；`python3 scripts/harness.py check`：PASS。
- `python3 tools/reuse_baseline.py`：复现文档数值（AUC 0.94 / 0.93 / 0.95 / 0.64）。

## 结论
**修复后通过，无阻断项。** 已核对：
- 只有网关调用模型端点；先预留后发送；4xx 释放；缺少 usage 时按 unknown 保留预留；不重试、不回退；总开关与 `owner_approved=false` 生效。
- 私有种子或画像 ID 不外发；设置接口不回传 Key。
- 不从“无动作”推断不喜欢，“太难”不是负例。
- 跨项目隔离；BUDGET-01 为 done 依据充分，其余任务为 review 且列出缺失输入。
- 证据如实：HTTP 测试未计为通过；socketpair 测试注明“不是 TCP 服务器测试”。

## 发现与处理

| # | 级别 | 发现 | 处理 |
|---|---|---|---|
| 1 | 重要 | 自由文本或含 `?#/` 的种子未编码。`InvalidURL` 和非 JSON 响应不属于 `SourceError`，在项目写入后抛出，导致连接中断；用户重试会得到重复项目 | **已修复**：只有可识别的标识才发请求，其余在本地标为 `invalid_input`；标识做 URL 编码；`InvalidURL` → `invalid_input`，非 JSON → `bad_response` 且不缓存；损坏的缓存会重新获取；种子循环兜底，异常不外抛。有回归测试与 socketpair 路由检查 |
| 2 | 重要 | 取消收藏后，重复点“有用”返回 `saved=True`，但没有重新保存 | **已修复**：重复的正向反馈会幂等地重新保存；有回归测试 |
| 3 | 重要 | 冻结期间撤销冻结前的反馈不生效，与 ADR 0009 的表述不一致 | **已修复**：冻结时记录 `through_feedback_id`，画像回放该编号及之前、未撤销的反馈；旧快照兼容；有回归测试 |
| 4 | 次要 | 旧项目没有 `project_default_terms_*`，“恢复默认”会清空钉死词（可从版本记录找回） | 未修，列为后续 |
| 5 | 次要 | `profile()` 的 base 取全局最新版本行 | 未修；目前没有 API 修改权重，影响有限 |
| 6 | 次要 | 冻结时证据面板仍用实时反馈 | 未修；建议在 UI 上注明 |
| 7 | 次要 | 同一版本号的迁移前备份不覆盖，迁移失败后重试时保留的是更早的快照 | 未修，列为后续 |
| 8 | 次要 | 并发双击可能写入重复的反馈行（按最新一条生效，不影响画像） | 未修，列为后续 |
| 9 | 次要 | `/api/project-papers` 接受客户端传入 `relation_kind=seed` | **已修复**：只接受 shared/imported，否则返回 400；有 socketpair 检查 |
| 10 | 次要 | `delete_project` 没有 HTTP 路由；旧引导会话没有 `draft.project_id` | 未修；PROJECT-01 验收不声称有面向用户的删除入口 |
| 11 | 次要 | 基线表写“与 build_batch 同代码”，表述过度 | **已修复**：改为复用排序函数，并注明差异 |
| 12 | 次要 | HANDOFF 和变更记录中有 2026-10-01 的未来日期（来自先前工作单元） | 未改先前单元的记录，在本单元的风险中注明 |
| 13 | 次要 | 网关账本锁仅在单进程内有效 | 当前只有单进程；在 worker 进程调用模型前需要文件锁 |

修复后的复验见 [检查](2026-09-30-project01-chain-checks.txt)。
