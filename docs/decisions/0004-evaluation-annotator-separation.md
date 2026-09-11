# ADR 0004：评估裁判与运行时 provider 分离

日期：2026-09-11。状态：由 owner 明确决定（"taomu 用来辅助判断和打分，training only；正式软件里的排序/辅助搜索还是用 deepseek"）。

## 背景

用大模型给推荐打「有用/不相关」标签时，如果**同一个模型既排序又当裁判**，会偏向自己的风格（self-preference），评估失真。owner 提供了一个第三方中转 `taomu.xyz` 专门做评估裁判，正式产品仍用 DeepSeek 官方。

## 决策

1. **运行时 provider = DeepSeek 官方**：排序、速览、追问、周报、划词、关键词扩展，价格可核验，登记在 `harness/budget.json` 的 `provider`。
2. **评估裁判 provider = taomu 中转 / `gpt-6-astra`**：**只用于构建评估标签**，绝不进入 App；登记在 `budget.json` 的独立 `evaluation` 段。
3. 这样裁判模型 ≠ 被评估的排序模型，减少自证循环；但**仍不能免除抽检**（见 `E-LLM-LABEL-VALIDITY`）。
4. `judge_relevance` 从运行时 operations 移到 evaluation operations；运行时 scenarios/额度不受影响。

## 已知代价（必须随结果一起报告）

- **隐藏前缀**：探针显示每次请求被注入约 **4,403 个输入 token**（对十几个字的请求）。因此评估预算按「每次调用 = 登记上限 + 隐藏前缀」计 token，且隐藏内容不可审计。
- **价格不可核验**：taomu 无公开价格表（`/pricing`、`/docs` 是空壳，`/api/*` 404）。所以 `evaluation` 段**只报 token，不计算 USD**，也不声称成本。
- **模型身份自报**：`owned_by: openai` 无法核实，不排除后端替换。
- **第三方可见内容**：评估请求会经过该中转；只发公开论文标题/摘要与画像词，**不发私人种子 ID、笔记或整个库**。

## 不改变

运行时仍受 DeepSeek 官方价格与已批准额度约束；`E-BUDGET` 继续阻断直至网关实现；私有数据不外发；无静默换模型。

## 验证

- `harness/budget.json` 的 `evaluation` 段 + `scripts/budget.py` 的 `validate_evaluation`（价格标记不可核验、隐藏前缀计入、token-only 渲染）。
- 探针证据 `docs/evidence/2026-09-11-taomu-probe.txt`。
- `E-LLM-LABEL-VALIDITY`（标签质量抽检）、`E-RANKING`（对照）、`E-BUDGET`（运行时准入）。
