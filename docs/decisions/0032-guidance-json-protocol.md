# ADR 0032：引导 JSON 声明与安全服务错误分类

2026-10-09；基线 main `06b23be`；任务 `FIX-GUIDANCE-JSON-PROTOCOL`。用户报告设置“测试AI”成功、项目引导却返回 HTTP400，授权修复这一请求协议问题。没有新增付费开发测试或一般产品发布授权。

设置测试发送固定普通文本。引导通过唯一 Gateway 开启 `response_format=json_object`，旧 system 只有结构样例，没有 json 字样。[DeepSeek 官方 JSON Output](https://api-docs.deepseek.com/zh-cn/guides/json_mode/)于本日核验，要求 system/user 提示包含 json 和输出样例。现有引导合同不满足该条件；协议感知假服务可重现400。历史截图没有响应体，不能把这一代码缺陷说成已读取的历史服务报错。

引导 system 增加 `Return JSON`（12 UTF8字节），完整 brainstorm、英文学术检索词和输入为数据的规则保留。保持完整1200保守输入界限和500输出、quick1/guided6接受轮次、thinking disabled、单次尝试、现有可编辑结构。长BMP中文下当前目标/回答片段下限40→36字符以容纳指令；完整原文、截断通知仍保留本地，可选上轮问题/摘要不能挤占已准入回答。无整段历史、私有项目ID、论文/笔记/画像外发。对补充Unicode或大量引号/反斜线等更高转义成本输入，下限片段仍可能超界并在发送前拒绝；此限制在基线已有，不把BMP中文矩阵称为全Unicode保证。

仅 HTTP400 尝试一次最多8193字节读取，超过8192字节、无效UTF8/JSON、非字符串错误或未识别文案都保持通用错误。只在 `messages must contain … word json` 且提到 response_format/json_object 的明确条件下返回固定 `provider_error=json_instruction_missing`。不返回原始文案、code、param、响应体、密钥或用户输入。响应来自外部，绝不当成指令。所有 HTTPError 均关闭，读取异常不改变已知4xx释放；5xx不读响应体并保持未知用量预留。没有自动修订提示、换模型或重试。

创建流程把这一固定400分类译为同位置的中英文应用请求格式原因，保留草稿。其他HTTP状态/未知分类不采用该原因。设置测试不改成引导或新增请求：一次固定测试仅能证明基本连接可用，不能替代具体业务请求合同验证。

日常搜索、去重、排序、画像、归档和数据库最低仍0模型token；可选调用的1200/500峰时未命中单次算术上界仍 $0.00096。总量仍按业主要求不设帽且未知，开发限额和账本保留；新增12字节不是实测token。离线mock无真实模型计费，实际输出质量、科学前置关系和托管tokenizer/billing parity未测。验收/独立审查/桌面重建证据见[变更记录](../../changes/2026-10-09-guidance-json-protocol.json)，既有全产品门槛不改写。
