# 实验 1：首个排序对照（探索性，负结果）

2026-09-11。这是**评测夹具的首个端到端跑通**，不是推荐质量结论。工具 `tools/eval_probe.py`，数据在 `.local/experiments/`（gitignored）。**不能凭此通过 `E-RANKING`。**

## 设置

- **候选集**：`title.search:world model` + arXiv source `S4306400194` + 日期上界，取最新 400 条，按 OpenAlex ID/DOI/规范化标题去重后 **318 篇**，日期 2026-07-29 .. 2026-09-08，摘要 0 缺失。数据集哈希 `0c06666429815cc8`。
- **画像**：owner 的 10 篇种子（冷启动，无反馈）。
- **对照系统**：
  1. `recency_baseline`：纯按日期倒序。
  2. `keyword_date_baseline`：画像 top-40 词命中数 + 日期（ROADMAP 的固定基线）。
  3. `tfidf_seed_centroid`：TF-IDF + 种子质心余弦（纯 stdlib，参考排序器）。
- **盲标**：taomu `gpt-6-astra` 标注三个系统 top-10 的并集（26 篇，去重）；标注请求**不含任何名次/分数**。

## 结果

```
labelled=26 useful=25 not_useful=1 (positive_rate=96%)
system                      P@5  useful@5   P@10  judged
recency_baseline           0.80         4   0.90      26
keyword_date_baseline      1.00         5   1.00      26
tfidf_seed_centroid        1.00         5   1.00      26
```

**结论：无法区分系统。** 两个系统 P@5 = 1.00，纯日期基线也有 0.80。

## 为什么区分不了（三个原因）

1. **候选池本身已经过领域过滤**：`title.search:world model` 使池子里几乎全是世界模型论文，所以任何排序器都"看起来对"。
2. **裁判过于宽松**：26 篇里 25 篇判为有用（96% 正例）。这正好是 `E-LLM-LABEL-VALIDITY` 要抓的风险——全是正例时 P@k 没有区分度。
3. **只标了各系统 top-10 的并集**，且被标注的 26 篇都落在高分区，缺少低排名的负例。

## 因此

- 评测管线（冻结 → 排序 → 盲标 → 计分 → 哈希）**可用且可复跑**，这步是成功的。
- 但**测量本身没有区分度**，`E-RANKING` 必须保持 `not_run`。不能说"推荐有效"，也不能说"tfidf 更好"。
- `E-LLM-LABEL-VALIDITY` 需要人工抽检；在只有 1 个负例的样本上无法验证。

## 下一步修正（建议）

1. **加干扰项**：从 arXiv cs.AI/cs.LG/cs.CV/cs.RO 拉一批**非世界模型**论文混入候选池，制造真实负例。
2. **改用分级相关度**（0–3 或 "想读/相关但不读/不相关"），而不是二值，以获得方差。
3. **标注更多低排名候选**（不只是 top-10），并对随机样本标注。
4. 之后再做 `E-LLM-LABEL-VALIDITY` 抽检。

## Provider 备注（实测）

- taomu 网关**屏蔽无 User-Agent 和 `Python-urllib` UA**（返回 502/404 "page not found"）；必须发送常见 UA。已修好。
- 每次调用仍有约 **4,224 个 cached + 约 1,000 个新增隐藏输入 token**（与登记的前缀一致）。
- 本次标注 6 次调用，合计约 **32,400 token**。

## 复跑

```sh
python3 tools/eval_probe.py freeze --pages 2 --per-page 200
python3 tools/eval_probe.py rank
python3 tools/eval_probe.py label --top-per-system 10 --batch 5   # 已缓存，不重复花钱
python3 tools/eval_probe.py score
```
