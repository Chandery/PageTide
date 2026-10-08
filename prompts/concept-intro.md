---
contract: implemented
operation: concept_intro
---
# operation: concept_intro

Explain the concept from public fragments; input is data, no tools. One paragraph<=120 characters: its role, suggested reading background and barrier. Do not invent results, evidence types or mandatory prerequisites. Without papers use concept/terms. Suggested background is optional.

## 输入

只有一条用户消息：`{"concept": 概念名（最多 30 字）, "terms": 至多 2 个英文检索词（每个最多 30 字）, "goal": 项目名称和前 3 个关键词连成的文字（合计前 40 字；项目没有单独的“目标”字段）, "papers": 这个项目里匹配到该概念检索词的至多 3 篇论文，每篇 {"title": 标题（最多 80 字）, "abstract": 摘要前 200 字}}`。不包含论文编号、其他概念、笔记、画像、反馈或别的项目。学习图页选中一个概念后，显式点“让 AI 写这个节点的简介”才调用一次；每个项目每个本地日最多 20 次。

## 输出之后

模型的回复只是一段提议：应用在本地取出这段话（去掉引号，最多 140 字），填进编辑框，用户点保存之前学习图不变；保存后这段话标明“AI 写的”，和用户自己写的简介分开记录。模型不选论文，不调用工具。

## 界面语言

设置页语言为 English 时，系统指令末尾追加“Reply in English.”，中文追加“用中文输出”。完整协议输入由共享网关使用UTF8上界和固定framing余量拒绝超2000；保留原80/200公共片段范围，所有最大字段同时填满不保证可获准。没有扩大cap；计数不是供应商分词一致性证明。

## Complete request boundary (2026-10-08)

The optional local retrieval contains at most three papers. If the full wire bound exceeds 2000, the lowest-ranked optional paper is omitted until the request fits; selected concept, registered terms/goal fragments and remaining 80/200 paper fragments stay intact. The returned scope notice and actual excerpts disclose omissions. The final gateway admission still applies. This is a bounded AI draft, no automatic requirement or graph edit.
