# 本轮重规划建立的决策快照

2026-09-11。这里仅保留本轮调研重规划时新建的文档、任务和验收快照，用于解释为什么推翻旧ABCD。它们不是当前计划或可执行旧应用，内容里的done/批准/“当前”均不继承。

- [旧任务](../../harness/archive/2026-09-10-tasks.json)、[旧需求](../../harness/archive/2026-09-10-requirements.json)、[旧验收定义](../../harness/archive/2026-09-10-evaluations.json)。其中历史证据路径可能已随旧开发清理，不用快照做活跃验收。
- 重规划前说明原文：[产品](2026-09-11-legacy-PRODUCT.txt)、[架构](2026-09-11-legacy-ARCHITECTURE.txt)、[调研](2026-09-11-legacy-RESEARCH.txt)、[路线](2026-09-11-legacy-ROADMAP.txt)、[可行性](2026-09-11-legacy-FEASIBILITY.txt)、[交接](2026-09-11-legacy-HANDOFF.txt)、[预算说明](2026-09-11-legacy-BUDGET.txt)、[harness说明](2026-09-11-legacy-HARNESS.txt)、[AGENTS](2026-09-11-legacy-AGENTS.txt)、[README](2026-09-11-legacy-README.txt)。纯文本保留原样，相对链接不作当前文件引用。

用户随后明确要求删除旧PDF开发、重新开始，替代“冻结源码保留”的安排。旧应用、依赖、测试、生成器、旧A阶段changes/evidence及ADR0001已从工作树移除。没有把旧源码搬进此目录。已提交历史仍可从Git查询。

未触碰真实论文库或 `.local/` 私有数据。此前已有的本机 `.local/replan-2026-09-11/` 快照保持不变，含原有未提交stage-a-close记录；它不是活跃开发内容，不应上传或自动恢复。

本轮调研的 `docs/evidence/replan-*` 和对应change record保留为**删除之前的历史检查结果**，其中旧应用15项失败并非已经修好。当前状态与命令见[HANDOFF](../HANDOFF.md)，唯一活跃路线见[ROADMAP](../ROADMAP.md)及 `harness/tasks.json`。
