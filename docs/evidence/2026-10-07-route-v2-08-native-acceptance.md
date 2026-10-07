# Route V2 原生验收与真实网关探针

2026-10-07；基线 f20e2f4，分支 codex/route-discovery-rework。人类原话“授权啊，全都授权”，回应此前原生验收及三项 Route 新范围/既定上限内付费测试。默认关闭和全局额度不变；授权不使发布门槛自动通过。

## 实际原生界面

使用新 Tauri .app 的真实 macOS WebView，CUA 读取原生 AX/截图、点击和填写。初始项目和19篇合成元数据在 .local/route-native-20261007/data 创建。AI_DISABLED、无key、隔离 HOME、出站失败代理。所有有意验收修改在此库；合成内容不能证明真实推荐价值。

| 场景 | 实际观察 | 状态 |
|---|---|---|
| 手工建图 | 五字段填写；基础与目标、明确前置保存；已知基础不自动掌握 | passed |
| 关注与解锁 | 显式掌握基础后目标可读；基础关注开启 | passed |
| 推送 | native 按钮生成3路径+1探索+1已满足关注新进展 | passed |
| 收藏/撤销 | 探索收藏产生 useful；画像正例1；点击撤销后正例0，收藏仍3 | passed |
| 双图身份 | 探索论文 x0 从今日定位学习图未匹配入口；返回关系图仍同标题；类别/单元/推荐用途分别显示 | passed |
| 目标完成 | 手动掌握目标后2/2完成；native 生成仅1探索发现 | passed |
| 修改预览/冲突 | 本地 service 准备手工 patch 预览；native 显示完成→学习中、重算掌握；另一 service 改 watch，native 确认409，输入/预览保留且旧确认禁用 | passed |
| AI关闭 | native 点生成草稿后显示关闭提示，原预览和需求保留，无发送 | passed |
| 新预览/确认 | 本地 service 重新预览同 patch；native 确认后节点改名，基础旧掌握隔离，人工简介保留 | passed |
| 重启/撤销 | 初次重启发现撤销按钮丢失。修复后 fresh backend/Tauri 构建，隔离重启 native 显示按钮；点击恢复原名与完成2/2 | passed after fix |
| 普通模式 | native 切普通排序，Map保留；生成5普通卡无Route用途，STEM中文元数据被同质量规则过滤 | passed |
| 语言界面 | 项目设置显示理工科仅英文、文科选项存在；最后切文科保存时Mac锁定，需解锁后完成 | pending |

预览生成和并发变更由受控 fixture service 完成；真实 native 执行显示、拒绝、确认和撤销，不声称关闭的 AI 生成了该预览。初次退出后 CUA 观察自动重开默认数据路径，页面加载失败；立即终止并按隔离配置启动，未操作默认库 UI。正式账本有本次付费记录，不能称其完全未动。

## 真实模型请求：各一次，无自动重试

DeepSeek Flash，thinking disabled，Gateway.dev=False；加载已批准登记，使用既有正式 usage.jsonl 合计历史预算。native 隔离进程一直AI关闭。只发送自写五字段、手工完整Map、公开 DreamerV3 标题及摘要节选。未发送私有ID、笔记、画像、全文或其他项目。创建失败后独立手工4节点 fallback；没有截短或修复响应冒充 AI 成功。

| 操作 | 完整wire UTF8+256估算 | 官方离线wire token | provider输入/输出/总量 | 峰费率账本USD | 结果 |
|---|---:|---:|---:|---:|---|
| 创建 | 1587 | 378 | 294/359/653 | 0.000519 | stop/有效JSON，但why超120字符，严格拒存 |
| 修改 | 2533 | 627 | 521/64/585 | 0.0002331 | 新增Evaluation及DreamerV3前置，sole target正确；预览确认成功 |
| 生长 | 2729 | 706 | 559/88/647 | 0.0002733 | covered定位DreamerV3，没有误增分支 |

共1885 token/$0.0010254。正式账本最后6条是各操作 reserved/reconciled，脱敏核对与 provider usage 对应；无未知探针记录。低于原全局上限。金额是已登记峰费率的本地计算，不是提供商账单；创建返回 Probability why125/intro151字符，DreamerV3 why121字符；创建质量失败不能写成三项AI质量通过。不提高额度，不自动再试。

官方[价格](https://api-docs.deepseek.com/quick_start/pricing/)、[协议](https://api-docs.deepseek.com/api/create-chat-completion)、[token说明](https://api-docs.deepseek.com/quick_start/token_usage)本轮HTTP200读取，SHA与上次一致。官方[tokenizer](https://cdn.deepseek.com/api-docs/deepseek_v4_tokenizer.zip)1911504bytes，SHA256 e7310d1dafe0a86d8a5629fe78a7c763760f651db9b8682718a1781dcd6fe495。隔离venv tokenizers0.22.1直接加载JSON，没有trust_remote_code。固定句 Hello!=2 token，学习目标：理解世界模型。=7 token。只校验本次3条完整wire和固定中英句，不置 tokenizer_parity_verified=true。公开论文来源[DreamerV3](https://arxiv.org/abs/2301.04104)。密钥、原始账本/付费响应在.local/App Support，不入Git。

## 修复与限制

P2：重启后 Undo 入口丢失。GET/api/route 通过 route_page 返回与图 revision 一致的持久 undo；core route_get 不变，兼容事务内推荐。UI load 恢复或清空 growth.undo；明确 event+revision 仍拒绝错撤销。Node 失败回归1fail→8pass，Python42pass，新包实际重启撤销通过。

独立审查 /root/route_logic：97项授权目标、146Python/71Node撤销目标通过；双连接、真实本机HTTP和loader交错探针通过，无剩余P1/P2。只取undo仍读取完整组织快照，大库成本未测。

脱敏探针独立解析复核通过，详见[独立审查](2026-10-07-route-v2-08-native-review.md)。生长原文重复 nearest:'c4' 同值，当前 parser 接受；只证明该覆盖场景能按当前合同解析，不证明严格重复字段合规或整体质量。

真实推荐价值、AI整体质量、全文语言准确率、账单/全面tokenizer、8GB资源及原发布门槛保留。语言最终保存和原生项目创建剩余验收需解锁完成；当前08不能done。
