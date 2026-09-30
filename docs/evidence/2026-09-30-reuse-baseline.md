# REUSE-01 本地基线：现有排序器 vs arxiv-sanity-lite 式线性 SVM（探索性）

2026-09-30。命令：`python3 tools/reuse_baseline.py --json-out docs/evidence/2026-09-30-reuse-baseline.json`，原始输出见 [txt](2026-09-30-reuse-baseline.txt) 与 [json](2026-09-30-reuse-baseline.json)。

## 范围

- **0 模型 token、0 网络请求**，仅标准库；读取 `.local/experiments` 的冻结候选池（754 篇，`candidates.json` sha256 前缀 `bc84cac1af8ae1d3`）与已缓存的 268 条 annotator 标签，未运行 `eval_probe.py label`。
- owner 选择“不做上游探针、只做本地基线”：**上游 arxiv-sanity-lite 探针未运行**，本文件不是上游可复用性的证明。
- 协议：有标签候选按发布日期切分，切点前为反馈（正 = 相关度 ≥2，显式负 = ≤1），切点后为留出集；4 个切点（40/50/60/70 分位）。IDF 只用无标签文本拟合，不使用标签。

## 结果（4 个切点均值）

| 系统 | P@5 | 有用/展示(10) | AUC | 有用平均名次 |
|---|---:|---:|---:|---:|
| existing_ranker（种子 + Rocchio + MMR，复用 `build_batch` 的排序函数；IDF 语料、钉死词、曝光与不足处理不同） | 1.00 | 1.00 | 0.94 | 43.41 |
| svm_unlabelled_neg（上游做法：未标注即负例） | 1.00 | 1.00 | 0.93 | 43.47 |
| svm_explicit_neg（只用显式负例） | 1.00 | 1.00 | 0.95 | 43.15 |
| recency | 1.00 | 1.00 | 0.64 | 51.66 |

资源：全部 4 个切点 × 4 个系统共 2.4 s，进程峰值 RSS 78.8 MB（开发机，非 8 GB 参考机）。

## 读法

- **P@5 与有用/展示饱和**：留出集约 70%–82% 为“有用”，前 10 名对任何系统都全有用，不能区分系统；只能看 AUC / 平均名次。
- SVM 与现有排序器差异在 ±0.01–0.03 AUC 之间，单次切分内波动同量级，**没有证据支持替换现有排序器**。
- 上游“未标注即负例”违反 AGENTS 边界 5（不从无动作推断不喜欢），即使更好也不能直接采用；显式负例变体可作为后续 EVAL-01 的候选对照。
- 偏差：annotator 标注时看过种子标题，偏向“与种子相似”的方法；标签不是 owner 标签。**结论只作探索性参考，不作为 E-RANKING / E-FEEDBACK-VALUE 通过证据。**
