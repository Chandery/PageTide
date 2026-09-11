# 测试领域与种子（用户确认，2026-09-11）

2026-09-11。本页记录 owner 确认的首个测试领域、语言与正例种子，作为 `PLAN-02` / `DATA-01` 的实验输入。**这些是用户声明的计划输入，未独立核验**；种子标题/venue 以用户提供为准，尚未解析成规范 ID。

## 决定

- **领域**：人工智能 / **world models**（世界模型）。英文论文为主。
- **语言**：候选与原文为英文；界面、推荐理由与 AI 速览/回答用中文。
- **首版范围**：推荐与画像核心 + **PDF 本地下载归档** + **AI 每日速览与追问**；笔记/高亮/划词后置。
- **平台**：仅 macOS、免服务器、本地保存。
- **论文软件**：Zotero（首版只评估只读/导入，不写入宿主库）。
- **PDF 存放**：首版默认写本机文件夹；Zotero 附件写入后置且需单独授权。
- **AI 开销上限**：owner 已接受（后台 12k/交互 35k/合计 45k 每日、800k 每月、$0.10/日、$1.00/月）。
- **外部外发**：**不允许**把种子/画像 ID 发给外部推荐服务。
- **排序**：允许显式启用的稀疏 + 大模型混合重排（[ADR 0003](decisions/0003-hybrid-llm-ranking.md)），默认关闭。
- **新增功能**：论文图谱/聚类（`GRAPH-01`，调研进行中）。

## 正例种子（10 篇，owner 提供）

| 推荐度 | 论文 | 时间 / Venue | 核心看点 |
|---|---|---|---|
| ⭐⭐⭐⭐⭐ | A Definition and Roadmap for World Models | 2026, arXiv | 建立整体认识：什么才算 world model、预测什么、怎么训练、未来路线 |
| ⭐⭐⭐⭐⭐ | V-JEPA 2: Self-Supervised Video Models Enable Understanding, Prediction and Planning | 2025 | Meta / Yann LeCun 路线，latent-space prediction + planning |
| ⭐⭐⭐⭐⭐ | DINO-WM: World Models on Pre-trained Visual Features enable Zero-shot Planning | ICML 2025 | 不重建像素，直接预测 DINO latent，zero-shot planning |
| ⭐⭐⭐⭐⭐ | LeWorldModel: Stable End-to-End Joint-Embedding Predictive Architecture from Pixels | 2026, arXiv | JEPA 新进展，小模型、端到端、无需 pretrained encoder |
| ⭐⭐⭐⭐ | DreamerV3 / Mastering diverse control tasks through world models | Nature 2025 | 经典 Model-based RL 世界模型，150+ control tasks |
| ⭐⭐⭐⭐ | Genie: Generative Interactive Environments | ICML 2024 | Foundation World Model 代表作，从无标注视频学 latent action |
| ⭐⭐⭐⭐ | Cosmos World Foundation Model Platform for Physical AI | 2025 | NVIDIA Physical AI，机器人 + 自动驾驶 + 生成式世界模拟 |
| ⭐⭐⭐⭐ | IRASim: A Fine-Grained World Model for Robot Manipulation | ICCV 2025 | action-conditioned video world model，机器人操作 |
| ⭐⭐⭐⭐ | Wonder: Video World Model Done Better | 2026, arXiv | 实时、可控、长时序 video world model |
| ⭐⭐⭐⭐ | SolarWM: Open Data and Scalable Training for Long-Horizon Video World Models | 2026-09, arXiv | 很新，长时序、实时交互、开放数据与训练 pipeline |

**反例**：暂无。按规则记为未知，**不自动制造负标签**；之后可由你补充 3–5 篇「看起来相关但不想看」及原因。

**规范 ID（DATA-01 已解析 10/10）**：完整机器可读版在 `harness/seeds.json`。其中 A Definition and Roadmap for World Models = arXiv `2607.06401`，Wonder: Video World Model Done Better = arXiv `2607.26037`（owner 提供）；DreamerV3 为 Nature DOI，LeWorldModel 只有 OpenAlex ID。

## 隐私与外发边界

- 私人种子/兴趣 ID 本身揭示研究方向。owner 已明确**不允许**把种子/画像 ID 发送给任何外部推荐服务（如 Semantic Scholar 推荐 API）；只允许公开元数据查询（按关键词/分类）。
- 本页只描述领域与种子清单；真实实验用的画像文件与请求快照应放在 `.local/`（gitignored），不随仓库分发。
- 种子解析成规范 ID、版本去重和时间切分的具体结果，由 `DATA-01` 记录，不能在本页预先假定成功。

## 下一步

1. 冻结「相关/有用」标签定义、时间切分、正向增益指标与样本量（`PLAN-02` 收尾）。
2. `DATA-01`：把上述种子解析为 arXiv/OpenAlex ID，测领域覆盖、摘要可用率、去重与时间语义。
3. `REUSE-01`：在隔离目录跑 ASReview / arxiv-sanity-X 的受限探针。
