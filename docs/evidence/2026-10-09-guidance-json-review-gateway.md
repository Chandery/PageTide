# 独立复核：项目引导 HTTP 错误诊断

日期：2026-10-09（北京时间）。本页复核者未编写本次 `app/gateway.py`、`app/creation.py` 及其诊断回归。范围限于这两个文件的本次差异、`tests/test_gateway_http_diagnostics.py`、`tests/test_guidance_error_diagnostics.py`，以及调用结果的两个独立 App 回放；本人编写的 `guidance_contract.py`、提示词和 JSON 协议测试不在本页独立结论内。

所有检查使用临时数据目录、合成凭据和假传输，没有真实 provider 调用，没有读取正式用户库或正式用量账本。没有通过现网重现用户截图中的具体 400 正文，合成错误不能证明原截图的错误类别。[DeepSeek 官方 JSON Output](https://api-docs.deepseek.com/zh-cn/guides/json_mode/) 于同日读取，明确要求 system/user 提示包含 json 字样及格式样例；该要求是固定诊断类别的协议依据。

## 源码结论

- HTTP 正文是不可信数据。仅 HTTP 400 读取一次 `read(8193)`，长度超过8192字节即不解析；8192字节以内严格 UTF8/JSON 解码，非 JSON 常量、结构不匹配、类型错误或解析异常都保持一般 HTTP 诊断。只有标准 `error.message` 同时符合 messages 必须包含 word json 的明确语句，以及 response_format、json_object 两个标记，才返回固定 `json_instruction_missing`。不返回 provider 原文、错误 code/param、URL、异常文本或秘密。
- 每个 HTTPError 在 finally 中关闭；非400没有正文读取，5xx也不解析正文。读取 OSError/IncompleteRead 或关闭 I/O 失败不会覆盖已知 HTTP 状态。正常传输没有新增重试、模型切换或提示词重写。
- 已有4xx释放预留的结算行为保留，解析诊断失败仍按已知4xx释放，不改成未知计费。5xx保留原预留且标用量未知；连接测试释放写入失败仍保存既有预留、HTTP状态、固定诊断类别和 tracking_failed。错误正文不进入回执或账本。
- `creation.degrade_reason` 只对 HTTP400 + 精确固定类别给出 `request_format`，中英文均明确指向应用缺少 JSON 输出声明，说明草稿保留，不让用户通过缩短目标解决应用请求格式问题。未知类别、其他状态仍走既有一般 HTTP 原因；401继续显示密钥原因，不回显未登记 provider 文本。
- 两个独立 App→实际 Gateway→假 HTTP400 回放检查 zh-CN/en-US：每次仅一个 provider 尝试，返回固定 request_format，保留已有手工图的完整内容、学习阶段及 user 作者标记，成功轮数仍为0，临时账本释放预留且 token为0。会话展示固定安全原因，原正文/合成秘密没有进入返回值。这些0 token只是拒绝请求的假回执结果，不是实际产品计费测量。

## 实际验证

```sh
python3 -m unittest tests.test_gateway_http_diagnostics tests.test_guidance_error_diagnostics -v
git diff --check
```

12个诊断回归通过（9网关 + 3原因/草稿），退出0；脱敏本地输出 `/tmp/pdh-independent-guidance-gateway.txt`。逐条读回测试，覆盖固定类别识别、其他字段含秘密、畸形/未知/非有限JSON、8192边界/过大正文、读异常、5xx未知预留、连接测试无原文输出及释放记录失败。

另执行8个独立合成回放，无源码修改：正文8191/8192可识别、8193不识别且读取量均为8193；401不读取正文并释放；400关闭失败仍保留固定类别和已知未计费状态；503关闭失败不读取正文、仍保留未知预留；另有上述中英文2个手工图保持回放。所有断言通过，真实调用0。边界及关闭失败不改变结算，也没有泄漏植入的正文/URL/异常秘密。

冻结复验文件 SHA-256：

```text
0bb166eac63ab19ae0c08d5166c7a35ec1beff5f9cf4ed5296c79dc35479aef8  app/gateway.py
8c24f98a06eba61fab65e0311255673026ef7014ad5f1d2392c31111269a380d  app/creation.py
1e7c73bfd69ebe253a8ac120ef8df05066f911d31ea192071ccdff6c224b6f30  tests/test_gateway_http_diagnostics.py
bc8dd12e57310464ce4b6dde08778aeea3fecfb8ca22b87707fcb50ed6c55bb1  tests/test_guidance_error_diagnostics.py
```

本次独立范围未发现剩余阻塞。该结论不代替本人提示词变更的另一独立审查、真实 provider 连通性/回复质量/计费验证、原生界面验收或桌面构建。
