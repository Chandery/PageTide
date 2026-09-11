# PaperDigHelper

本地优先、面向低算力 Mac 的论文发现、阅读与知识整理工具。

**当前交付是 Stage 0：规划、调研、预算与项目 harness，不是可运行的论文应用。** A/B/C/D 均纳入首版路线，尚未实现。没有调用付费模型，没有实测产品内存、推荐质量或真实 API token 用量。

## 从这里开始

- 产品与 brainstorming：[docs/PRODUCT.md](docs/PRODUCT.md)
- 架构和数据边界：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- 调研与出处：[docs/RESEARCH.md](docs/RESEARCH.md)
- 可行性审查与待验证风险：[docs/FEASIBILITY.md](docs/FEASIBILITY.md)
- 阶段、任务与验收：[docs/ROADMAP.md](docs/ROADMAP.md)、[harness/tasks.json](harness/tasks.json)
- 预算方法：[docs/BUDGET.md](docs/BUDGET.md)
- **可复算预算表**：[docs/BUDGET.generated.md](docs/BUDGET.generated.md)
- 项目维护机制：[docs/HARNESS.md](docs/HARNESS.md)
- agent 接手入口：[AGENTS.md](AGENTS.md)
- 当前交接：[docs/HANDOFF.md](docs/HANDOFF.md)

## 本地检查，不访问网络、不调用模型

要求 Python 3.9+ 和 Git。检查工具只用 Python 标准库，应用后续仍采用 Electron / React / TypeScript / SQLite / PDF.js。

```sh
python3 scripts/budget.py
python3 scripts/budget.py --check
python3 scripts/harness.py check
python3 -m unittest discover -s tests -v
```

更新 `harness/budget.json` 后，用 `python3 scripts/budget.py --write` 重建预算表。生成表不手工编辑。

## 关键边界

- 不部署后端、不默认跑本地大模型或 embedding 模型。
- 检索、排序、数据库、归档、基础画像维护使用本地确定性逻辑，运行时 LLM token = 0。
- 云模型仅用于明确登记、限额的摘要、问答等能力。外部数据源费用与 LLM token 分开。
- 本地保存不等于云模型看不到所发送的文本；默认不上传私人笔记和整个论文库。
- 预算表是场景测算与设计限额，不是账单、质量保证或已实现的运行时拦截器。
- 用户尚未批准预算基线；没有 API Key 时，任何 agent 不得以“验证”为由发起付费调用。

本仓库已在本地初始化 Git；没有远程仓库、提交或发布。应用运行数据必须放在 Git 之外，示例与评估数据须脱敏。
