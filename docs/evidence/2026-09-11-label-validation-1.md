# 标签验证 1：taomu 标签 vs owner 盲评（并修正实验 2 的结论）

2026-09-11。owner 对 15 篇做了盲评（不看模型结论），与 taomu 的 `labels.json` 对齐。对应 `E-LLM-LABEL-VALIDITY`。命令：`python3 tools/eval_probe.py spotcheck-score`。

## 结果

```
compared=15  exact=40%  within1=100%  binary(>=2)=100%
owner distribution     : {0: 6, 1: 2, 2: 3, 3: 4}
annotator distribution : {0: 0, 1: 8, 2: 0, 3: 7}
confusion (owner -> annotator):
  owner=0  -> annotator 1   (6/6)
  owner=1  -> annotator 1   (2/2)
  owner=2  -> annotator 3   (3/3)
  owner=3  -> annotator 3   (4/4)
```

## 解读

1. **二分判断完全一致（15/15）**：owner 认为「不相关/非本方向」的 8 篇，annotator 全给 1；owner 认为「值得看」的 7 篇，annotator 全给 3。所以**代理标签可以当二值"有用/没用"信号**。
2. **绝对分级不可信（exact 仅 40%）**：annotator **从不输出 0**，而且把 owner 的 0 映射成 1、把 owner 的 2 映射成 3——整体**向上平移**。所以 `meanRelevance` 和分级均值**不能当测量**。
3. **annotator=2 的含义未定**：这次 15 篇里恰好没有 annotator=2 的样本，无法判断它算不算"有用"。

## 对实验 2 结论的修正（重要）

实验 2 我说过「严格阈值 `>=3` 下 recency P@5=0.40、画像系统 1.00，所以画像排序优于时间基线」。**这个结论现在要收回**：

- 在**被验证过的二值口径（`>=2`）**下，实验 2 三个系统的 P@5 **都是 1.00**，**没有区分度**。
- 之前看到的区分度依赖 `>=3`，而 `>=3` 是否等于 owner 的"有用"取决于 **annotator=2** 怎么算——这一点本次抽检没覆盖。

因此当前正确结论是：**推荐质量仍未得到证明**；`E-RANKING` 保持 `not_run`。

## 下一步

1. **抽检表 2**：`.local/experiments/spotcheck-sheet-2.md`，是 5 篇 annotator=2 的边界样本，请 owner 再打一次分，用来定阈值。
2. 定完阈值后，**预先冻结**（写进 `EVALUATION.md` 与 evaluations），重跑 `score`。
3. 之后再决定是否扩大标注，把 keyword 基线与 TF-IDF 分出高下。

## 诚实边界

- n=15，且阈值是事后讨论的；不能据此宣称一致率高。
- 抽检样本全部来自已标注的 45 篇，不代表全体候选分布。
- 结论只覆盖"这个 annotator（taomu/gpt-6-astra）+ 这个提示词版本"。
