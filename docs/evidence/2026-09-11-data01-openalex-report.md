# DATA-01 报告：arXiv / OpenAlex 领域数据实测（2026-09-11）

任务 `DATA-01`。只读、零模型 token、不外发私人种子 ID。探针 `tools/data_probe.py`（stdlib，可复跑），原始快照与报告在 `.local/data01/`（gitignored）。**不是推荐质量测量，不代表 DATA-01 通过。**

本轮跑了两次，第一次证明错的做法，第二次给出可用配方。

## 1. 种子解析：8/10 → 10/10

第一轮用标题搜索，8/10 命中；两篇 2026 新预印本未命中。owner 给出两个 arXiv 链接后，改用**显式 ID 直接解析**并复核标题：

| 种子 | 规范 ID | 解析方式 |
|---|---|---|
| A Definition and Roadmap for World Models | arXiv 2607.06401 | owner 提供 |
| V-JEPA 2 | arXiv 2506.09985 | 标题搜索 |
| DINO-WM | arXiv 2411.04983 | 标题搜索 |
| LeWorldModel | OpenAlex W7140238461（无 DOI） | 标题搜索 |
| Mastering diverse control tasks (DreamerV3) | DOI 10.1038/s41586-025-08744-2 | 标题搜索 |
| Genie | arXiv 2402.15391 | 标题搜索 |
| Cosmos World Foundation Model | arXiv 2501.03575 | 标题搜索 |
| IRASim | arXiv 2406.14540 | 标题搜索 |
| Wonder: Video World Model Done Better | arXiv 2607.26037 | owner 提供 |
| SolarWM | arXiv 2609.02886 | 标题搜索 |

**10/10 resolved，标题不一致 0。** 显式 ID 作为权威来源；若标题不符会记录 `+title_mismatch` 而不是静默接受。

## 2. 发现配方：裸关键词 → arXiv 源 + 标题搜索

| 查询 | 报告条数 | 结果质量 |
|---|---:|---|
| `search="world model"`（第一轮） | **3,281,291** | 医学/仓储库/信息学污染，117/200 未来日期 |
| `+primary_topic.field.id:fields/17` | 127,273 | 仍被污染 |
| `primary_location.source.id:S4306400194` + `title_and_abstract.search` | 52,678 | 仍偏宽 |
| **`source.id:S4306400194` + `title.search:world model` + 日期上界** | **3,226** | **200/200 来自 arXiv，全部是世界模型主题** |

**结论**：发现必须锁定**来源（arXiv）+ 标题级搜索 + 时间窗**，不能用自由文本搜索。已固化进探针。

## 3. 可用候选池

```
查询上限 3,226 条；本轮取最新 200 条
日期 2026-08-10 .. 2026-09-08
来源：arXiv 200/200
摘要缺失：0/200
引用边缺失：200/200      ← 整个近期切片都没有
相关论文缺失：200/200    ← 同上
重复：DOI 0 组，标题 1 组
```

**关键限制**：对最近一个月的 arXiv 切片，OpenAlex **没有任何引用或 related_works 边**。因此：

- **推荐**可以用内容（标题/摘要）+ 种子相似度，不依赖引用图 —— 可行。
- **论文图谱**的引用边**必须**换源（Semantic Scholar 或书目耦合），见 [KNOWLEDGE-GRAPH](../KNOWLEDGE-GRAPH.md)。

## 4. 限流与费用（实测）

```
OpenAlex：每次 search $0.001 / 10 credits；日额度 1000 credits 与 $0.10（约 17–22h 重置）
本会话累计：剩余 credits 765（用掉约 235），剩余 $0.0765（用掉约 $0.0235）
0.3s 连发 → HTTP 429；2.0s 间隔 + 尊重 Retry-After 后稳定
arXiv legacy API：本次探测期间对本机 IP 持续 HTTP 429，未能用于候选池
```

## 5. 复跑

```sh
python3 tools/data_probe.py --source openalex --out-dir .local/data01 \
  --max-candidates 200 --from-date 2024-01-01 --to-date 2026-09-11
# 已缓存快照直接回放；--refresh 强制联网（消耗额度）
```

## 6. 仍未完成（DATA-01 保持 in_progress）

- 未测「已知相关论文回收率」（需要一小批确认相关集）。
- 候选池只有 1 个月切片；按时间切分训练/测试集尚未冻结。
- 未比较 Semantic Scholar 的引用/推荐覆盖。
- 未验证 license 细节与延迟分布。
