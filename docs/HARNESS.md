# 项目 Harness：核验证据，不替产品做决定

2026-09-11 重新规划后继续保留标准库检查。它的职责是防止需求/任务/证据/预算漂移，让任何 agent 只读 [AGENTS](../AGENTS.md) → [HANDOFF](HANDOFF.md) → `harness/*.json` 就能接手，而不是验证产品已经有用。

## 事实源（单一来源，不复制）

- [PRODUCT](PRODUCT.md) / [ARCHITECTURE](ARCHITECTURE.md) / [ROADMAP](ROADMAP.md) / [RESEARCH](RESEARCH.md)：目标、边界、阶段、复用证据。
- `harness/tasks.json`：**唯一**活跃任务表，`stages` 显式声明，不把 ABCD 硬编码进检查器。
- `harness/requirements.json` → `harness/evaluations.json`：需求到 gate 的追溯；未运行就是 `not_run`。
- `harness/budget.json` → 生成 [BUDGET.generated.md](BUDGET.generated.md)：模型操作、价格、日/月 token 与金额提案；[BUDGET.md](BUDGET.md) 只解释。
- `harness/sources.json`：外部事实与复查日期；价格/许可/合同过期会被标记。
- `docs/evidence/`：真实的命令输出；`changes/<id>.json`：一个连贯工作单元一份记录。
- `docs/archive/`、`harness/archive/`：历史快照，不继承 done/批准。

## 比例适当的改动要求

| 级别 | 典型范围 | 检查 |
|---|---|---|
| docs | 不改合同的文字/链接 | 简短记录、链接及实际 diff |
| standard | 普通行为修复 | 需求/任务、失败回归、有关测试、预算零变化理由 |
| feature | 新可观察行为 | 范围批准、验收、失败状态、隐私/生命周期/资源审查、独立 review 后才发布 |
| critical | harness/AGENTS、prompt/模型/预算、IPC、迁移/备份/恢复 | 上述加合同/恢复与独立审查；用户批准不得由 agent 自填 |

一个 coherent 工作单元一个 change record。先用回归证明旧行为会失败，再最小修改；不为赶进度降级风险或削弱 gate。

## 命令与证据

```sh
python3 scripts/budget.py --check        # 预算算术与生成文档一致（不发请求）
python3 scripts/budget.py --write        # 只生成，不授权；diff 需人工审
python3 scripts/harness.py check         # 结构、链接、任务/需求/gate 追溯、来源日期、技能与提示词登记
python3 scripts/harness.py impact        # 工作树改动与最低 class
python3 scripts/harness.py review changes/<id>.json
python3 scripts/harness.py check --release   # 保守发布门槛，本轮应阻断
```

`check` 只验证仓库契约：**不执行推荐实验、不判定事实真伪、不证明 GUI/性能/预算/恢复正确**。`impact` 覆盖 tracked/staged/untracked；`review` 要求 record 的 `files` 恰好覆盖当前全部变更。已有未提交工作必须保留、隔离或明确纳入范围，不能为通过检查擅删。

每条 check 必须使用已注册 category/command、真实 exit code 和非空 `docs/evidence/` 证据。失败不得写 passed。独立 review 看真实 diff、契约和失败路径，不读实施者总结就签字；行为修改后重新核验。

## 本轮吸收的开源 harness 做法

参考（已核验许可与文件，未复制代码）：openai/codex（AGENTS.md 路由 + 生成契约同步）、github/spec-kit（稳定 ID 的需求覆盖表 + 重新生成并 diff 的产物 + constitution）、obra/superpowers（“完成声明必须有新鲜的验证证据”、技能命名动作而非工具、跨 harness 别名）、BMAD（带规则 ID/严重度的确定性校验器、禁止过时术语、技能 frontmatter 校验）、Aider（读只读约定文件 + 编辑后跑测试）。

落到本项目：

1. **ID 是 JSON 与文档的接合键**：需求 `R-*`、验收 `E-*`、任务 `*`；文档只链接 ID，不复述数值。
2. **生成产物 + 漂移检查**：`BUDGET.generated.md` 必须与 `budget.json` 逐字节一致，改了 JSON 不重生成就 fail。
3. **追溯覆盖**：每个 requirement 必须被至少一个 task 引用且 gate 存在；每个 evaluation 必须被至少一个 requirement 引用（本轮新增孤儿检查）。
4. **技能只写触发、不写流程摘要**：`SKILL.md` frontmatter 必须有 `name`/`description`，描述有 1024 字符预算；工作流写在正文，避免 agent 只读摘要就跳步。
5. **证据先于声明**：`done` 任务要有 evidence；行为变更要有失败回归；发布要独立 review。
6. **跨 agent 单入口**：`AGENTS.md` 是路由，细节在链接文档；不复制第二份任务清单。

## 评估和发布

核心评估覆盖数据来源、排序、画像规则与收益、无债务、捕获/恢复、无模型/隐私、性能和实际试用。阅读器/AI/周报的 gate 在启用其功能前必须激活为阻断并落实验收。

`check --release` 保留保守批准/预算门槛：当前 `approved_by_owner=false`、`runtime_enforcement_implemented=false`、`tokenizer_parity_verified=false`，全部 blocking gate 为 `not_run`，因此必须阻断。外部资料在采用、发布、价格/合同变更时重核；不靠刷新日期假装新鲜。mock、源码/单测存在、任务 done 都不是通过。
