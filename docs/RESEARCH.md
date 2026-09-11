# 重新调研：先复用论文推荐与画像系统

核验日期：2026-09-11。目标是减少自建工作并验证推荐价值，不为旧 Electron/PDF 架构寻找理由。

**结论：画像与排序内核优先评估 `asreview/asreview` 的模型/querier 层（Apache-2.0、纯 sklearn、显式相关/不相关、有主动学习策略）；整链路仍先验证 arxiv-sanity-X 的纯推荐子集能否直接承担闭环，以 arxiv-sanity-lite 做轻量基线和兜底。不要先新建阅读器，也不要直接 fork 一个功能最多的 agent 项目。** 没有“开箱即用的每日五篇 + 可撤销画像”产品，需要的是一层薄适配，而不是重写稀疏算法或元数据客户端。X 如果不能通过小范围依赖/配置适配独立运行，就转 lite/ASReview 组合，不为关闭它的 PDF/AI 子系统再做一轮大重构。

本次核验了官方 README、固定commit代码、许可证和测试配置；未安装运行这些候选、未执行其测试、未访问你的论文库、未调用模型。这里的“有实现”不等于“实测好用”，尚无用户领域推荐准确率或 Mac 资源测量。

## 1. 开源候选：哪里可以不再造轮子

| 项目 / 固定快照 | 能复用什么 | 主要不适配点 | 结论 |
|---|---|---|---|
| [arxiv-sanity-X](https://github.com/xihuai18/arxiv-sanity-x/tree/f6c6b0a961776a18cfc73859fab5cd8ad2986245) · MIT | 正/负标签、撤销、组合标签、排序界面、本地状态、阅读列表；TF-IDF-only路径 | 默认开启embedding/摘要/备份push；标准依赖仍含Intel扩展；没有本项目的完整画像事件语义 | **先做受限适配探针**，通过就复用整套核心，不重新写标签UI/排序服务 |
| [arxiv-sanity-lite](https://github.com/karpathy/arxiv-sanity-lite/tree/d7a303b410b0246fbd19087e37f1885f7ca8a9dc) · MIT | TF-IDF/SVM兴趣排序、标签存储、词权重解释和简单UI | 依赖钉在旧版本；无独立显式负反馈；测试与单类输入保护不足 | **轻量基线/兜底**，优先复用内核而非移植重写 |
| [PaperFlow](https://github.com/OpenRaiser/PaperFlow/tree/4a835e737490785b3ce51025c85b630cd224318c) · MIT | 结构化画像、长短期兴趣、反馈追踪、本地GUI | 有效语义推荐依赖embedding；CLI首次未选择会形成weak skipped；agent/PDF/Wiki范围大 | **先借鉴画像与反馈契约**；如要整体采用，需另批模型路线并修正反馈语义 |
| [zotero-arxiv-daily](https://github.com/tidedra/zotero-arxiv-daily/tree/2879bcdf4ae3f021b77faa84bdfd01185509ebf2) · AGPLv3 | 书库驱动日推、加权相似度与邮件交付 | 不是显式反馈闭环；本地/API embedding、LLM及重依赖；远端模式发送书库摘要 | **可选日推产品**，不是当前核心的先决条件 |

[precision-papers](https://github.com/guanqun-yang/precision-papers) 也展示“书库 → TF-IDF/SVM → 日推”的复用路线，但与 lite 重叠，本次只做README初筛，不宣称已经核验其全套许可/实现。

### arxiv-sanity-X：不是下载后直接启动默认daemon

- [排序代码](https://github.com/xihuai18/arxiv-sanity-x/blob/f6c6b0a961776a18cfc73859fab5cd8ad2986245/backend/services/search_service.py#L1120-L1210) 将正例记为1，未标注记为背景0，明确负例提高样本权重；使用LinearSVC。这不是概率，也不是严格正例-未标注学习算法。
- [反馈API](https://github.com/xihuai18/arxiv-sanity-x/blob/f6c6b0a961776a18cfc73859fab5cd8ad2986245/backend/services/tag_service.py#L375-L405) 区分正向、负向与remove。没有发现“浏览没点就新增dislike”的逻辑，但“背景负类参与训练”和“用户明确不喜欢”必须分开保存与展示。
- [运行配置](https://github.com/xihuai18/arxiv-sanity-x/blob/f6c6b0a961776a18cfc73859fab5cd8ad2986245/config/settings_runtime.py#L8-L35) 默认summary、embeddings、git backup/push为true。实际push还需有效remote，但验证前必须全部关闭，不装成“默认离线产品”。
- [pyproject](https://github.com/xihuai18/arxiv-sanity-x/blob/f6c6b0a961776a18cfc73859fab5cd8ad2986245/pyproject.toml#L14-L78) 把Torch/vLLM/MinerU拆成可选，但仍必需`scikit-learn-intelex`。其[官方平台说明](https://uxlfoundation.github.io/scikit-learn-intelex/2025.11/quick-start.html)的预构建包为Windows/Linux x86-64；不能承诺Mac arm64原样安装。
- 好消息是[实际导入](https://github.com/xihuai18/arxiv-sanity-x/blob/f6c6b0a961776a18cfc73859fab5cd8ad2986245/backend/legacy.py#L231-L238)允许回退普通sklearn，所以“移除不适用加速依赖”是小范围适配候选，而非重写算法的理由。默认数值线程数也需限制，未测前不称轻量。
- [同一运行配置的前端选项](https://github.com/xihuai18/arxiv-sanity-x/blob/f6c6b0a961776a18cfc73859fab5cd8ad2986245/config/settings_runtime.py#L141-L144)还默认启用jsDelivr CDN。探针必须检查浏览器与后端两端的出站，把第三方脚本/静态资源本地化；只关闭Python模型调用不足以称离线。
- [embedding异常路径](https://github.com/xihuai18/arxiv-sanity-x/blob/f6c6b0a961776a18cfc73859fab5cd8ad2986245/tools/compute.py#L542-L572)存在随机向量回退；纯词法实验必须确认完全不进入该路径。
- 有[推荐回归测试](https://github.com/xihuai18/arxiv-sanity-x/blob/f6c6b0a961776a18cfc73859fab5cd8ad2986245/tests/unit/test_search_service.py#L494-L592)，但[CI](https://github.com/xihuai18/arxiv-sanity-x/blob/f6c6b0a961776a18cfc73859fab5cd8ad2986245/.github/workflows/ci.yml#L21-L37)不覆盖daemon，后台行为需单独截获网络验证。

### lite：真正的轻量候选，但有年代和语言限制

[特征代码](https://github.com/karpathy/arxiv-sanity-lite/blob/d7a303b410b0246fbd19087e37f1885f7ca8a9dc/compute.py#L18-L57) 使用标题、摘要、作者，英文unigram/bigram TF-IDF、默认20,000特征、float32稀疏矩阵。[SVM排序](https://github.com/karpathy/arxiv-sanity-lite/blob/d7a303b410b0246fbd19087e37f1885f7ca8a9dc/serve.py#L120-L170) 把标签内论文作正例，其余作背景类。它不需要LLM、GPU或神经模型权重。

但2022年源码快照的[依赖](https://github.com/karpathy/arxiv-sanity-lite/blob/d7a303b410b0246fbd19087e37f1885f7ca8a9dc/requirements.txt)含Flask2.0.2、NumPy1.21.4、sklearn1.0.1。现代Python/macOS兼容性、全正例/无正例、小语料空词表、中文与跨语言均需测试。每次更新建特征、请求时训练SVM的开销不能用作者“轻量”自述代替测量。

### PaperFlow：最值得吸收的是反馈经验，也最要查语义

它的[画像模板](https://github.com/OpenRaiser/PaperFlow/blob/4a835e737490785b3ce51025c85b630cd224318c/config/user-profile-template.json)确有主题、方法、作者/机构、阅读历史与兴趣向量。[更新实现](https://github.com/OpenRaiser/PaperFlow/blob/4a835e737490785b3ce51025c85b630cd224318c/skills/profile-updater/scripts/update_profile.py#L1296-L1402)区分长短窗口；但来源/期刊启发式的“质量分”不能当论文质量真值。

[CLI反馈](https://github.com/OpenRaiser/PaperFlow/blob/4a835e737490785b3ce51025c85b630cd224318c/agents/feedback-agent/main.py#L646-L776)会把首次未选择的其余论文变成弱负反馈；[GUI](https://github.com/OpenRaiser/PaperFlow/blob/4a835e737490785b3ce51025c85b630cd224318c/deployments/desktop/shared/agents.py#L2473-L2548)将selected/skipped/later分开。不能笼统说所有入口都正确或都错误，必须统一到本产品“没选不是不喜欢”的规则。

[README和provider](https://github.com/OpenRaiser/PaperFlow/blob/4a835e737490785b3ce51025c85b630cd224318c/paperflow/providers/embedding.py#L51-L152)也表明mock/hash适合演示，不证明语义推荐有效。没有批准模型路线前，不把mock跑通当成推荐验收。

### zotero-arxiv-daily：书库是兴趣代理，不是你确认的全部喜好

[排序实现](https://github.com/tidedra/zotero-arxiv-daily/blob/2879bcdf4ae3f021b77faa84bdfd01185509ebf2/src/zotero_arxiv_daily/reranker/base.py#L10-L19)按书库加入时间的排序位置加权相似度，不是按相隔天数衰减；没有独立like/dislike/skip画像。

[API reranker](https://github.com/tidedra/zotero-arxiv-daily/blob/2879bcdf4ae3f021b77faa84bdfd01185509ebf2/src/zotero_arxiv_daily/reranker/api.py#L6-L22)发送候选和选定书库摘要；[本地模式](https://github.com/tidedra/zotero-arxiv-daily/blob/2879bcdf4ae3f021b77faa84bdfd01185509ebf2/src/zotero_arxiv_daily/reranker/local.py#L7-L30)启用`trust_remote_code=True`；[主流程](https://github.com/tidedra/zotero-arxiv-daily/blob/2879bcdf4ae3f021b77faa84bdfd01185509ebf2/src/zotero_arxiv_daily/executor.py#L93-L123)还生成TL;DR并邮件发送。GitHub Actions的免费配额不等于本地、无模型开销或无数据外传。

## 1b. 追加盘点：最接近「可复用画像引擎」的项目（2026-09-11）

在上表之外扩大搜索后，出现一个比 arxiv-sanity-X 更适合**画像与反馈**部分、且许可和算力都干净的候选。以下许可已用 LICENSE 原文核验（txtai/ASReview/Paper-Agent-Zotero/arXivDigest），其余以 GitHub 元数据核验并注明。

| 项目 | 许可 | 栈 / 本地 | 排序与画像 | 结论 |
|---|---|---|---|---|
| [asreview/asreview](https://github.com/asreview/asreview) | Apache-2.0（LICENSE原文） | Python + numpy/pandas/scikit-learn/Flask，CPU，无 torch | TF-IDF + NB/SVM/LogReg/RF；主动学习 querier（Max/Uncertainty/Random/Hybrid）；显式 relevant/irrelevant；项目持久化 | **首选抽取画像引擎**；UX 是系统综述筛选，不是每日五篇 |
| [dorianbrown/rank_bm25](https://github.com/dorianbrown/rank_bm25) | Apache-2.0（LICENSE原文） | 纯 Python | BM25 检索 | **可直接用的最小零token检索库** |
| [neuml/txtai](https://github.com/neuml/txtai) / [paperetl](https://github.com/neuml/paperetl) | Apache-2.0 | Python，本地 | 词法+向量混合索引、RAG、PDF→SQLite ETL | 借用基础设施；默认保持词法，向量按你的规则后置 |
| [Marverlises/Paper-Agent-Zotero](https://github.com/Marverlises/Paper-Agent-Zotero) | Apache-2.0（LICENSE原文） | Python，MiniLM CPU | 对 Zotero 语料的余弦 + 时间指数加权；**隐式反馈（书库）** | 若要向量路线可借；默认路径不启用权重下载 |
| [iai-group/arXivDigest](https://github.com/iai-group/arXivDigest) | MIT（LICENSE原文） | Flask+MySQL+Elasticsearch，服务端 | BM25/语义 + 多臂老虎机/交错实验 | **借“交错在线评估”设计**；拒绝其服务端栈 |
| [AutoLLM/ArxivDigest](https://github.com/AutoLLM/ArxivDigest) | MIT | Python + OpenAI | GPT pointwise 1–10 打分 | 只借提示思路；不符合零token与隐私边界 |
| [karpathy/arxiv-sanity-preserver](https://github.com/karpathy/arxiv-sanity-preserver) | MIT | Flask+sklearn | `LinearSVC(class_weight=balanced)` + 余弦 | 经典但 2021 停更，无 dislike/undo |
| 抓取库：[arxiv.py](https://github.com/lukasschwab/arxiv.py) / [pyalex](https://github.com/J535D165/pyalex) / [semanticscholar](https://github.com/danielnsilva/semanticscholar) / [paperscraper](https://github.com/jannisborn/paperscraper) | MIT | Python | 元数据客户端，无排序 | **复用，不自造客户端** |

**淘汰与阻断**：`researchpooler`、`sepehr125/arxiv-doc2vec-recommender` 无 LICENSE（等于保留所有权利）；`Kaffaljidhmah2/Arxiv-Recommender`、`paperless-ngx`、`papis`、`LocalCitationNetwork` 为 GPL-3.0；`zotero-arxiv-daily`、多个 `windingwind/*` Zotero 插件、`zotero-scihub` 为 AGPL-3.0（网络 copyleft，分发前单独审）；`citeomatic`(2020)、`scibert`(2022) 等已停更或需 GPU/大数据。`xihuai18/arxiv-sanity-x` 的 GitHub 元数据为 NOASSERTION，但 LICENSE 原文为 MIT，以原文为准。

**这些系统都没解决好的缺口（正是本产品的差异化）**：

1. 透明、**可编辑的按主题画像**（能增删兴趣权重）——现成系统要么是不透明向量，要么只是配置关键词。
2. **显式负向记忆**——多数只建模正例（书库/收藏），ASReview 是二分类筛选语义，不等于「明确不喜欢」。
3. **撤销与画像回滚**——在 arxiv-sanity、ASReview 及 Zotero 工具中未发现后端 undo。
4. 少标签冷启动且**不把无活动当负例**。
5. 严格 ≤5 篇/天预算下的**多样性/去重 + 「为什么推它」解释**。
6. **零 token 排序**：2024–2026 的新项目几乎都依赖 OpenAI；真正零token的只有 ASReview/arxiv-sanity/BM25 一类。
7. **可移植、带版本的私有画像格式**，跨 arXiv/OpenAlex/S2。

**对选型的影响**：`REUSE-01` 不再只测 X。建议优先评估 **ASReview 的模型/querier 层** 作为画像与排序内核（许可与算力最干净），X/lite 作为整链路与兜底候选；数据接入优先 `arxiv.py`/`pyalex`，检索可用 `rank_bm25`。仍然没有「开箱即用的每日五篇 + 可撤销画像」产品，这部分需要薄适配层，但**不需要重写稀疏算法或元数据客户端**。

## 1c. 论文图谱与聚类（本轮新增，owner 请求）

owner 新增需求：自动把论文分类、相似聚类、不同观点/子领域分开，并调研开源知识图谱方案。完整调研与建议栈见 [KNOWLEDGE-GRAPH](KNOWLEDGE-GRAPH.md)，对应任务 `GRAPH-01` / 验收 `E-GRAPH`。

要点：

- **建议最小栈（全部宽松许可、无权重、无服务器、CPU）**：scikit-learn `TfidfVectorizer`+`TruncatedSVD` → 内置 `sklearn.cluster.HDBSCAN` 或 KMeans/Agglomerative；`networkx`+`python-louvain` 做社区发现；`pyalex`（MIT）从 OpenAlex 取引用边；存储优先沿用 SQLite（必要时 DuckDB/Kuzu）；标签用本地 c-TF-IDF top term。
- **零 token 部分**：抓取、向量、聚类、建边、标签、可视化。**可选便宜大模型**：仅给簇起名/写一句子领域区别，按簇缓存、经预算网关。
- **回避**：GPL 的 igraph/leidenalg/Gephi/LocalCitationNetwork/Neo4j community；服务器型 Neo4j/Memgraph；构建困难的 graph-tool；闭源产品（Connected Papers/Litmaps/ResearchRabbit/Inciteful/SciSpace）。
- **风险**：「不同观点分开」比「相似聚类」难，首版先做「相似聚合 + 子领域分开 + 标签可编辑」，观点维度单独实验。

## 2. 开源许可不是一个统一的“能复制”标签

- X、lite、PaperFlow为MIT，复制/改造需保留版权和许可证，依赖另审：[X LICENSE](https://github.com/xihuai18/arxiv-sanity-x/blob/f6c6b0a961776a18cfc73859fab5cd8ad2986245/LICENSE)、[lite LICENSE](https://github.com/karpathy/arxiv-sanity-lite/blob/d7a303b410b0246fbd19087e37f1885f7ca8a9dc/LICENSE)、[PaperFlow LICENSE](https://github.com/OpenRaiser/PaperFlow/blob/4a835e737490785b3ce51025c85b630cd224318c/LICENSE)。
- [zotero-arxiv-daily LICENSE](https://github.com/tidedra/zotero-arxiv-daily/blob/2879bcdf4ae3f021b77faa84bdfd01185509ebf2/LICENSE)和[Zotero reader](https://github.com/zotero/reader/blob/master/COPYING)是AGPLv3。私用不意味着必须向所有人公开；修改版分发及网络交互的对应源码义务不能忽略。是否嵌入与怎么分发需单独审查，不把AGPL误标为MIT。
- 连接文献软件API、打开文件与复制其实现是不同的复用方式。优先低耦合连接，而不是因为软件开源就fork整个宿主。

## 3. 论文数据源：先由你的领域决定

| 来源 | 可复用能力 | 限制及下一步 |
|---|---|---|
| [arXiv API](https://info.arxiv.org/help/api/tou.html) | 预印本元数据、类别、更新；许多候选已有采集器 | 学科覆盖不通用；legacy接口串行、至少3秒间隔；元数据CC0不代表PDF可重新分发 |
| [OpenAlex](https://developers.openalex.org/api-reference/authentication) | 跨学科元数据、过滤与搜索 | 免费日额度和按次收费共存，需要账户验证；10次关键词搜索+20次filter毛额度$0.012是算术示例，不是账单/所有使用免费 |
| [Semantic Scholar](https://api.semanticscholar.org/api-docs/recommendations) | 直接接收positivePaperIds/negativePaperIds推荐相似论文，可少造一层召回 | 不是可嵌入的开源排序器；种子ID揭示研究兴趣，外发需同意；需测领域覆盖/新鲜度/key/限流 |
| [Crossref](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) | DOI解析、规范元数据与去重辅助 | abstract可缺失；不要单独当个性化推荐引擎。按响应头处理限流，不能预设固定无限配额 |

Semantic Scholar [官方教程](https://webflow.semanticscholar.org/product/api/tutorial)与[端点合同](https://api.semanticscholar.org/api-docs/recommendations)交叉确认多种子推荐。其单种子`recent`/`all-cs`候选池不等于所有领域的每日全量；[许可](https://www.semanticscholar.org/product/api/license)要求归因、遵守底层数据许可，并说明请求数据可用于提供/改进服务。本轮未发送你的种子。

OpenAlex当前[价格页](https://developers.openalex.org/api-reference/authentication)写每日$1免费额度，search为$1/1000次、filter为$0.10/1000次。semantic项在表格与示例有差异，本轮不启用。免费额度与网站共用，预付余额可能自动续用；若将来选择它，应独立限额、禁止未批准付费，不只依赖“免费Key”。

数据适配计划必须区分首次发表、版本更新、抓取发现日期；标题相似不能直接合并不同论文。要先测领域种子回收和摘要完整性，再选一个主源，不能默认所有研究都在arXiv。

### 3b. DATA-01 实测（2026-09-11）

只读探针 `tools/data_probe.py` + 原始快照，完整报告见 [DATA-01 报告](evidence/2026-09-11-data01-openalex-report.md)。要点：

- **种子解析 8/10**（OpenAlex，标题匹配）；未解析的两篇是 2026 新预印本，不能当作不存在。
- **摘要可用**，但 **arXiv 预印本的引用边几乎全缺**（8 篇种子只有 1 篇有 `referenced_works`）→ 图谱的引用边不能只靠 OpenAlex。
- **裸关键词不能当领域过滤器**：`search="world model"` 报 328 万条，加计算机领域过滤仍 12.7 万条且被医学/信息学/仓储库污染。发现必须走 arXiv 分类或种子扩展。
- **日期必须带上界**：不设上限时 200 条里 117 条未来日期（最远 2036）。
- **限流/费用**：OpenAlex 每次 search $0.001 / 10 credits，日额度 1000 credits / $0.10（≈22h 重置），突发 429；arXiv 旧 API 本次对本机 IP 持续 429。

所以主源分工变为：**arXiv 分类 = 发现；OpenAlex = ID/DOI/摘要富化与去重；引用边另找 Semantic Scholar 或书目耦合兜底**。`DATA-01` 仍 `in_progress`（未测已知相关回收率，未稳定候选池）。

## 4. 论文软件：已经有轮子，但属于后置选项

- **Zotero**：官方[本地API](https://www.zotero.org/support/dev/web_api/v3/local_api)可在启用本机通信后读取本地库。当前文档说明Zotero10+支持经本地授权的写入，而旧客户端行为不同；不能沿用旧“只读”文章断言所有版本。首个适配只读指定collection、只取元数据；分页明确设limit，默认可能返回全库。未检查你已安装的版本。
- **JabRef**：[开源BibTeX/BibLaTeX管理器](https://github.com/JabRef/jabref)，[MIT许可](https://github.com/JabRef/jabref/blob/main/LICENSE)。如果你已使用它，先交换标准文件，不为推荐功能复刻一个Java桌面管理器。
- **预览**：默认原论文网页或现有阅读器就够用于推荐验收。必须内嵌时再评估[PDF.js官方组件示例](https://github.com/mozilla/pdf.js/blob/master/examples/components/simpleviewer.mjs)和Zotero reader，单独做视觉/选区/恢复验收。此轮不做。

## 5. 下一次验证的最小范围

1. 先取得一个领域和少量种子，确认反馈语义与对照协议。
2. 在隔离目录做两个**受限适配探针**：(a) arxiv-sanity-X 的纯推荐子集，验证标签/负反馈/撤销/重启与出站边界；(b) asreview 的 TF-IDF+线性分类+querier 层能否作为每日≤5篇的画像内核（其筛选UX需另做薄适配）。两者都限时、限改动范围，达到上限就停止评估，不边做边扩大。
3. 若必须大规模改PDF/agent/后台框架才能独立推荐，停止X适配；用lite现有内核和最少反馈适配做基线，不继续造另一套“大而全”。
4. 以同一候选集比较固定关键词基线、复用推荐和反馈更新；跨语言/单类/小样本/日期泄漏/未标注背景影响必须进入失败案例。
5. 只有这条闭环达到你认可的价值，才决定常驻界面、软件连接和AI配套。

选择顺序是有条件的建议，不是已经选定上游或保证能在Mac上原样运行。具体任务与停止条件见 [ROADMAP](ROADMAP.md)，所有未运行评估保持`not_run`。
