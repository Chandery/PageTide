# 学习匹配修复与六目标冻结回放（2026-10-08）

本轮修复了科学身份遗漏、前沿选择只看最强单元、跨段拼词、用户固定目标未进入匹配，以及无用途的探索内容凑槽。以下是原有公开语料与原有代理标签的回归，不是新的人类盲评。软件通过不等于全部学科推荐有效、学习收益成立或整产品可发布。

## 1. 改了哪些软件行为

| 对应问题 | 最小修复 | 明确保留的边界 |
|---|---|---|
| B12/B20 前沿漏材料 | 尚未满足的最强单元锁定时，论文有明确原文匹配的第二单元可作为当前前沿材料；卡片记录实际前沿单元。 | 掌握仍只计最强一个单元；已满足的最强单元不借第二单元凑常规推荐。 |
| B14/B20 科学词法 | 支持一个具名科学限定词（如 latent graph dynamics、sulfide solid electrolyte）；视觉表征的 latent space/visual features 别名须有视觉输入证据；IFNα/β/γ 与 interfacial stabilization 使用窄身份/词形表面。 | 不把任意插词、心理学裸 latent、泛 cycling stability/impedance 当对应概念；原文引文必须是当前本地retrieval_text中的连续子串（题名、摘要或经过版本验证的本地文本）；公共探索query证据限题名/摘要。 |
| B20 跨段伪证据 | 精确匹配和限定词匹配两条分支都允许一次正常折行，拒绝空段、换页、段落分隔及跨句拼接。 | 正常 PDF 单折行和 CRLF 不受影响。 |
| B20 固定目标未接线 | 新 local learning_scope 只读已保存 goal/include 和明确项目关键词，固定 brief 对象优先；肯定矛盾的癌种、治疗、商业环境或电极 focus 被拦截。 | 不读论文 key/评审标签，不由宽学科名猜目标，不据排除子句扩大目标；通用基础和真正含目标对象的多对象比较保留。无已知矛盾不等于已证明有用。 |
| B20 全流程一致 | 普通候选、Route/探索、掌握、概念材料/简介、反馈重确认和当前卡片共用 scope；来源原论文仍保留。保存前原子核对目标未变，主页缓存签名包含 scope。 | 不改历史推荐用途；历史卡若与新目标冲突显示提示。模型 wire/额度不增加。 |
| B20 探索用途缺失 | 未匹配本身不再构成探索用途。只保留未满足的明确侧枝、真实公共探索query在题名/摘要中的命中、具已有正向资料的潜在方向；目的回执与批次/曝光在同一事务保存，卡片可核。 | 不凑探索槽；方向标为待用户审核，不授掌握；历史卡无回执明确提示。回执最多5条、UTF8 JSON32KiB，导出包含，失败全回滚。 |
| 本地重复处理 | 科学规范化显式缓存按 4 MiB、128 条、单输入8192字符同时限额；词组显式缓存256条、每条编译对象+pattern文本不超8KiB，key不超256字符；分类重用当前批已有分段。 | 新显式缓存合计保守上界约6.4MiB；没有新增整库或无界全文缓存，也不是整个App内存/8GB性能认证。 |

固定目标过滤回执包含固定来源字段、正向命中原文、论文题名和冲突 reason_code；界面提供原文依据。`semantic_value_judged:false` 明确说明这不是科学价值判定。独立复审的长前置排除与直接后置排除反例均先失败后修复，中英文正反控制保留；关键词不能扩大已保存的固定对象。人类元认知题名加被试/反应时间证据与视觉目标冲突，真实机器人/vision-based比较仍保留。

## 2. 数据与执行协议

- 六个原目标、原图、种子、300篇非种子/学科（40暖启动、10×20连续批次、最后60）、资格规则、独立曝光和逐批反馈不改。四策略各自新副本，先锁推荐再开放反馈。
- 每情境12个时间点：暖启动、10个连续批次、最终60。下表只汇总10批，普通与学习推荐分开。三学科共90论文—单元配对仍按原裸 `assign(graph,paper)` 协议衡量，未知不转有用。
- 本轮以发布日期模拟回放，固定既有来源结果；没有再次联网抓取，不能声称来源找回率或覆盖改善。
- 诊断中已经看过最后60标签，因此后续只能叫**已曝光回归集**，不是新的未见留出。
- 运行前冻结 App 源码快照，再载入。四阶段全部 passed，网络尝试0、模型调用0，原语料/标签/旧结果SHA均未变。

| 执行阶段 | 实际秒数 |
|---|---:|
| evaluate | 25.8208 |
| route-evaluate | 149.9255 |
| route | 77.7558 |
| lexical | 6.8778 |

本次源于 2026-10-07 21:51:52 UTC 冻结，全部回放依赖从冻结副本载入，运行中副本字节未变。原10个 App 入口加探索方向入口共11个 AST 与当前源一致；完整模块逐项 SHA 及输入 SHA 留在追溯记录。此次用途修复使用**新的完整回放**，不拿旧scope等效收据代替。

| 本次关键源码 | 冻结SHA256 |
|---|---|
| `app/learning_scope.py` | `c0a8a8d582d207fe713faf0148c75c3f5b4d1c174ded22e76e06f0c8897adc08` |
| `app/pathgrowth.py` | `417cd698f4317cf70bb93daf6bd0eb0ee797aceb9bb4e392c622259c7813ef04` |
| `app/ranking.py` | `85a82ccaa4719ac97b3f57d7549efad8bc6f5c743fb38a07b192de2f2521e205` |
| `app/route_batch.py` | `0851113dbf1a2cd1375a4c73c15f23aca8e537ae60315d00337c51039915f50f` |
| `app/db.py` | `883e755e6735024e5b40c963b333c8979fa38bb87ed494e25e3f6489d8e9a300` |
| `app/service.py` | `6dd659deb11e9691aa0d6a234e1bccb7fd1e49787c813263a2dd5e7396af1b1d` |
| `app/eligibility.py` | `26cb1b713a1b7b1e18c3487f3b164707ac7320bcf5c5a8a8eab5446199bb793e` |
| `app/organization_facets.py` | `0a354a647f833e42563ddd996d89585ccb9e865b8e2945f855ed22202ab934ef` |


回放后仅 `growthproposal.py` 顶层AI生成提示常量变化，函数AST全部相同；此回放使用固定图，无生成/已保存潜在方向、没有模型请求，故不影响推荐依赖。核心模块字节和全部11入口AST一致。六目标逐一复核300候选+5种子共 **6×305=1830条scope receipts**，冻结副本与当前代码同值1830、差异0。这是已知对象冲突软件判定，不是1830个人有用评级。

## 3. 普通推荐：同资格策略对照

单元格为“已一致有用/实际推送；U未知或分歧”。U没有计为有用。固定槽位P@5分母始终5。当前资格门在四个策略都执行，未给当前系统独占更容易的候选池。

| 情境 | 最新优先 | 关键词+日期 | 当前系统 | 冻结画像 | 当前P@5上下界 | 当前重复/难度错配 |
|---|---|---|---|---|---|---|
| 计算机·入门 | 27/50；U3 | 37/50；U7 | 44/50；U3 | 44/50；U3 | 0.88–0.94 | 0；8/27已评 |
| 计算机·研究 | 24/50；U10 | 28/50；U9 | 38/50；U7 | 38/50；U7 | 0.76–0.90 | 0；0/20已评 |
| 材料·入门 | 35/50；U7 | 40/50；U7 | 38/50；U9 | 38/50；U9 | 0.76–0.94 | 0；3/43已评 |
| 材料·研究 | 20/50；U15 | 32/50；U12 | 34/50；U12 | 34/50；U12 | 0.68–0.92 | 0；0/43已评 |
| 医学·入门 | 31/50；U14 | 36/50；U12 | 44/50；U4 | 44/50；U4 | 0.88–0.96 | 0；2/42已评 |
| 医学·研究 | 22/50；U7 | 20/50；U12 | 37/50；U6 | 37/50；U7 | 0.74–0.86 | 0；0/40已评 |

普通四策略同资格。材料入门关键词基线的有用数仍高于当前；不能把当前系统自动写成胜出。当前与冻结画像几乎相同，本协议没有证实稳定反馈收益；显式反馈软件正确不代替推荐收益。

## 4. 学习推荐：前沿与来源语义仍有短板

| 情境 | 最新优先 | 关键词+日期 | 当前系统 | 冻结画像 | 当前P@5上下界 | 当前重复/难度错配 |
|---|---|---|---|---|---|---|
| 计算机·入门 | 23/40；U0 | 22/40；U0 | 22/40；U0 | 22/40；U0 | 0.44–0.44 | 11；6/29已评 |
| 计算机·研究 | 18/50；U15 | 18/50；U15 | 17/50；U16 | 17/50；U16 | 0.34–0.66 | 21；0/37已评 |
| 材料·入门 | 40/50；U5 | 39/50；U6 | 40/50；U6 | 39/50；U6 | 0.80–0.92 | 0；2/43已评 |
| 材料·研究 | 16/50；U26 | 20/50；U25 | 21/50；U24 | 21/50；U25 | 0.42–0.90 | 14；0/46已评 |
| 医学·入门 | 29/50；U18 | 30/50；U19 | 33/50；U17 | 33/50；U17 | 0.66–1.00 | 13；2/39已评 |
| 医学·研究 | 24/50；U7 | 21/50；U9 | 28/50；U7 | 29/50；U6 | 0.56–0.70 | 12；0/45已评 |

少推导致固定槽位P@5与有用/实推不同，不能把少推后的有用率当学习覆盖充分。计算机基础偏难和材料研究标签分歧仍需逐科关注。探索不再仅因unmatched填槽，来源query/侧枝/正向方向目的必须可核。仓库P@5≥0.6只作探索筛查，未用于通过整个产品。


十批当前实际覆盖的去重论文数（重复曝光不重复算篇）：

| 情境 | 普通去重有用/去重实推 | 学习去重有用/去重实推 |
|---|---|---|
| 计算机·入门 | 44/50 | 22/29 |
| 计算机·研究 | 38/50 | 17/30 |
| 材料·入门 | 38/50 | 40/50 |
| 材料·研究 | 34/50 | 21/36 |
| 医学·入门 | 44/50 | 33/37 |
| 医学·研究 | 37/50 | 28/38 |

各批原协议候选池覆盖上下界、实际论文题名/来源/理由/角色和少推原因保留于coverage-and-cases。该覆盖只针对当时合格可见池，不是全领域召回；Route原工具的分母排除已有反馈论文，而路径允许尚未理解材料重现，因此Route此诊断列不能直接作为前沿有效覆盖。上表用去重有用篇数显示实际触达。CS研究原P@5下降且十批21次重复，不能称体验/学习收益已通过；移除无用途探索还改变后续曝光与反馈轨迹，此前较好的中间版本数值未作为最终结论。

## 5. 前后差值与反馈收益限制

此处“新–旧”是完整pipeline回归：同时有资格、词法和选择改变，**不是纯排序收益**。新四策略已有同资格公平对照。差值范围包含原标签未知；95%包络仅是10时间批次描述性重采样，不是独立用户总体置信区间。

| 模式/情境 | 旧当前有用/推送；U | 新当前有用/推送；U | 新–旧ΔP@5范围 | 描述性95%包络 | 当前–冻结ΔP@5范围 |
|---|---|---|---|---|---|
| 普通·计算机·入门 | 44/50；U3 | 44/50；U3 | -0.06–0.06 | -0.14–0.14 | -0.06–0.06 |
| 普通·计算机·研究 | 41/50；U6 | 38/50；U7 | -0.18–0.08 | -0.28–0.18 | -0.14–0.14 |
| 普通·材料·入门 | 34/50；U12 | 38/50；U9 | -0.16–0.26 | -0.30–0.38 | -0.18–0.18 |
| 普通·材料·研究 | 37/50；U10 | 34/50；U12 | -0.26–0.18 | -0.40–0.28 | -0.24–0.24 |
| 普通·医学·入门 | 43/50；U4 | 44/50；U4 | -0.06–0.10 | -0.16–0.18 | -0.08–0.08 |
| 普通·医学·研究 | 37/50；U6 | 37/50；U6 | -0.12–0.12 | -0.24–0.20 | -0.14–0.12 |
| 学习·计算机·入门 | 22/49；U7 | 22/40；U0 | -0.14–0.00 | -0.32–0.22 | 0.00–0.00 |
| 学习·计算机·研究 | 21/50；U15 | 17/50；U16 | -0.38–0.24 | -0.52–0.32 | -0.32–0.32 |
| 学习·材料·入门 | 26/50；U19 | 40/50；U6 | -0.10–0.40 | -0.26–0.50 | -0.10–0.14 |
| 学习·材料·研究 | 21/50；U20 | 21/50；U24 | -0.40–0.48 | -0.50–0.66 | -0.50–0.48 |
| 学习·医学·入门 | 30/50；U16 | 33/50；U17 | -0.26–0.40 | -0.42–0.52 | -0.34–0.34 |
| 学习·医学·研究 | 29/50；U6 | 28/50；U7 | -0.14–0.12 | -0.28–0.26 | -0.14–0.12 |

同轮基线差值（每项为均值上下界；括号内描述性95%包络）：

| 模式/情境 | 当前–最新ΔP@5 | 当前–关键词日期ΔP@5 |
|---|---|---|
| 普通·计算机·入门 | 0.28–0.40（0.14–0.54） | 0.00–0.20（-0.10–0.28） |
| 普通·计算机·研究 | 0.08–0.42（0.00–0.54） | 0.02–0.34（-0.08–0.44） |
| 普通·材料·入门 | -0.08–0.24（-0.20–0.32） | -0.18–0.14（-0.32–0.20） |
| 普通·材料·研究 | -0.02–0.52（-0.10–0.64） | -0.20–0.28（-0.30–0.40） |
| 普通·医学·入门 | -0.02–0.34（-0.12–0.52） | -0.08–0.24（-0.18–0.36） |
| 普通·医学·研究 | 0.16–0.42（-0.00–0.54） | 0.10–0.46（-0.08–0.56） |
| 学习·计算机·入门 | -0.02–-0.02（-0.08–0.04） | 0.00–0.00（-0.06–0.06） |
| 学习·计算机·研究 | -0.32–0.30（-0.42–0.42） | -0.32–0.30（-0.42–0.42） |
| 学习·材料·入门 | -0.10–0.12（-0.20–0.22） | -0.10–0.14（-0.24–0.22） |
| 学习·材料·研究 | -0.42–0.58（-0.58–0.76） | -0.48–0.50（-0.60–0.68） |
| 学习·医学·入门 | -0.28–0.42（-0.42–0.52） | -0.32–0.40（-0.46–0.54） |
| 学习·医学·研究 | -0.06–0.22（-0.18–0.34） | -0.04–0.28（-0.16–0.38） |

所有六目标的当前–冻结范围均包含0；不关闭画像个人价值门槛。逐批差值、曝光、反馈、实际key、来源/缺摘要/语言资格/短缺原因均保存在隔离私有追溯结果，旧结果未覆盖。

## 6. 已曝光最后60：少推与合适材料不能混淆

| 情境 | 普通当前有用/实推；U、P@5 | 学习当前有用/实推；U、P@5 |
|---|---|---|
| 计算机·入门 | 3/5；U1，0.60–0.80 | 1/1；U0，0.20–0.20 |
| 计算机·研究 | 2/5；U2，0.40–0.80 | 1/1；U0，0.20–0.20 |
| 材料·入门 | 3/5；U1，0.60–0.80 | 4/5；U1，0.80–1.00 |
| 材料·研究 | 4/5；U1，0.80–1.00 | 3/5；U2，0.60–1.00 |
| 医学·入门 | 4/5；U1，0.80–1.00 | 4/5；U1，0.80–1.00 |
| 医学·研究 | 4/5；U1，0.80–1.00 | 4/5；U1，0.80–1.00 |

计算机最后60中45篇语言未知，15篇报英语，但英语且有可用摘要仅6篇；保持语言资格，没有由标题猜语言。本次最终学习推荐在两类CS目标均只送1篇、有用1篇（1/1，固定P@5=0.2）。材料是 **Shaping latent space by architecture for improved world model planning**（DOI `10.21256/zhaw-37476`）：摘要明确DINOv2视觉features→learned latent space→Push-T规划，支持当前视觉前沿。此前冻结版本总推2篇/有用1篇，其中心理学 **Dissociating Reasoning and Planning through Markov and Quantum Metacognitive Dynamics** 被无用途unmatched探索槽带回；本次已由目标环境与用途门排除。这里明确区分此前1有用/2实推与当前1有用/1实推，不隐藏探索槽。其余合格MPC/视觉伺服论文不自动成为尚未完成的视觉表征基础，故没有凑五篇；找到1篇适合材料仍不是充分覆盖。

## 7. 原90配对与实际scope要分开看

原90调用只有图和论文，没有个人目标。医学固定4节点没有NSCLC词，材料transport节点只有sulfide electrolyte/ionic conductivity，CS dynamics只有world model/latent dynamics；因此裸测量不足以检查不同癌种/电极/环境的固定目标。**未修改原90协议和结果**；另外把应用已有固定scope传给同90素材作软件回归，并非新的独立盲评。

| 学科 | 原裸assign TP/FN/FP/TN；未知 | 新裸assign TP/FN/FP/TN；未知 | 另列实际固定scope TP/FN/FP/TN；未知 |
|---|---|---|---|
| 计算机 | 0/14/1/12；3 | 2/12/1/12；3 | 2/12/0/13；3 |
| 材料 | 7/14/1/7；1 | 8/13/1/7；1 | 8/13/0/8；1 |
| 医学 | 7/6/1/12；4 | 7/6/2/11；4 | 7/6/0/13；4 |

### 四个确定误配逐例

| 固定案例 | 原文focus与问题 | 最终处理 |
|---|---|---|
| cs-pair-30：Business World Model | 商业语义、组织和市场的world model，明确与物理环境不同；裸world model词语有匹配。 | 用户视觉世界模型/规划scope下拦截different_environment_focus；商业目标正控制保留。 |
| materials-pair-13：Si/Sulfide Electrolyte Interface | Si/Li3PS4合金化SEI实测界面，不是固定锂金属/硫化物bulk基础。论文确实含sulfide electrolyte。 | 固定锂金属界面scope下拦截different_electrode_focus；真实同时比较锂金属的控制保留。 |
| medicine-pair-11：Liver Cancer TME | 肝癌代谢/免疫微环境综述，摘要无NSCLC目标对象。 | NSCLC scope下拦截different_disease_focus。 |
| medicine-pair-25：TNBC Spatial Immunophenotypes | TNBC antiPD1反应、患者phase-II证据；不能当NSCLC验证。 | NSCLC scope下拦截different_disease_focus；多癌种含NSCLC比较正控制保留。 |

### 尚未匹配的有用标签逐例

下表忠实保留代理有用标签，同时区分其支持是直接词法、关系语义、相邻背景还是材料不足。没有为增加TP改图/检索词/目标或论文key规则。

| 案例 | 论文 | 漏配链与限制 |
|---|---|---|
| cs-pair-01 | [Learning Concept-Based Causal Transition and Symbolic Reasoning for Visual Planning](https://doi.org/10.1109/iros58592.2024.10802420) | 视觉输入被抽象成concept representations，明确关系语义；未出现固定visual representation/latent state表面。不能只见visual inputs就授表征覆盖。 |
| cs-pair-06 | [Visual Servoing of AGV Based on Nonlinear Model Predictive Control](https://doi.org/10.1109/ccdc55256.2022.10034193) | AGV解析非线性MPC/运动学，相邻控制知识；固定单元是latent dynamics/world model，标签支持比术语范围更宽。 |
| cs-pair-11 | [Audio-Visual World Models: Learning Physically Grounded Multisensory Dynamics](https://doi.org/10.48550/arxiv.2512.00883) | Audio-visual world model主要是多感官动作动态，能作为规划背景；未给固定MPC/visual planning表面或充分规划算法。 |
| cs-pair-13 | [Learning Robotic Manipulation Tasks through Visual Planning.](https://openalex.org/W3135512538) | 视觉DQN/model-free机器人任务，能补背景；没有明确潜变量表征，不能把所有vision-based应用等同表征基础。 |
| cs-pair-15 | [Learning from Reward-Free Offline Data: A Case for Planning with Latent Dynamics Models](https://doi.org/10.48550/arxiv.2502.14819) | 离线JEPA latent-dynamics规划，直接模型规划关系；MPC/visual planning固定词未出现，需关系语义不能泛别名。 |
| cs-pair-19 | [Predictive but Not Plannable: RC-aux for Latent World Models](https://doi.org/10.48550/arxiv.2605.07278) | RC-aux可达性与像素世界模型规划，直接planner关系；固定MPC/visual planning未出现。 |
| cs-pair-22 | [On Trade-offs of Image Prediction in Visual Model-Based Reinforcement Learning](https://openalex.org/W3126279544) | 图像预测MBRL的预测环境动态与规划关系，缺latent dynamics/world model表面；科学关系不是简单拼词。 |
| cs-pair-23 | [Visual-Inertial Odometry With Online Calibration of Velocity-Control Based Kinematic Motion Models](https://doi.org/10.1109/lra.2022.3169837) | 视觉惯性估计和速度控制运动学，主要VIO、规划前向模型背景；不是固定规划法的直接表面。 |
| cs-pair-24 | [Back to Parsimonious Latents: Learning Task-Centric World Models from Visual Foundations](https://doi.org/10.48550/arxiv.2605.25620) | 任务中心latent与多环境/test-time planning可作评估背景；未明确generalization/model uncertainty测量。 |
| cs-pair-25 | [Active View Planning for Visual SLAM in Outdoor Environments Based on Continuous Information Modeling](https://doi.org/10.1109/tmech.2023.3272910) | SLAM信息/Fisher/地图状态视图规划，视觉状态/map概念相关；不是既定潜变量编码表面，不能宽映射所有visual。 |
| cs-pair-26 | [DR-MPC: Disturbance-Resilient Model Predictive Visual Servoing Control for Quadrotor UAV Pipeline Inspect](https://doi.org/10.1109/iros60139.2025.11247550) | 解析MPC+扰动观测器的视觉伺服，属控制背景；未建立learned latent dynamics/world model。 |
| cs-pair-27 | [Sampling-Based View Planning for MAVs in Active Visual-inertial State Estimation](https://doi.org/10.1109/iros47612.2022.9981941) | MAV采样view planning与视觉惯性状态估计，规划方法相邻；无固定MPC/visual planning表面。 |
| materials-pair-01 | [The role of phosphorus in the solid electrolyte interphase of argyrodite solid electrolytes](https://doi.org/10.1038/s41467-025-64357-3) | Li6PS5Cl中LixP扩散控制SEI生长，界面输运有用；缺sulfide electrolyte/ionic conductivity表面，化学身份/过程关系需进一步语义证据。 |
| materials-pair-03 | [Effect of current density on the solid electrolyte interphase formation at the lithium∣Li6PS5Cl interface](https://doi.org/10.1038/s41467-022-34855-9) | Li沉积current density与SEI，未测critical current density/枝晶；interface/characterization已有两匹配，failure标签语义更宽。 |
| materials-pair-04 | [Degradation of Lithium Iron Phosphate Sulfide Solid-State Batteries by Conductive Interfaces](https://doi.org/10.1021/acs.jpcc.3c05039) | LFP化学/电化学失稳与XAS/XPS，能学评估但对象是正极；未出现稳定性/阻抗固定表面，需对象和过程关系判定。 |
| materials-pair-06 | [Unprecedented Self‐Healing Effect of Li6PS5Cl‐Based All‐Solid‐State Lithium Battery](https://doi.org/10.1002/smll.202101326) | Li6PS5Cl分解/metallic lithium生长、self-healing原文有用；Li-metal和interface不构成固定短语，关系语义不是词法同一。 |
| materials-pair-07 | [Synthesis of Fluorine-Doped Lithium Argyrodite Solid Electrolytes for Solid-State Lithium Metal Batteries](https://doi.org/10.1021/acsami.1c24468) | F掺杂SEI/XPS/AIMD和对称循环可补背景；摘要没有枝晶或CCD失效测试，不能为匹配冒称有此证据。 |
| materials-pair-10 | [Interface Design Enabling Stable Polymer/Thiophosphate Electrolyte Separators for Dendrite‐Free Lithium Metal Batteries](https://doi.org/10.1002/ange.202218044) | Li/SE界面副反应与LiF层，直接关系但缩写未形成lithium metal interface同一词组；Li/SE不能无对象证据自动等同锂金属界面。 |
| materials-pair-14 | [Interface Design for High‐Performance All‐Solid‐State Lithium Batteries](https://doi.org/10.1002/aenm.202303046) | 插入interlayer、Li3Bi锂化和沉积位置，直接反应知识；interlayer不自动等于interphase，不能为通过改科学含义。 |
| materials-pair-16 | [In situ formation of a Li 3 N-rich interface between lithium and argyrodite solid electrolyte enabled by nitrogen doping](https://doi.org/10.1039/d1ta03343c) | 短摘要仅给N掺杂、Li3N-SEI、CCD/循环表现；测试条件/方法不足，不能当完整稳定性评估材料。 |
| materials-pair-21 | [Li6PS5Cl microstructure and influence on dendrite growth in solid-state batteries with lithium metal anode](https://doi.org/10.1016/j.xcrp.2022.101043) | Li6PS5Cl晶粒/微结构/局部电流与CCD，输运应用背景；缺固定离子电导/bulk词，主线机械失效。 |
| materials-pair-22 | [One Stone, Three Birds: An Air and Interface Stable Argyrodite Solid Electrolyte with Multifunctional Nanoshells](https://doi.org/10.1002/advs.202304117) | 纳壳界面compatibility及interfacial reactions能支持反应；固定lithium metal interface/interphase不出现，需对象关系语义。 |
| materials-pair-24 | [Sulfide/Polymer Composite Solid‐State Electrolytes for All‐Solid‐State Lithium Batteries](https://doi.org/10.1002/aenm.202403602) | 复合电解质综述的interface impedance，评估背景有用；impedance含频率/反应成分，不无条件改写成resistance。 |
| materials-pair-26 | [Purity of lithium metal electrode and its impact on lithium stripping in solid-state batteries](https://doi.org/10.1038/s41467-025-61006-7) | steel/Li6PS5Cl电沉积纯度和Na杂质/stripping，界面应用背景；没有固定interphase/metal-interface短语。 |
| materials-pair-29 | [High plating currents without dendrites at the interface between a lithium anode and solid electrolyte](https://doi.org/10.1038/s41560-025-01847-0) | 致密化/孔裂纹/CCD模型与实测，导体结构输运背景；主要枝晶机械问题，缺离子电导/硫化物表面。 |
| medicine-pair-03 | [MER4 endogenous retrovirus correlated with better efficacy of anti-PD1/PD-L1 therapy in non-small cell lung cancer](https://doi.org/10.1136/jitc-2021-004241) | MER4/嗜酸细胞浸润与ICI结局关联，能学微环境相关证据；未出现TME/exhaustion表面，不宣称因果耗竭。 |
| medicine-pair-04 | [Hsa-LINC02418/mmu-4930573I07Rik regulated by METTL3 dictates anti-PD-L1 immunotherapeutic efficacy via enhancement of Trim21-mediated PD-L1 ubiquitination](https://doi.org/10.1136/jitc-2023-007415) | lncRNA-PDL1、细胞/鼠和患者IHC，适合比较证据；没有primary/acquired-resistance研究设计，节点名比固定词更宽。 |
| medicine-pair-16 | [High-dose ascorbic acid synergizes with anti-PD1 therapy in non-small cell lung cancer in vitro and in vivo models](https://doi.org/10.3389/fimmu.2024.1512605) | AA+antiPD1体外/鼠模型，支持临床前证据边界；没有原发/获得性耐药队列或患者获益证明。 |
| medicine-pair-18 | [Hypoxia is linked to acquired resistance to immune checkpoint inhibitors in lung cancer](https://doi.org/10.1084/jem.20231106) | IFNγ别名现有原文evidence，概念材料接口已找回；裸assign最多2节点，axis/evidence分值先占两位，presentation仍被表示上限截断。保留该FN，不冒充符号修复已提高90 TP。 |
| medicine-pair-23 | [N6-methyladenosine-modified circIGF2BP3 inhibits CD8+ T-cell responses to facilitate tumor immune evasion by promoting the deubiquitination of PD-L1 in non-small cell lung cancer](https://doi.org/10.1186/s12943-021-01398-4) | circIGF2BP3-PDL1、CD8互作/鼠干预/患者关联，能支持微环境机制；未出现固定TME/exhaustion表面，需要关系级语义判定。 |
| medicine-pair-24 | [Cell-intrinsic PD-L1 signaling drives immunosuppression by myeloid-derived suppressor cells through IL-6/Jak/Stat3 in PD-L1-high lung cancer](https://doi.org/10.1136/jitc-2024-010612) | IL6/Jak/Stat3/MDSC、鼠干预与ICI患者关联，证据评估有用；未明确primary/acquired resistance分型，不能凭一般nonresponse替代。 |

另两个已明确找回的CS正例：Hierarchical Planning with Latent World Models 的 visual world models/latent space 在视觉证据下匹配visual；G-DOOM 的latent graph dynamics匹配dynamics。材料 Interfacial Stabilization by Prelithiated Trithiocyanuric Acid 的词形与原文稳定界面现在支持characterization（原30配对TP7→8）。

## 8. 软件验证与尚未关闭的门槛

- 失败先行：核心学习匹配初次4断言失败+1IndexError；跨段反例初次失败；窄IFN/稳定化回归初次IndexError；已有目标接线3个真实App回归初次全部断言失败；长否定回归初次失败。均未改评审标签后通过。
- 最终 focused Python：280/280 passed，exit0，5.129秒；包括学习匹配13项、scope13项及既有Route/基础排序/分类/组织/增长回归。用途失败先行回归在旧行为下无依据仍推送；添加正向来源后才允许探索。
- Node实际UI/i18n/Route批次合同32/32 passed，exit0，83.1255ms；英文extractor 0 missing /1405；实际native原文详情几何由主工作单元补验，不能以Node代替。
- 独立实际API复核确认侧枝用途冷重启仍可查、没有来源目的的unmatched不推；receipt INSERT故障时批次/曝光/receipt全部回滚；未知key、40KiB、NaN拒绝，旧默认Store调用兼容。旧Route fixture最初12项失败，因为它们仅提供无用途unmatched内容；补明确题名/摘要公共来源前提，并在同输入双App里复制相同来源，保留原3+1+1断言与未匹配负控制；未改六目标公开语料、原标签或旧协议。
- 原90按学科保留差异；另列scope90软件回归把4个确定错对象拦截。原种子没有 prior exposure 的重复返回0/30种子、六目标均为0；Route的沉默允许材料重现，重复数已如表披露。
- API/source未知语言、缺摘要及固定词无法表达完整关系语义仍可限制覆盖。没有新来源抓取、人类盲评、真实长期学习效果或满意度；个人价值、标签有效性、科学语义质量与整产品发布门槛仍 open。
- 此代理未启动正式App、未使用模型或更改正式资料/账本；之前正式库一致性backup、196稳定文件/两账本保护与独立native资料副本见 [保护准备](2026-10-08-fixes-baseline-preservation.md)。
- 真实桌面构建、原生save/quit/恢复和最后资料保护复核由主工作单元完成；本报告只记录这里实际跑过的检查。

追溯文件全部在本轮隔离 `.local/audit-fixes-native-20261008/replay-purpose-final/`：不可变输入/旧结果、冻结源与SHA、comparison、sanitized-summary、逐批rank/feedback、scoped-unit-pair-check、scope-final-equivalence、dependency-source-check、coverage-and-cases；私有输入没有写入Git。文档中的论文均是原公开测试库资料，不含原用户私有论文详情。

## 主工作单元追加的同源边界

回放完成后，AI 的首批 fixed_scope、growthproposal.messages/提示和原文窗口防护又有修复；周报 learning_map 也补接现有固定 scope。它们不在本次禁止模型调用、无生成方向的排序回放调用路径。独立复核确认原29输入、45冻结源清单、11实际排序入口AST和1830范围收据均与回放封存一致；不能把所有当前模块称为与冻结版同字节。周报真实入口的错癌种/错治疗/正确癌种/比较研究五组另行复核，错误论文不再虚报单元推进；不改原回放标签或排名。
