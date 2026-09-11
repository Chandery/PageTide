# 论文图谱与聚类：开源调研与建议栈

2026-09-11。对应任务 `GRAPH-01`（stage `graph`，需求 `R-GRAPH`，验收 `E-GRAPH`）。**本页是调研与提案，不是已选型或已实现。**

## 1. 目标

把你库里的论文自动组织成图/簇：相似论文聚在一起，不同子领域/观点分开，分组标签可编辑。默认本地、免服务器、低资源。

## 2. 建议的最小栈（全部宽松许可、无模型权重、无服务器、CPU）

| 层 | 建议 | 许可 | 说明 |
|---|---|---|---|
| 内容向量 | scikit-learn `TfidfVectorizer` → `TruncatedSVD` | BSD-3 | 零下载，秒级 |
| 聚类 | `sklearn.cluster.HDBSCAN`（内置）或 KMeans/Agglomerative | BSD-3 | 已核验 sklearn 源码存在；无需单独装 hdbscan |
| 社区发现 | `networkx` + `python-louvain` | BSD-3 / BSD | 避免 GPL 的 igraph/leidenalg |
| 引用边 | `pyalex`（MIT）查 OpenAlex `referenced_works` / cites | MIT | 公开元数据，无需 key |
| 存储 | 优先沿用本地 **SQLite**；确需图查询再评估 DuckDB(+DuckPGQ) 或 Kuzu | MIT | 嵌入式、单文件 |
| 标签 | c-TF-IDF 式每簇 top term，本地计算并落库 | — | 零 token；标签可编辑 |
| 可视化 | 应用内 D3/cytoscape（MIT）；或导出 GraphML/GEXF 用 VOSviewer-Online（MIT） | MIT | 不引入服务器 |

**可选（需单独批准）**：一次性下载 `all-MiniLM-L6-v2`（~90 MB，Apache-2.0）或 SPECTER2（Apache-2.0）做语义向量，或用 BERTopic（MIT）包一层。这违反「默认不下载模型权重」，必须单独授权并实测 8GB 资源。

## 3. 零 token 与大模型的分工

- **零 API token**：元数据/引用抓取、TF-IDF+SVD、聚类、社区发现、建边、top-term 标签、存储、可视化、确定性画像更新。
- **可选便宜大模型**：仅在 top term 噪声大时给簇起自然语言名字，或写一句「A 子领域 vs B 的区别」。已批准用 `deepseek-flash`（`judge_relevance` 同类模式），按簇批量、按簇指纹缓存、只在成员变化时重算，经唯一预算网关。**不是必需。**

## 4. 淘汰/阻断

- **copyleft（若应用闭源分发需注意）**：python-igraph(GPL-2.0)、leidenalg(GPL-3.0)、Gephi(GPL-3.0)、LocalCitationNetwork(GPL-3.0)、Neo4j community(GPL-3.0)。优先 BSD/MIT 替代，或把 GPL 工具当可选 CLI。
- **服务器**：Neo4j、Memgraph(BSL，非 OSI 开源)——单用户本地应用不采用。
- **构建困难**：graph-tool（GPLv3、无 pip wheel）；Python 3.9 上独立 hdbscan 无 arm64 wheel（用 sklearn 内置即可）。
- **闭源产品**：CiteSpace、VOSviewer 桌面版、Connected Papers、Litmaps、ResearchRabbit、Inciteful、SciSpace——只能借鉴形式，不能复用代码。

## 5. 资源预期（估算，**未实测**）

几千篇摘要量级：TF-IDF+SVD 秒级、<1 GB RAM；UMAP 数秒到数分钟、数百 MB；本地 MiniLM/SPECTER2 推理 CPU 约 1–5 分钟、~2 GB。结论：**纯 sklearn 路径在 8GB M1 上最稳**。

## 6. 未决与风险

- **「不同观点分开」比「相似聚类」更难**：簇通常能分出子领域，但观点对立往往共享词汇，可能需要 aspect/立场抽取或人工标注，属于研究性风险；首版建议先做「相似聚合 + 子领域分开 + 可编辑标签」，观点维度单独实验。
- **可视化交互**（缩放/筛选/高亮）需要单独的 UI 验收，不属于 `E-GRAPH` 的核心断言。
- **Python 版本**：BERTopic/sklearn HDBSCAN 需要 Python ≥3.10。若采用这些，应用运行时建议抬到 3.11；仓库 harness 脚本可继续只用 3.9 标准库。这是一个新的平台决策点，未批准。
- 引用边依赖 OpenAlex 覆盖与许可；缺边或缺摘要必须可见，不能假装图是完整的。
