# DATA-01 报告：arXiv / OpenAlex 领域数据实测（2026-09-11）

任务 `DATA-01`。只读、零模型 token、不外发私人种子 ID。原始快照与报告在 `.local/data01/`（gitignored），探针 `tools/data_probe.py`（stdlib，可复跑）。**不是推荐质量测量，不代表 DATA-01 通过。**

## 1. 种子解析（OpenAlex）

**8/10 解析成功**（标题精确/前缀匹配）。用同一组镜像快照复跑，结果可复现。

| 种子 | 状态 | 规范 ID |
|---|---|---|
| A Definition and Roadmap for World Models | **ambiguous**（0.43，错配到一篇机械系统论文） | — |
| V-JEPA 2 | resolved | DOI 10.48550/arxiv.2506.09985 |
| DINO-WM | resolved | DOI 10.48550/arxiv.2411.04983 |
| LeWorldModel | resolved | OpenAlex W7140238461（无 DOI） |
| DreamerV3 / Mastering diverse control tasks | resolved | DOI 10.1038/s41586-025-08744-2 |
| Genie | resolved | DOI 10.48550/arxiv.2402.15391 |
| Cosmos World Foundation Model | resolved | DOI 10.48550/arxiv.2501.03575 |
| IRASim | resolved | DOI 10.48550/arxiv.2406.14540 |
| Wonder: Video World Model Done Better | **not_found** | — |
| SolarWM | resolved | DOI 10.48550/arxiv.2609.02886 |

未解析的两篇都是 2026 年新 arXiv 预印本，可能尚未被索引或标题不同。**不能把“没解析到”当作论文不存在**，需要人工确认标题或换源。

## 2. 摘要与引用覆盖

- 已解析种子的摘要**全部可用**（843–1711 字符）。
- 但**引用边几乎全缺**：`referenced_works` 只有 DreamerV3（Nature，39 条），其余 **0**。对 world-model 预印本，OpenAlex 的引用图基本不可用 → 图谱功能的引用边不能只靠 OpenAlex。
- 候选池（200 条）：摘要缺失 **48/200（24%）**，引用缺失 **124/200（62%）**。

## 3. 裸关键词不是领域过滤器（重要）

`search="world model"` 返回 **3,281,291** 条；加上 `primary_topic.field.id:fields/17`（计算机）仍返回 127,273 条且结果被无关领域污染。候选池 top sources：

```
Research Square(37) · Zenodo(30) · Scientific Reports(8) · Royal Society Open Science(7) ·
Mendeley Data(3) · Figshare(3) · Discover Computing(3) · 消化病学/医学期刊(各3)
```

**结论**：不能用自由文本关键词做发现。发现必须走**明确的领域来源**（arXiv 分类 cs.AI/cs.LG/cs.CV/cs.RO）或**种子扩展**（引用/相关论文），关键词只用于打分。

## 4. 日期质量

不设 `to_publication_date` 时，200 条里有 **117 条未来日期**（最远 2036-04-23）。这是元数据错误，会让时间切分泄漏。
**规则**：所有查询必须带上界日期；入库前校验 `publication_date <= today`。

## 5. 限流与费用（实测头）

OpenAlex（本期账户）：

```
每次 search：X-RateLimit-Cost-USD = 0.001，Credits-Used = 10
上限：1000 credits/日，Limit-USD = 0.1/日（Reset ≈ 21.8 小时后）
本探针共 11 次调用 ≈ $0.011；剩余 credits 817，剩余 $0.0817
0.3s 连发会触发 HTTP 429；2.0s 间隔 + 尊重 Retry-After 后稳定
```

arXiv 旧 API：本次探测期间本机 IP 持续 `HTTP 429 Rate exceeded`（此前调研的批量查询触发）。**不能假设 arXiv 随时可用**；需要 ≥3s 间隔、指数退避、并记录失败。探针因此默认用 OpenAlex，arXiv 保留为备用源。

## 6. 对方案的影响

1. **主力分工**：arXiv（按分类）= 发现；OpenAlex = ID/DOI/摘要富化与去重；引用边另找 Semantic Scholar 或书目耦合兜底。
2. **候选构造**：从种子做引用/相关扩展，或抓 arXiv 分类时间窗；不用自由文本搜索。
3. **必须带时间上界**并过滤未来日期。
4. **图谱功能**需重新评估引用边来源（见 [KNOWLEDGE-GRAPH](../KNOWLEDGE-GRAPH.md) 的开放问题）。
5. OpenAlex 有日额度与按次费用，要登记进预算（当前只在计划口径，未实现网关）。

## 7. 复跑方式

```sh
python3 tools/data_probe.py --source openalex --out-dir .local/data01 \
  --max-candidates 200 --from-date 2024-01-01 --to-date 2026-09-11
# 已缓存快照会直接回放；加 --refresh 强制重新联网（消耗额度）
```

## 8. 尚未完成（所以 DATA-01 仍 in_progress）

- 未测「已知相关论文的回收率」（需要一小批人工/种子确认的相关集）。
- 未做稳定的候选池（当前是反例：证明关键词池不可用）。
- 未比较 Semantic Scholar 的引用/推荐覆盖。
- 未验证许可证细节与更大抽样的延迟分布。
