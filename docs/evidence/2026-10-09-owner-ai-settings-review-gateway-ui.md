# 独立复核：运行时用量策略与测试 AI 界面

复核日期：2026-10-09（北京时间）。本页由未编写网关、预算脚本、AI 测试 App/HTTP 接口及本次界面实现的代理完成。本人编写的标题派生与推荐初筛后端不在本页独立结论内；其独立复核见 [后端复核](2026-10-09-owner-ai-settings-review-backend.md)。

范围：`app/gateway.py`、`scripts/budget.py`、`harness/budget.json`、`prompts/ai-connection-test.md`，相关 `App.test_ai_connection` 与 `/api/ai-test` 调用；`settings.html` 的真实测试处理器、`paper-policy.js` 报告、首页语言卡片/详情/用量页脚、导入页旧额度说明和新增英文系统文本。所有检查使用合成凭据、受控假 provider、临时数据目录及函数级 DOM；没有真实模型请求，也没有访问正式用户库或正式用量账本。

## 发现与修复复验

- **P2，已修复**：操作注册表的分类和生长审阅 `scope` 仍以当前语气宣称执行旧日/月总帽，与 `aggregate_limits_enabled=false` 矛盾。实现者已将这两处当前合同改为单次请求约束和用量记录，保留历史授权记录。独立读回确认，预算生成/检查通过。
- **P2，已修复**：早期 `/api/ai-test` 的 `except Conflict` 被 `do_POST` 后部局部导入同名 `Conflict` 遮蔽。独立临时 HTTP 请求重现 `UnboundLocalError`，忙碌响应为 503 而非 409。实现者改用模块级 `OrganizationConflict` 别名；最终 11 个 App/HTTP 测试全绿，独立确认明确 409、没有第二次测试调用。

## 合同与界面结论

- 运行时总帽开关明确为 false，有效限额返回 `None`，历史总帽数字不成为零额度或余额。既有高用量不会拒绝新运行时请求；开发模式仍使用独立账本和明确启用的独立限额。原有额度/独立进程回归显式开启历史策略，不把这些回归冒充当前运行时政策。
- 单次操作登记、单次完整请求约束、显式 AI 开关和操作授权仍检查。测试 AI 为唯一窄例外：只发送固定 `Reply only OK.`，768/16 单次输入/输出合同，默认 30 秒，一次调用，无自动重试或模型切换，不发送用户论文、画像、笔记或会话。
- 临时密钥仅在本次授权头中使用；没有保存或改动 AI 开关。空输入使用已有密钥；无效参数、跨域、错误消息或以测试密钥调用其他操作在传输前拒绝。App 响应使用配置的模型名、过滤用量字段，并保留具体 HTTP/网络原因而不回显秘密或 provider 原文。
- 每次调用仍保留预留及账本串行化。未知用量跨重启保留；重复核账不会重复累计。连接成功与计量确定性分开表达：未知时接口的实测 `usage/usd` 为 null，保留 reservation；界面显示未确认，首页和设置页明确包含待确认预留。
- 独立读取并运行实际设置处理器：按钮等待时禁用，重复点击不发第二次请求；输入密钥改变或重载设置会使旧结果失效。状态在密钥旁显示原因和用时、文本隐藏秘密；完成后仅刷新用量，不覆盖尚未保存的设置或 AI 开关。没有自动重试；慢用量刷新不会令等待计时器覆盖成功结果。
- 首页接受运行时 null 总帽，保留开发模式有限总帽及预留提示。语言报告同时呈现来源报告/来源名称与全文验证状态，标题字形警告不被表达为已确认的正文语言；卡片和详情调用相同报告。题名、摘要和用户文本仍保留原文，动态报告经显示端转义。导入说明不再宣称会因旧每日总帽中止。

## 实际执行

```sh
PYTHONPATH=tests python3 -m unittest tests.test_gateway_policy tests.test_gateway_budget tests.test_budget -v
PYTHONPATH=tests python3 -m unittest tests.test_gateway_process -v
PYTHONPATH=tests python3 -m unittest tests.test_ai_connection -v
node --test tests/test_ai_connection_settings.cjs tests/test_paper_policy.cjs tests/test_system_i18n_fixes.cjs tests/test_paper_context.cjs tests/test_i18n.cjs
python3 scripts/budget.py --check
git diff --check
```

首次独立复核结果：58 个网关/预算测试通过；8 个独立进程/串行化测试通过；11 个 App/HTTP 测试通过；66 个界面/英文相关 Node 测试通过；预算生成一致性与差异空白检查通过，退出均为 0。原始本地输出分别保存在 `/tmp/pdh-independent-gateway-related.txt`、`/tmp/pdh-independent-gateway-process.txt`、`/tmp/pdh-independent-ai-connection.txt`、`/tmp/pdh-independent-owner-ai-ui.txt`，本页仅记录脱敏结果。

## 最后记账失败与用量显示补丁复验

同日实现者冻结后追加独立只读复核；没有重跑上述未变的全量范围。新增范围包括固定连接测试发送前/后的记账异常、App 原因翻译、实际设置处理器缺失 `total_tokens` 的回执，以及两项测试夹具调整。

- **P2，已修复**：连接测试发送前写预留、读取账本或取锁失败，原 App 泛化异常处理曾误称网络失败、用量未知且有预留。网关现在为这个固定测试跟踪本次传输阶段：发送前失败没有 provider 调用，`tracking_failed=true`、未知/预留均 false、reservation 为 null；App 明确显示本地用量记录失败及本次未发送，不回显原异常。一般操作原有抛异常行为保留。
- 发送后核账写入失败、未知回执写入失败或 HTTP 4xx 释放写入失败，已有持久预留保留，未知/预留均 true，重启后的账本仍可见待核对记录。网关保留 4xx 状态，App 同时解释 provider 原因和记录失败；独立 401 + 释放失败回归确认显示密钥原因与记账原因。意外异常只有未知而没有已记录预留证据时，App 不编造预留。
- **P2，已修复**：真实设置处理器曾把已知 prompt/completion 但缺少 total 的有效回执显示为待确认。现在可由两个有效非负整数相加得到本次 token；用量未知与预留证据分别呈现，仅 `usage_reserved=true` 才声称预留保留。原成功但计量未知回归仍通过，不把缺失计量显示为零。
- 中文词法排序夹具把先前中文题名却标英文/STEM 的合成数据改为明确 humanities + `zh` 来源报告，原中文命中排名断言保留。它测试中文排序，不绕开默认 English-only 的标题冲突检查。过大 HTTP 请求夹具仅发 `Content-Length: 9000` 并断言 413、没有网关调用，验证正文读取前的拒绝；没有改生产 guard，也没有依赖被拒后未读取正文导致的 macOS socket reset。

实际追加执行：

```sh
PYTHONPATH=tests python3 -m unittest \
  tests.test_gateway_policy.GatewayPolicyTests.test_connection_initial_tracking_write_failure_stops_before_transport \
  tests.test_gateway_policy.GatewayPolicyTests.test_connection_post_send_reconcile_failure_keeps_durable_reservation \
  tests.test_gateway_policy.GatewayPolicyTests.test_regular_operation_tracking_write_errors_retain_existing_exception_behavior \
  tests.test_gateway_policy.GatewayPolicyTests.test_connection_pre_send_ledger_read_or_lock_failure_does_not_claim_a_charge \
  tests.test_gateway_policy.GatewayPolicyTests.test_connection_post_send_unknown_or_release_write_failure_keeps_pending_accounting -v
PYTHONPATH=tests python3 -m unittest tests.test_ai_connection tests.test_ranking_foundation -v
node --test --test-name-pattern='known prompt and completion usage|unknown usage without a retained reservation|successful connection with unknown usage' tests/test_ai_connection_settings.cjs
git diff --check
```

网关新增 5 个阶段/记账回归通过；最终 App/HTTP 与排序夹具共 30 个测试通过；实际 UI 处理器选定 3 个用量状态测试通过，退出均为 0。脱敏本地输出为 `/tmp/pdh-independent-gateway-tracking-material.txt`、`/tmp/pdh-independent-ai-service-material.txt`、`/tmp/pdh-independent-ai-ui-material.txt`。这些都是临时目录和假传输结果，不是实际 provider 计费。

## 本地操作锁生命周期补充复验

随后独立 API 审查发现另一个 **P2，已修复**：App 外层操作锁建立的 I/O 失败仍会逃出接口，形成泛化 HTTP 失败。冻结后的 App 使用是否已取得网关结果区分生命周期：进入锁失败时网关没有调用，返回具体本地记录诊断、已知未发送且无预留；退出锁失败时保留现有网关回执，增加 `local_lock_failed` 原因，已知的 token/USD 不被清零或改成未知，已发送请求也不被称为未发送。已有失败回执的 provider/记账原因继续保留，并附锁释放说明。错误文本不回显原始秘密。

独立读回最终源码，运行 `PYTHONPATH=tests python3 -m unittest tests.test_ai_connection -v`：最终 18 个 App/HTTP 测试通过，包括进入锁失败的服务和完整 HTTP JSON 回归、成功网关回执之后的上下文释放失败回归。退出 0，脱敏本地输出 `/tmp/pdh-independent-ai-claim-material.txt`；仍无真实模型请求或正式数据访问。

最终冻结复验文件的 SHA-256（仅指本页相关源码与回归，不代表整产品构建指纹）：

```text
db1464f2c58576539b25f6d6ede3c142a6cb5662aaef4ca0148885c610538547  app/gateway.py
ce064f3b1c3b48a5c30cfb07249bfc5eba9cd3b0d757a9dd8ae1abf7be4a23f9  app/service.py
f27bdd22034a688b2d244d25823a4acd09d0fb80505c30bd28be19740ebc0528  app/server.py
84664bfc280159ab3ee3bc74cbc078e63df6a1763a42d433506b30a062c1a7fb  app/static/settings.html
6ca60f8b728b239e3a2adc74a6f08f9c0ca6bc907fd8907a2f55b8080a5af6fd  tests/test_ai_connection.py
45d2fdd7eba7ae95412c114c73847136f0d2fc75febaee0d45e2bfd69fc21fb7  tests/test_gateway_policy.py
005b04207fdc11c0e3b313eb45d7807529e72119eca8a1eb719fceb2e46faab5  tests/test_ai_connection_settings.cjs
```

结论：首次及追加独立范围的 P2 均已修复并独立复验，当前范围未见剩余阻塞。基础检索/排序/画像/维护仍为零模型 token；手工连接测试的参考量、单次上限和费用只是登记算术，假 provider 用量不是实际产品计费。未测真实 provider 连通性、真实计费一致性或原生窗口交互；本页不替代桌面构建、真人体验及整产品发布验收。
