# 实验 2：加入干扰项与分级相关度后的排序对照（探索性）

2026-09-11。`tools/eval_probe.py`（已升级）。数据在 `.local/experiments/`（gitignored）。**仍不是推荐质量结论，`E-RANKING` 保持 `not_run`。**

## 相对实验 1 的修正

1. **候选池加干扰项**：除 `title.search:world model`（field）外，加入 5 个相邻但非本方向的检索（diffusion / LLM / RL / video generation / image segmentation）。
2. **裁判改为 0–3 分级**（0 不相关 / 1 相关领域但非本方向 / 2 值得扫一眼 / 3 很想读），并要求严格判断。
3. **抽样**：标注「各系统 top-10 并集 + 20 篇随机候选」。

## 冻结与排名

```
deduped=1126  field=318  distractor=808  abstract_missing=0
dates 2026-06-16 .. 2026-09-08   dataset_hash=5c27c2aa8bfbf91c
```

三个系统 top-5 全部是 field 论文：
- `recency_baseline`：最新 5 篇 field
- `keyword_date_baseline`：画像词命中 + 日期
- `tfidf_seed_centroid`：TF-IDF 种子质心

## 标注分布（45 篇，9 次调用，约 50k token）

```
relevance 分布: {0: 0, 1: 18, 2: 5, 3: 22}
field      (26 篇): {2: 4, 3: 22}
distractor (19 篇): {1: 18, 2: 1}
```

裁判能明确把干扰项判为 1（19 篇中 18 篇），说明分级 rubric 生效、标签有了方差。

## 结果

```
system                    P@5>=2  P@5>=3  meanRel@5  P@10>=2
recency_baseline            1.00    0.40       2.40     0.60
keyword_date_baseline       1.00    1.00       3.00     1.00
tfidf_seed_centroid         1.00    1.00       3.00     1.00
```

**现在有区分度了**：在严格阈值（>=3）下，纯日期基线 P@5=0.40，两个基于画像的系统 = 1.00。

但 **`keyword_date` 与 `tfidf_seed_centroid` 并列满分**，无法分出优劣；而且 field 论文里 22/26 都被判 3，**领域内方差仍然偏低**。

## 诚实的限制

- **n=45，P@5 只有 5 个样本**，差距不具统计意义。
- **干扰项构造有循环性**：干扰项本来就是"非世界模型"，被判 1 是构造使然，不是独立发现。
- **裁判是代理**，未经 `E-LLM-LABEL-VALIDITY` 抽检（抽检表已生成，待 owner 填）。
- 结论只能到"**画像排序优于纯时间基线**"这一层，**还不能说 TF-IDF 优于关键词基线**。

## 抽检表（待 owner）

已生成盲评表：`.local/experiments/spotcheck-sheet.md`（15 篇，隐藏答案在 `spotcheck-key.json`）。
填完后可算一致率，判断 taomu 标签是否可用。

## 复跑

```sh
python3 tools/eval_probe.py freeze --field-pages 2 --distractor-pages 1
python3 tools/eval_probe.py rank
python3 tools/eval_probe.py label --top-per-system 10 --random-sample 20 --batch 5   # 已缓存
python3 tools/eval_probe.py score
python3 tools/eval_probe.py spotcheck --count 15
```
