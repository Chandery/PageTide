# 独立后端与通用 AI 失败审查（2026-10-08）

审查者：organization_ai 子代理。本人实现的 category_review_service、organization_facets 与 organization.js 不算本次独立审查范围。本次独立检查 root 的通用错误解释、速览反馈、学习图调用计数，以及另一代理的创建会话/本地学习图/引导合同实现；没有接受实现者总结代替检查。

范围：app/creation.py、app/growthproposal.py、app/service.py、app/guidance_contract.py、app/ai_guide.py、app/server.py、app/static/index.html、prompts/project-guidance.md。读取实际 caller、Gateway 失败结果形状、最终 diff；所有测试使用临时库与网关替身，没有模型请求或真实用户库访问。

## 发现及修复复验

1. **P1，已修复：展示 HTTP 原因后错误退还未知计费的调用次数。** `_ROUTE_UNPAID` 原先仅按展示 code 判断；HTTP 503 + usage_unknown 改为显示 http 后，生长、概念简介、旧创建起草与旧项目起草都错误退还尝试。学习图修改则仍用泛化 network 覆盖 HTTP 原因。新增独立 `tests/test_ai_failure_quotas.py`，首次运行 6 项全部失败：growth 10≠9，intro 20≠19（含 reserved-only），项目起草 3≠2，会话起草 0≠1，修改原因 network≠http。修复后，`_route_unpaid` 独立检查未知/预留标志，HTTP 仅明确 4xx 才退还；所有 6 项通过，HTTP 原因和原图均保留，明确 401 拒绝退次数，无自动重试。
2. **P2，已修复：切项目后旧 AI 故障仍显示。** 全局速览 banner 原先不会随项目切换清除，异步旧回复还能在新项目弹出旧成功/失败 toast。最终实现切换时清理 banner，回复和异常处理均检查原项目。独立执行实际页面函数的 6 个迟到场景（单篇/整批 × 成功/失败/异常），以跨项目 toast/load 调用即抛错作为断言，全部通过。单篇故障存储按项目和论文组合编号，先前摘要保留。
3. **P2，已修复：新增 choices 输入类型导致 500。** 模型解析器虽验证 choices，但客户端 draft 的数值/对象可在 `_bounded_guidance_draft` 切片时触发 TypeError/KeyError。已改为校验列表/文本/布尔类型并抛 ValueError；创建回归涵盖未发网关、未创建项目。

## 实际验证

- `python3 -m unittest discover -s tests -p test_ai_failure_quotas.py`：首次 exit 1 / 6 failed；修后 exit 0 / 6 passed。
- 独立组合运行失败解释、独立调用次数、创建 brainstorm、概念简介、项目管理、旧会话起草、学习图模型、生长建议：**205 tests / exit 0**，9.945 s。完整命令：`PYTHONPATH=tests python3 -m unittest tests.test_ai_failure_quotas tests.test_ai_failure_explanations tests.test_creation_brainstorm tests.test_concept_intro tests.test_project_manage tests.test_route_plan tests.test_route_map_model tests.test_growth_proposals`。
- `node --test tests/test_ai_failure_ui.cjs`：3 passed / exit 0；另外独立 6 个实际函数迟到执行场景通过。
- 独立敏感诊断哨兵检查：HTTP 401 与 URLError 中附带的秘密样例文本不会进入返回的展示文本。
- 独立中/英文引导请求检查：短目标和当前消息中明确的“不要机器人/强化学习”完整进入请求；完整 encoded envelope ≤ 1200。注册提示词包含当前 SYSTEM。
- 创建回归确认真实本地地图由目标/阶段生成并在 finalize 保存，阶段不冒充必需前置；AI 简介保持 AI 来源，手工改阶段保持用户来源，显式 skip_route 才可放弃地图，已有 AI 起草优先且不自动计为掌握。

## 结论与限制

上述独立范围内，发现的阻塞缺陷均已修复并重新验证，未发现剩余阻塞问题。唯一网关、1200/500 引导上限、显式触发、无自动重试、默认本地零模型 token 的边界保持。

这是离线软件行为审查，不是付费模型质量、用户满意度、计费精确性、原生界面或发布认证。长目标/消息、关键词、上一问和摘要仍可能按既有上限节选；最终 caller 根据实际已发送文本比较并给 scope_notice，完整原文留本地。这不能证明模型看到了全部约束，也不能证明新的 brainstorm 或论文分类模型判断稳定。构建及完整工作树/harness 验证由 root 留档；本人没有执行本轮构建。

## 追加：轻量 brainstorm 规则与预留标志独立复核

用户随后要求引导接入类似 brainstorm 的轻量 skill。本次另读 `app/project_brainstorm.py`、`app/guidance_contract.py`、注册提示词及实际 `guidance_turn` 网关消息，没有重新把已通过的 205 项全量当作新增模块证据。

- 初读提醒实现者：模块说明不能代替真正发给模型的规则，早确认必须写入实发规则；最终 `RULES` 已含 `skip known`、`ready=>confirm`、建议与取舍、一次一个缺口/二至三个选项、不确定时先建议、范围过宽或矛盾时提示、保留用户选择/不推断排除项。完整 RULES 由 guidance_contract.SYSTEM 直接拼接，并在实际 Gateway.call 捕获的系统消息中出现；注册提示词同步。
- 六阶段表只是本地 fallback 的优先话题表，没有作为强制六轮问卷外发。`known` 能跳过已明确阶段，`ready` 能第一轮进入确认。本地缺 key 的真实会话已提供目标时从 scope 开始，不重复询问领域；阶段细节属于本地代码，并未宣称模型看到了完整 `_LOCAL` 表。
- 独立执行早确认全链：第一条实际 guidance_turn 的替身回复 `ready=true`、空 next_question/choices，保存后 turn_count=1，立即 finalize 成功；没有要求补足六轮。网关实发内容包含轻量 RULES，不包含私有项目名。
- 中/英文、turn 1/2/6/20、极长中文/四字节 emoji 共 16 个完整 wire 场景：中文完整请求在 ≤1200；超长 emoji 在最小节选仍无法容纳时安全 ValueError；所有返回的 envelope output=500，turn 20 本地限制到6。拒绝也是合法结果，没有扩大预算来使测试通过。
- `python3 -m unittest discover -s tests -p test_creation_brainstorm.py`：**12 passed / exit 0**。上述实发捕获、早确认、wire 与预留标志断言另以独立离线脚本运行通过。
- `_ai_receipt` 的 reserved-only 修复已读并独立断言：usage_unknown=false、usage_reserved=true 不被改写为“无预留”，reservation 保留；该结果不能退还 HTTP 尝试，明确无未知/无预留的401可以退还。

新增模块未发现阻塞的软件合同问题。`skip known` 和建议规则确实进入模型消息，但实际模型能否识别明确领域、提出恰当方向、有效争论取舍仍为未付费实测的质量事项；本地阶段测试不能替代它。

## 追加：compact AI 学习图独立复核（2026-10-09）

用户继续要求把确认细节与右侧关键词、检索词、学习图接成简单闭环。待实现者明确源码稳定后，重新读 `guidance_contract.parse_graph/parse`、`service.guidance_turn/_bounded_guidance_draft/_finalize_guidance`、`ai_guide.local_route_draft`、真实 `project-creation.js` 的 `setDraft` 及注册提示词；只跑新增范围 targeted，没有重复旧 205 项全量，也没有付费调用或真实用户库访问。

新增独立发现并复验的两个 P2：

1. **已修复：清理后无检索词或简介仍接受模型图。** 原 parser 仅检查原字符串非空；中文名 + `terms=[":"]` 被接受为 `terms=[]`，英文名则静默补名称为检索词，`["---"]` 也被接受；控制字符简介能在清理后消失。独立首次实跑证实上述 terms 行为并通知实现者，最终 parser 在模型合同内检查清理后的有效英文词项和非空简介，未改变通用手工图规则。最终独立矩阵确认这三种词项样例及控制字符简介整图拒绝，不用名称补词使坏回复过关。
2. **已修复：只确认、未生成路径的回复改写手工文本作者。** 独立临时会话向 `guidance_turn` 传入用户阶段 `My stage / I wrote this`，模型 compact 仅回复确认信息、没有 graph/path；首次实际结果将路径和简介都标成 AI。最终成功分支只在模型实际返回 learning_graph/learning_path 时改来源，省略路径的确认回复保留用户作者。新增真实会话及 finalize 回归通过，独立同场景亦确认项目保存后的 intro_by=user。

最终合同与真实链路检查：

- 实发 SYSTEM 是 `r/d` 与 `k/q/a/c/s` 短键 schema，含 `prereqs=[[from,to]]`、显式 `targets=[id]`；后端转成现有草稿字段，旧 long-key 与 kw/queries/ask 回复仍兼容。为容纳图，最终 RULES 使用 `6max/ready now` 表达早确认，仍含 skip known、主动建议/取舍、不确定时建议和保留用户选择。实际系统消息包含 RULES，注册提示词与 SYSTEM 一致；没有把模块说明或完整本地阶段表说成实发模型指令。
- 独立 parser 矩阵：**20 个非法图提案全部 ValueError**，包括环、悬空/自边/重复边、重复 id/名称/目标、缺失/未知/非字符串目标、超量边、额外字段、空词和清理后无效内容。有效 3 节点/3 边地图保持全部显式边（包含传递边），目标未被自动补成叶子；空图返回 omitted。每节点保留有效检索词、简介及 AI 作者，论文形状不作为概念接纳。
- 独立真实临时会话：单次 compact 替身回复生成 source=ai_guidance 的 route_draft，stage_ids、三条前置和目标与模型提案一致；learning_path 从实际节点名称/简介派生。下一次坏图整图拒绝为 bad_reply，保留原图、accepted-turn count 与未知计费/预留标志；随后空图确认保留原图。finalize 无网关请求，保存图除已有反馈截点元数据外逐字段相同，AI 作者保持，manual mastery 为空。
- 读取并执行真实页面 `setDraft` 的 Node 回归：AI graph 替换自动本地图，阶段行取实际节点和简介并绑定实际 id，原前置边保留；手工编辑或明确丢弃的图不被覆盖。创建仍要求显式地图确认或放弃。该证据是生产函数执行，不是原生窗口视觉测量。
- 中/英文 × turn 1/2/6/20 × 极长中文/四字节 emoji 共16 个完整 wire 场景：**8 个完整 envelope ≤1200 且 output=500，8 个最小节选仍不够时安全拒绝**。短目标/当前回答的明确“不要机器人/强化学习”“不做代码复现”在两种语言实发 body 中完整保留；私有项目名与会话 id 不外发。单次 guidance call 复用原操作，无新增请求、无自动重试，quick1/guided6 频率和注册预算未扩大。

实际 targeted 结果：`python3 -m unittest discover -s tests -p test_creation_brainstorm.py` **16 passed / exit0**；`node --test tests/test_creation_review_fixes.cjs` **8 passed / exit0**。独立 matrix、wire、真实临时会话及手工作者脚本均 exit0，输出留于本机 `/tmp/pdh-independent-compact-graph-{python,node,matrix}.txt`（临时路径不作为可移植发布工件）。

本追加范围内发现的两个软件合同缺陷已修复并复验，未发现剩余阻塞问题。学习图前置是经过用户检查的 AI 提案，尚无付费模型质量或科学前置有效性实测；500-token 实际输出充分性、对话建议质量与付费使用量仍未测。本地目标/阶段图证据与替身 AI 回复证据分别标明，不把前者当作真实模型学习图测量。完整测试、harness 和桌面构建仍由 root 记录。
