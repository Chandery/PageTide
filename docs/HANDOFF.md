# 当前交接：推荐优先路线、复用调研与行动前 token 预算

2026-09-11。旧 ABCD 已退出执行；本轮完成**复用调研、S0–S6 阶段计划、行动前 token 预算提案、harness 说明**，并继续清理旧应用。**新实现未批准、未开始；推荐质量、画像收益与 AI 成本均未实测。**

## 当前状态

- `PLAN-01` 完成（调研与重规划）。`CLEAN-01`、`BUDGET-01` 处于 `review`（实现完成、等待独立审查）；`PLAN-02` 及之后全部未开始，`PLAN-02` 因等待你的输入而 `blocked`。
- 新实施批准为 `false`，预算批准为 `false`；agent 不自批。
- 活跃任务与依赖只在 `harness/tasks.json`（stages: research/benchmark/feedback/reading/assist/delivery/release）。旧 A-01～A-06 不再活跃。

## 本轮交付

- [BRAINSTORM](BRAINSTORM.md)：需求拆解、算法选型、A/B/C 路线、「没空/暂停/督促」语义、第一版形态候选。
- [RESEARCH](RESEARCH.md)：新增 ASReview（Apache-2.0、纯 sklearn、显式相关/不相关、主动学习 querier）为首选画像内核；补齐 txtai/paperetl、Paper-Agent-Zotero、arXivDigest、rank_bm25、抓取库；列出「没人解决好的缺口」。
- [ROADMAP](ROADMAP.md)：按风险排的 S0–S6，覆盖推荐/画像/阅读/AI 四类能力，含实验协议与停止条件。
- [BUDGET](BUDGET.md) + `harness/budget.json` + 生成表：**核心零 token**（搜索/去重/排序/画像/归档/DB 维护）；AI 层每日速览+周报参考约 **4,500 token/天**、上限约 **10,800/天**，月度上限约 19.2 万；全部为**未批准、未实测**提案。
- `prompts/`：5 个操作合同（速览、追问、周报、划词、关键词扩展），每个都声明有界上下文与不可信源文本规则。
- Harness：新增「孤儿 evaluation 检查」与技能描述长度预算；`docs/HARNESS.md` 记录吸收的开源做法。

## 检查边界（精确结果见 `docs/evidence/2026-09-11-plan-budget-checks.txt`）

最终结果：预算检查 exit 0；仓库检查 exit 0；**Python 40 测试通过**；`check --release` exit 1（预期阻断：批准缺失、enforcement/tokenizer 未实现、20 个 blocking gate 全 `not_run`）。自查见 `docs/evidence/2026-09-11-plan-budget-self-review.md`。**没有独立审查，没有运行任何上游候选，没有发出任何模型请求。**

```sh
python3 scripts/budget.py --check
python3 scripts/harness.py check
python3 -m unittest discover -s tests -v
python3 scripts/harness.py check --release    # 应阻断
python3 scripts/harness.py review changes/2026-09-11-recommendation-plan-and-budget.json
```

## 预算与安全

- 核心路径 0 模型 token；真实成本是元数据 API 请求、CPU/RSS/磁盘/时间，尚未测量。
- AI 层价格按 DeepSeek peak cache-miss（$0.30/$1.20 per 1M），来源已核查 2026-09-11；未做离线 tokenizer 校准。
- 旧 Key、旧校准、旧批准都不继承；未授权不发起真实调用、不下载模型权重、不外发私人种子/笔记。
- 保留本地优先、低资源、不把没空/难懂当不喜欢、原件/来源保护等边界。

## 工作区与历史

- 按用户要求已删除全部旧 Git 历史并重建仓库：当前只有**一个初始基线提交**（`git log -1` 查看），不含旧 A-01～A-06 任何提交。未配置远程、未 push；用户将自行新建远程仓库。
- 旧历史保险备份在 `.local/git-history-backup-before-reset.bundle`（受 `.gitignore` 忽略，不会提交或推送；确认不再需要可删除）。
- `changes/` 里的两条记录现在是**基线内**的历史记录；之后每个新工作单元再新建 `changes/<id>.json`（此时 `harness.py review` 才有可比较的工作树差异）。
- 旧说明与旧任务快照在 `docs/archive/`、`harness/archive/`，不继承完成/批准结论。`.local/` 是本机私有数据，不应提交。

## 下一步（等你）

1. 研究方向/领域与语言（中英？），允许先粗略。
2. 5–10 篇有用的论文；可选 3–5 篇「看起来相关但不想看」及原因。
3. 是否首版就包含阅读/笔记/划词层；是否默认开启 AI 速览。
4. 是否接受 [BUDGET](BUDGET.md) 提案的每日/每月 token 与金额上限。
5. 确认首版只做 macOS、免服务器、本地保存。

有了 1/2 才可跑 `REUSE-01`（ASReview/X 受限探针）与 `DATA-01`（领域覆盖）。**不开始新的 PDF 阅读器平台，不自动执行整条路线。**
