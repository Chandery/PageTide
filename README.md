# PaperDigHelper

**论文推荐与可解释用户画像工具。** 目标是推荐值得看的论文，基于明确反馈改进下一批推荐，并把画像做成你可检查、可修改、可撤销的数据；论文整理、笔记与 AI 速览是在此之上的第二层。

2026-09-11：旧 ABCD 路线已退出执行，旧应用、未完成阅读器修复和依赖已删除。本轮完成了**复用调研、阶段计划、行动前 token 预算提案和 harness 说明**；**新实现尚未批准或开始，推荐质量与 AI 成本均未实测**，当前只有规划文档和标准库仓库检查，没有可运行应用。

## 阅读顺序

1. [产品目标](docs/PRODUCT.md)：推荐与画像的最短闭环，以及首版与后置范围。
2. [测试领域与种子](docs/DOMAIN.md)：英文 AI / world models 与 10 篇正例种子（无反例）。
3. [设计头脑风暴](docs/BRAINSTORM.md)：需求拆解、算法选型、候选路线与形态取舍。
4. [开源与数据源调研](docs/RESEARCH.md)：ASReview/X/lite/PaperFlow 等实际代码、许可与缺口；论文图谱/聚类见 [KNOWLEDGE-GRAPH](docs/KNOWLEDGE-GRAPH.md)。
5. [路线与阶段](docs/ROADMAP.md)：S0–S6、实验协议与停止条件；标注/裁判协议见 [EVALUATION](docs/EVALUATION.md)。
6. [预算](docs/BUDGET.md)与[生成表](docs/BUDGET.generated.md)：核心 0 token；AI 层每日最低约 4,500 token 参考、上限约 10,800（未批准）。
7. [Harness](docs/HARNESS.md) 与 [当前交接](docs/HANDOFF.md)：如何记录、审查、验证与换 agent。
8. 任务与验收事实源：`harness/tasks.json`、`harness/requirements.json`、`harness/evaluations.json`。

## 暂保留的安全边界

本地保存、低资源、无默认模型权重下载、无托管后端/云同步/遥测；模型和新数据外发先授权；没选/没空/看不懂不等于不喜欢。论文软件连接和预览器都不是核心前提。

## 规划一致性检查

Python 3.9+、标准库，无应用依赖：

```sh
python3 scripts/budget.py --check
python3 scripts/harness.py check
python3 -m unittest discover -s tests -v
```

这些检查只证明预算算术、仓库契约和 harness 一致性，**不证明推荐质量、真实GUI、模型计费或性能**。发布检查 `python3 scripts/harness.py check --release` 应保持阻断。

## 下一步

领域/种子/首版范围已确认（英文 AI / world models，10 篇正例；首版含 PDF 下载与 AI 速览+追问；见 [DOMAIN](docs/DOMAIN.md)）。仍需确认 AI 每日/每月 token 与金额上限、数据外发范围、PDF 存放位置。随后在隔离目录跑上游复用（ASReview/X）与数据覆盖探针。
