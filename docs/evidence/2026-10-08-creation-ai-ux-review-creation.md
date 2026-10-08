# 创建页面独立复核

复核日期：2026-10-09（北京时间）；工作单元按开始日期 2026-10-08 命名。

本复核由负责创建后端、未编写创建前端实现的代理完成。范围为 `app/static/project-creation.js`、`project_creation.html`、`project-creation.css` 和对应的生产函数回归；不替代整产品发布验收、原生窗口验收或真实模型质量评价。未调用真实 AI，未访问用户库。

## 发现与修复复验

1. **P2，已修复**：点击「自己搭一张」只替换图，保留旧阶段行和绑定。提交时旧行会将被放弃的概念加回新图。实现者已清空旧阶段行、恢复添加阶段，并清除旧起点。独立重新读取实际 `mapStart` 处理器及生产函数回归，确认图仅剩新建概念，旧行不会复活。
2. **P2，已修复**：等待引导回复时只禁止关键词输入，关键词删除按钮仍可操作，随后返回的草稿会覆盖这次删除。实现者已在 `refresh` 中统一锁定关键词区的 `input, button`。独立复验等待时二者均禁用，结束后恢复。
3. **P2，已修复**：清空已绑定阶段的标题和目的会被当作新空占位行忽略，既保留旧图内容，又保留确认勾选。实现者已令阶段输入立即撤销确认、保护人工编辑；绑定行空标题定位报错并阻止提交，仅未绑定的新空行可忽略。独立复验生产 `addPathItem` 处理器和提交结果。

## 关键契约

- `setDraft` 消费后端规范字段；显式 `route_plan` 优先，其次 `route_draft`。`source=ai_guidance` 从实际图概念重建阶段行并按节点 ID 绑定，保留前置、目标和 AI 简介作者；不将旧文字阶段重新加入 AI 图。
- 人工改图或阶段后，后续 AI 草稿不会覆盖当前图。新增阶段成为独立目标，不从行顺序推断前置。改目的成为用户作者，仅改名称且简介未变时保留 AI 作者。
- 创建前先验证学科/语言，错误出现在对应控件并聚焦滚动；图需要显式勾选确认。正常提交携带真实图和需求，只有明确放弃图时 `route=null, skip_route=true`，且不会因阶段行重新恢复被放弃的图。
- `summary`、`next_question`、`choices`、`ready` 均来自后端规范草稿。选项作为用户回答发送一次；等待时禁用，达到六轮上限时禁用继续发送。`ready` 在六轮前也能提示审阅创建。

## 实际执行证据

修复后独立执行：

```sh
node --test tests/test_creation_review_fixes.cjs tests/test_creation_brief_page.cjs tests/test_creation_quit_fixes.cjs
```

结果：22 tests，22 pass，0 fail，0 skipped，退出 0。包含新增三项缺陷的生产处理器回归及图确认、显式放弃、AI 图绑定、选项发送、字段焦点和退出草稿检查。原始本地输出位于 `/tmp/pdh-independent-creation-ui-review.txt`；本页只记录脱敏结果。

结论：本次复核发现的三项 P2 均已修复并独立复验，当前范围未见剩余阻塞。原生交互和真实 AI 回答质量未由本复核测量。

## 追加独立范围：分类后端

按主代理最终复核请求追加只读检查 `app/category_review_service.py`、`app/organization_facets.py` 的差异，以及分类任务调用、网关结果和预览应用消费者。本复核代理未编写这两个模块；仅使用合成数据、受控假网关和临时 SQLite，未调用真实 AI 或访问用户库，也未修改被复核源码。

已确认：

- 空分类目录可接受有论文证据的新类，先保存完整预览；已有论文归属在明确应用前保持不变。显式应用后新增类别与归属，可撤销，私有笔记保持原样且不进入请求。
- 本地待分类说明区分标题摘要缺失、可归组论文不足、术语未匹配；前端逐篇读取 `pending_details`，不会将此结果解释为 AI 无法创建类别。
- AI 失败返回明确原因，失败或未完成方案不保存。HTTP 状态和网络失败原因独立于 `usage_unknown`、`usage_reserved`；用量未知时 `total_tokens=null, tokens_known=false`，保留预算预留，不将 cap 当作实测用量；没有自动重试或继续批次。

发现 **P2，已修复并独立复验**：网关返回已确认用量但 `ok=false, bad_reply=true`（例如回复被截断）时，服务原先在汇总 `usage` 前进入失败分支，返回的分类任务统计漏计这次已消耗 token。独立合成复现中，首批失败且真实已确认 200 token，得到 `total_tokens=0, tokens_known=true`；先成功一批 100、第二批失败且已确认 200 时，得到 100 而非 300。网关自身账本仍正确，整份方案也未保存；缺陷影响任务统计的准确性。实现者已在失败处理前汇总明确已确认、非预算预留的有效用量，成功路径不会重复汇总。复核代理没有修改源码。

实际独立执行：

```sh
PYTHONPATH=tests python3 -m unittest tests.test_category_review_service -v
PYTHONPATH=tests python3 -m unittest tests.test_organization_review.UnplacedTests.test_pending_reasons_identify_missing_metadata_and_single_paper_local_limit -v
```

首次结果：22 个服务测试和 1 个待分类原因测试通过，退出均为 0；新增 P2 另以两个受控网关返回案例只读复现，不被当时通过的测试覆盖。

最小修复后独立重新执行服务测试文件：25 tests，25 pass，0 fail，退出 0。另独立检查四个网关结果：首批已知失败用量为 200、第二批已知失败与前批合计为 300、第二批未知用量仍为 `null/false` 并保留预留、预留数值没有进入已测总量；四种情况均保留 `bad_reply` 原因且没有保存不完整方案。`git diff --check` 通过。

追加范围结论：本次发现的统计 P2 已修复并独立复验，当前追加范围未见剩余阻塞。真实模型分类准确率和线上计费一致性未由本复核测量。
