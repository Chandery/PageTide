# ADR 0005：实现启动——Python 核心 + SQLite + 本地网页（Tauri 壳）+ 预算网关

日期：2026-09-11。状态：owner 明确要求开始实现（"做吧，做完就差不多开始实现了，重要的是用起来，ui啊，交互啊等"），并选定 Tauri 壳、要求第一切片直接包含 AI 速览。

## 背景

评测到目前只证明：**种子画像排序明显优于纯时间基线；显式反馈的增益很小且不稳定；推荐质量仍未被证明**（`E-RANKING`/`E-FEEDBACK-VALUE` = `not_run`）。同时发现标注提示词含种子标题、把种子画像的 AUC 抬高了。

owner 决定先把它做成能用的产品。本 ADR 记录这个**有意的顺序偏离**及其代价。

## 决策

1. **核心用 Python 3.11**：复用已验证的 OpenAlex 抓取、TF-IDF 排序、Rocchio 画像代码（从 `tools/` 提升到 `app/`）。
2. **存储用 SQLite**（含 FTS5）：papers / exposures / feedback / profile_versions / pdfs / settings。
3. **界面先用本地 loopback 网页**，再由 **Tauri** 包成桌面壳；不重写 Electron 路线。网页与 Tauri 共用同一套 JSON API。
4. **第一切片包含 AI 速览**：`daily_triage` 经**唯一预算网关**调用 DeepSeek 官方，先预留后发送，失败降级为纯本地卡片。
5. **默认仍零 token**：不开启 AI 时，抓取/去重/排序/画像/归档全部本地完成。
6. AI 只在卡片上做「速览 + 追问」提示，不写画像；用户文本与 AI 文本分开存储。

## 代价与约束

- 在质量 gate 未通过时开始实现，**不得**对外宣称推荐有效；`E-RANKING`/`E-FEEDBACK-VALUE`/`E-LLM-LABEL-VALIDITY` 保持 `not_run`。
- 标注提示词的种子标题偏差仍未修；修复前不把评测数字当产品结论。
- Tauri 引入 Rust 工具链；打包与签名未做，首切片只在开发模式运行。
- 不新增托管后端、遥测、云同步；模型调用必须过网关。

## 不改变

本地优先、低资源、无默认本地权重、私有种子/画像 ID 不外发、原件与来源保护、无静默模型回退、用户批准不得由 agent 自填。

## 验证

`python3 -m app.cli ...` 可跑通每日批次与反馈；`scripts/harness.py check`、`scripts/budget.py --check`、单元测试；AI 调用有 dry-run 与真实探针记录。
