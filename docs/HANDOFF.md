# 当前交接：推荐优先路线、复用调研与行动前 token 预算

2026-09-11。旧 ABCD 已退出执行；本轮完成**复用调研、S0–S6 阶段计划、行动前 token 预算提案、harness 说明**，并继续清理旧应用。**新实现未批准、未开始；推荐质量、画像收益与 AI 成本均未实测。**

## 当前状态

- `PLAN-01` 完成（调研与重规划）。`CLEAN-01`、`BUDGET-01` 处于 `review`（实现完成、等待独立审查）；`PLAN-02` 现为 `in_progress`（领域/种子/首版范围已确认；AI 上限已获 owner 批准；待冻结实验指标）。`REUSE-01`、`DATA-01` 及之后尚未开始。
- owner 已确认 AI 开销上限（`budget.json` `approved_by_owner=true`）、不允许外发私人种子/画像 ID、PDF 默认写本机、允许显式启用的混合大模型重排（[ADR 0003](decisions/0003-hybrid-llm-ranking.md)，`llm_rerank` 默认关且未获批额度）。论文图谱/聚类调研进行中（`GRAPH-01`）。
- 新实施批准为 `false`，预算批准为 `false`；agent 不自批。
- 活跃任务与依赖只在 `harness/tasks.json`（stages: research/benchmark/feedback/reading/assist/delivery/release）。旧 A-01～A-06 不再活跃。

## 本轮交付

- [DOMAIN](DOMAIN.md)：已确认测试领域（英文 AI / world models）与 10 篇正例种子，及外发边界。
- [KNOWLEDGE-GRAPH](KNOWLEDGE-GRAPH.md)：论文图谱/聚类的开源调研与建议栈（sklearn HDBSCAN + networkx/python-louvain + OpenAlex 引用边，零 token）。
- [EVALUATION](EVALUATION.md)：大模型辅助标注 + 人工抽检的评估协议；[ADR 0004](decisions/0004-evaluation-annotator-separation.md) 规定运行时（DeepSeek）与评估裁判（taomu/gpt-6-astra）分离。
- [BRAINSTORM](BRAINSTORM.md)：需求拆解、算法选型、A/B/C 路线、「没空/暂停/督促」语义、第一版形态候选。
- [RESEARCH](RESEARCH.md)：新增 ASReview（Apache-2.0、纯 sklearn、显式相关/不相关、主动学习 querier）为首选画像内核；补齐 txtai/paperetl、Paper-Agent-Zotero、arXivDigest、rank_bm25、抓取库；列出「没人解决好的缺口」。
- [ROADMAP](ROADMAP.md)：按风险排的 S0–S6，覆盖推荐/画像/阅读/AI 四类能力，含实验协议与停止条件。
- [BUDGET](BUDGET.md) + `harness/budget.json` + 生成表：**核心零 token**（搜索/去重/排序/画像/归档/DB 维护）；运行时 AI 层已批准额度（后台 26k/交互 35k/合计 55k 每日、150 万每月、$0.15/日、$1.50/月），含 `llm_rerank`（默认关闭）；评估裁判单独走 `evaluation` 段（taomu，只计 token）。除两次探针外均未实测。
- `prompts/`：7 个操作合同（速览、重排、标注、追问、周报、划词、关键词扩展），每个都声明有界上下文与不可信源文本规则。
- Harness：新增「孤儿 evaluation 检查」与技能描述长度预算；`docs/HARNESS.md` 记录吸收的开源做法。

### 检查边界（精确结果见 `docs/evidence/2026-09-11-plan02-decisions-and-graph-checks.txt`）

最终结果：预算检查 exit 0；仓库检查 exit 0；**Python 41 测试通过**；`check --release` exit 1（预期阻断：实现未批准、enforcement/tokenizer 未实现、全部 blocking gate 为 `not_run`）。**没有独立审查，没有运行任何上游候选。** 两次真实模型调用都只是非私密探针（`docs/evidence/2026-09-11-deepseek-probe.txt`、`docs/evidence/2026-09-11-taomu-probe.txt`），不是产品测量，也不代表任何 gate 通过。

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

- 按用户要求已删除全部旧 Git 历史并重建仓库，不含旧 A-01～A-06 任何提交。当前历史为：初始基线 + 规划基线 v2（`git log --oneline` 查看）。未配置远程、未 push；用户将自行新建远程仓库。
- 旧历史保险备份在 `.local/git-history-backup-before-reset.bundle`（受 `.gitignore` 忽略，不会提交或推送；确认不再需要可删除）。
- `changes/` 里的记录随对应提交一起进入历史；之后每个新工作单元再新建 `changes/<id>.json`（此时 `harness.py review` 才有可比较的工作树差异）。
- 旧说明与旧任务快照在 `docs/archive/`、`harness/archive/`，不继承完成/批准结论。`.local/` 是本机私有数据，不应提交。

## 下一步

已确认（2026-09-11）：领域 = 英文 AI / world models；10 篇正例种子（无反例，记未知）；首版 = 推荐画像核心 + **PDF 下载归档** + **AI 每日速览与追问**；仅 macOS、本地保存；论文软件 Zotero（只读/导入）。详见 [DOMAIN](DOMAIN.md)。

`PLAN-02` 收尾仍需：

1. 冻结「相关/有用」标签定义、静态与滚动时间切分、正向增益指标/最小有意义差值/样本量。
2. ~~若启用混合重排：批准 `llm_rerank` 的新增每日/每月额度~~ —— **已完成（owner 批准，默认仍关闭）**。
3. 可选的 3–5 篇反例（owner 暂无法提供，保持未知）。

已解决：AI 上限（已接受，含 `llm_rerank`）、数据外发（不允许私人ID外发，只发公开元数据）、PDF 存放（本机文件夹）。
- 新增 `LABEL-01` 大模型辅助评估标注；运行时用 DeepSeek 官方，评估裁判用 taomu/gpt-6-astra（[ADR 0004](decisions/0004-evaluation-annotator-separation.md)）。两个 key 都**仅存于 `.local/`（未入 Git）**，建议实验后轮换；已跑通两次非私密探针（deepseek 122 token；taomu 发现每次注入 ~4.4k 隐藏 token）。
- 随后跑 `REUSE-01`（ASReview/X 受限探针）与 `DATA-01`（领域覆盖），再按 [EVALUATION](EVALUATION.md) 跑 `LABEL-01`。**不开始新的 PDF 阅读器平台，不自动执行整条路线。**
