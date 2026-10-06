# 论文图谱与聚类：开源调研与建议栈

> **界面名称（2026-10-06 起）**：顶栏只有 今日 / 论文库 / 画像。“论文库”页（原“论文整理”，顶栏曾另有一个“知识库”入口，指向同一页）里切换 **列表 | 图谱**（原“论文库 | 知识图谱”）；图谱里是 **论文关系 | 学习图**；原“整理建议”叫 **整理分类**。下文及更早的记录按当时的叫法保留，不逐条改写。

2026-09-11 调研；2026-09-14 开始实施。对应任务 `GRAPH-01`（stage `graph`，需求 `R-GRAPH`，验收 `E-GRAPH` / `E-ORGANIZATION`）。

当前切片选定 Cytoscape.js 3.33.1 + 现有 TF-IDF + NetworkX 3.2.1 内置 Louvain，见
[ADR 0006](decisions/0006-library-organization.md)。不升级现有 Python 构建环境，不引入
scikit-learn/HDBSCAN、本地模型或额外后端。自动分类限已收藏论文，先预览再应用；相似边不是引用边。
以下保留早期候选调研，不代表全部已接入或通过验收。

2026-10-01 修订：整理建议不再用 Louvain 社区或 OpenAlex topic。建议改由
`app/organization_facets.py` 生成：一级类别是画像固定关键词，子类是多篇标题共有的短语（见
[PRODUCT](PRODUCT.md) 同日一节）。NetworkX/Louvain 现在只用于图谱的相似边与布局分组。

2026-09-14 交互修订：采用 Cytoscape 内置 [CoSE 布局](https://js.cytoscape.org/#layouts/cose)
展示单论文节点、多方向连线与相似边。空方向不显示。`graph` 后台操作复用本地聚类结果的
相似边，但不写分类建议、不更改手工分类或笔记。已放置节点保留坐标，仅新节点补位；
全量重排须用户显式点击。当前没有引用关系、观点推断或凭空补足的链路。

类别和论文点击使用 550ms 缓入缓出的画布聚焦，突出相邻节点和连线，其余淡出。
连续点击取消旧动画；拖拽中断镜头移动；工具栏缩放围绕画布中心，尊重减少动态效果设置。
浏览器小型合成库已检查，尚无原生帧率或大规模真实库性能测量。

## 1. 目标

2026-09-15：按用户动效参考，增加基于 Cytoscape animate 的有界局部缓动，不运行常驻物理模拟。
只响应最多32个直接邻居，牵引上限18屏幕像素；释放余势最多10像素，约520ms内回到新落点。
邻居回到原坐标；保存使用独立稳定坐标而非动画帧坐标。首次分层淡入320–620ms；展开只移动
新增节点最多40屏幕像素；收起先淡出180ms。点击沿真实一跳关系做一次非方向性高亮。
不增加持续漂浮、长距离画布惯性或传播粒子。系统减少动态效果关闭上述非必要运动。

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
