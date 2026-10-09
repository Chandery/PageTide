# 独立审查：显式 AI 连接测试接口

审查日期：2026-10-09。审查者负责本工作单元的前端实现，本记录只对他人实现的 `App.test_ai_connection`、`POST /api/ai-test` 及 Gateway 调用协议作独立评估，不对自己的前端代码作独立评级。前端独立审查另见 [Gateway 与界面审查](2026-10-09-owner-ai-settings-review-gateway-ui.md)。

## 范围与隔离

检查实际 service/server/Gateway diff、凭证来源、桌面会话与同源保护、请求体限制、固定测试内容、互斥锁、净化后的失败原因、未知计费及重启后的计量状态。仅复制预算配置到临时独立 root，使用临时数据目录和合成密钥。执行环境移除正式数据目录、环境密钥和外部密钥文件覆盖；真实 DeepSeek 传输额外阻断。没有读取或修改正式用户库、正式密钥或正式账本，没有真实模型调用或收费测量。

## 已完成验证

```sh
env -u PAPERDIGHELPER_DATA -u DEEPSEEK_API_KEY -u PAPERDIGHELPER_KEY_FILE PDH_DEV=0 PYTHONPATH=.local/creation-ai-ux-verification/network-guard:tests:. python3 -m unittest tests.test_ai_connection tests.test_gateway_policy tests.test_provider_settings -v
```

初轮退出 0，30 tests passed，3.682s；账本错误修复后独立重跑 39 tests passed；App claim 错误修复后的最终独立重跑退出 0，42 tests passed，4.330s。包括实际本地 HTTP 请求及合成 Gateway 响应。初次模块运行遗漏 `tests` 的导入路径，产生 `recommendation_fixtures` 导入错误；补齐执行路径后重跑，不改动或弱化断言。私有输出：`.local/owner-ai-settings-review-api-python.txt`、`.local/owner-ai-settings-review-api-python-final.txt`。

另运行私有独立探针，保留真实 HTTP → App → Gateway → 账本链路，只替换外部 provider transport：

```sh
env -u PAPERDIGHELPER_DATA -u DEEPSEEK_API_KEY -u PAPERDIGHELPER_KEY_FILE PDH_DEV=0 PYTHONPATH=.local/creation-ai-ux-verification/network-guard:tests:. python3 .local/owner-ai-settings-review-api-probe.py
```

退出 0。最终扩展探针进行了 7 次合成 provider transport，真实 provider 请求为 0。测试缺桌面会话、跨源、错误 Host、额外 body 字段均在调用 provider 前拒绝；临时密钥与已保存密钥两条路径；测试后保存密钥字节和 AI 关闭标记字节完全保留；401 原文净化与预留释放；网络失败不暴露凭证、保留未知计费，重启仍有一条待确认预留；一个真实在途测试时第二个 HTTP 请求返回 409，且没有第二次 provider transport。错误 Host 最终通过直接本地 HTTP 发送，避免客户端重写 Host 造成假测试。追加外发前 `_record(reserved)` 写失败时 provider 发送 0 次、API 明确未发送且没有计费未知或预留；外发后 `_record(reconciled)` 写失败时发送 1 次、保留原 reservation，重启的待核对计数增加 1。App claim 进入阶段失败时 provider 发送 0 次、HTTP 返回具体未发送原因且没有未知预留；claim 退出阶段失败时 provider 已发送 1 次，HTTP 返回净化的本地锁失败原因，保留已有计量结果，没有误称未发送。输出：`.local/owner-ai-settings-review-api-probe.txt`。

已修的 server `Conflict` 内部导入遮蔽问题由 root 实现顶层别名处理；本审查通过真实并发 HTTP 409 独立复验。固定测试仅允许 `Reply only OK.`、注册 operation、原有 bounded output 和单次请求；临时密钥不能传入其他 operation，AI 关闭例外没有扩展到其他业务调用。API 使用配置中的 provider/model，不回传 provider prose 或任意 provider model 字段。未知用量返回 `usage=null`、`usd=null`，计量预留与测量值分开。

## 审查发现与处理

| 优先级 | 发现 | 状态 |
|---|---|---|
| P2 | Gateway 在外发前写计量账本失败时，service 把任意异常视作 `usage_unknown=true`；通用 receipt 进而返回 `usage_reserved=true`。独立模拟 `_record` 抛出 `PermissionError`，实际 provider 发送 0 次、账本不存在，API 却报告网络失败且声称保留预留。 | root / organization_ai 已修；真实 HTTP 预/后发送账本错误对照独立复验通过，resolved。 |
| P2 | App 的 operation claim 位于 Gateway 之前，只捕获 busy `ValueError`，没有捕获 `OSError`。独立模拟 claim 抛出 `PermissionError`，App 直接抛异常且 provider 调用 0 次；对应 HTTP 路由也没有该异常的净化响应。 | root 已修；真实 HTTP 的 claim 进入/退出对照独立复验通过，resolved。 |

该例不能通过将所有异常改为“没有消费”解决：请求发出后核账失败仍须保留未知状态。应区分可确认的外发前本地计量失败与可能已外发的异常，并给出具体且不含密钥的本地失败原因。

## 限制与当前结论

上述检查证明软件调用、权限和计量协议的合成行为；不证明真实 DeepSeek 凭证有效性、网络可用性、provider 账单准确性、tokenizer parity 或真实模型质量。没有进行原生界面视觉验收、真实模型测试或完整发布评估。

未发现新增 P1 凭证泄露、无保护的 HTTP 调用或其他 operation 的关闭开关旁路。两项 P2 均已修复并独立复验；本 API 范围独立审查状态为 **passed**，没有剩余已发现阻塞。

最终审查的源码 SHA-256：

```text
app/service.py  ce064f3b1c3b48a5c30cfb07249bfc5eba9cd3b0d757a9dd8ae1abf7be4a23f9
app/server.py   f27bdd22034a688b2d244d25823a4acd09d0fb80505c30bd28be19740ebc0528
app/gateway.py  db1464f2c58576539b25f6d6ede3c142a6cb5662aaef4ca0148885c610538547
```
