# 独立代理科学内容盲评 D — final r19

日期：2026-10-08。唯一输入 SHA256：`cdc53d964fd4d7f89bec96bac44198951c046cf783d88e1bb4264da95cfaff68`。

只读指定盲包，未读源码、排名/金标准、其他评审或账本，未联网、未调用其他模型/UI，结束前未交换结论。这里的完整来源仅为输入的完整公开标题/摘要；未核全文、来源真实性或外部事实。此报告是代理判断，**不是人类学科专家审查、真实用户价值/满意度或产品实测验证**。

18个案例是三学科×两固定目标×三重复；每案例20个论文判断，共360条实例、60个学科内标题/摘要记录。版本相同方法和重复运行不能当独立研究。363个实际窗口实例中，材料v1r1有3篇重复送窗；原因未评，不由此推算收费。72条来源摘要缺失实例对应12个记录。

## 判定方法

passed仅表示具体最终结论或可选探索任务得到包内来源支持；failed要求具体对象、治疗、研究证据能力或映射错误；unclear最终动作一律unknown，即使其理由另有错误；not_evaluated表示未开展的验证。短引能逐字匹配并不等于其上下文支持科学判断。case含failed则failed，其余有unknown则unknown。方向与其对应论文重复计数在不同分母，不相加。 12个方向中9个optional_relation显式true，3个为null；空强制前置和new_branch分类不等于已验证界面显式展示探索标签。

## 真实计数

|分母|passed|failed|unknown|not_evaluated|
|---|---:|---:|---:|---:|
|论文判断360|23|17|320|0|
|完整案例18|0|10|8|0|
|持久化方向12|4|4|4|0|

实际输出：{'unclear': 311, 'covered': 37, 'new': 12}。所有311条unclear都保持unknown，未把保守弃权算成有用推荐。引用核对124条，offset逐字失配0条，不在送窗中的引文0条；这仅是来源位置核对。

|学科（各120条）|passed|failed|unknown|方向数|
|---|---:|---:|---:|---:|
|cs|23|5|92|12|
|materials|0|0|120|0|
|medicine|0|12|108|0|

## 分学科结论

CS：多数已覆盖判断能粗映射世界模型动力学/规划，DINO-WM/JEPA-Bisim可保留为候选。但高级长时程/OOD用途往往只在完整摘要可见，模型窗口删除了关键评估。泛潜空间导航和视觉RL新方向重复已有能力，真正的policy初始化/residual action增量未保住。量化研究属于规划误差评估，不能仅凭world model把nearest放在动作动力学。

材料：全部120条均未达到本审的完整肯定支持（1条covered仍为window证据不足）。这不是材料120条正确率100%；该输出未建立明确候选用途。完整源已存在Li界面模拟、Li6PS5Cl/Li7P3S11稳定性/层析比较、失败机制综述。正极/负极、金属硫化物人工层/硫化物电解质、固态Li/ether-based液态Li必须分开；不能把共现当体系相同。

医学：12条covered全部错误集中在基础PD1/PDL1轴。CD155是回顾性关联，cytokine是观察性预测，ascorbic acid是共培养/鼠增敏，circUSP7是外泌体CD8机制，能力和研究类型不同。KRAS/铂耐药不能替换PD1耐药；GP病例系列不能证明疗效，TAM/Blimp1模型不能当患者因果/临床疗效验证。其余大量unknown没有经过真实价值验证。

## 缺陷线索

- **D1 (failed)**：医学12条持久化covered全部映射到基础PD1/PDL1轴，抹平TME、CD8功能、CD155观察性关联、cytokine预测和动物增敏实验。 关键词/治疗名可能主导nearest；需要保持研究对象、实验类型及foundation与机制/证据任务分离。未读源码，原因仅是假设。
- **D2 (failed)**：模型窗口选择经常丢掉方法、对象或设计：cfDNA仅作者/引文尾部，LDN标题删除对象，ascorbic acid标题删药名和in vitro/in vivo，Planning Limits删除全部关键对照。 需要检查窗口选择/截断；较高unclear比例是实际功能缺口，不是科学正确率。
- **D3 (unknown)**：材料120条判断仅1 covered且仍只能由完整源核对；Li6PS5Cl/Li7P3S11比较/表征及硫化物-卤化物failure摘要窗口已含任务，却持续unclear。 可能将可归现有节点的学习内容和独立新增任务混为一谈，或证据门槛过严；需源码/新增真实运行复核。
- **D4 (failed)**：CS有泛world-model navigation或visual RL新方向重复既有动力学/规划和高级已知基础，未保留policy prior或residual action真实增量。 先判断已有topic中的具体方法增量，再决定新增branch；把强前置降为optional可降低风险，但不能解决新旧能力错误。
- **D5 (unknown)**：同源同窗重复判断不稳定；Drive-WM两个版本亦可能一covered一unclear。材料v1r1送出23fragment，#1/#10/#15各出现两次。 检查版本去重、重复续跑及同窗判定稳定性；仅凭本包不能判定重复是缺陷还是有意重试，也不推算账单。
- **D6 (unknown)**：原graph的医学内在→TME及材料化学→失效依赖不能视为普遍必需，高级基础active状态与persona已有知识有张力。最终新增方向未保留强制needs/required_by。 区别用户给定教学顺序、学科因果、实际学习必要性；原graph来源与prompt完整性未评。

## 逐案例、逐论文记录

下表编号为对应案例输入中的0-based原source顺序。JSON保留每条完整对象/治疗/实验解释、实际窗口文字/offset、模型原判断、持久化判断、映射/理由独立状态及引用核对。每条下述结论只评价所述包内科学内容。

### cs-growth-v0-r1 — failed

目标：理解世界模型如何从视觉观测预测状态并支持规划，能比较基础方法的假设和局限。 已有基础：了解监督学习、基础概率与神经网络；尚未系统学习强化学习。

论文计数：{'passed': 3, 'failed': 1, 'unknown': 16, 'not_evaluated': 0}；方向计数：{'passed': 0, 'failed': 1, 'unknown': 0, 'not_evaluated': 0}。有内容/映射失败，不能判该完整案例科学正确。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 An Empirical Study of World Model Quantization|unclear / 无映射 → **unknown**|DINO-WM量化实验比较权重/激活、位宽、50轮规划与任务成功失配；与误差及规划局限有关，不只是无关模型压缩。 窗口只有失败结论，丢失DINO-WM、量化配置、规划视野和实验设计；不能据此详细比较模块敏感度。|
|1 Beyond Visual Quality: A Study of Test-Time Planning with World Action Models|unclear / 无映射 → **unknown**|世界动作模型同状态候选行动选择，比较视觉质量、物理一致性与任务进展评分；是决策用途评估，不等于生成质量。 窗口保留selector与干预，但丢失WAM定义、oracle对照、同状态设计和轨迹阶段；无法核实收益大小。|
|2 DINO-WM: World Models on Pre-trained Visual Features enable Zero-shot Planning|covered / 动作条件动力学 → **passed**|DINO-WM用离线轨迹预测DINOv2 patch特征，经行动序列优化达成目标；六环境零样本规划直接相关。 标题与首句支持控制条件预测/规划，窗口丢失离线训练、patch特征、目标优化及六环境细节。|
|3 Driving Into the Future: Multiview Visual Forecasting and Planning with World Model for Autonomous Driving|unclear / 无映射 → **unknown**|Drive-WM在自动驾驶场景预测多视图未来，以图像奖励比较轨迹；是具体应用示例，不能当必需基础。 窗口只有驾驶规划背景和模型名，未展示多视图条件、不同maneuver、图像奖励或评估；高级机器人OOD用途仅部分对应。|
|4 Driving into the Future: Multiview Visual Forecasting and Planning with World Model for Autonomous Driving|unclear / 无映射 → **unknown**|与前一Drive-WM记录为同一方法的不同出版版本；不构成独立方法或独立验证。 与前一版本的可见摘要窗口语义相同；一个covered、另一个unclear的差异缺乏来源依据。|
|5 Gradient-based Planning with World Models|covered / 模型规划 → **passed**|可微世界模型梯度MPC与CEM/MPPI、policy对照，匹配模型规划；高级已知MPC可作方法比较，不能重复当基础课。 标题+MPC短窗足以粗映射规划，但丢失梯度优化机制、基线比较、混合policy及样本效率结果。|
|6 HiWE: Hierarchical World Knowledge Model with Visual Keypoint Enhancement for Zero-Shot 3D Path Planning|unclear / 无映射 → **unknown**|HiWE通过PointVLM视觉坐标、深度、3DLLM末端waypoint和grasp执行任务；并未展示动作条件潜动力学世界模型。 窗口保留交互定位/运动/接触，却丢失语言规划器和visual fine-tuning背景；不能按标题world knowledge推世界模型动力学。|
|7 JEPA-Bisim: Learning Robust Visual Representations for Planning with Joint-Embedding Predictive World Models|covered / 动作条件动力学 → **passed**|JEPA-Bisim用bisimulation控制相关表征改善背景变化/视觉干扰鲁棒性，PointMaze和PushT；直接对应高级OOD目标。 窗口只讲潜空间规划，不含slow features、bisimulation、两个任务或鲁棒性结果；可粗映射动力学，不能验证其OOD贡献。|
|8 Learning Visual Planning Models from Partially Observed Images|unclear / 无映射 → **unknown**|Recplan从部分观测图像学习latent transition及距离启发式，用经典规划器；部分可观测状态/动力学与规划相关。 窗口保留部分观测转移模型，却截掉潜表征、heuristic和classical planner；可以做候选粗映射，不能证明新独立基础。|
|9 Planning with Reasoning using Vision Language World Model|unclear / 无映射 → **unknown**|VLWM从自然视频学习语义动作policy及world-state dynamics，用critic语义距离反思规划；并非仅语言生成。 窗口只见language-based world modeling，丢失interleaved actions/state、rollout cost及VPA任务；未知合理，但不能认定完整来源无规划。|
|10 Policy-Guided World Model Planning for Language-Conditioned Visual Navigation|new / 无映射 → **failed**|PiJEPA用Octo policy分布warm-start MPPI，JEPA预测冻结编码器潜状态；语言条件视觉导航和长时程问题直接相关。 窗口可核JEPA预测及MPPI，但丢失policy warm-start、语言输入、CAST训练及真实导航对照；泛称潜空间规划与现有节点重叠。 理由错误：与现有动作条件动力学/模型规划重复，intro未保留policy warm-start这一具体增量；可当c3方法示例，不能宣称缺少现有能力或必需新基础。 窗口可核JEPA预测及MPPI，但丢失policy warm-start、语言输入、CAST训练及真实导航对照；泛称潜空间规划与现有节点重叠。 判失败：与现有动作条件动力学/模型规划重复，intro未保留policy warm-start这一具体增量；可当c3方法示例，不能宣称缺少现有能力或必需新基础。 窗口可核JEPA预测及MPPI，但丢失policy warm-start、语言输入、CAST训练及真实导航对照；泛称潜空间规划与现有节点重叠。|
|11 ResWM: Residual-Action World Model for Visual RL|unclear / 无映射 → **unknown**|ResWM将绝对动作改为相对前步的残差动作，Dreamer式潜动力学及差分encoder；DMC实验支持控制平滑和样本效率，不能扩大成真实机器人OOD证明。 窗口仅视觉RL背景，丢失residual action和差分encoder；新方向若只重复视觉世界模型，会丢掉论文真正增量。|
|12 Revision, Not Restart: Revisable Visual Plans for Closed-Loop World-Action Models|unclear / 无映射 → **unknown**|RTP保存生成中间状态并用learned revision bridge按反馈修订未来，闭环任务评估；具体反馈修订机制可作可选探索。 窗口保留revision bridge机制，但丢失action supervision、保留/修订/重规划策略及闭环benchmark；不得扩大结果可靠性。|
|13 Sparse Imagination for Efficient Visual World Model Planning|unclear / 无映射 → **unknown**|Sparse Imagination用稀疏token和random grouped attention减少latent rollout计算，研究效率/性能取舍。 标题和窗口可核稀疏视觉规划主题，但丢失具体token机制和实验；效率用途清楚，对高级OOD目标的额外价值未知。|
|14 TRTP: a three-stage robust task planning framework for open worlds via visual-language models and digital twin simulation|unclear / 无映射 → **unknown**|TRTP只有完整标题，无摘要；标题含VLM和digital twin，无法判定其是否学习动力学或如何闭环评估。 实际标题也被截断，无摘要；不推荐/不新增的未知状态合适，但不得算作内容正确推荐。|
|15 The Planning Limits of Latent World Models|unclear / 无映射 → **unknown**|Planning Limits比较五个视觉backbone，Meta-World/BridgeData及完美simulator，对目标距离、rollout长度、MPC和subgoal作对照；核心规划局限证据。 窗口只保留动机，完全丢失5步rollout、目标距离、perfect prediction对照和subgoal结论；来源有证据而模型窗口没有。 理由错误：完整源任务和比较很具体；只有实际窗口丢失设计，不能把不足归于完整来源。|
|16 Thinking with Patterns: Breaking the Perceptual Bottleneck in Visual Planning via Pattern Induction|unclear / 无映射 → **unknown**|Thinking with Patterns是VLM的TWI/pattern induction视觉规划，FrozenLake/Crafter/CubeBench；可作初学比较，对高级机器人潜动力学OOD只能相邻参考。 窗口保留TWI构建内部world model，丢失online patterns、三任务和训练自由策略；不能因world model术语认定行动条件预测。|
|17 Towards Surgical World-Action Modeling: A Preliminary Joint Visual-Trajectory Forecasting for Surgical Motion Planning|unclear / 无映射 → **unknown**|手术模型从历史视频/器械轨迹联合预测未来15步，评价PSNR/ADE与误差累积；有预测证据，尚无闭环规划或控制收益证据。 窗口保留联合预测对象，缺少15步、chunked rollout和渐进误差；不能把联合预测本身叫动作条件规划证明。|
|18 World Action Modeling with Progressive Visual Planning|unclear / 无映射 → **unknown**|ProWAM联合行动与有序稀疏视觉subgoal，闭环重规划，仿真及零样本真实新场景；长时程/OOD目标直接相关。 窗口只见action-free视频学习subgoal及视觉规划，丢失行动联合预测、闭环执行与OOD结果；可粗映射，不能验证具体鲁棒性结论。|
|19 iVideoGPT: Interactive VideoGPTs are Scalable World Models|unclear / 无映射 → **unknown**|iVideoGPT把视觉、行动、reward token化并预训练人/机器人轨迹，明确动作条件预测、视觉规划及model-based RL。 窗口明确action-conditioned video prediction和visual planning，足够粗任务映射；丢失token化/训练/评估，不足以判断实验强度。|

前置核查：视觉表征→动力学→规划适用于该初学教学路线，但不是所有planner/应用的普遍必需依赖；具体机器人/手术应用不是必需基础。

- 方向 **潜空间世界模型规划**：failed。与现有动作条件动力学/模型规划重复，intro未保留policy warm-start这一具体增量；可当c3方法示例，不能宣称缺少现有能力或必需新基础。 最终强制前置为空；实际用户用途验证not_evaluated。

### cs-growth-v0-r2 — unknown

目标：理解世界模型如何从视觉观测预测状态并支持规划，能比较基础方法的假设和局限。 已有基础：了解监督学习、基础概率与神经网络；尚未系统学习强化学习。

论文计数：{'passed': 2, 'failed': 0, 'unknown': 18, 'not_evaluated': 0}；方向计数：{'passed': 0, 'failed': 0, 'unknown': 1, 'not_evaluated': 0}。保留大量未知，尚未建立完整案例的科学内容有效性；不是已通过推荐价值测试。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 An Empirical Study of World Model Quantization|unclear / 无映射 → **unknown**|DINO-WM量化实验比较权重/激活、位宽、50轮规划与任务成功失配；与误差及规划局限有关，不只是无关模型压缩。 窗口只有失败结论，丢失DINO-WM、量化配置、规划视野和实验设计；不能据此详细比较模块敏感度。 理由错误：完整源用DINO-WM视觉规划、规划视野和任务成功作量化评估；不能断言非规划或表征任务。|
|1 Beyond Visual Quality: A Study of Test-Time Planning with World Action Models|new / 无映射 → **unknown**|世界动作模型同状态候选行动选择，比较视觉质量、物理一致性与任务进展评分；是决策用途评估，不等于生成质量。 窗口保留selector与干预，但丢失WAM定义、oracle对照、同状态设计和轨迹阶段；无法核实收益大小。|
|2 DINO-WM: World Models on Pre-trained Visual Features enable Zero-shot Planning|covered / 动作条件动力学 → **passed**|DINO-WM用离线轨迹预测DINOv2 patch特征，经行动序列优化达成目标；六环境零样本规划直接相关。 标题与首句支持控制条件预测/规划，窗口丢失离线训练、patch特征、目标优化及六环境细节。|
|3 Driving Into the Future: Multiview Visual Forecasting and Planning with World Model for Autonomous Driving|unclear / 无映射 → **unknown**|Drive-WM在自动驾驶场景预测多视图未来，以图像奖励比较轨迹；是具体应用示例，不能当必需基础。 窗口只有驾驶规划背景和模型名，未展示多视图条件、不同maneuver、图像奖励或评估；高级机器人OOD用途仅部分对应。|
|4 Driving into the Future: Multiview Visual Forecasting and Planning with World Model for Autonomous Driving|unclear / 无映射 → **unknown**|与前一Drive-WM记录为同一方法的不同出版版本；不构成独立方法或独立验证。 与前一版本的可见摘要窗口语义相同；一个covered、另一个unclear的差异缺乏来源依据。|
|5 Gradient-based Planning with World Models|unclear / 无映射 → **unknown**|可微世界模型梯度MPC与CEM/MPPI、policy对照，匹配模型规划；高级已知MPC可作方法比较，不能重复当基础课。 标题+MPC短窗足以粗映射规划，但丢失梯度优化机制、基线比较、混合policy及样本效率结果。|
|6 HiWE: Hierarchical World Knowledge Model with Visual Keypoint Enhancement for Zero-Shot 3D Path Planning|unclear / 无映射 → **unknown**|HiWE通过PointVLM视觉坐标、深度、3DLLM末端waypoint和grasp执行任务；并未展示动作条件潜动力学世界模型。 窗口保留交互定位/运动/接触，却丢失语言规划器和visual fine-tuning背景；不能按标题world knowledge推世界模型动力学。|
|7 JEPA-Bisim: Learning Robust Visual Representations for Planning with Joint-Embedding Predictive World Models|covered / 动作条件动力学 → **passed**|JEPA-Bisim用bisimulation控制相关表征改善背景变化/视觉干扰鲁棒性，PointMaze和PushT；直接对应高级OOD目标。 窗口只讲潜空间规划，不含slow features、bisimulation、两个任务或鲁棒性结果；可粗映射动力学，不能验证其OOD贡献。|
|8 Learning Visual Planning Models from Partially Observed Images|unclear / 无映射 → **unknown**|Recplan从部分观测图像学习latent transition及距离启发式，用经典规划器；部分可观测状态/动力学与规划相关。 窗口保留部分观测转移模型，却截掉潜表征、heuristic和classical planner；可以做候选粗映射，不能证明新独立基础。|
|9 Planning with Reasoning using Vision Language World Model|unclear / 无映射 → **unknown**|VLWM从自然视频学习语义动作policy及world-state dynamics，用critic语义距离反思规划；并非仅语言生成。 窗口只见language-based world modeling，丢失interleaved actions/state、rollout cost及VPA任务；未知合理，但不能认定完整来源无规划。|
|10 Policy-Guided World Model Planning for Language-Conditioned Visual Navigation|unclear / 无映射 → **unknown**|PiJEPA用Octo policy分布warm-start MPPI，JEPA预测冻结编码器潜状态；语言条件视觉导航和长时程问题直接相关。 窗口可核JEPA预测及MPPI，但丢失policy warm-start、语言输入、CAST训练及真实导航对照；泛称潜空间规划与现有节点重叠。|
|11 ResWM: Residual-Action World Model for Visual RL|unclear / 无映射 → **unknown**|ResWM将绝对动作改为相对前步的残差动作，Dreamer式潜动力学及差分encoder；DMC实验支持控制平滑和样本效率，不能扩大成真实机器人OOD证明。 窗口仅视觉RL背景，丢失residual action和差分encoder；新方向若只重复视觉世界模型，会丢掉论文真正增量。|
|12 Revision, Not Restart: Revisable Visual Plans for Closed-Loop World-Action Models|unclear / 无映射 → **unknown**|RTP保存生成中间状态并用learned revision bridge按反馈修订未来，闭环任务评估；具体反馈修订机制可作可选探索。 窗口保留revision bridge机制，但丢失action supervision、保留/修订/重规划策略及闭环benchmark；不得扩大结果可靠性。|
|13 Sparse Imagination for Efficient Visual World Model Planning|unclear / 无映射 → **unknown**|Sparse Imagination用稀疏token和random grouped attention减少latent rollout计算，研究效率/性能取舍。 标题和窗口可核稀疏视觉规划主题，但丢失具体token机制和实验；效率用途清楚，对高级OOD目标的额外价值未知。|
|14 TRTP: a three-stage robust task planning framework for open worlds via visual-language models and digital twin simulation|unclear / 无映射 → **unknown**|TRTP只有完整标题，无摘要；标题含VLM和digital twin，无法判定其是否学习动力学或如何闭环评估。 实际标题也被截断，无摘要；不推荐/不新增的未知状态合适，但不得算作内容正确推荐。|
|15 The Planning Limits of Latent World Models|unclear / 无映射 → **unknown**|Planning Limits比较五个视觉backbone，Meta-World/BridgeData及完美simulator，对目标距离、rollout长度、MPC和subgoal作对照；核心规划局限证据。 窗口只保留动机，完全丢失5步rollout、目标距离、perfect prediction对照和subgoal结论；来源有证据而模型窗口没有。 理由错误：同一窗口遗漏设计，不等于完整来源任务未知。|
|16 Thinking with Patterns: Breaking the Perceptual Bottleneck in Visual Planning via Pattern Induction|unclear / 无映射 → **unknown**|Thinking with Patterns是VLM的TWI/pattern induction视觉规划，FrozenLake/Crafter/CubeBench；可作初学比较，对高级机器人潜动力学OOD只能相邻参考。 窗口保留TWI构建内部world model，丢失online patterns、三任务和训练自由策略；不能因world model术语认定行动条件预测。|
|17 Towards Surgical World-Action Modeling: A Preliminary Joint Visual-Trajectory Forecasting for Surgical Motion Planning|unclear / 无映射 → **unknown**|手术模型从历史视频/器械轨迹联合预测未来15步，评价PSNR/ADE与误差累积；有预测证据，尚无闭环规划或控制收益证据。 窗口保留联合预测对象，缺少15步、chunked rollout和渐进误差；不能把联合预测本身叫动作条件规划证明。|
|18 World Action Modeling with Progressive Visual Planning|unclear / 无映射 → **unknown**|ProWAM联合行动与有序稀疏视觉subgoal，闭环重规划，仿真及零样本真实新场景；长时程/OOD目标直接相关。 窗口只见action-free视频学习subgoal及视觉规划，丢失行动联合预测、闭环执行与OOD结果；可粗映射，不能验证具体鲁棒性结论。|
|19 iVideoGPT: Interactive VideoGPTs are Scalable World Models|unclear / 无映射 → **unknown**|iVideoGPT把视觉、行动、reward token化并预训练人/机器人轨迹，明确动作条件预测、视觉规划及model-based RL。 窗口明确action-conditioned video prediction和visual planning，足够粗任务映射；丢失token化/训练/评估，不足以判断实验强度。|

前置核查：视觉表征→动力学→规划适用于该初学教学路线，但不是所有planner/应用的普遍必需依赖；具体机器人/手术应用不是必需基础。

- 方向 **世界动作模型测试时规划**：unknown。测试选择器的决策用途明确，完整源有依据；与现有规划评估重叠，独立新branch价值未知，仍可作可选评估专题。 最终强制前置为空；实际用户用途验证not_evaluated。

### cs-growth-v0-r3 — unknown

目标：理解世界模型如何从视觉观测预测状态并支持规划，能比较基础方法的假设和局限。 已有基础：了解监督学习、基础概率与神经网络；尚未系统学习强化学习。

论文计数：{'passed': 3, 'failed': 0, 'unknown': 17, 'not_evaluated': 0}；方向计数：{'passed': 1, 'failed': 0, 'unknown': 0, 'not_evaluated': 0}。保留大量未知，尚未建立完整案例的科学内容有效性；不是已通过推荐价值测试。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 An Empirical Study of World Model Quantization|new / 无映射 → **passed**|DINO-WM量化实验比较权重/激活、位宽、50轮规划与任务成功失配；与误差及规划局限有关，不只是无关模型压缩。 窗口只有失败结论，丢失DINO-WM、量化配置、规划视野和实验设计；不能据此详细比较模块敏感度。 理由错误：完整源明确量化对规划的影响；非现有规划的强排除理由过度，方向本身仍可选。|
|1 Beyond Visual Quality: A Study of Test-Time Planning with World Action Models|unclear / 无映射 → **unknown**|世界动作模型同状态候选行动选择，比较视觉质量、物理一致性与任务进展评分；是决策用途评估，不等于生成质量。 窗口保留selector与干预，但丢失WAM定义、oracle对照、同状态设计和轨迹阶段；无法核实收益大小。|
|2 DINO-WM: World Models on Pre-trained Visual Features enable Zero-shot Planning|covered / 模型规划 → **passed**|DINO-WM用离线轨迹预测DINOv2 patch特征，经行动序列优化达成目标；六环境零样本规划直接相关。 标题与首句支持控制条件预测/规划，窗口丢失离线训练、patch特征、目标优化及六环境细节。|
|3 Driving Into the Future: Multiview Visual Forecasting and Planning with World Model for Autonomous Driving|unclear / 无映射 → **unknown**|Drive-WM在自动驾驶场景预测多视图未来，以图像奖励比较轨迹；是具体应用示例，不能当必需基础。 窗口只有驾驶规划背景和模型名，未展示多视图条件、不同maneuver、图像奖励或评估；高级机器人OOD用途仅部分对应。|
|4 Driving into the Future: Multiview Visual Forecasting and Planning with World Model for Autonomous Driving|unclear / 无映射 → **unknown**|与前一Drive-WM记录为同一方法的不同出版版本；不构成独立方法或独立验证。 与前一版本的可见摘要窗口语义相同；一个covered、另一个unclear的差异缺乏来源依据。|
|5 Gradient-based Planning with World Models|unclear / 无映射 → **unknown**|可微世界模型梯度MPC与CEM/MPPI、policy对照，匹配模型规划；高级已知MPC可作方法比较，不能重复当基础课。 标题+MPC短窗足以粗映射规划，但丢失梯度优化机制、基线比较、混合policy及样本效率结果。|
|6 HiWE: Hierarchical World Knowledge Model with Visual Keypoint Enhancement for Zero-Shot 3D Path Planning|unclear / 无映射 → **unknown**|HiWE通过PointVLM视觉坐标、深度、3DLLM末端waypoint和grasp执行任务；并未展示动作条件潜动力学世界模型。 窗口保留交互定位/运动/接触，却丢失语言规划器和visual fine-tuning背景；不能按标题world knowledge推世界模型动力学。|
|7 JEPA-Bisim: Learning Robust Visual Representations for Planning with Joint-Embedding Predictive World Models|unclear / 无映射 → **unknown**|JEPA-Bisim用bisimulation控制相关表征改善背景变化/视觉干扰鲁棒性，PointMaze和PushT；直接对应高级OOD目标。 窗口只讲潜空间规划，不含slow features、bisimulation、两个任务或鲁棒性结果；可粗映射动力学，不能验证其OOD贡献。|
|8 Learning Visual Planning Models from Partially Observed Images|unclear / 无映射 → **unknown**|Recplan从部分观测图像学习latent transition及距离启发式，用经典规划器；部分可观测状态/动力学与规划相关。 窗口保留部分观测转移模型，却截掉潜表征、heuristic和classical planner；可以做候选粗映射，不能证明新独立基础。|
|9 Planning with Reasoning using Vision Language World Model|unclear / 无映射 → **unknown**|VLWM从自然视频学习语义动作policy及world-state dynamics，用critic语义距离反思规划；并非仅语言生成。 窗口只见language-based world modeling，丢失interleaved actions/state、rollout cost及VPA任务；未知合理，但不能认定完整来源无规划。|
|10 Policy-Guided World Model Planning for Language-Conditioned Visual Navigation|unclear / 无映射 → **unknown**|PiJEPA用Octo policy分布warm-start MPPI，JEPA预测冻结编码器潜状态；语言条件视觉导航和长时程问题直接相关。 窗口可核JEPA预测及MPPI，但丢失policy warm-start、语言输入、CAST训练及真实导航对照；泛称潜空间规划与现有节点重叠。|
|11 ResWM: Residual-Action World Model for Visual RL|covered / 动作条件动力学 → **passed**|ResWM将绝对动作改为相对前步的残差动作，Dreamer式潜动力学及差分encoder；DMC实验支持控制平滑和样本效率，不能扩大成真实机器人OOD证明。 窗口仅视觉RL背景，丢失residual action和差分encoder；新方向若只重复视觉世界模型，会丢掉论文真正增量。|
|12 Revision, Not Restart: Revisable Visual Plans for Closed-Loop World-Action Models|unclear / 无映射 → **unknown**|RTP保存生成中间状态并用learned revision bridge按反馈修订未来，闭环任务评估；具体反馈修订机制可作可选探索。 窗口保留revision bridge机制，但丢失action supervision、保留/修订/重规划策略及闭环benchmark；不得扩大结果可靠性。|
|13 Sparse Imagination for Efficient Visual World Model Planning|unclear / 无映射 → **unknown**|Sparse Imagination用稀疏token和random grouped attention减少latent rollout计算，研究效率/性能取舍。 标题和窗口可核稀疏视觉规划主题，但丢失具体token机制和实验；效率用途清楚，对高级OOD目标的额外价值未知。|
|14 TRTP: a three-stage robust task planning framework for open worlds via visual-language models and digital twin simulation|unclear / 无映射 → **unknown**|TRTP只有完整标题，无摘要；标题含VLM和digital twin，无法判定其是否学习动力学或如何闭环评估。 实际标题也被截断，无摘要；不推荐/不新增的未知状态合适，但不得算作内容正确推荐。|
|15 The Planning Limits of Latent World Models|unclear / 无映射 → **unknown**|Planning Limits比较五个视觉backbone，Meta-World/BridgeData及完美simulator，对目标距离、rollout长度、MPC和subgoal作对照；核心规划局限证据。 窗口只保留动机，完全丢失5步rollout、目标距离、perfect prediction对照和subgoal结论；来源有证据而模型窗口没有。 理由错误：同一窗口遗漏设计，不等于完整来源任务未知。|
|16 Thinking with Patterns: Breaking the Perceptual Bottleneck in Visual Planning via Pattern Induction|unclear / 无映射 → **unknown**|Thinking with Patterns是VLM的TWI/pattern induction视觉规划，FrozenLake/Crafter/CubeBench；可作初学比较，对高级机器人潜动力学OOD只能相邻参考。 窗口保留TWI构建内部world model，丢失online patterns、三任务和训练自由策略；不能因world model术语认定行动条件预测。|
|17 Towards Surgical World-Action Modeling: A Preliminary Joint Visual-Trajectory Forecasting for Surgical Motion Planning|unclear / 无映射 → **unknown**|手术模型从历史视频/器械轨迹联合预测未来15步，评价PSNR/ADE与误差累积；有预测证据，尚无闭环规划或控制收益证据。 窗口保留联合预测对象，缺少15步、chunked rollout和渐进误差；不能把联合预测本身叫动作条件规划证明。|
|18 World Action Modeling with Progressive Visual Planning|unclear / 无映射 → **unknown**|ProWAM联合行动与有序稀疏视觉subgoal，闭环重规划，仿真及零样本真实新场景；长时程/OOD目标直接相关。 窗口只见action-free视频学习subgoal及视觉规划，丢失行动联合预测、闭环执行与OOD结果；可粗映射，不能验证具体鲁棒性结论。|
|19 iVideoGPT: Interactive VideoGPTs are Scalable World Models|unclear / 无映射 → **unknown**|iVideoGPT把视觉、行动、reward token化并预训练人/机器人轨迹，明确动作条件预测、视觉规划及model-based RL。 窗口明确action-conditioned video prediction和visual planning，足够粗任务映射；丢失token化/训练/评估，不足以判断实验强度。|

前置核查：视觉表征→动力学→规划适用于该初学教学路线，但不是所有planner/应用的普遍必需依赖；具体机器人/手术应用不是必需基础。

- 方向 **世界模型量化评估**：passed。量化配置与任务失败关系是明确的可选方法评估用途；不能将其升级为初学必需前置，理由称非规划忽略完整源的规划实验。 最终强制前置为空；实际用户用途验证not_evaluated。

### cs-growth-v1-r1 — failed

目标：研究视觉世界模型在长时程机器人规划中的分布外泛化和模型误差。 已有基础：熟悉强化学习、潜变量模型、MPC与基础机器人控制。

论文计数：{'passed': 5, 'failed': 1, 'unknown': 14, 'not_evaluated': 0}；方向计数：{'passed': 0, 'failed': 1, 'unknown': 1, 'not_evaluated': 0}。有内容/映射失败，不能判该完整案例科学正确。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 An Empirical Study of World Model Quantization|unclear / 无映射 → **unknown**|DINO-WM量化实验比较权重/激活、位宽、50轮规划与任务成功失配；与误差及规划局限有关，不只是无关模型压缩。 窗口只有失败结论，丢失DINO-WM、量化配置、规划视野和实验设计；不能据此详细比较模块敏感度。 理由错误：原窗口确实短，但完整源有具体规划任务；应描述window不足而非来源未明确规划。|
|1 Beyond Visual Quality: A Study of Test-Time Planning with World Action Models|unclear / 无映射 → **unknown**|世界动作模型同状态候选行动选择，比较视觉质量、物理一致性与任务进展评分；是决策用途评估，不等于生成质量。 窗口保留selector与干预，但丢失WAM定义、oracle对照、同状态设计和轨迹阶段；无法核实收益大小。|
|2 DINO-WM: World Models on Pre-trained Visual Features enable Zero-shot Planning|covered / 动作条件动力学 → **passed**|DINO-WM用离线轨迹预测DINOv2 patch特征，经行动序列优化达成目标；六环境零样本规划直接相关。 标题与首句支持控制条件预测/规划，窗口丢失离线训练、patch特征、目标优化及六环境细节。|
|3 Driving Into the Future: Multiview Visual Forecasting and Planning with World Model for Autonomous Driving|covered / 模型规划 → **unknown**|Drive-WM在自动驾驶场景预测多视图未来，以图像奖励比较轨迹；是具体应用示例，不能当必需基础。 窗口只有驾驶规划背景和模型名，未展示多视图条件、不同maneuver、图像奖励或评估；高级机器人OOD用途仅部分对应。|
|4 Driving into the Future: Multiview Visual Forecasting and Planning with World Model for Autonomous Driving|covered / 动作条件动力学 → **unknown**|与前一Drive-WM记录为同一方法的不同出版版本；不构成独立方法或独立验证。 与前一版本的可见摘要窗口语义相同；一个covered、另一个unclear的差异缺乏来源依据。|
|5 Gradient-based Planning with World Models|covered / 模型规划 → **passed**|可微世界模型梯度MPC与CEM/MPPI、policy对照，匹配模型规划；高级已知MPC可作方法比较，不能重复当基础课。 标题+MPC短窗足以粗映射规划，但丢失梯度优化机制、基线比较、混合policy及样本效率结果。|
|6 HiWE: Hierarchical World Knowledge Model with Visual Keypoint Enhancement for Zero-Shot 3D Path Planning|unclear / 无映射 → **unknown**|HiWE通过PointVLM视觉坐标、深度、3DLLM末端waypoint和grasp执行任务；并未展示动作条件潜动力学世界模型。 窗口保留交互定位/运动/接触，却丢失语言规划器和visual fine-tuning背景；不能按标题world knowledge推世界模型动力学。|
|7 JEPA-Bisim: Learning Robust Visual Representations for Planning with Joint-Embedding Predictive World Models|covered / 动作条件动力学 → **passed**|JEPA-Bisim用bisimulation控制相关表征改善背景变化/视觉干扰鲁棒性，PointMaze和PushT；直接对应高级OOD目标。 窗口只讲潜空间规划，不含slow features、bisimulation、两个任务或鲁棒性结果；可粗映射动力学，不能验证其OOD贡献。|
|8 Learning Visual Planning Models from Partially Observed Images|new / 无映射 → **unknown**|Recplan从部分观测图像学习latent transition及距离启发式，用经典规划器；部分可观测状态/动力学与规划相关。 窗口保留部分观测转移模型，却截掉潜表征、heuristic和classical planner；可以做候选粗映射，不能证明新独立基础。|
|9 Planning with Reasoning using Vision Language World Model|unclear / 无映射 → **unknown**|VLWM从自然视频学习语义动作policy及world-state dynamics，用critic语义距离反思规划；并非仅语言生成。 窗口只见language-based world modeling，丢失interleaved actions/state、rollout cost及VPA任务；未知合理，但不能认定完整来源无规划。|
|10 Policy-Guided World Model Planning for Language-Conditioned Visual Navigation|unclear / 无映射 → **unknown**|PiJEPA用Octo policy分布warm-start MPPI，JEPA预测冻结编码器潜状态；语言条件视觉导航和长时程问题直接相关。 窗口可核JEPA预测及MPPI，但丢失policy warm-start、语言输入、CAST训练及真实导航对照；泛称潜空间规划与现有节点重叠。|
|11 ResWM: Residual-Action World Model for Visual RL|new / 无映射 → **failed**|ResWM将绝对动作改为相对前步的残差动作，Dreamer式潜动力学及差分encoder；DMC实验支持控制平滑和样本效率，不能扩大成真实机器人OOD证明。 窗口仅视觉RL背景，丢失residual action和差分encoder；新方向若只重复视觉世界模型，会丢掉论文真正增量。 理由错误：intro泛称从视觉学习世界模型支持RL，重复高级已知背景和c2；没有提原论文残差动作或长时程误差用途，未形成目标所需增量。 窗口仅视觉RL背景，丢失residual action和差分encoder；新方向若只重复视觉世界模型，会丢掉论文真正增量。 判失败：intro泛称从视觉学习世界模型支持RL，重复高级已知背景和c2；没有提原论文残差动作或长时程误差用途，未形成目标所需增量。 窗口仅视觉RL背景，丢失residual action和差分encoder；新方向若只重复视觉世界模型，会丢掉论文真正增量。|
|12 Revision, Not Restart: Revisable Visual Plans for Closed-Loop World-Action Models|unclear / 无映射 → **unknown**|RTP保存生成中间状态并用learned revision bridge按反馈修订未来，闭环任务评估；具体反馈修订机制可作可选探索。 窗口保留revision bridge机制，但丢失action supervision、保留/修订/重规划策略及闭环benchmark；不得扩大结果可靠性。|
|13 Sparse Imagination for Efficient Visual World Model Planning|covered / 模型规划 → **passed**|Sparse Imagination用稀疏token和random grouped attention减少latent rollout计算，研究效率/性能取舍。 标题和窗口可核稀疏视觉规划主题，但丢失具体token机制和实验；效率用途清楚，对高级OOD目标的额外价值未知。|
|14 TRTP: a three-stage robust task planning framework for open worlds via visual-language models and digital twin simulation|unclear / 无映射 → **unknown**|TRTP只有完整标题，无摘要；标题含VLM和digital twin，无法判定其是否学习动力学或如何闭环评估。 实际标题也被截断，无摘要；不推荐/不新增的未知状态合适，但不得算作内容正确推荐。|
|15 The Planning Limits of Latent World Models|unclear / 无映射 → **unknown**|Planning Limits比较五个视觉backbone，Meta-World/BridgeData及完美simulator，对目标距离、rollout长度、MPC和subgoal作对照；核心规划局限证据。 窗口只保留动机，完全丢失5步rollout、目标距离、perfect prediction对照和subgoal结论；来源有证据而模型窗口没有。|
|16 Thinking with Patterns: Breaking the Perceptual Bottleneck in Visual Planning via Pattern Induction|unclear / 无映射 → **unknown**|Thinking with Patterns是VLM的TWI/pattern induction视觉规划，FrozenLake/Crafter/CubeBench；可作初学比较，对高级机器人潜动力学OOD只能相邻参考。 窗口保留TWI构建内部world model，丢失online patterns、三任务和训练自由策略；不能因world model术语认定行动条件预测。|
|17 Towards Surgical World-Action Modeling: A Preliminary Joint Visual-Trajectory Forecasting for Surgical Motion Planning|unclear / 无映射 → **unknown**|手术模型从历史视频/器械轨迹联合预测未来15步，评价PSNR/ADE与误差累积；有预测证据，尚无闭环规划或控制收益证据。 窗口保留联合预测对象，缺少15步、chunked rollout和渐进误差；不能把联合预测本身叫动作条件规划证明。|
|18 World Action Modeling with Progressive Visual Planning|covered / 模型规划 → **passed**|ProWAM联合行动与有序稀疏视觉subgoal，闭环重规划，仿真及零样本真实新场景；长时程/OOD目标直接相关。 窗口只见action-free视频学习subgoal及视觉规划，丢失行动联合预测、闭环执行与OOD结果；可粗映射，不能验证具体鲁棒性结论。|
|19 iVideoGPT: Interactive VideoGPTs are Scalable World Models|unclear / 无映射 → **unknown**|iVideoGPT把视觉、行动、reward token化并预训练人/机器人轨迹，明确动作条件预测、视觉规划及model-based RL。 窗口明确action-conditioned video prediction和visual planning，足够粗任务映射；丢失token化/训练/评估，不足以判断实验强度。|

前置核查：视觉表征→动力学→规划适用于该初学教学路线，但不是所有planner/应用的普遍必需依赖；具体机器人/手术应用不是必需基础。 高级persona声明已熟悉基础，原graph仍把基础节点active/foundation；应把已知背景和新增研究能力区分。输入未提供完整prompt，不能断言已知背景没有发送给模型。

- 方向 **部分观测视觉动力学**：unknown。部分可观测状态转移是具体专题，来源支持；intro未连到高级OOD/长期误差目标，且与已知潜动力学重叠，新增独立能力价值未知。 最终强制前置为空；实际用户用途验证not_evaluated。
- 方向 **视觉RL世界模型**：failed。intro泛称从视觉学习世界模型支持RL，重复高级已知背景和c2；没有提原论文残差动作或长时程误差用途，未形成目标所需增量。 最终强制前置为空；实际用户用途验证not_evaluated。

### cs-growth-v1-r2 — failed

目标：研究视觉世界模型在长时程机器人规划中的分布外泛化和模型误差。 已有基础：熟悉强化学习、潜变量模型、MPC与基础机器人控制。

论文计数：{'passed': 4, 'failed': 1, 'unknown': 15, 'not_evaluated': 0}；方向计数：{'passed': 1, 'failed': 1, 'unknown': 1, 'not_evaluated': 0}。有内容/映射失败，不能判该完整案例科学正确。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 An Empirical Study of World Model Quantization|unclear / 无映射 → **unknown**|DINO-WM量化实验比较权重/激活、位宽、50轮规划与任务成功失配；与误差及规划局限有关，不只是无关模型压缩。 窗口只有失败结论，丢失DINO-WM、量化配置、规划视野和实验设计；不能据此详细比较模块敏感度。 理由错误：量化诱导的任务成功/目标失配属于模型误差与规划评估；非泛化评估的排除边界过窄。|
|1 Beyond Visual Quality: A Study of Test-Time Planning with World Action Models|unclear / 无映射 → **unknown**|世界动作模型同状态候选行动选择，比较视觉质量、物理一致性与任务进展评分；是决策用途评估，不等于生成质量。 窗口保留selector与干预，但丢失WAM定义、oracle对照、同状态设计和轨迹阶段；无法核实收益大小。|
|2 DINO-WM: World Models on Pre-trained Visual Features enable Zero-shot Planning|covered / 动作条件动力学 → **passed**|DINO-WM用离线轨迹预测DINOv2 patch特征，经行动序列优化达成目标；六环境零样本规划直接相关。 标题与首句支持控制条件预测/规划，窗口丢失离线训练、patch特征、目标优化及六环境细节。|
|3 Driving Into the Future: Multiview Visual Forecasting and Planning with World Model for Autonomous Driving|unclear / 无映射 → **unknown**|Drive-WM在自动驾驶场景预测多视图未来，以图像奖励比较轨迹；是具体应用示例，不能当必需基础。 窗口只有驾驶规划背景和模型名，未展示多视图条件、不同maneuver、图像奖励或评估；高级机器人OOD用途仅部分对应。|
|4 Driving into the Future: Multiview Visual Forecasting and Planning with World Model for Autonomous Driving|covered / 动作条件动力学 → **unknown**|与前一Drive-WM记录为同一方法的不同出版版本；不构成独立方法或独立验证。 与前一版本的可见摘要窗口语义相同；一个covered、另一个unclear的差异缺乏来源依据。|
|5 Gradient-based Planning with World Models|unclear / 无映射 → **unknown**|可微世界模型梯度MPC与CEM/MPPI、policy对照，匹配模型规划；高级已知MPC可作方法比较，不能重复当基础课。 标题+MPC短窗足以粗映射规划，但丢失梯度优化机制、基线比较、混合policy及样本效率结果。|
|6 HiWE: Hierarchical World Knowledge Model with Visual Keypoint Enhancement for Zero-Shot 3D Path Planning|unclear / 无映射 → **unknown**|HiWE通过PointVLM视觉坐标、深度、3DLLM末端waypoint和grasp执行任务；并未展示动作条件潜动力学世界模型。 窗口保留交互定位/运动/接触，却丢失语言规划器和visual fine-tuning背景；不能按标题world knowledge推世界模型动力学。|
|7 JEPA-Bisim: Learning Robust Visual Representations for Planning with Joint-Embedding Predictive World Models|covered / 动作条件动力学 → **passed**|JEPA-Bisim用bisimulation控制相关表征改善背景变化/视觉干扰鲁棒性，PointMaze和PushT；直接对应高级OOD目标。 窗口只讲潜空间规划，不含slow features、bisimulation、两个任务或鲁棒性结果；可粗映射动力学，不能验证其OOD贡献。|
|8 Learning Visual Planning Models from Partially Observed Images|unclear / 无映射 → **unknown**|Recplan从部分观测图像学习latent transition及距离启发式，用经典规划器；部分可观测状态/动力学与规划相关。 窗口保留部分观测转移模型，却截掉潜表征、heuristic和classical planner；可以做候选粗映射，不能证明新独立基础。|
|9 Planning with Reasoning using Vision Language World Model|unclear / 无映射 → **unknown**|VLWM从自然视频学习语义动作policy及world-state dynamics，用critic语义距离反思规划；并非仅语言生成。 窗口只见language-based world modeling，丢失interleaved actions/state、rollout cost及VPA任务；未知合理，但不能认定完整来源无规划。|
|10 Policy-Guided World Model Planning for Language-Conditioned Visual Navigation|new / 无映射 → **failed**|PiJEPA用Octo policy分布warm-start MPPI，JEPA预测冻结编码器潜状态；语言条件视觉导航和长时程问题直接相关。 窗口可核JEPA预测及MPPI，但丢失policy warm-start、语言输入、CAST训练及真实导航对照；泛称潜空间规划与现有节点重叠。 理由错误：no Map node covers this task与既有模型规划/动作动力学冲突；泛潜空间导航描述未体现policy初始化及长时程误差比较，不足以证明独立新分支。 窗口可核JEPA预测及MPPI，但丢失policy warm-start、语言输入、CAST训练及真实导航对照；泛称潜空间规划与现有节点重叠。 判失败：no Map node covers this task与既有模型规划/动作动力学冲突；泛潜空间导航描述未体现policy初始化及长时程误差比较，不足以证明独立新分支。 窗口可核JEPA预测及MPPI，但丢失policy warm-start、语言输入、CAST训练及真实导航对照；泛称潜空间规划与现有节点重叠。|
|11 ResWM: Residual-Action World Model for Visual RL|covered / 动作条件动力学 → **passed**|ResWM将绝对动作改为相对前步的残差动作，Dreamer式潜动力学及差分encoder；DMC实验支持控制平滑和样本效率，不能扩大成真实机器人OOD证明。 窗口仅视觉RL背景，丢失residual action和差分encoder；新方向若只重复视觉世界模型，会丢掉论文真正增量。|
|12 Revision, Not Restart: Revisable Visual Plans for Closed-Loop World-Action Models|unclear / 无映射 → **unknown**|RTP保存生成中间状态并用learned revision bridge按反馈修订未来，闭环任务评估；具体反馈修订机制可作可选探索。 窗口保留revision bridge机制，但丢失action supervision、保留/修订/重规划策略及闭环benchmark；不得扩大结果可靠性。|
|13 Sparse Imagination for Efficient Visual World Model Planning|new / 无映射 → **unknown**|Sparse Imagination用稀疏token和random grouped attention减少latent rollout计算，研究效率/性能取舍。 标题和窗口可核稀疏视觉规划主题，但丢失具体token机制和实验；效率用途清楚，对高级OOD目标的额外价值未知。|
|14 TRTP: a three-stage robust task planning framework for open worlds via visual-language models and digital twin simulation|unclear / 无映射 → **unknown**|TRTP只有完整标题，无摘要；标题含VLM和digital twin，无法判定其是否学习动力学或如何闭环评估。 实际标题也被截断，无摘要；不推荐/不新增的未知状态合适，但不得算作内容正确推荐。|
|15 The Planning Limits of Latent World Models|unclear / 无映射 → **unknown**|Planning Limits比较五个视觉backbone，Meta-World/BridgeData及完美simulator，对目标距离、rollout长度、MPC和subgoal作对照；核心规划局限证据。 窗口只保留动机，完全丢失5步rollout、目标距离、perfect prediction对照和subgoal结论；来源有证据而模型窗口没有。|
|16 Thinking with Patterns: Breaking the Perceptual Bottleneck in Visual Planning via Pattern Induction|unclear / 无映射 → **unknown**|Thinking with Patterns是VLM的TWI/pattern induction视觉规划，FrozenLake/Crafter/CubeBench；可作初学比较，对高级机器人潜动力学OOD只能相邻参考。 窗口保留TWI构建内部world model，丢失online patterns、三任务和训练自由策略；不能因world model术语认定行动条件预测。|
|17 Towards Surgical World-Action Modeling: A Preliminary Joint Visual-Trajectory Forecasting for Surgical Motion Planning|unclear / 无映射 → **unknown**|手术模型从历史视频/器械轨迹联合预测未来15步，评价PSNR/ADE与误差累积；有预测证据，尚无闭环规划或控制收益证据。 窗口保留联合预测对象，缺少15步、chunked rollout和渐进误差；不能把联合预测本身叫动作条件规划证明。|
|18 World Action Modeling with Progressive Visual Planning|new / 无映射 → **passed**|ProWAM联合行动与有序稀疏视觉subgoal，闭环重规划，仿真及零样本真实新场景；长时程/OOD目标直接相关。 窗口只见action-free视频学习subgoal及视觉规划，丢失行动联合预测、闭环执行与OOD结果；可粗映射，不能验证具体鲁棒性结论。|
|19 iVideoGPT: Interactive VideoGPTs are Scalable World Models|unclear / 无映射 → **unknown**|iVideoGPT把视觉、行动、reward token化并预训练人/机器人轨迹，明确动作条件预测、视觉规划及model-based RL。 窗口明确action-conditioned video prediction和visual planning，足够粗任务映射；丢失token化/训练/评估，不足以判断实验强度。|

前置核查：视觉表征→动力学→规划适用于该初学教学路线，但不是所有planner/应用的普遍必需依赖；具体机器人/手术应用不是必需基础。 高级persona声明已熟悉基础，原graph仍把基础节点active/foundation；应把已知背景和新增研究能力区分。输入未提供完整prompt，不能断言已知背景没有发送给模型。

- 方向 **World-Model Visual Navigation**：failed。no Map node covers this task与既有模型规划/动作动力学冲突；泛潜空间导航描述未体现policy初始化及长时程误差比较，不足以证明独立新分支。 最终强制前置为空；实际用户用途验证not_evaluated。
- 方向 **Sparse Visual World Planning**：unknown。稀疏想象效率用途和来源相符，可作规划方法专题；对固定高级OOD/误差问题的具体探索价值未在intro说明，独立branch价值未知。 最终强制前置为空；实际用户用途验证not_evaluated。
- 方向 **Progressive Visual Planning**：passed。稀疏视觉subgoal可以研究长时程规划，完整源含OOD/闭环；是可选专题，不能从短窗宣称已经验证鲁棒性或必要基础。 最终强制前置为空；实际用户用途验证not_evaluated。

### cs-growth-v1-r3 — failed

目标：研究视觉世界模型在长时程机器人规划中的分布外泛化和模型误差。 已有基础：熟悉强化学习、潜变量模型、MPC与基础机器人控制。

论文计数：{'passed': 6, 'failed': 2, 'unknown': 12, 'not_evaluated': 0}；方向计数：{'passed': 2, 'failed': 1, 'unknown': 1, 'not_evaluated': 0}。有内容/映射失败，不能判该完整案例科学正确。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 An Empirical Study of World Model Quantization|covered / 动作条件动力学 → **failed**|DINO-WM量化实验比较权重/激活、位宽、50轮规划与任务成功失配；与误差及规划局限有关，不只是无关模型压缩。 窗口只有失败结论，丢失DINO-WM、量化配置、规划视野和实验设计；不能据此详细比较模块敏感度。 理由错误：量化诱导规划成功失配应主要归规划/模型误差评估；nearest动作条件动力学未准确表达实际研究能力。窗口只有失败结论，丢失DINO-WM、量化配置、规划视野和实验设计；不能据此详细比较模块敏感度。 判失败：量化诱导规划成功失配应主要归规划/模型误差评估；nearest动作条件动力学未准确表达实际研究能力。窗口只有失败结论，丢失DINO-WM、量化配置、规划视野和实验设计；不能据此详细比较模块敏感度。|
|1 Beyond Visual Quality: A Study of Test-Time Planning with World Action Models|unclear / 无映射 → **unknown**|世界动作模型同状态候选行动选择，比较视觉质量、物理一致性与任务进展评分；是决策用途评估，不等于生成质量。 窗口保留selector与干预，但丢失WAM定义、oracle对照、同状态设计和轨迹阶段；无法核实收益大小。|
|2 DINO-WM: World Models on Pre-trained Visual Features enable Zero-shot Planning|covered / 动作条件动力学 → **passed**|DINO-WM用离线轨迹预测DINOv2 patch特征，经行动序列优化达成目标；六环境零样本规划直接相关。 标题与首句支持控制条件预测/规划，窗口丢失离线训练、patch特征、目标优化及六环境细节。|
|3 Driving Into the Future: Multiview Visual Forecasting and Planning with World Model for Autonomous Driving|unclear / 无映射 → **unknown**|Drive-WM在自动驾驶场景预测多视图未来，以图像奖励比较轨迹；是具体应用示例，不能当必需基础。 窗口只有驾驶规划背景和模型名，未展示多视图条件、不同maneuver、图像奖励或评估；高级机器人OOD用途仅部分对应。|
|4 Driving into the Future: Multiview Visual Forecasting and Planning with World Model for Autonomous Driving|covered / 动作条件动力学 → **unknown**|与前一Drive-WM记录为同一方法的不同出版版本；不构成独立方法或独立验证。 与前一版本的可见摘要窗口语义相同；一个covered、另一个unclear的差异缺乏来源依据。|
|5 Gradient-based Planning with World Models|covered / 模型规划 → **passed**|可微世界模型梯度MPC与CEM/MPPI、policy对照，匹配模型规划；高级已知MPC可作方法比较，不能重复当基础课。 标题+MPC短窗足以粗映射规划，但丢失梯度优化机制、基线比较、混合policy及样本效率结果。|
|6 HiWE: Hierarchical World Knowledge Model with Visual Keypoint Enhancement for Zero-Shot 3D Path Planning|unclear / 无映射 → **unknown**|HiWE通过PointVLM视觉坐标、深度、3DLLM末端waypoint和grasp执行任务；并未展示动作条件潜动力学世界模型。 窗口保留交互定位/运动/接触，却丢失语言规划器和visual fine-tuning背景；不能按标题world knowledge推世界模型动力学。|
|7 JEPA-Bisim: Learning Robust Visual Representations for Planning with Joint-Embedding Predictive World Models|covered / 动作条件动力学 → **passed**|JEPA-Bisim用bisimulation控制相关表征改善背景变化/视觉干扰鲁棒性，PointMaze和PushT；直接对应高级OOD目标。 窗口只讲潜空间规划，不含slow features、bisimulation、两个任务或鲁棒性结果；可粗映射动力学，不能验证其OOD贡献。|
|8 Learning Visual Planning Models from Partially Observed Images|unclear / 无映射 → **unknown**|Recplan从部分观测图像学习latent transition及距离启发式，用经典规划器；部分可观测状态/动力学与规划相关。 窗口保留部分观测转移模型，却截掉潜表征、heuristic和classical planner；可以做候选粗映射，不能证明新独立基础。|
|9 Planning with Reasoning using Vision Language World Model|unclear / 无映射 → **unknown**|VLWM从自然视频学习语义动作policy及world-state dynamics，用critic语义距离反思规划；并非仅语言生成。 窗口只见language-based world modeling，丢失interleaved actions/state、rollout cost及VPA任务；未知合理，但不能认定完整来源无规划。|
|10 Policy-Guided World Model Planning for Language-Conditioned Visual Navigation|new / 无映射 → **failed**|PiJEPA用Octo policy分布warm-start MPPI，JEPA预测冻结编码器潜状态；语言条件视觉导航和长时程问题直接相关。 窗口可核JEPA预测及MPPI，但丢失policy warm-start、语言输入、CAST训练及真实导航对照；泛称潜空间规划与现有节点重叠。 理由错误：与上一重复的泛world-model navigation同样重叠现有c3；无Map覆盖的原理由不成立，缺具体新能力及针对目标的比较用途。 窗口可核JEPA预测及MPPI，但丢失policy warm-start、语言输入、CAST训练及真实导航对照；泛称潜空间规划与现有节点重叠。 判失败：与上一重复的泛world-model navigation同样重叠现有c3；无Map覆盖的原理由不成立，缺具体新能力及针对目标的比较用途。 窗口可核JEPA预测及MPPI，但丢失policy warm-start、语言输入、CAST训练及真实导航对照；泛称潜空间规划与现有节点重叠。|
|11 ResWM: Residual-Action World Model for Visual RL|covered / 动作条件动力学 → **passed**|ResWM将绝对动作改为相对前步的残差动作，Dreamer式潜动力学及差分encoder；DMC实验支持控制平滑和样本效率，不能扩大成真实机器人OOD证明。 窗口仅视觉RL背景，丢失residual action和差分encoder；新方向若只重复视觉世界模型，会丢掉论文真正增量。|
|12 Revision, Not Restart: Revisable Visual Plans for Closed-Loop World-Action Models|new / 无映射 → **passed**|RTP保存生成中间状态并用learned revision bridge按反馈修订未来，闭环任务评估；具体反馈修订机制可作可选探索。 窗口保留revision bridge机制，但丢失action supervision、保留/修订/重规划策略及闭环benchmark；不得扩大结果可靠性。|
|13 Sparse Imagination for Efficient Visual World Model Planning|new / 无映射 → **unknown**|Sparse Imagination用稀疏token和random grouped attention减少latent rollout计算，研究效率/性能取舍。 标题和窗口可核稀疏视觉规划主题，但丢失具体token机制和实验；效率用途清楚，对高级OOD目标的额外价值未知。|
|14 TRTP: a three-stage robust task planning framework for open worlds via visual-language models and digital twin simulation|unclear / 无映射 → **unknown**|TRTP只有完整标题，无摘要；标题含VLM和digital twin，无法判定其是否学习动力学或如何闭环评估。 实际标题也被截断，无摘要；不推荐/不新增的未知状态合适，但不得算作内容正确推荐。|
|15 The Planning Limits of Latent World Models|unclear / 无映射 → **unknown**|Planning Limits比较五个视觉backbone，Meta-World/BridgeData及完美simulator，对目标距离、rollout长度、MPC和subgoal作对照；核心规划局限证据。 窗口只保留动机，完全丢失5步rollout、目标距离、perfect prediction对照和subgoal结论；来源有证据而模型窗口没有。|
|16 Thinking with Patterns: Breaking the Perceptual Bottleneck in Visual Planning via Pattern Induction|unclear / 无映射 → **unknown**|Thinking with Patterns是VLM的TWI/pattern induction视觉规划，FrozenLake/Crafter/CubeBench；可作初学比较，对高级机器人潜动力学OOD只能相邻参考。 窗口保留TWI构建内部world model，丢失online patterns、三任务和训练自由策略；不能因world model术语认定行动条件预测。|
|17 Towards Surgical World-Action Modeling: A Preliminary Joint Visual-Trajectory Forecasting for Surgical Motion Planning|unclear / 无映射 → **unknown**|手术模型从历史视频/器械轨迹联合预测未来15步，评价PSNR/ADE与误差累积；有预测证据，尚无闭环规划或控制收益证据。 窗口保留联合预测对象，缺少15步、chunked rollout和渐进误差；不能把联合预测本身叫动作条件规划证明。|
|18 World Action Modeling with Progressive Visual Planning|new / 无映射 → **passed**|ProWAM联合行动与有序稀疏视觉subgoal，闭环重规划，仿真及零样本真实新场景；长时程/OOD目标直接相关。 窗口只见action-free视频学习subgoal及视觉规划，丢失行动联合预测、闭环执行与OOD结果；可粗映射，不能验证具体鲁棒性结论。|
|19 iVideoGPT: Interactive VideoGPTs are Scalable World Models|unclear / 无映射 → **unknown**|iVideoGPT把视觉、行动、reward token化并预训练人/机器人轨迹，明确动作条件预测、视觉规划及model-based RL。 窗口明确action-conditioned video prediction和visual planning，足够粗任务映射；丢失token化/训练/评估，不足以判断实验强度。|

前置核查：视觉表征→动力学→规划适用于该初学教学路线，但不是所有planner/应用的普遍必需依赖；具体机器人/手术应用不是必需基础。 高级persona声明已熟悉基础，原graph仍把基础节点active/foundation；应把已知背景和新增研究能力区分。输入未提供完整prompt，不能断言已知背景没有发送给模型。

- 方向 **World-Model Visual Navigation**：failed。与上一重复的泛world-model navigation同样重叠现有c3；无Map覆盖的原理由不成立，缺具体新能力及针对目标的比较用途。 最终强制前置为空；实际用户用途验证not_evaluated。
- 方向 **Revisable Visual Planning**：passed。反馈驱动revision bridge是明确机制，intro与window一致；用作闭环模型误差/修订方法探索合理，不能据此确立统一必需前置。 最终强制前置为空；实际用户用途验证not_evaluated。
- 方向 **Sparse Visual World Planning**：unknown。效率/信息损失取舍是可选方法问题；目标更重OOD和长期误差，新增能力/独立branch价值仍未知，barrier是推测而非实测。 最终强制前置为空；实际用户用途验证not_evaluated。
- 方向 **Progressive Visual Planning**：passed。有序视觉subgoal研究用途对长时程目标明确；完整源支持方法与OOD任务，intro可作为可选探索，errors may compound须保留假设语气。 最终强制前置为空；实际用户用途验证not_evaluated。

### materials-growth-v0-r1 — unknown

目标：理解硫化物全固态锂电池中锂金属与电解质界面的分解、接触和枝晶问题。 已有基础：了解基础电化学与电池组成，不熟悉固态离子导体和界面表征。

论文计数：{'passed': 0, 'failed': 0, 'unknown': 20, 'not_evaluated': 0}；方向计数：{'passed': 0, 'failed': 0, 'unknown': 0, 'not_evaluated': 0}。保留大量未知，尚未建立完整案例的科学内容有效性；不是已通过推荐价值测试。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 (Digital Presentation) On the Origin of High Resistance at the Interface between Lithium Metal and Sulfide Solid Electrolytes|unclear / 无映射 → **unknown**|β-Li3PS4的first-principles/AIMD研究：锂化分解Li2S/Li3P、输运与void；这是计算研究/会议摘要，不是测得电池寿命。 窗口只保留高界面阻抗与空气稳定性，丢掉β-LPS、计算方法、分解和void；高阻抗不自动证明化学反应机制。|
|1 Challenges and optimization strategies at the interface between sulfide solid electrolyte and lithium anode|unclear / 无映射 → **unknown**|仅题名指向硫化物/锂负极界面挑战和优化；没有摘要，不能核研究类型、机制或效果。 标题截断，无摘要。|
|2 Doping effects of metal cation on sulfide solid electrolyte/lithium metal interface|unclear / 无映射 → **unknown**|仅题名显示金属阳离子掺杂与硫化物/锂金属界面；没有证据说明何种掺杂、表征和效果。 标题截断，无摘要。|
|3 Electrochemically and chemically stable electrolyte–electrode interfaces for lithium iron phosphate all-solid-state batteries with sulfide electrolytes|unclear / 无映射 → **unknown**|研究LiFePO4正极/硫化物电解质涂层防界面反应；固定任务是锂金属负极界面，不能替换对象。 窗口仍含LiFePO4，足以识别正极边界；丢失具体coating材料/结果。|
|4 Graphitic carbon nitride stabilized the lithium anode/sulfide electrolyte interface for all-solid-state lithium-sulfur battery|unclear / 无映射 → **unknown**|题名有graphitic carbon nitride、Li负极/硫化物界面与Li-S；缺摘要，效果和设计类型未知。 标题截断，无摘要。|
|5 High Ionic Conductive, Mechanical Robust Sulfide Solid Electrolyte Films and Interface Design for All‐Solid‐State Lithium Metal Batteries|unclear / 无映射 → **unknown**|硫化物薄膜/PEVA/PTFE与Li3N-rich SEI缓解PTFE还原，0.2 mA/cm2对称电池800h；不是CCD测试，也不是无界面证据容量宣传。 窗口保留PTFE/Li还原缓解动机却截掉Li3N、800h和测试条件；应与纯输运能力区分。|
|6 In situ formed LiF-Li3N interface layer enables ultra-stable sulfide electrolyte-based all-solid-state lithium batteries|unclear / 无映射 → **unknown**|题名给出in situ LiF-Li3N层与硫化物固态电池；缺摘要，不能认定寿命、CCD或层作用机制。 标题截断，无摘要。|
|7 Insight Into All‐Solid‐State Lithium‐Sulfur Batteries: Challenges and Interface Engineering at the Electrode‐Sulfide Solid Electrolyte Interface|unclear / 无映射 → **unknown**|Li-S综述以硫正极为重点，也明确讨论电解质/负极；可以作有边界背景，摘要未具体说明锂金属界面证据。 末尾泛总结窗口丢失两侧界面及正极重点；不能当独立Li负极机制证据。|
|8 Interface failure mechanisms and engineering strategies in sulfide and halide solid electrolytes for lithium metal solid-state batteries|unclear / 无映射 → **unknown**|mini-review按硫化物与卤化物区分dendrite、分解、void、机械失效及诊断取舍；硫化物部分直接相关。 窗口明确失败模式和材料类差异，足够候选映射沉积/界面失效；丢失Li-electrolyte界面背景、策略与诊断范围。|
|9 Interfaces in Sulfide Solid Electrolyte-Based All-Solid-State Lithium Batteries: Characterization, Mechanism and Strategy|unclear / 无映射 → **unknown**|题名是硫化物全固态电池界面表征/机制/策略；无摘要，负极/正极范围和证据未知。 标题截断，无摘要。|
|10 Lithium–sulfur cells with a sulfide solid electrolyte/polysulfide cathode interface|unclear / 无映射 → **unknown**|硫化物固态电解质/多硫化物正极的液-固界面与charge transfer；不是固定锂金属负极界面。 窗口保留polysulfide cathode及liquid-solid，足以辨别对象；不得以出现lithium/sulfide归负极失效。|
|11 Metal Sulfide Artificial Solid-Electrolyte Interface for Improved Lithium Anode Stability|unclear / 无映射 → **unknown**|金属硫化物/LMS人工SEI涂覆锂负极，SEM/XRD/XPS/EIS及对称电池；人工层是硫化物不等于电解质也是硫化物，摘要未明确电解质类别。 窗口只见涂层和Li metal；须保留electrolyte类别未知，不能默认目标材料体系。|
|12 New Types of Binder for Ceramic Solid Electrolyte Films: Sulfide Electrolyte, Lithium Metal, Interfaces and Cyclability|unclear / 无映射 → **unknown**|会议摘要研究sulfide film binder与Li接口、枝晶/裂纹和pouch cell压力条件700cycles；相关但摘要级证据、条件不可扩展。 窗口截在dendrite，丢失binder开发、压力、pouch cell及循环条件；不能判断堆压/工艺贡献。|
|13 Ni-Rich Layered Oxide Cathodes/Sulfide Electrolyte Interface in Solid-State Lithium Battery|unclear / 无映射 → **unknown**|Ni-rich layered oxide正极/硫化物电解质综述；不是锂金属负极界面机制。 完整可见标题已经指明Cathodes，模型不必等抽象学习动词才识别对象。|
|14 Simultaneously in-situ fabrication of lithium fluoride and sulfide enriched artificial solid electrolyte interface facilitates high stable lithium metal anode|unclear / 无映射 → **unknown**|题名是LiF及sulfide-rich人工SEI；没有说明电解质是硫化物，缺摘要，不能并入目标材料体系。 标题截断，无摘要。|
|15 Stable Interface between Sulfide Solid Electrolyte and Room-Temperature Liquid Lithium Anode|unclear / 无映射 → **unknown**|ether-based室温液态锂负极与sulfide保护层，1000h稳定solid-liquid界面；这不是所要求固态锂金属界面体系。 窗口明确room-temperature liquid lithium和ether-based；初学理由说属于锂金属界面节点忽略对象区别。可作显式相邻比较，不能直接覆盖。 理由错误：实际window明确ether-based room-temperature liquid lithium；理由将其归锂金属界面核心混淆固/液负极对象。|
|16 Study of the Cathode/Electrolyte Interface in an All-Sulfide-Solid-State Battery Using Lithium-Rich Transition Metal Sulfide|unclear / 无映射 → **unknown**|cell有Li金属负极，但研究的是Li1.2Ti0.8S2正极/argyrodite接口XPS及20cycles；不能因为整电池含Li metal就把研究对象换成负极。 窗口同时给cathode、Li metal anode和positive electrode接口；应以实际被研究的positive接口为对象。|
|17 Sulfide-Based Solid-State Lithium-Sulfur Batteries: An in-Depth Study of the Li-Electrolyte Interface|unclear / 无映射 → **unknown**|Li6PS5Cl/Li7P3S11与Li稳定性比较，EIS/XPS/ToF-SIMS及GCIB深度层析揭示interphase分层；目标最直接的表征/稳定性候选。 窗口明确compare、assess stability against lithium、characterize interphase，可作候选归characterization；丢失方法、层序和结果，不应宣称无任务。|
|18 Tailoring the Interface between Sulfur and Sulfide Solid Electrolyte for High-Areal-Capacity All-Solid-State Lithium–Sulfur Batteries|unclear / 无映射 → **unknown**|S8硫正极与LPSCl间多硫化物中间物改善wettability/ionic contact，5.1mAh/cm2和250cycles；不是Li金属负极反应。 标题及S8窗口可识别硫正极；不要把泛界面改性直接归锂金属负极节点。|
|19 Thin, flexible sulfide-based electrolyte film and its interface engineering for high performance solid-state lithium metal batteries|unclear / 无映射 → **unknown**|题名为薄柔性硫化物膜及Li金属电池interface engineering；没有摘要，不能核层设计/实验类型。 标题截断，无摘要。|

前置核查：interface→failure应区分化学分解、机械接触与沉积；化学反应不是每种机械失效的必要学习前置。transport可作初学背景，不应以topic边强证因果必需。

持久化方向：0；无方向不等于已证明不存在有用探索。

### materials-growth-v0-r2 — unknown

目标：理解硫化物全固态锂电池中锂金属与电解质界面的分解、接触和枝晶问题。 已有基础：了解基础电化学与电池组成，不熟悉固态离子导体和界面表征。

论文计数：{'passed': 0, 'failed': 0, 'unknown': 20, 'not_evaluated': 0}；方向计数：{'passed': 0, 'failed': 0, 'unknown': 0, 'not_evaluated': 0}。保留大量未知，尚未建立完整案例的科学内容有效性；不是已通过推荐价值测试。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 (Digital Presentation) On the Origin of High Resistance at the Interface between Lithium Metal and Sulfide Solid Electrolytes|unclear / 无映射 → **unknown**|β-Li3PS4的first-principles/AIMD研究：锂化分解Li2S/Li3P、输运与void；这是计算研究/会议摘要，不是测得电池寿命。 窗口只保留高界面阻抗与空气稳定性，丢掉β-LPS、计算方法、分解和void；高阻抗不自动证明化学反应机制。|
|1 Challenges and optimization strategies at the interface between sulfide solid electrolyte and lithium anode|unclear / 无映射 → **unknown**|仅题名指向硫化物/锂负极界面挑战和优化；没有摘要，不能核研究类型、机制或效果。 标题截断，无摘要。|
|2 Doping effects of metal cation on sulfide solid electrolyte/lithium metal interface|unclear / 无映射 → **unknown**|仅题名显示金属阳离子掺杂与硫化物/锂金属界面；没有证据说明何种掺杂、表征和效果。 标题截断，无摘要。|
|3 Electrochemically and chemically stable electrolyte–electrode interfaces for lithium iron phosphate all-solid-state batteries with sulfide electrolytes|unclear / 无映射 → **unknown**|研究LiFePO4正极/硫化物电解质涂层防界面反应；固定任务是锂金属负极界面，不能替换对象。 窗口仍含LiFePO4，足以识别正极边界；丢失具体coating材料/结果。|
|4 Graphitic carbon nitride stabilized the lithium anode/sulfide electrolyte interface for all-solid-state lithium-sulfur battery|unclear / 无映射 → **unknown**|题名有graphitic carbon nitride、Li负极/硫化物界面与Li-S；缺摘要，效果和设计类型未知。 标题截断，无摘要。|
|5 High Ionic Conductive, Mechanical Robust Sulfide Solid Electrolyte Films and Interface Design for All‐Solid‐State Lithium Metal Batteries|unclear / 无映射 → **unknown**|硫化物薄膜/PEVA/PTFE与Li3N-rich SEI缓解PTFE还原，0.2 mA/cm2对称电池800h；不是CCD测试，也不是无界面证据容量宣传。 窗口保留PTFE/Li还原缓解动机却截掉Li3N、800h和测试条件；应与纯输运能力区分。|
|6 In situ formed LiF-Li3N interface layer enables ultra-stable sulfide electrolyte-based all-solid-state lithium batteries|unclear / 无映射 → **unknown**|题名给出in situ LiF-Li3N层与硫化物固态电池；缺摘要，不能认定寿命、CCD或层作用机制。 标题截断，无摘要。|
|7 Insight Into All‐Solid‐State Lithium‐Sulfur Batteries: Challenges and Interface Engineering at the Electrode‐Sulfide Solid Electrolyte Interface|unclear / 无映射 → **unknown**|Li-S综述以硫正极为重点，也明确讨论电解质/负极；可以作有边界背景，摘要未具体说明锂金属界面证据。 末尾泛总结窗口丢失两侧界面及正极重点；不能当独立Li负极机制证据。|
|8 Interface failure mechanisms and engineering strategies in sulfide and halide solid electrolytes for lithium metal solid-state batteries|unclear / 无映射 → **unknown**|mini-review按硫化物与卤化物区分dendrite、分解、void、机械失效及诊断取舍；硫化物部分直接相关。 窗口明确失败模式和材料类差异，足够候选映射沉积/界面失效；丢失Li-electrolyte界面背景、策略与诊断范围。|
|9 Interfaces in Sulfide Solid Electrolyte-Based All-Solid-State Lithium Batteries: Characterization, Mechanism and Strategy|unclear / 无映射 → **unknown**|题名是硫化物全固态电池界面表征/机制/策略；无摘要，负极/正极范围和证据未知。 标题截断，无摘要。|
|10 Lithium–sulfur cells with a sulfide solid electrolyte/polysulfide cathode interface|unclear / 无映射 → **unknown**|硫化物固态电解质/多硫化物正极的液-固界面与charge transfer；不是固定锂金属负极界面。 窗口保留polysulfide cathode及liquid-solid，足以辨别对象；不得以出现lithium/sulfide归负极失效。|
|11 Metal Sulfide Artificial Solid-Electrolyte Interface for Improved Lithium Anode Stability|unclear / 无映射 → **unknown**|金属硫化物/LMS人工SEI涂覆锂负极，SEM/XRD/XPS/EIS及对称电池；人工层是硫化物不等于电解质也是硫化物，摘要未明确电解质类别。 窗口只见涂层和Li metal；须保留electrolyte类别未知，不能默认目标材料体系。|
|12 New Types of Binder for Ceramic Solid Electrolyte Films: Sulfide Electrolyte, Lithium Metal, Interfaces and Cyclability|unclear / 无映射 → **unknown**|会议摘要研究sulfide film binder与Li接口、枝晶/裂纹和pouch cell压力条件700cycles；相关但摘要级证据、条件不可扩展。 窗口截在dendrite，丢失binder开发、压力、pouch cell及循环条件；不能判断堆压/工艺贡献。|
|13 Ni-Rich Layered Oxide Cathodes/Sulfide Electrolyte Interface in Solid-State Lithium Battery|unclear / 无映射 → **unknown**|Ni-rich layered oxide正极/硫化物电解质综述；不是锂金属负极界面机制。 完整可见标题已经指明Cathodes，模型不必等抽象学习动词才识别对象。|
|14 Simultaneously in-situ fabrication of lithium fluoride and sulfide enriched artificial solid electrolyte interface facilitates high stable lithium metal anode|unclear / 无映射 → **unknown**|题名是LiF及sulfide-rich人工SEI；没有说明电解质是硫化物，缺摘要，不能并入目标材料体系。 标题截断，无摘要。|
|15 Stable Interface between Sulfide Solid Electrolyte and Room-Temperature Liquid Lithium Anode|unclear / 无映射 → **unknown**|ether-based室温液态锂负极与sulfide保护层，1000h稳定solid-liquid界面；这不是所要求固态锂金属界面体系。 窗口明确room-temperature liquid lithium和ether-based；初学理由说属于锂金属界面节点忽略对象区别。可作显式相邻比较，不能直接覆盖。 理由错误：实际window明确ether-based room-temperature liquid lithium；理由将其归锂金属界面核心混淆固/液负极对象。|
|16 Study of the Cathode/Electrolyte Interface in an All-Sulfide-Solid-State Battery Using Lithium-Rich Transition Metal Sulfide|unclear / 无映射 → **unknown**|cell有Li金属负极，但研究的是Li1.2Ti0.8S2正极/argyrodite接口XPS及20cycles；不能因为整电池含Li metal就把研究对象换成负极。 窗口同时给cathode、Li metal anode和positive electrode接口；应以实际被研究的positive接口为对象。|
|17 Sulfide-Based Solid-State Lithium-Sulfur Batteries: An in-Depth Study of the Li-Electrolyte Interface|unclear / 无映射 → **unknown**|Li6PS5Cl/Li7P3S11与Li稳定性比较，EIS/XPS/ToF-SIMS及GCIB深度层析揭示interphase分层；目标最直接的表征/稳定性候选。 窗口明确compare、assess stability against lithium、characterize interphase，可作候选归characterization；丢失方法、层序和结果，不应宣称无任务。 理由错误：window已有compare two sulfide electrolytes、assess stability against lithium、characterize interphase；声称未明确任务过严。|
|18 Tailoring the Interface between Sulfur and Sulfide Solid Electrolyte for High-Areal-Capacity All-Solid-State Lithium–Sulfur Batteries|unclear / 无映射 → **unknown**|S8硫正极与LPSCl间多硫化物中间物改善wettability/ionic contact，5.1mAh/cm2和250cycles；不是Li金属负极反应。 标题及S8窗口可识别硫正极；不要把泛界面改性直接归锂金属负极节点。|
|19 Thin, flexible sulfide-based electrolyte film and its interface engineering for high performance solid-state lithium metal batteries|unclear / 无映射 → **unknown**|题名为薄柔性硫化物膜及Li金属电池interface engineering；没有摘要，不能核层设计/实验类型。 标题截断，无摘要。|

前置核查：interface→failure应区分化学分解、机械接触与沉积；化学反应不是每种机械失效的必要学习前置。transport可作初学背景，不应以topic边强证因果必需。

持久化方向：0；无方向不等于已证明不存在有用探索。

### materials-growth-v0-r3 — unknown

目标：理解硫化物全固态锂电池中锂金属与电解质界面的分解、接触和枝晶问题。 已有基础：了解基础电化学与电池组成，不熟悉固态离子导体和界面表征。

论文计数：{'passed': 0, 'failed': 0, 'unknown': 20, 'not_evaluated': 0}；方向计数：{'passed': 0, 'failed': 0, 'unknown': 0, 'not_evaluated': 0}。保留大量未知，尚未建立完整案例的科学内容有效性；不是已通过推荐价值测试。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 (Digital Presentation) On the Origin of High Resistance at the Interface between Lithium Metal and Sulfide Solid Electrolytes|unclear / 无映射 → **unknown**|β-Li3PS4的first-principles/AIMD研究：锂化分解Li2S/Li3P、输运与void；这是计算研究/会议摘要，不是测得电池寿命。 窗口只保留高界面阻抗与空气稳定性，丢掉β-LPS、计算方法、分解和void；高阻抗不自动证明化学反应机制。|
|1 Challenges and optimization strategies at the interface between sulfide solid electrolyte and lithium anode|unclear / 无映射 → **unknown**|仅题名指向硫化物/锂负极界面挑战和优化；没有摘要，不能核研究类型、机制或效果。 标题截断，无摘要。|
|2 Doping effects of metal cation on sulfide solid electrolyte/lithium metal interface|unclear / 无映射 → **unknown**|仅题名显示金属阳离子掺杂与硫化物/锂金属界面；没有证据说明何种掺杂、表征和效果。 标题截断，无摘要。|
|3 Electrochemically and chemically stable electrolyte–electrode interfaces for lithium iron phosphate all-solid-state batteries with sulfide electrolytes|unclear / 无映射 → **unknown**|研究LiFePO4正极/硫化物电解质涂层防界面反应；固定任务是锂金属负极界面，不能替换对象。 窗口仍含LiFePO4，足以识别正极边界；丢失具体coating材料/结果。|
|4 Graphitic carbon nitride stabilized the lithium anode/sulfide electrolyte interface for all-solid-state lithium-sulfur battery|unclear / 无映射 → **unknown**|题名有graphitic carbon nitride、Li负极/硫化物界面与Li-S；缺摘要，效果和设计类型未知。 标题截断，无摘要。|
|5 High Ionic Conductive, Mechanical Robust Sulfide Solid Electrolyte Films and Interface Design for All‐Solid‐State Lithium Metal Batteries|unclear / 无映射 → **unknown**|硫化物薄膜/PEVA/PTFE与Li3N-rich SEI缓解PTFE还原，0.2 mA/cm2对称电池800h；不是CCD测试，也不是无界面证据容量宣传。 窗口保留PTFE/Li还原缓解动机却截掉Li3N、800h和测试条件；应与纯输运能力区分。|
|6 In situ formed LiF-Li3N interface layer enables ultra-stable sulfide electrolyte-based all-solid-state lithium batteries|unclear / 无映射 → **unknown**|题名给出in situ LiF-Li3N层与硫化物固态电池；缺摘要，不能认定寿命、CCD或层作用机制。 标题截断，无摘要。|
|7 Insight Into All‐Solid‐State Lithium‐Sulfur Batteries: Challenges and Interface Engineering at the Electrode‐Sulfide Solid Electrolyte Interface|unclear / 无映射 → **unknown**|Li-S综述以硫正极为重点，也明确讨论电解质/负极；可以作有边界背景，摘要未具体说明锂金属界面证据。 末尾泛总结窗口丢失两侧界面及正极重点；不能当独立Li负极机制证据。|
|8 Interface failure mechanisms and engineering strategies in sulfide and halide solid electrolytes for lithium metal solid-state batteries|unclear / 无映射 → **unknown**|mini-review按硫化物与卤化物区分dendrite、分解、void、机械失效及诊断取舍；硫化物部分直接相关。 窗口明确失败模式和材料类差异，足够候选映射沉积/界面失效；丢失Li-electrolyte界面背景、策略与诊断范围。|
|9 Interfaces in Sulfide Solid Electrolyte-Based All-Solid-State Lithium Batteries: Characterization, Mechanism and Strategy|unclear / 无映射 → **unknown**|题名是硫化物全固态电池界面表征/机制/策略；无摘要，负极/正极范围和证据未知。 标题截断，无摘要。|
|10 Lithium–sulfur cells with a sulfide solid electrolyte/polysulfide cathode interface|unclear / 无映射 → **unknown**|硫化物固态电解质/多硫化物正极的液-固界面与charge transfer；不是固定锂金属负极界面。 窗口保留polysulfide cathode及liquid-solid，足以辨别对象；不得以出现lithium/sulfide归负极失效。|
|11 Metal Sulfide Artificial Solid-Electrolyte Interface for Improved Lithium Anode Stability|unclear / 无映射 → **unknown**|金属硫化物/LMS人工SEI涂覆锂负极，SEM/XRD/XPS/EIS及对称电池；人工层是硫化物不等于电解质也是硫化物，摘要未明确电解质类别。 窗口只见涂层和Li metal；须保留electrolyte类别未知，不能默认目标材料体系。|
|12 New Types of Binder for Ceramic Solid Electrolyte Films: Sulfide Electrolyte, Lithium Metal, Interfaces and Cyclability|unclear / 无映射 → **unknown**|会议摘要研究sulfide film binder与Li接口、枝晶/裂纹和pouch cell压力条件700cycles；相关但摘要级证据、条件不可扩展。 窗口截在dendrite，丢失binder开发、压力、pouch cell及循环条件；不能判断堆压/工艺贡献。|
|13 Ni-Rich Layered Oxide Cathodes/Sulfide Electrolyte Interface in Solid-State Lithium Battery|unclear / 无映射 → **unknown**|Ni-rich layered oxide正极/硫化物电解质综述；不是锂金属负极界面机制。 完整可见标题已经指明Cathodes，模型不必等抽象学习动词才识别对象。|
|14 Simultaneously in-situ fabrication of lithium fluoride and sulfide enriched artificial solid electrolyte interface facilitates high stable lithium metal anode|unclear / 无映射 → **unknown**|题名是LiF及sulfide-rich人工SEI；没有说明电解质是硫化物，缺摘要，不能并入目标材料体系。 标题截断，无摘要。|
|15 Stable Interface between Sulfide Solid Electrolyte and Room-Temperature Liquid Lithium Anode|unclear / 无映射 → **unknown**|ether-based室温液态锂负极与sulfide保护层，1000h稳定solid-liquid界面；这不是所要求固态锂金属界面体系。 窗口明确room-temperature liquid lithium和ether-based；初学理由说属于锂金属界面节点忽略对象区别。可作显式相邻比较，不能直接覆盖。 理由错误：实际window明确ether-based room-temperature liquid lithium；理由将其归锂金属界面核心混淆固/液负极对象。|
|16 Study of the Cathode/Electrolyte Interface in an All-Sulfide-Solid-State Battery Using Lithium-Rich Transition Metal Sulfide|unclear / 无映射 → **unknown**|cell有Li金属负极，但研究的是Li1.2Ti0.8S2正极/argyrodite接口XPS及20cycles；不能因为整电池含Li metal就把研究对象换成负极。 窗口同时给cathode、Li metal anode和positive electrode接口；应以实际被研究的positive接口为对象。|
|17 Sulfide-Based Solid-State Lithium-Sulfur Batteries: An in-Depth Study of the Li-Electrolyte Interface|unclear / 无映射 → **unknown**|Li6PS5Cl/Li7P3S11与Li稳定性比较，EIS/XPS/ToF-SIMS及GCIB深度层析揭示interphase分层；目标最直接的表征/稳定性候选。 窗口明确compare、assess stability against lithium、characterize interphase，可作候选归characterization；丢失方法、层序和结果，不应宣称无任务。|
|18 Tailoring the Interface between Sulfur and Sulfide Solid Electrolyte for High-Areal-Capacity All-Solid-State Lithium–Sulfur Batteries|unclear / 无映射 → **unknown**|S8硫正极与LPSCl间多硫化物中间物改善wettability/ionic contact，5.1mAh/cm2和250cycles；不是Li金属负极反应。 标题及S8窗口可识别硫正极；不要把泛界面改性直接归锂金属负极节点。|
|19 Thin, flexible sulfide-based electrolyte film and its interface engineering for high performance solid-state lithium metal batteries|unclear / 无映射 → **unknown**|题名为薄柔性硫化物膜及Li金属电池interface engineering；没有摘要，不能核层设计/实验类型。 标题截断，无摘要。|

前置核查：interface→failure应区分化学分解、机械接触与沉积；化学反应不是每种机械失效的必要学习前置。transport可作初学背景，不应以topic边强证因果必需。

持久化方向：0；无方向不等于已证明不存在有用探索。

### materials-growth-v1-r1 — unknown

目标：比较硫化物全固态锂电池界面层设计对长期稳定性和临界电流密度的作用及失效机制。 已有基础：熟悉固态电解质、电化学阻抗与基本表面表征。

论文计数：{'passed': 0, 'failed': 0, 'unknown': 20, 'not_evaluated': 0}；方向计数：{'passed': 0, 'failed': 0, 'unknown': 0, 'not_evaluated': 0}。保留大量未知，尚未建立完整案例的科学内容有效性；不是已通过推荐价值测试。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 (Digital Presentation) On the Origin of High Resistance at the Interface between Lithium Metal and Sulfide Solid Electrolytes|covered / 锂金属界面反应 → **unknown**|β-Li3PS4的first-principles/AIMD研究：锂化分解Li2S/Li3P、输运与void；这是计算研究/会议摘要，不是测得电池寿命。 窗口只保留高界面阻抗与空气稳定性，丢掉β-LPS、计算方法、分解和void；高阻抗不自动证明化学反应机制。|
|1 Challenges and optimization strategies at the interface between sulfide solid electrolyte and lithium anode|unclear / 无映射 → **unknown**|仅题名指向硫化物/锂负极界面挑战和优化；没有摘要，不能核研究类型、机制或效果。 标题截断，无摘要。|
|2 Doping effects of metal cation on sulfide solid electrolyte/lithium metal interface|unclear / 无映射 → **unknown**|仅题名显示金属阳离子掺杂与硫化物/锂金属界面；没有证据说明何种掺杂、表征和效果。 标题截断，无摘要。|
|3 Electrochemically and chemically stable electrolyte–electrode interfaces for lithium iron phosphate all-solid-state batteries with sulfide electrolytes|unclear / 无映射 → **unknown**|研究LiFePO4正极/硫化物电解质涂层防界面反应；固定任务是锂金属负极界面，不能替换对象。 窗口仍含LiFePO4，足以识别正极边界；丢失具体coating材料/结果。|
|4 Graphitic carbon nitride stabilized the lithium anode/sulfide electrolyte interface for all-solid-state lithium-sulfur battery|unclear / 无映射 → **unknown**|题名有graphitic carbon nitride、Li负极/硫化物界面与Li-S；缺摘要，效果和设计类型未知。 标题截断，无摘要。|
|5 High Ionic Conductive, Mechanical Robust Sulfide Solid Electrolyte Films and Interface Design for All‐Solid‐State Lithium Metal Batteries|unclear / 无映射 → **unknown**|硫化物薄膜/PEVA/PTFE与Li3N-rich SEI缓解PTFE还原，0.2 mA/cm2对称电池800h；不是CCD测试，也不是无界面证据容量宣传。 窗口保留PTFE/Li还原缓解动机却截掉Li3N、800h和测试条件；应与纯输运能力区分。|
|6 In situ formed LiF-Li3N interface layer enables ultra-stable sulfide electrolyte-based all-solid-state lithium batteries|unclear / 无映射 → **unknown**|题名给出in situ LiF-Li3N层与硫化物固态电池；缺摘要，不能认定寿命、CCD或层作用机制。 标题截断，无摘要。|
|7 Insight Into All‐Solid‐State Lithium‐Sulfur Batteries: Challenges and Interface Engineering at the Electrode‐Sulfide Solid Electrolyte Interface|unclear / 无映射 → **unknown**|Li-S综述以硫正极为重点，也明确讨论电解质/负极；可以作有边界背景，摘要未具体说明锂金属界面证据。 末尾泛总结窗口丢失两侧界面及正极重点；不能当独立Li负极机制证据。|
|8 Interface failure mechanisms and engineering strategies in sulfide and halide solid electrolytes for lithium metal solid-state batteries|unclear / 无映射 → **unknown**|mini-review按硫化物与卤化物区分dendrite、分解、void、机械失效及诊断取舍；硫化物部分直接相关。 窗口明确失败模式和材料类差异，足够候选映射沉积/界面失效；丢失Li-electrolyte界面背景、策略与诊断范围。 理由错误：window已明确dendrite penetration、decomposition、void、mechanical failure，与failure节点直接有关；要求必须新增任务才识别关联过严。|
|9 Interfaces in Sulfide Solid Electrolyte-Based All-Solid-State Lithium Batteries: Characterization, Mechanism and Strategy|unclear / 无映射 → **unknown**|题名是硫化物全固态电池界面表征/机制/策略；无摘要，负极/正极范围和证据未知。 标题截断，无摘要。|
|10 Lithium–sulfur cells with a sulfide solid electrolyte/polysulfide cathode interface|unclear / 无映射 → **unknown**|硫化物固态电解质/多硫化物正极的液-固界面与charge transfer；不是固定锂金属负极界面。 窗口保留polysulfide cathode及liquid-solid，足以辨别对象；不得以出现lithium/sulfide归负极失效。|
|11 Metal Sulfide Artificial Solid-Electrolyte Interface for Improved Lithium Anode Stability|unclear / 无映射 → **unknown**|金属硫化物/LMS人工SEI涂覆锂负极，SEM/XRD/XPS/EIS及对称电池；人工层是硫化物不等于电解质也是硫化物，摘要未明确电解质类别。 窗口只见涂层和Li metal；须保留electrolyte类别未知，不能默认目标材料体系。|
|12 New Types of Binder for Ceramic Solid Electrolyte Films: Sulfide Electrolyte, Lithium Metal, Interfaces and Cyclability|unclear / 无映射 → **unknown**|会议摘要研究sulfide film binder与Li接口、枝晶/裂纹和pouch cell压力条件700cycles；相关但摘要级证据、条件不可扩展。 窗口截在dendrite，丢失binder开发、压力、pouch cell及循环条件；不能判断堆压/工艺贡献。|
|13 Ni-Rich Layered Oxide Cathodes/Sulfide Electrolyte Interface in Solid-State Lithium Battery|unclear / 无映射 → **unknown**|Ni-rich layered oxide正极/硫化物电解质综述；不是锂金属负极界面机制。 完整可见标题已经指明Cathodes，模型不必等抽象学习动词才识别对象。|
|14 Simultaneously in-situ fabrication of lithium fluoride and sulfide enriched artificial solid electrolyte interface facilitates high stable lithium metal anode|unclear / 无映射 → **unknown**|题名是LiF及sulfide-rich人工SEI；没有说明电解质是硫化物，缺摘要，不能并入目标材料体系。 标题截断，无摘要。|
|15 Stable Interface between Sulfide Solid Electrolyte and Room-Temperature Liquid Lithium Anode|unclear / 无映射 → **unknown**|ether-based室温液态锂负极与sulfide保护层，1000h稳定solid-liquid界面；这不是所要求固态锂金属界面体系。 窗口明确room-temperature liquid lithium和ether-based；初学理由说属于锂金属界面节点忽略对象区别。可作显式相邻比较，不能直接覆盖。|
|16 Study of the Cathode/Electrolyte Interface in an All-Sulfide-Solid-State Battery Using Lithium-Rich Transition Metal Sulfide|unclear / 无映射 → **unknown**|cell有Li金属负极，但研究的是Li1.2Ti0.8S2正极/argyrodite接口XPS及20cycles；不能因为整电池含Li metal就把研究对象换成负极。 窗口同时给cathode、Li metal anode和positive electrode接口；应以实际被研究的positive接口为对象。|
|17 Sulfide-Based Solid-State Lithium-Sulfur Batteries: An in-Depth Study of the Li-Electrolyte Interface|unclear / 无映射 → **unknown**|Li6PS5Cl/Li7P3S11与Li稳定性比较，EIS/XPS/ToF-SIMS及GCIB深度层析揭示interphase分层；目标最直接的表征/稳定性候选。 窗口明确compare、assess stability against lithium、characterize interphase，可作候选归characterization；丢失方法、层序和结果，不应宣称无任务。|
|18 Tailoring the Interface between Sulfur and Sulfide Solid Electrolyte for High-Areal-Capacity All-Solid-State Lithium–Sulfur Batteries|unclear / 无映射 → **unknown**|S8硫正极与LPSCl间多硫化物中间物改善wettability/ionic contact，5.1mAh/cm2和250cycles；不是Li金属负极反应。 标题及S8窗口可识别硫正极；不要把泛界面改性直接归锂金属负极节点。|
|19 Thin, flexible sulfide-based electrolyte film and its interface engineering for high performance solid-state lithium metal batteries|unclear / 无映射 → **unknown**|题名为薄柔性硫化物膜及Li金属电池interface engineering；没有摘要，不能核层设计/实验类型。 标题截断，无摘要。|

前置核查：interface→failure应区分化学分解、机械接触与沉积；化学反应不是每种机械失效的必要学习前置。transport可作初学背景，不应以topic边强证因果必需。 高级persona声明已熟悉基础，原graph仍把基础节点active/foundation；应把已知背景和新增研究能力区分。输入未提供完整prompt，不能断言已知背景没有发送给模型。

持久化方向：0；无方向不等于已证明不存在有用探索。

### materials-growth-v1-r2 — unknown

目标：比较硫化物全固态锂电池界面层设计对长期稳定性和临界电流密度的作用及失效机制。 已有基础：熟悉固态电解质、电化学阻抗与基本表面表征。

论文计数：{'passed': 0, 'failed': 0, 'unknown': 20, 'not_evaluated': 0}；方向计数：{'passed': 0, 'failed': 0, 'unknown': 0, 'not_evaluated': 0}。保留大量未知，尚未建立完整案例的科学内容有效性；不是已通过推荐价值测试。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 (Digital Presentation) On the Origin of High Resistance at the Interface between Lithium Metal and Sulfide Solid Electrolytes|unclear / 无映射 → **unknown**|β-Li3PS4的first-principles/AIMD研究：锂化分解Li2S/Li3P、输运与void；这是计算研究/会议摘要，不是测得电池寿命。 窗口只保留高界面阻抗与空气稳定性，丢掉β-LPS、计算方法、分解和void；高阻抗不自动证明化学反应机制。|
|1 Challenges and optimization strategies at the interface between sulfide solid electrolyte and lithium anode|unclear / 无映射 → **unknown**|仅题名指向硫化物/锂负极界面挑战和优化；没有摘要，不能核研究类型、机制或效果。 标题截断，无摘要。|
|2 Doping effects of metal cation on sulfide solid electrolyte/lithium metal interface|unclear / 无映射 → **unknown**|仅题名显示金属阳离子掺杂与硫化物/锂金属界面；没有证据说明何种掺杂、表征和效果。 标题截断，无摘要。|
|3 Electrochemically and chemically stable electrolyte–electrode interfaces for lithium iron phosphate all-solid-state batteries with sulfide electrolytes|unclear / 无映射 → **unknown**|研究LiFePO4正极/硫化物电解质涂层防界面反应；固定任务是锂金属负极界面，不能替换对象。 窗口仍含LiFePO4，足以识别正极边界；丢失具体coating材料/结果。|
|4 Graphitic carbon nitride stabilized the lithium anode/sulfide electrolyte interface for all-solid-state lithium-sulfur battery|unclear / 无映射 → **unknown**|题名有graphitic carbon nitride、Li负极/硫化物界面与Li-S；缺摘要，效果和设计类型未知。 标题截断，无摘要。|
|5 High Ionic Conductive, Mechanical Robust Sulfide Solid Electrolyte Films and Interface Design for All‐Solid‐State Lithium Metal Batteries|unclear / 无映射 → **unknown**|硫化物薄膜/PEVA/PTFE与Li3N-rich SEI缓解PTFE还原，0.2 mA/cm2对称电池800h；不是CCD测试，也不是无界面证据容量宣传。 窗口保留PTFE/Li还原缓解动机却截掉Li3N、800h和测试条件；应与纯输运能力区分。|
|6 In situ formed LiF-Li3N interface layer enables ultra-stable sulfide electrolyte-based all-solid-state lithium batteries|unclear / 无映射 → **unknown**|题名给出in situ LiF-Li3N层与硫化物固态电池；缺摘要，不能认定寿命、CCD或层作用机制。 标题截断，无摘要。|
|7 Insight Into All‐Solid‐State Lithium‐Sulfur Batteries: Challenges and Interface Engineering at the Electrode‐Sulfide Solid Electrolyte Interface|unclear / 无映射 → **unknown**|Li-S综述以硫正极为重点，也明确讨论电解质/负极；可以作有边界背景，摘要未具体说明锂金属界面证据。 末尾泛总结窗口丢失两侧界面及正极重点；不能当独立Li负极机制证据。|
|8 Interface failure mechanisms and engineering strategies in sulfide and halide solid electrolytes for lithium metal solid-state batteries|unclear / 无映射 → **unknown**|mini-review按硫化物与卤化物区分dendrite、分解、void、机械失效及诊断取舍；硫化物部分直接相关。 窗口明确失败模式和材料类差异，足够候选映射沉积/界面失效；丢失Li-electrolyte界面背景、策略与诊断范围。 理由错误：window已明确dendrite penetration、decomposition、void、mechanical failure，与failure节点直接有关；要求必须新增任务才识别关联过严。|
|9 Interfaces in Sulfide Solid Electrolyte-Based All-Solid-State Lithium Batteries: Characterization, Mechanism and Strategy|unclear / 无映射 → **unknown**|题名是硫化物全固态电池界面表征/机制/策略；无摘要，负极/正极范围和证据未知。 标题截断，无摘要。|
|10 Lithium–sulfur cells with a sulfide solid electrolyte/polysulfide cathode interface|unclear / 无映射 → **unknown**|硫化物固态电解质/多硫化物正极的液-固界面与charge transfer；不是固定锂金属负极界面。 窗口保留polysulfide cathode及liquid-solid，足以辨别对象；不得以出现lithium/sulfide归负极失效。|
|11 Metal Sulfide Artificial Solid-Electrolyte Interface for Improved Lithium Anode Stability|unclear / 无映射 → **unknown**|金属硫化物/LMS人工SEI涂覆锂负极，SEM/XRD/XPS/EIS及对称电池；人工层是硫化物不等于电解质也是硫化物，摘要未明确电解质类别。 窗口只见涂层和Li metal；须保留electrolyte类别未知，不能默认目标材料体系。|
|12 New Types of Binder for Ceramic Solid Electrolyte Films: Sulfide Electrolyte, Lithium Metal, Interfaces and Cyclability|unclear / 无映射 → **unknown**|会议摘要研究sulfide film binder与Li接口、枝晶/裂纹和pouch cell压力条件700cycles；相关但摘要级证据、条件不可扩展。 窗口截在dendrite，丢失binder开发、压力、pouch cell及循环条件；不能判断堆压/工艺贡献。|
|13 Ni-Rich Layered Oxide Cathodes/Sulfide Electrolyte Interface in Solid-State Lithium Battery|unclear / 无映射 → **unknown**|Ni-rich layered oxide正极/硫化物电解质综述；不是锂金属负极界面机制。 完整可见标题已经指明Cathodes，模型不必等抽象学习动词才识别对象。|
|14 Simultaneously in-situ fabrication of lithium fluoride and sulfide enriched artificial solid electrolyte interface facilitates high stable lithium metal anode|unclear / 无映射 → **unknown**|题名是LiF及sulfide-rich人工SEI；没有说明电解质是硫化物，缺摘要，不能并入目标材料体系。 标题截断，无摘要。|
|15 Stable Interface between Sulfide Solid Electrolyte and Room-Temperature Liquid Lithium Anode|unclear / 无映射 → **unknown**|ether-based室温液态锂负极与sulfide保护层，1000h稳定solid-liquid界面；这不是所要求固态锂金属界面体系。 窗口明确room-temperature liquid lithium和ether-based；初学理由说属于锂金属界面节点忽略对象区别。可作显式相邻比较，不能直接覆盖。|
|16 Study of the Cathode/Electrolyte Interface in an All-Sulfide-Solid-State Battery Using Lithium-Rich Transition Metal Sulfide|unclear / 无映射 → **unknown**|cell有Li金属负极，但研究的是Li1.2Ti0.8S2正极/argyrodite接口XPS及20cycles；不能因为整电池含Li metal就把研究对象换成负极。 窗口同时给cathode、Li metal anode和positive electrode接口；应以实际被研究的positive接口为对象。|
|17 Sulfide-Based Solid-State Lithium-Sulfur Batteries: An in-Depth Study of the Li-Electrolyte Interface|unclear / 无映射 → **unknown**|Li6PS5Cl/Li7P3S11与Li稳定性比较，EIS/XPS/ToF-SIMS及GCIB深度层析揭示interphase分层；目标最直接的表征/稳定性候选。 窗口明确compare、assess stability against lithium、characterize interphase，可作候选归characterization；丢失方法、层序和结果，不应宣称无任务。|
|18 Tailoring the Interface between Sulfur and Sulfide Solid Electrolyte for High-Areal-Capacity All-Solid-State Lithium–Sulfur Batteries|unclear / 无映射 → **unknown**|S8硫正极与LPSCl间多硫化物中间物改善wettability/ionic contact，5.1mAh/cm2和250cycles；不是Li金属负极反应。 标题及S8窗口可识别硫正极；不要把泛界面改性直接归锂金属负极节点。|
|19 Thin, flexible sulfide-based electrolyte film and its interface engineering for high performance solid-state lithium metal batteries|unclear / 无映射 → **unknown**|题名为薄柔性硫化物膜及Li金属电池interface engineering；没有摘要，不能核层设计/实验类型。 标题截断，无摘要。|

前置核查：interface→failure应区分化学分解、机械接触与沉积；化学反应不是每种机械失效的必要学习前置。transport可作初学背景，不应以topic边强证因果必需。 高级persona声明已熟悉基础，原graph仍把基础节点active/foundation；应把已知背景和新增研究能力区分。输入未提供完整prompt，不能断言已知背景没有发送给模型。

持久化方向：0；无方向不等于已证明不存在有用探索。

### materials-growth-v1-r3 — unknown

目标：比较硫化物全固态锂电池界面层设计对长期稳定性和临界电流密度的作用及失效机制。 已有基础：熟悉固态电解质、电化学阻抗与基本表面表征。

论文计数：{'passed': 0, 'failed': 0, 'unknown': 20, 'not_evaluated': 0}；方向计数：{'passed': 0, 'failed': 0, 'unknown': 0, 'not_evaluated': 0}。保留大量未知，尚未建立完整案例的科学内容有效性；不是已通过推荐价值测试。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 (Digital Presentation) On the Origin of High Resistance at the Interface between Lithium Metal and Sulfide Solid Electrolytes|unclear / 无映射 → **unknown**|β-Li3PS4的first-principles/AIMD研究：锂化分解Li2S/Li3P、输运与void；这是计算研究/会议摘要，不是测得电池寿命。 窗口只保留高界面阻抗与空气稳定性，丢掉β-LPS、计算方法、分解和void；高阻抗不自动证明化学反应机制。|
|1 Challenges and optimization strategies at the interface between sulfide solid electrolyte and lithium anode|unclear / 无映射 → **unknown**|仅题名指向硫化物/锂负极界面挑战和优化；没有摘要，不能核研究类型、机制或效果。 标题截断，无摘要。|
|2 Doping effects of metal cation on sulfide solid electrolyte/lithium metal interface|unclear / 无映射 → **unknown**|仅题名显示金属阳离子掺杂与硫化物/锂金属界面；没有证据说明何种掺杂、表征和效果。 标题截断，无摘要。|
|3 Electrochemically and chemically stable electrolyte–electrode interfaces for lithium iron phosphate all-solid-state batteries with sulfide electrolytes|unclear / 无映射 → **unknown**|研究LiFePO4正极/硫化物电解质涂层防界面反应；固定任务是锂金属负极界面，不能替换对象。 窗口仍含LiFePO4，足以识别正极边界；丢失具体coating材料/结果。|
|4 Graphitic carbon nitride stabilized the lithium anode/sulfide electrolyte interface for all-solid-state lithium-sulfur battery|unclear / 无映射 → **unknown**|题名有graphitic carbon nitride、Li负极/硫化物界面与Li-S；缺摘要，效果和设计类型未知。 标题截断，无摘要。|
|5 High Ionic Conductive, Mechanical Robust Sulfide Solid Electrolyte Films and Interface Design for All‐Solid‐State Lithium Metal Batteries|unclear / 无映射 → **unknown**|硫化物薄膜/PEVA/PTFE与Li3N-rich SEI缓解PTFE还原，0.2 mA/cm2对称电池800h；不是CCD测试，也不是无界面证据容量宣传。 窗口保留PTFE/Li还原缓解动机却截掉Li3N、800h和测试条件；应与纯输运能力区分。|
|6 In situ formed LiF-Li3N interface layer enables ultra-stable sulfide electrolyte-based all-solid-state lithium batteries|unclear / 无映射 → **unknown**|题名给出in situ LiF-Li3N层与硫化物固态电池；缺摘要，不能认定寿命、CCD或层作用机制。 标题截断，无摘要。|
|7 Insight Into All‐Solid‐State Lithium‐Sulfur Batteries: Challenges and Interface Engineering at the Electrode‐Sulfide Solid Electrolyte Interface|unclear / 无映射 → **unknown**|Li-S综述以硫正极为重点，也明确讨论电解质/负极；可以作有边界背景，摘要未具体说明锂金属界面证据。 末尾泛总结窗口丢失两侧界面及正极重点；不能当独立Li负极机制证据。|
|8 Interface failure mechanisms and engineering strategies in sulfide and halide solid electrolytes for lithium metal solid-state batteries|unclear / 无映射 → **unknown**|mini-review按硫化物与卤化物区分dendrite、分解、void、机械失效及诊断取舍；硫化物部分直接相关。 窗口明确失败模式和材料类差异，足够候选映射沉积/界面失效；丢失Li-electrolyte界面背景、策略与诊断范围。 理由错误：window已明确dendrite penetration、decomposition、void、mechanical failure，与failure节点直接有关；要求必须新增任务才识别关联过严。|
|9 Interfaces in Sulfide Solid Electrolyte-Based All-Solid-State Lithium Batteries: Characterization, Mechanism and Strategy|unclear / 无映射 → **unknown**|题名是硫化物全固态电池界面表征/机制/策略；无摘要，负极/正极范围和证据未知。 标题截断，无摘要。|
|10 Lithium–sulfur cells with a sulfide solid electrolyte/polysulfide cathode interface|unclear / 无映射 → **unknown**|硫化物固态电解质/多硫化物正极的液-固界面与charge transfer；不是固定锂金属负极界面。 窗口保留polysulfide cathode及liquid-solid，足以辨别对象；不得以出现lithium/sulfide归负极失效。|
|11 Metal Sulfide Artificial Solid-Electrolyte Interface for Improved Lithium Anode Stability|unclear / 无映射 → **unknown**|金属硫化物/LMS人工SEI涂覆锂负极，SEM/XRD/XPS/EIS及对称电池；人工层是硫化物不等于电解质也是硫化物，摘要未明确电解质类别。 窗口只见涂层和Li metal；须保留electrolyte类别未知，不能默认目标材料体系。|
|12 New Types of Binder for Ceramic Solid Electrolyte Films: Sulfide Electrolyte, Lithium Metal, Interfaces and Cyclability|unclear / 无映射 → **unknown**|会议摘要研究sulfide film binder与Li接口、枝晶/裂纹和pouch cell压力条件700cycles；相关但摘要级证据、条件不可扩展。 窗口截在dendrite，丢失binder开发、压力、pouch cell及循环条件；不能判断堆压/工艺贡献。|
|13 Ni-Rich Layered Oxide Cathodes/Sulfide Electrolyte Interface in Solid-State Lithium Battery|unclear / 无映射 → **unknown**|Ni-rich layered oxide正极/硫化物电解质综述；不是锂金属负极界面机制。 完整可见标题已经指明Cathodes，模型不必等抽象学习动词才识别对象。|
|14 Simultaneously in-situ fabrication of lithium fluoride and sulfide enriched artificial solid electrolyte interface facilitates high stable lithium metal anode|unclear / 无映射 → **unknown**|题名是LiF及sulfide-rich人工SEI；没有说明电解质是硫化物，缺摘要，不能并入目标材料体系。 标题截断，无摘要。|
|15 Stable Interface between Sulfide Solid Electrolyte and Room-Temperature Liquid Lithium Anode|unclear / 无映射 → **unknown**|ether-based室温液态锂负极与sulfide保护层，1000h稳定solid-liquid界面；这不是所要求固态锂金属界面体系。 窗口明确room-temperature liquid lithium和ether-based；初学理由说属于锂金属界面节点忽略对象区别。可作显式相邻比较，不能直接覆盖。|
|16 Study of the Cathode/Electrolyte Interface in an All-Sulfide-Solid-State Battery Using Lithium-Rich Transition Metal Sulfide|unclear / 无映射 → **unknown**|cell有Li金属负极，但研究的是Li1.2Ti0.8S2正极/argyrodite接口XPS及20cycles；不能因为整电池含Li metal就把研究对象换成负极。 窗口同时给cathode、Li metal anode和positive electrode接口；应以实际被研究的positive接口为对象。|
|17 Sulfide-Based Solid-State Lithium-Sulfur Batteries: An in-Depth Study of the Li-Electrolyte Interface|unclear / 无映射 → **unknown**|Li6PS5Cl/Li7P3S11与Li稳定性比较，EIS/XPS/ToF-SIMS及GCIB深度层析揭示interphase分层；目标最直接的表征/稳定性候选。 窗口明确compare、assess stability against lithium、characterize interphase，可作候选归characterization；丢失方法、层序和结果，不应宣称无任务。|
|18 Tailoring the Interface between Sulfur and Sulfide Solid Electrolyte for High-Areal-Capacity All-Solid-State Lithium–Sulfur Batteries|unclear / 无映射 → **unknown**|S8硫正极与LPSCl间多硫化物中间物改善wettability/ionic contact，5.1mAh/cm2和250cycles；不是Li金属负极反应。 标题及S8窗口可识别硫正极；不要把泛界面改性直接归锂金属负极节点。|
|19 Thin, flexible sulfide-based electrolyte film and its interface engineering for high performance solid-state lithium metal batteries|unclear / 无映射 → **unknown**|题名为薄柔性硫化物膜及Li金属电池interface engineering；没有摘要，不能核层设计/实验类型。 标题截断，无摘要。|

前置核查：interface→failure应区分化学分解、机械接触与沉积；化学反应不是每种机械失效的必要学习前置。transport可作初学背景，不应以topic边强证因果必需。 高级persona声明已熟悉基础，原graph仍把基础节点active/foundation；应把已知背景和新增研究能力区分。输入未提供完整prompt，不能断言已知背景没有发送给模型。

持久化方向：0；无方向不等于已证明不存在有用探索。

### medicine-growth-v0-r1 — failed

目标：理解NSCLC抗PD1/PDL1治疗的原发和获得性耐药机制，并区分基础机制与临床研究证据。 已有基础：了解分子肿瘤学和基本统计，尚未系统学习肿瘤免疫。

论文计数：{'passed': 0, 'failed': 2, 'unknown': 18, 'not_evaluated': 0}；方向计数：{'passed': 0, 'failed': 0, 'unknown': 0, 'not_evaluated': 0}。有内容/映射失败，不能判该完整案例科学正确。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 234P Plasma cell free DNA hydroxymethylation profiling reveals anti-PD1 treatment response and resistance biology in non-small cell lung cancer|unclear / 无映射 → **unknown**|会议题名有NSCLC、anti-PD1 response/resistance与cfDNA 5hmC，但无摘要，样本和设计未知。 标题截断，无摘要。|
|1 Abstract 3660: Plasma cell free DNA hydroxymethylation profiling reveals anti-PD1 treatment response and resistance biology in non-small cell lung cancer|unclear / 无映射 → **unknown**|31 NSCLC患者151纵向血样，cfDNA 5hmC与RECIST应答相关；是观察性biomarker/pathway关联，不是耐药因果验证或已验证临床预测工具。 窗口抽到作者名单/引用题名，丢失31/151、RECIST、IFN/EMT与设计；不是原来源无摘要。|
|2 Abstract 6527: Ginseng polysaccharides circumvent acquired resistance to anti-pd1 immunotherapy in patients with non-small cell lung cancer|unclear / 无映射 → **unknown**|GP口服与继续PD1药物的获得性耐药NSCLC病例系列，5例再应答/ORR50%，无对照、会议初步数据；适合分析设计局限，不证明疗效或建议用药。 窗口仅trial目的与入组条件，丢失case series、5例/50%、结果及无对照；不能说已克服耐药。|
|3 Anti-PD1/PD-L1 Immunotherapy for Non-Small Cell Lung Cancer with Actionable Oncogenic Driver Mutations|unclear / 无映射 → **unknown**|oncogenic EGFR/ALK/BRAF/MET驱动突变与TME、PD1抵抗的综述，兼有临床数据；直接匹配内在机制-微环境交叉。 窗口丢失驱动基因和综述设计，仍有TME/抗PD1疗效；不能从短窗判缺少任何耐药联系。|
|4 CD155 expression impairs anti-PD1 therapy response in non-small cell lung cancer|unclear / 无映射 → **unknown**|CD155/TIGIT与antiPD1应答的回顾性IHC观察研究，CD155阳性ORR/PFS关联；来源标题impairs并不能把关联升级成机制因果或联合靶向疗效。 窗口保留研究问题，丢失observational/retrospective、IHC、ORR/PFS及TIGIT无关联；covered基础免疫轴掩盖证据任务。|
|5 Cancer cell-derived exosomal circUSP7 induces CD8+ T cell dysfunction and anti-PD1 resistance by regulating the miR-934/SHP2 axis in NSCLC|unclear / 无映射 → **unknown**|NSCLC exosomal circUSP7→miR-934/SHP2→CD8功能抑制，实验机制与回顾性临床关联混合；不是基础PD1轴本身，也不是临床治疗效果验证。 窗口保留SHP2/miR及may promote resistance，题名含CD8 dysfunction；能够候选归微环境/证据，不能把may与clinical association变成确认疗效。|
|6 Circular RNA CELF1 drives immunosuppression and anti-PD1 therapy resistance in non-small cell lung cancer via the miR-491-5p/EGFR axis|unclear / 无映射 → **unknown**|circCELF1-miR491-EGFR的NSCLC细胞/鼠机制，患者组织相关；摘要未详述antiPD1耐药实验，治疗特异性证据强度未知。 窗口与标题均提示immunosuppression/antiPD1 resistance，但缺模型与实验；说非PD1轴不等于与目标免疫耐药无关。 理由错误：circRNA-EGFR可通过免疫抑制影响antiPD1抵抗；可见标题有antiPD1 resistance，不在PD1通路本体不等于与耐药目标无关。|
|7 Circulating Low Density Neutrophils Are Associated with Resistance to First Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|LDN前瞻监测NSCLC一线PD1单药及CT+IT队列、ex vivo机制；基线LDN关联原发耐药与HGF/cMET免疫抑制，非随机组合疗效证明。 窗口只有一线ICI背景与机制未明，丢失LDN、队列、ex vivo和原发耐药结果；标题也被裁掉LDN对象。|
|8 Circulating Low Density Neutrophils Are Associated with Resistance to First-Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|LDN研究的preprint版本，前瞻队列/蛋白组/ex vivo；与上一出版版本重叠，不能当独立样本/复现。 窗口也是治疗背景，丢失关键LDN对象和设计；未知不足不能计推荐有效。|
|9 Circulating Low Density Neutrophils are Associated with Resistance to First-Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|第三LDN版本只有题名；无摘要，不能用另一个版本自动补全模型实际所见。 标题裁掉LDN对象，无摘要；版本相同主题不等于独立证据。|
|10 Clinical and molecular features of acquired resistance to immunotherapy in non-small cell lung cancer|unclear / 无映射 → **unknown**|1201患者PD(L)1获得性耐药及IFN/antigen-presentation改变，含多鼠模型/in vitro IFNγ机制；临床和模型须分层，是固定高级目标核心候选。 窗口只取研究动机和1201患者，丢失IFN、antigen-presentation和模型交叉验证；完整来源有具体机制，不能把短窗未知写成来源没有。|
|11 Dual inhibition of IDO1/TDO2 enhances anti-tumor immunity in platinum-resistant non-small cell lung cancer|unclear / 无映射 → **unknown**|cisplatin/platinum-resistant NSCLC代谢IDO1/TDO2与KYN、co-culture/鼠模型及antiPD1组合；铂耐药不是PD1耐药，作免疫抑制相邻机制需明确界限。 窗口含NK/CD8、Treg/MDSC及AT-1074（原文如此），丢失鼠、platinum-selected定义与组合方案；不能直接替换耐药治疗对象。|
|12 High-dose ascorbic acid synergizes with anti-PD1 therapy in non-small cell lung cancer in vitro and in vivo models|covered / PD1/PDL1免疫轴 → **failed**|高剂量ascorbic acid+antiPD1在H460/CD8共培养和LLC1小鼠增敏/免疫蛋白组；未显示经确立原发/获得性PD1耐药模型，也不是患者治疗效果。 标题被截断为某acid，截掉in vitro/in vivo models，窗口是ICI临床背景；模型证据类型unknown未保住疾病治疗/实验类型。 理由错误：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。高剂量ascorbic acid+antiPD1在H460/CD8共培养和LLC1小鼠增敏/免疫蛋白组；未显示经确立原发/获得性PD1耐药模型，也不是患者治疗效果。 标题被截断为某acid，截掉in vitro/in vivo models，窗口是ICI临床背景；模型证据类型unknown未保住疾病治疗/实验类型。 判失败：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。高剂量ascorbic acid+antiPD1在H460/CD8共培养和LLC1小鼠增敏/免疫蛋白组；未显示经确立原发/获得性PD1耐药模型，也不是患者治疗效果。 标题被截断为某acid，截掉in vitro/in vivo models，窗口是ICI临床背景；模型证据类型unknown未保住疾病治疗/实验类型。|
|13 Non-small-cell lung cancer|unclear / 无映射 → **unknown**|仅疾病名，无摘要；不能确认PD1耐药机制或文献类型。 无摘要，题名未截断；某次理由称题名截断不符合输入标记。|
|14 P2.05-17 A Novel Autoantibodies Panel Predicted the Prognosis of Advanced Non-Small Cell Lung Cancer Receiving Anti-PD1 Combined With Chemotherapy|unclear / 无映射 → **unknown**|autoantibodies panel/PD1+chemo/prognosis的会议题名，缺摘要；与机制目标是否相关未知，不能把预后当耐药因果。 标题截断，缺摘要。|
|15 Resistance to KRASG12C Inhibitors in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|KRASG12C inhibitor resistance是sotorasib/adagrasib靶向治疗原发/继发耐药，非PD1/PDL1免疫耐药；不能因NSCLC和resistance共现泛化。 完整可见title足以辨治疗对象；现有拒绝直接归免疫节点的理由边界合理，最终仍是unclear。|
|16 Sex-specific cytokine signatures as predictors of anti-PD1 therapy response in non-small cell lung cancer|covered / PD1/PDL1免疫轴 → **failed**|24血浆cytokine/chemokine与response/PFS/OS的性别分层相关和聚类；用于观察性证据/biomarker局限比较，不是PD1基础通路机制。 窗口可见patient plasma采集前/中及profiling，但裁掉sex-specific、correlation/results；c1 foundation错配，应证据评估/微环境候选。 理由错误：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。24血浆cytokine/chemokine与response/PFS/OS的性别分层相关和聚类；用于观察性证据/biomarker局限比较，不是PD1基础通路机制。 窗口可见patient plasma采集前/中及profiling，但裁掉sex-specific、correlation/results；c1 foundation错配，应证据评估/微环境候选。 判失败：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。24血浆cytokine/chemokine与response/PFS/OS的性别分层相关和聚类；用于观察性证据/biomarker局限比较，不是PD1基础通路机制。 窗口可见patient plasma采集前/中及profiling，但裁掉sex-specific、correlation/results；c1 foundation错配，应证据评估/微环境候选。|
|17 Spatial transcriptomics of macrophage infiltration in non-small cell lung cancer reveals determinants of sensitivity and resistance to anti-PD1/PD-L1 antibodies|unclear / 无映射 → **unknown**|TAM IHC152患者、16空间转录组及三独立数据集，CD163关联PFS/OS；CSF1R在responders高且可能非适当靶点，不能由TAM关联推出阻断疗效。 窗口保留TAM/ICB resistance及患者调查目的，丢失样本、关联设计、CSF1R反直觉结果；与目标相关但强度无法从窗口核。|
|18 The Applications of PD1 Monoclonal Antibody in Non-small Cell Lung Cancer|unclear / 无映射 → **unknown**|泛PD1应用综述含机制/疗效/不良事件/组合，但没有具体耐药路径和设计细节；初学可背景，高级价值未证实。其将Atezolizumab纳入PD1 mAb列举有靶点分类疑点，本审不外查。 窗口仅PD1/PDL1恢复T细胞和drug resistance背景；没有足够具体机制，不宜判新增治疗方案。|
|19 The role of the transcription factor Blimp-1 in T cells in anti-PD1 immunotherapy in non-small cell lung cancer 2258857|unclear / 无映射 → **unknown**|患者组织/PBMC观察与Lck T细胞Blimp1缺失NSCLC鼠+PD1阻断，Treg/T-effector机制；这是免疫逃逸机制候选，不等于患者疗效已证实。 窗口明确murine antiPD1与patient Blimp1表达，丢失缺失实验、Treg与效应细胞结果；任务潜相关，不该因为非核心PD1轴排除免疫耐药。|

前置核查：presentation→microenvironment不是普遍必需前置：内在抗原呈递/IFN与外在TME机制可并行分支；共现和生物相互作用不能建立必学顺序。

持久化方向：0；无方向不等于已证明不存在有用探索。

### medicine-growth-v0-r2 — failed

目标：理解NSCLC抗PD1/PDL1治疗的原发和获得性耐药机制，并区分基础机制与临床研究证据。 已有基础：了解分子肿瘤学和基本统计，尚未系统学习肿瘤免疫。

论文计数：{'passed': 0, 'failed': 2, 'unknown': 18, 'not_evaluated': 0}；方向计数：{'passed': 0, 'failed': 0, 'unknown': 0, 'not_evaluated': 0}。有内容/映射失败，不能判该完整案例科学正确。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 234P Plasma cell free DNA hydroxymethylation profiling reveals anti-PD1 treatment response and resistance biology in non-small cell lung cancer|unclear / 无映射 → **unknown**|会议题名有NSCLC、anti-PD1 response/resistance与cfDNA 5hmC，但无摘要，样本和设计未知。 标题截断，无摘要。|
|1 Abstract 3660: Plasma cell free DNA hydroxymethylation profiling reveals anti-PD1 treatment response and resistance biology in non-small cell lung cancer|unclear / 无映射 → **unknown**|31 NSCLC患者151纵向血样，cfDNA 5hmC与RECIST应答相关；是观察性biomarker/pathway关联，不是耐药因果验证或已验证临床预测工具。 窗口抽到作者名单/引用题名，丢失31/151、RECIST、IFN/EMT与设计；不是原来源无摘要。|
|2 Abstract 6527: Ginseng polysaccharides circumvent acquired resistance to anti-pd1 immunotherapy in patients with non-small cell lung cancer|unclear / 无映射 → **unknown**|GP口服与继续PD1药物的获得性耐药NSCLC病例系列，5例再应答/ORR50%，无对照、会议初步数据；适合分析设计局限，不证明疗效或建议用药。 窗口仅trial目的与入组条件，丢失case series、5例/50%、结果及无对照；不能说已克服耐药。|
|3 Anti-PD1/PD-L1 Immunotherapy for Non-Small Cell Lung Cancer with Actionable Oncogenic Driver Mutations|unclear / 无映射 → **unknown**|oncogenic EGFR/ALK/BRAF/MET驱动突变与TME、PD1抵抗的综述，兼有临床数据；直接匹配内在机制-微环境交叉。 窗口丢失驱动基因和综述设计，仍有TME/抗PD1疗效；不能从短窗判缺少任何耐药联系。|
|4 CD155 expression impairs anti-PD1 therapy response in non-small cell lung cancer|unclear / 无映射 → **unknown**|CD155/TIGIT与antiPD1应答的回顾性IHC观察研究，CD155阳性ORR/PFS关联；来源标题impairs并不能把关联升级成机制因果或联合靶向疗效。 窗口保留研究问题，丢失observational/retrospective、IHC、ORR/PFS及TIGIT无关联；covered基础免疫轴掩盖证据任务。|
|5 Cancer cell-derived exosomal circUSP7 induces CD8+ T cell dysfunction and anti-PD1 resistance by regulating the miR-934/SHP2 axis in NSCLC|unclear / 无映射 → **unknown**|NSCLC exosomal circUSP7→miR-934/SHP2→CD8功能抑制，实验机制与回顾性临床关联混合；不是基础PD1轴本身，也不是临床治疗效果验证。 窗口保留SHP2/miR及may promote resistance，题名含CD8 dysfunction；能够候选归微环境/证据，不能把may与clinical association变成确认疗效。|
|6 Circular RNA CELF1 drives immunosuppression and anti-PD1 therapy resistance in non-small cell lung cancer via the miR-491-5p/EGFR axis|unclear / 无映射 → **unknown**|circCELF1-miR491-EGFR的NSCLC细胞/鼠机制，患者组织相关；摘要未详述antiPD1耐药实验，治疗特异性证据强度未知。 窗口与标题均提示immunosuppression/antiPD1 resistance，但缺模型与实验；说非PD1轴不等于与目标免疫耐药无关。 理由错误：circRNA-EGFR可通过免疫抑制影响antiPD1抵抗；可见标题有antiPD1 resistance，不在PD1通路本体不等于与耐药目标无关。|
|7 Circulating Low Density Neutrophils Are Associated with Resistance to First Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|LDN前瞻监测NSCLC一线PD1单药及CT+IT队列、ex vivo机制；基线LDN关联原发耐药与HGF/cMET免疫抑制，非随机组合疗效证明。 窗口只有一线ICI背景与机制未明，丢失LDN、队列、ex vivo和原发耐药结果；标题也被裁掉LDN对象。|
|8 Circulating Low Density Neutrophils Are Associated with Resistance to First-Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|LDN研究的preprint版本，前瞻队列/蛋白组/ex vivo；与上一出版版本重叠，不能当独立样本/复现。 窗口也是治疗背景，丢失关键LDN对象和设计；未知不足不能计推荐有效。|
|9 Circulating Low Density Neutrophils are Associated with Resistance to First-Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|第三LDN版本只有题名；无摘要，不能用另一个版本自动补全模型实际所见。 标题裁掉LDN对象，无摘要；版本相同主题不等于独立证据。|
|10 Clinical and molecular features of acquired resistance to immunotherapy in non-small cell lung cancer|unclear / 无映射 → **unknown**|1201患者PD(L)1获得性耐药及IFN/antigen-presentation改变，含多鼠模型/in vitro IFNγ机制；临床和模型须分层，是固定高级目标核心候选。 窗口只取研究动机和1201患者，丢失IFN、antigen-presentation和模型交叉验证；完整来源有具体机制，不能把短窗未知写成来源没有。|
|11 Dual inhibition of IDO1/TDO2 enhances anti-tumor immunity in platinum-resistant non-small cell lung cancer|unclear / 无映射 → **unknown**|cisplatin/platinum-resistant NSCLC代谢IDO1/TDO2与KYN、co-culture/鼠模型及antiPD1组合；铂耐药不是PD1耐药，作免疫抑制相邻机制需明确界限。 窗口含NK/CD8、Treg/MDSC及AT-1074（原文如此），丢失鼠、platinum-selected定义与组合方案；不能直接替换耐药治疗对象。|
|12 High-dose ascorbic acid synergizes with anti-PD1 therapy in non-small cell lung cancer in vitro and in vivo models|covered / PD1/PDL1免疫轴 → **failed**|高剂量ascorbic acid+antiPD1在H460/CD8共培养和LLC1小鼠增敏/免疫蛋白组；未显示经确立原发/获得性PD1耐药模型，也不是患者治疗效果。 标题被截断为某acid，截掉in vitro/in vivo models，窗口是ICI临床背景；模型证据类型unknown未保住疾病治疗/实验类型。 理由错误：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。高剂量ascorbic acid+antiPD1在H460/CD8共培养和LLC1小鼠增敏/免疫蛋白组；未显示经确立原发/获得性PD1耐药模型，也不是患者治疗效果。 标题被截断为某acid，截掉in vitro/in vivo models，窗口是ICI临床背景；模型证据类型unknown未保住疾病治疗/实验类型。 判失败：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。高剂量ascorbic acid+antiPD1在H460/CD8共培养和LLC1小鼠增敏/免疫蛋白组；未显示经确立原发/获得性PD1耐药模型，也不是患者治疗效果。 标题被截断为某acid，截掉in vitro/in vivo models，窗口是ICI临床背景；模型证据类型unknown未保住疾病治疗/实验类型。|
|13 Non-small-cell lung cancer|unclear / 无映射 → **unknown**|仅疾病名，无摘要；不能确认PD1耐药机制或文献类型。 无摘要，题名未截断；某次理由称题名截断不符合输入标记。|
|14 P2.05-17 A Novel Autoantibodies Panel Predicted the Prognosis of Advanced Non-Small Cell Lung Cancer Receiving Anti-PD1 Combined With Chemotherapy|unclear / 无映射 → **unknown**|autoantibodies panel/PD1+chemo/prognosis的会议题名，缺摘要；与机制目标是否相关未知，不能把预后当耐药因果。 标题截断，缺摘要。|
|15 Resistance to KRASG12C Inhibitors in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|KRASG12C inhibitor resistance是sotorasib/adagrasib靶向治疗原发/继发耐药，非PD1/PDL1免疫耐药；不能因NSCLC和resistance共现泛化。 完整可见title足以辨治疗对象；现有拒绝直接归免疫节点的理由边界合理，最终仍是unclear。|
|16 Sex-specific cytokine signatures as predictors of anti-PD1 therapy response in non-small cell lung cancer|covered / PD1/PDL1免疫轴 → **failed**|24血浆cytokine/chemokine与response/PFS/OS的性别分层相关和聚类；用于观察性证据/biomarker局限比较，不是PD1基础通路机制。 窗口可见patient plasma采集前/中及profiling，但裁掉sex-specific、correlation/results；c1 foundation错配，应证据评估/微环境候选。 理由错误：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。24血浆cytokine/chemokine与response/PFS/OS的性别分层相关和聚类；用于观察性证据/biomarker局限比较，不是PD1基础通路机制。 窗口可见patient plasma采集前/中及profiling，但裁掉sex-specific、correlation/results；c1 foundation错配，应证据评估/微环境候选。 判失败：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。24血浆cytokine/chemokine与response/PFS/OS的性别分层相关和聚类；用于观察性证据/biomarker局限比较，不是PD1基础通路机制。 窗口可见patient plasma采集前/中及profiling，但裁掉sex-specific、correlation/results；c1 foundation错配，应证据评估/微环境候选。|
|17 Spatial transcriptomics of macrophage infiltration in non-small cell lung cancer reveals determinants of sensitivity and resistance to anti-PD1/PD-L1 antibodies|unclear / 无映射 → **unknown**|TAM IHC152患者、16空间转录组及三独立数据集，CD163关联PFS/OS；CSF1R在responders高且可能非适当靶点，不能由TAM关联推出阻断疗效。 窗口保留TAM/ICB resistance及患者调查目的，丢失样本、关联设计、CSF1R反直觉结果；与目标相关但强度无法从窗口核。|
|18 The Applications of PD1 Monoclonal Antibody in Non-small Cell Lung Cancer|unclear / 无映射 → **unknown**|泛PD1应用综述含机制/疗效/不良事件/组合，但没有具体耐药路径和设计细节；初学可背景，高级价值未证实。其将Atezolizumab纳入PD1 mAb列举有靶点分类疑点，本审不外查。 窗口仅PD1/PDL1恢复T细胞和drug resistance背景；没有足够具体机制，不宜判新增治疗方案。|
|19 The role of the transcription factor Blimp-1 in T cells in anti-PD1 immunotherapy in non-small cell lung cancer 2258857|unclear / 无映射 → **unknown**|患者组织/PBMC观察与Lck T细胞Blimp1缺失NSCLC鼠+PD1阻断，Treg/T-effector机制；这是免疫逃逸机制候选，不等于患者疗效已证实。 窗口明确murine antiPD1与patient Blimp1表达，丢失缺失实验、Treg与效应细胞结果；任务潜相关，不该因为非核心PD1轴排除免疫耐药。|

前置核查：presentation→microenvironment不是普遍必需前置：内在抗原呈递/IFN与外在TME机制可并行分支；共现和生物相互作用不能建立必学顺序。

持久化方向：0；无方向不等于已证明不存在有用探索。

### medicine-growth-v0-r3 — failed

目标：理解NSCLC抗PD1/PDL1治疗的原发和获得性耐药机制，并区分基础机制与临床研究证据。 已有基础：了解分子肿瘤学和基本统计，尚未系统学习肿瘤免疫。

论文计数：{'passed': 0, 'failed': 3, 'unknown': 17, 'not_evaluated': 0}；方向计数：{'passed': 0, 'failed': 0, 'unknown': 0, 'not_evaluated': 0}。有内容/映射失败，不能判该完整案例科学正确。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 234P Plasma cell free DNA hydroxymethylation profiling reveals anti-PD1 treatment response and resistance biology in non-small cell lung cancer|unclear / 无映射 → **unknown**|会议题名有NSCLC、anti-PD1 response/resistance与cfDNA 5hmC，但无摘要，样本和设计未知。 标题截断，无摘要。|
|1 Abstract 3660: Plasma cell free DNA hydroxymethylation profiling reveals anti-PD1 treatment response and resistance biology in non-small cell lung cancer|unclear / 无映射 → **unknown**|31 NSCLC患者151纵向血样，cfDNA 5hmC与RECIST应答相关；是观察性biomarker/pathway关联，不是耐药因果验证或已验证临床预测工具。 窗口抽到作者名单/引用题名，丢失31/151、RECIST、IFN/EMT与设计；不是原来源无摘要。|
|2 Abstract 6527: Ginseng polysaccharides circumvent acquired resistance to anti-pd1 immunotherapy in patients with non-small cell lung cancer|unclear / 无映射 → **unknown**|GP口服与继续PD1药物的获得性耐药NSCLC病例系列，5例再应答/ORR50%，无对照、会议初步数据；适合分析设计局限，不证明疗效或建议用药。 窗口仅trial目的与入组条件，丢失case series、5例/50%、结果及无对照；不能说已克服耐药。|
|3 Anti-PD1/PD-L1 Immunotherapy for Non-Small Cell Lung Cancer with Actionable Oncogenic Driver Mutations|unclear / 无映射 → **unknown**|oncogenic EGFR/ALK/BRAF/MET驱动突变与TME、PD1抵抗的综述，兼有临床数据；直接匹配内在机制-微环境交叉。 窗口丢失驱动基因和综述设计，仍有TME/抗PD1疗效；不能从短窗判缺少任何耐药联系。|
|4 CD155 expression impairs anti-PD1 therapy response in non-small cell lung cancer|unclear / 无映射 → **unknown**|CD155/TIGIT与antiPD1应答的回顾性IHC观察研究，CD155阳性ORR/PFS关联；来源标题impairs并不能把关联升级成机制因果或联合靶向疗效。 窗口保留研究问题，丢失observational/retrospective、IHC、ORR/PFS及TIGIT无关联；covered基础免疫轴掩盖证据任务。|
|5 Cancer cell-derived exosomal circUSP7 induces CD8+ T cell dysfunction and anti-PD1 resistance by regulating the miR-934/SHP2 axis in NSCLC|covered / PD1/PDL1免疫轴 → **failed**|NSCLC exosomal circUSP7→miR-934/SHP2→CD8功能抑制，实验机制与回顾性临床关联混合；不是基础PD1轴本身，也不是临床治疗效果验证。 窗口保留SHP2/miR及may promote resistance，题名含CD8 dysfunction；能够候选归微环境/证据，不能把may与clinical association变成确认疗效。 理由错误：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。NSCLC exosomal circUSP7→miR-934/SHP2→CD8功能抑制，实验机制与回顾性临床关联混合；不是基础PD1轴本身，也不是临床治疗效果验证。 窗口保留SHP2/miR及may promote resistance，题名含CD8 dysfunction；能够候选归微环境/证据，不能把may与clinical association变成确认疗效。 判失败：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。NSCLC exosomal circUSP7→miR-934/SHP2→CD8功能抑制，实验机制与回顾性临床关联混合；不是基础PD1轴本身，也不是临床治疗效果验证。 窗口保留SHP2/miR及may promote resistance，题名含CD8 dysfunction；能够候选归微环境/证据，不能把may与clinical association变成确认疗效。|
|6 Circular RNA CELF1 drives immunosuppression and anti-PD1 therapy resistance in non-small cell lung cancer via the miR-491-5p/EGFR axis|unclear / 无映射 → **unknown**|circCELF1-miR491-EGFR的NSCLC细胞/鼠机制，患者组织相关；摘要未详述antiPD1耐药实验，治疗特异性证据强度未知。 窗口与标题均提示immunosuppression/antiPD1 resistance，但缺模型与实验；说非PD1轴不等于与目标免疫耐药无关。 理由错误：circRNA-EGFR可通过免疫抑制影响antiPD1抵抗；可见标题有antiPD1 resistance，不在PD1通路本体不等于与耐药目标无关。|
|7 Circulating Low Density Neutrophils Are Associated with Resistance to First Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|LDN前瞻监测NSCLC一线PD1单药及CT+IT队列、ex vivo机制；基线LDN关联原发耐药与HGF/cMET免疫抑制，非随机组合疗效证明。 窗口只有一线ICI背景与机制未明，丢失LDN、队列、ex vivo和原发耐药结果；标题也被裁掉LDN对象。|
|8 Circulating Low Density Neutrophils Are Associated with Resistance to First-Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|LDN研究的preprint版本，前瞻队列/蛋白组/ex vivo；与上一出版版本重叠，不能当独立样本/复现。 窗口也是治疗背景，丢失关键LDN对象和设计；未知不足不能计推荐有效。|
|9 Circulating Low Density Neutrophils are Associated with Resistance to First-Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|第三LDN版本只有题名；无摘要，不能用另一个版本自动补全模型实际所见。 标题裁掉LDN对象，无摘要；版本相同主题不等于独立证据。|
|10 Clinical and molecular features of acquired resistance to immunotherapy in non-small cell lung cancer|unclear / 无映射 → **unknown**|1201患者PD(L)1获得性耐药及IFN/antigen-presentation改变，含多鼠模型/in vitro IFNγ机制；临床和模型须分层，是固定高级目标核心候选。 窗口只取研究动机和1201患者，丢失IFN、antigen-presentation和模型交叉验证；完整来源有具体机制，不能把短窗未知写成来源没有。|
|11 Dual inhibition of IDO1/TDO2 enhances anti-tumor immunity in platinum-resistant non-small cell lung cancer|unclear / 无映射 → **unknown**|cisplatin/platinum-resistant NSCLC代谢IDO1/TDO2与KYN、co-culture/鼠模型及antiPD1组合；铂耐药不是PD1耐药，作免疫抑制相邻机制需明确界限。 窗口含NK/CD8、Treg/MDSC及AT-1074（原文如此），丢失鼠、platinum-selected定义与组合方案；不能直接替换耐药治疗对象。|
|12 High-dose ascorbic acid synergizes with anti-PD1 therapy in non-small cell lung cancer in vitro and in vivo models|covered / PD1/PDL1免疫轴 → **failed**|高剂量ascorbic acid+antiPD1在H460/CD8共培养和LLC1小鼠增敏/免疫蛋白组；未显示经确立原发/获得性PD1耐药模型，也不是患者治疗效果。 标题被截断为某acid，截掉in vitro/in vivo models，窗口是ICI临床背景；模型证据类型unknown未保住疾病治疗/实验类型。 理由错误：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。高剂量ascorbic acid+antiPD1在H460/CD8共培养和LLC1小鼠增敏/免疫蛋白组；未显示经确立原发/获得性PD1耐药模型，也不是患者治疗效果。 标题被截断为某acid，截掉in vitro/in vivo models，窗口是ICI临床背景；模型证据类型unknown未保住疾病治疗/实验类型。 判失败：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。高剂量ascorbic acid+antiPD1在H460/CD8共培养和LLC1小鼠增敏/免疫蛋白组；未显示经确立原发/获得性PD1耐药模型，也不是患者治疗效果。 标题被截断为某acid，截掉in vitro/in vivo models，窗口是ICI临床背景；模型证据类型unknown未保住疾病治疗/实验类型。|
|13 Non-small-cell lung cancer|unclear / 无映射 → **unknown**|仅疾病名，无摘要；不能确认PD1耐药机制或文献类型。 无摘要，题名未截断；某次理由称题名截断不符合输入标记。|
|14 P2.05-17 A Novel Autoantibodies Panel Predicted the Prognosis of Advanced Non-Small Cell Lung Cancer Receiving Anti-PD1 Combined With Chemotherapy|unclear / 无映射 → **unknown**|autoantibodies panel/PD1+chemo/prognosis的会议题名，缺摘要；与机制目标是否相关未知，不能把预后当耐药因果。 标题截断，缺摘要。|
|15 Resistance to KRASG12C Inhibitors in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|KRASG12C inhibitor resistance是sotorasib/adagrasib靶向治疗原发/继发耐药，非PD1/PDL1免疫耐药；不能因NSCLC和resistance共现泛化。 完整可见title足以辨治疗对象；现有拒绝直接归免疫节点的理由边界合理，最终仍是unclear。|
|16 Sex-specific cytokine signatures as predictors of anti-PD1 therapy response in non-small cell lung cancer|covered / PD1/PDL1免疫轴 → **failed**|24血浆cytokine/chemokine与response/PFS/OS的性别分层相关和聚类；用于观察性证据/biomarker局限比较，不是PD1基础通路机制。 窗口可见patient plasma采集前/中及profiling，但裁掉sex-specific、correlation/results；c1 foundation错配，应证据评估/微环境候选。 理由错误：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。24血浆cytokine/chemokine与response/PFS/OS的性别分层相关和聚类；用于观察性证据/biomarker局限比较，不是PD1基础通路机制。 窗口可见patient plasma采集前/中及profiling，但裁掉sex-specific、correlation/results；c1 foundation错配，应证据评估/微环境候选。 判失败：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。24血浆cytokine/chemokine与response/PFS/OS的性别分层相关和聚类；用于观察性证据/biomarker局限比较，不是PD1基础通路机制。 窗口可见patient plasma采集前/中及profiling，但裁掉sex-specific、correlation/results；c1 foundation错配，应证据评估/微环境候选。|
|17 Spatial transcriptomics of macrophage infiltration in non-small cell lung cancer reveals determinants of sensitivity and resistance to anti-PD1/PD-L1 antibodies|unclear / 无映射 → **unknown**|TAM IHC152患者、16空间转录组及三独立数据集，CD163关联PFS/OS；CSF1R在responders高且可能非适当靶点，不能由TAM关联推出阻断疗效。 窗口保留TAM/ICB resistance及患者调查目的，丢失样本、关联设计、CSF1R反直觉结果；与目标相关但强度无法从窗口核。|
|18 The Applications of PD1 Monoclonal Antibody in Non-small Cell Lung Cancer|unclear / 无映射 → **unknown**|泛PD1应用综述含机制/疗效/不良事件/组合，但没有具体耐药路径和设计细节；初学可背景，高级价值未证实。其将Atezolizumab纳入PD1 mAb列举有靶点分类疑点，本审不外查。 窗口仅PD1/PDL1恢复T细胞和drug resistance背景；没有足够具体机制，不宜判新增治疗方案。|
|19 The role of the transcription factor Blimp-1 in T cells in anti-PD1 immunotherapy in non-small cell lung cancer 2258857|unclear / 无映射 → **unknown**|患者组织/PBMC观察与Lck T细胞Blimp1缺失NSCLC鼠+PD1阻断，Treg/T-effector机制；这是免疫逃逸机制候选，不等于患者疗效已证实。 窗口明确murine antiPD1与patient Blimp1表达，丢失缺失实验、Treg与效应细胞结果；任务潜相关，不该因为非核心PD1轴排除免疫耐药。|

前置核查：presentation→microenvironment不是普遍必需前置：内在抗原呈递/IFN与外在TME机制可并行分支；共现和生物相互作用不能建立必学顺序。

持久化方向：0；无方向不等于已证明不存在有用探索。

### medicine-growth-v1-r1 — failed

目标：比较NSCLC抗PD1/PDL1耐药中肿瘤内在机制与微环境机制的证据强度和研究设计局限。 已有基础：熟悉肿瘤免疫、PD1/PDL1通路和临床研究基本设计。

论文计数：{'passed': 0, 'failed': 1, 'unknown': 19, 'not_evaluated': 0}；方向计数：{'passed': 0, 'failed': 0, 'unknown': 0, 'not_evaluated': 0}。有内容/映射失败，不能判该完整案例科学正确。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 234P Plasma cell free DNA hydroxymethylation profiling reveals anti-PD1 treatment response and resistance biology in non-small cell lung cancer|unclear / 无映射 → **unknown**|会议题名有NSCLC、anti-PD1 response/resistance与cfDNA 5hmC，但无摘要，样本和设计未知。 标题截断，无摘要。|
|1 Abstract 3660: Plasma cell free DNA hydroxymethylation profiling reveals anti-PD1 treatment response and resistance biology in non-small cell lung cancer|unclear / 无映射 → **unknown**|31 NSCLC患者151纵向血样，cfDNA 5hmC与RECIST应答相关；是观察性biomarker/pathway关联，不是耐药因果验证或已验证临床预测工具。 窗口抽到作者名单/引用题名，丢失31/151、RECIST、IFN/EMT与设计；不是原来源无摘要。|
|2 Abstract 6527: Ginseng polysaccharides circumvent acquired resistance to anti-pd1 immunotherapy in patients with non-small cell lung cancer|unclear / 无映射 → **unknown**|GP口服与继续PD1药物的获得性耐药NSCLC病例系列，5例再应答/ORR50%，无对照、会议初步数据；适合分析设计局限，不证明疗效或建议用药。 窗口仅trial目的与入组条件，丢失case series、5例/50%、结果及无对照；不能说已克服耐药。|
|3 Anti-PD1/PD-L1 Immunotherapy for Non-Small Cell Lung Cancer with Actionable Oncogenic Driver Mutations|unclear / 无映射 → **unknown**|oncogenic EGFR/ALK/BRAF/MET驱动突变与TME、PD1抵抗的综述，兼有临床数据；直接匹配内在机制-微环境交叉。 窗口丢失驱动基因和综述设计，仍有TME/抗PD1疗效；不能从短窗判缺少任何耐药联系。|
|4 CD155 expression impairs anti-PD1 therapy response in non-small cell lung cancer|covered / PD1/PDL1免疫轴 → **failed**|CD155/TIGIT与antiPD1应答的回顾性IHC观察研究，CD155阳性ORR/PFS关联；来源标题impairs并不能把关联升级成机制因果或联合靶向疗效。 窗口保留研究问题，丢失observational/retrospective、IHC、ORR/PFS及TIGIT无关联；covered基础免疫轴掩盖证据任务。 理由错误：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。CD155/TIGIT与antiPD1应答的回顾性IHC观察研究，CD155阳性ORR/PFS关联；来源标题impairs并不能把关联升级成机制因果或联合靶向疗效。 窗口保留研究问题，丢失observational/retrospective、IHC、ORR/PFS及TIGIT无关联；covered基础免疫轴掩盖证据任务。 判失败：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。CD155/TIGIT与antiPD1应答的回顾性IHC观察研究，CD155阳性ORR/PFS关联；来源标题impairs并不能把关联升级成机制因果或联合靶向疗效。 窗口保留研究问题，丢失observational/retrospective、IHC、ORR/PFS及TIGIT无关联；covered基础免疫轴掩盖证据任务。|
|5 Cancer cell-derived exosomal circUSP7 induces CD8+ T cell dysfunction and anti-PD1 resistance by regulating the miR-934/SHP2 axis in NSCLC|unclear / 无映射 → **unknown**|NSCLC exosomal circUSP7→miR-934/SHP2→CD8功能抑制，实验机制与回顾性临床关联混合；不是基础PD1轴本身，也不是临床治疗效果验证。 窗口保留SHP2/miR及may promote resistance，题名含CD8 dysfunction；能够候选归微环境/证据，不能把may与clinical association变成确认疗效。|
|6 Circular RNA CELF1 drives immunosuppression and anti-PD1 therapy resistance in non-small cell lung cancer via the miR-491-5p/EGFR axis|unclear / 无映射 → **unknown**|circCELF1-miR491-EGFR的NSCLC细胞/鼠机制，患者组织相关；摘要未详述antiPD1耐药实验，治疗特异性证据强度未知。 窗口与标题均提示immunosuppression/antiPD1 resistance，但缺模型与实验；说非PD1轴不等于与目标免疫耐药无关。|
|7 Circulating Low Density Neutrophils Are Associated with Resistance to First Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|LDN前瞻监测NSCLC一线PD1单药及CT+IT队列、ex vivo机制；基线LDN关联原发耐药与HGF/cMET免疫抑制，非随机组合疗效证明。 窗口只有一线ICI背景与机制未明，丢失LDN、队列、ex vivo和原发耐药结果；标题也被裁掉LDN对象。|
|8 Circulating Low Density Neutrophils Are Associated with Resistance to First-Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|LDN研究的preprint版本，前瞻队列/蛋白组/ex vivo；与上一出版版本重叠，不能当独立样本/复现。 窗口也是治疗背景，丢失关键LDN对象和设计；未知不足不能计推荐有效。|
|9 Circulating Low Density Neutrophils are Associated with Resistance to First-Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|第三LDN版本只有题名；无摘要，不能用另一个版本自动补全模型实际所见。 标题裁掉LDN对象，无摘要；版本相同主题不等于独立证据。|
|10 Clinical and molecular features of acquired resistance to immunotherapy in non-small cell lung cancer|unclear / 无映射 → **unknown**|1201患者PD(L)1获得性耐药及IFN/antigen-presentation改变，含多鼠模型/in vitro IFNγ机制；临床和模型须分层，是固定高级目标核心候选。 窗口只取研究动机和1201患者，丢失IFN、antigen-presentation和模型交叉验证；完整来源有具体机制，不能把短窗未知写成来源没有。|
|11 Dual inhibition of IDO1/TDO2 enhances anti-tumor immunity in platinum-resistant non-small cell lung cancer|unclear / 无映射 → **unknown**|cisplatin/platinum-resistant NSCLC代谢IDO1/TDO2与KYN、co-culture/鼠模型及antiPD1组合；铂耐药不是PD1耐药，作免疫抑制相邻机制需明确界限。 窗口含NK/CD8、Treg/MDSC及AT-1074（原文如此），丢失鼠、platinum-selected定义与组合方案；不能直接替换耐药治疗对象。|
|12 High-dose ascorbic acid synergizes with anti-PD1 therapy in non-small cell lung cancer in vitro and in vivo models|unclear / 无映射 → **unknown**|高剂量ascorbic acid+antiPD1在H460/CD8共培养和LLC1小鼠增敏/免疫蛋白组；未显示经确立原发/获得性PD1耐药模型，也不是患者治疗效果。 标题被截断为某acid，截掉in vitro/in vivo models，窗口是ICI临床背景；模型证据类型unknown未保住疾病治疗/实验类型。|
|13 Non-small-cell lung cancer|unclear / 无映射 → **unknown**|仅疾病名，无摘要；不能确认PD1耐药机制或文献类型。 无摘要，题名未截断；某次理由称题名截断不符合输入标记。 理由错误：该title完整且title_truncated=false；无摘要才是信息不足，题名截断理由不实。|
|14 P2.05-17 A Novel Autoantibodies Panel Predicted the Prognosis of Advanced Non-Small Cell Lung Cancer Receiving Anti-PD1 Combined With Chemotherapy|unclear / 无映射 → **unknown**|autoantibodies panel/PD1+chemo/prognosis的会议题名，缺摘要；与机制目标是否相关未知，不能把预后当耐药因果。 标题截断，缺摘要。|
|15 Resistance to KRASG12C Inhibitors in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|KRASG12C inhibitor resistance是sotorasib/adagrasib靶向治疗原发/继发耐药，非PD1/PDL1免疫耐药；不能因NSCLC和resistance共现泛化。 完整可见title足以辨治疗对象；现有拒绝直接归免疫节点的理由边界合理，最终仍是unclear。|
|16 Sex-specific cytokine signatures as predictors of anti-PD1 therapy response in non-small cell lung cancer|unclear / 无映射 → **unknown**|24血浆cytokine/chemokine与response/PFS/OS的性别分层相关和聚类；用于观察性证据/biomarker局限比较，不是PD1基础通路机制。 窗口可见patient plasma采集前/中及profiling，但裁掉sex-specific、correlation/results；c1 foundation错配，应证据评估/微环境候选。|
|17 Spatial transcriptomics of macrophage infiltration in non-small cell lung cancer reveals determinants of sensitivity and resistance to anti-PD1/PD-L1 antibodies|unclear / 无映射 → **unknown**|TAM IHC152患者、16空间转录组及三独立数据集，CD163关联PFS/OS；CSF1R在responders高且可能非适当靶点，不能由TAM关联推出阻断疗效。 窗口保留TAM/ICB resistance及患者调查目的，丢失样本、关联设计、CSF1R反直觉结果；与目标相关但强度无法从窗口核。|
|18 The Applications of PD1 Monoclonal Antibody in Non-small Cell Lung Cancer|unclear / 无映射 → **unknown**|泛PD1应用综述含机制/疗效/不良事件/组合，但没有具体耐药路径和设计细节；初学可背景，高级价值未证实。其将Atezolizumab纳入PD1 mAb列举有靶点分类疑点，本审不外查。 窗口仅PD1/PDL1恢复T细胞和drug resistance背景；没有足够具体机制，不宜判新增治疗方案。|
|19 The role of the transcription factor Blimp-1 in T cells in anti-PD1 immunotherapy in non-small cell lung cancer 2258857|unclear / 无映射 → **unknown**|患者组织/PBMC观察与Lck T细胞Blimp1缺失NSCLC鼠+PD1阻断，Treg/T-effector机制；这是免疫逃逸机制候选，不等于患者疗效已证实。 窗口明确murine antiPD1与patient Blimp1表达，丢失缺失实验、Treg与效应细胞结果；任务潜相关，不该因为非核心PD1轴排除免疫耐药。 理由错误：固定任务不只限PD1轴核心；Blimp1/Treg免疫逃逸可以是机制分支，非核心轴不能直接等价于不相关。|

前置核查：presentation→microenvironment不是普遍必需前置：内在抗原呈递/IFN与外在TME机制可并行分支；共现和生物相互作用不能建立必学顺序。 高级persona声明已熟悉基础，原graph仍把基础节点active/foundation；应把已知背景和新增研究能力区分。输入未提供完整prompt，不能断言已知背景没有发送给模型。

持久化方向：0；无方向不等于已证明不存在有用探索。

### medicine-growth-v1-r2 — failed

目标：比较NSCLC抗PD1/PDL1耐药中肿瘤内在机制与微环境机制的证据强度和研究设计局限。 已有基础：熟悉肿瘤免疫、PD1/PDL1通路和临床研究基本设计。

论文计数：{'passed': 0, 'failed': 1, 'unknown': 19, 'not_evaluated': 0}；方向计数：{'passed': 0, 'failed': 0, 'unknown': 0, 'not_evaluated': 0}。有内容/映射失败，不能判该完整案例科学正确。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 234P Plasma cell free DNA hydroxymethylation profiling reveals anti-PD1 treatment response and resistance biology in non-small cell lung cancer|unclear / 无映射 → **unknown**|会议题名有NSCLC、anti-PD1 response/resistance与cfDNA 5hmC，但无摘要，样本和设计未知。 标题截断，无摘要。|
|1 Abstract 3660: Plasma cell free DNA hydroxymethylation profiling reveals anti-PD1 treatment response and resistance biology in non-small cell lung cancer|unclear / 无映射 → **unknown**|31 NSCLC患者151纵向血样，cfDNA 5hmC与RECIST应答相关；是观察性biomarker/pathway关联，不是耐药因果验证或已验证临床预测工具。 窗口抽到作者名单/引用题名，丢失31/151、RECIST、IFN/EMT与设计；不是原来源无摘要。 理由错误：原来源有完整长摘要，模型收到的是作者/引文尾部，不应描述成原资料无摘要。|
|2 Abstract 6527: Ginseng polysaccharides circumvent acquired resistance to anti-pd1 immunotherapy in patients with non-small cell lung cancer|unclear / 无映射 → **unknown**|GP口服与继续PD1药物的获得性耐药NSCLC病例系列，5例再应答/ORR50%，无对照、会议初步数据；适合分析设计局限，不证明疗效或建议用药。 窗口仅trial目的与入组条件，丢失case series、5例/50%、结果及无对照；不能说已克服耐药。|
|3 Anti-PD1/PD-L1 Immunotherapy for Non-Small Cell Lung Cancer with Actionable Oncogenic Driver Mutations|unclear / 无映射 → **unknown**|oncogenic EGFR/ALK/BRAF/MET驱动突变与TME、PD1抵抗的综述，兼有临床数据；直接匹配内在机制-微环境交叉。 窗口丢失驱动基因和综述设计，仍有TME/抗PD1疗效；不能从短窗判缺少任何耐药联系。|
|4 CD155 expression impairs anti-PD1 therapy response in non-small cell lung cancer|covered / PD1/PDL1免疫轴 → **failed**|CD155/TIGIT与antiPD1应答的回顾性IHC观察研究，CD155阳性ORR/PFS关联；来源标题impairs并不能把关联升级成机制因果或联合靶向疗效。 窗口保留研究问题，丢失observational/retrospective、IHC、ORR/PFS及TIGIT无关联；covered基础免疫轴掩盖证据任务。 理由错误：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。CD155/TIGIT与antiPD1应答的回顾性IHC观察研究，CD155阳性ORR/PFS关联；来源标题impairs并不能把关联升级成机制因果或联合靶向疗效。 窗口保留研究问题，丢失observational/retrospective、IHC、ORR/PFS及TIGIT无关联；covered基础免疫轴掩盖证据任务。 判失败：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。CD155/TIGIT与antiPD1应答的回顾性IHC观察研究，CD155阳性ORR/PFS关联；来源标题impairs并不能把关联升级成机制因果或联合靶向疗效。 窗口保留研究问题，丢失observational/retrospective、IHC、ORR/PFS及TIGIT无关联；covered基础免疫轴掩盖证据任务。|
|5 Cancer cell-derived exosomal circUSP7 induces CD8+ T cell dysfunction and anti-PD1 resistance by regulating the miR-934/SHP2 axis in NSCLC|unclear / 无映射 → **unknown**|NSCLC exosomal circUSP7→miR-934/SHP2→CD8功能抑制，实验机制与回顾性临床关联混合；不是基础PD1轴本身，也不是临床治疗效果验证。 窗口保留SHP2/miR及may promote resistance，题名含CD8 dysfunction；能够候选归微环境/证据，不能把may与clinical association变成确认疗效。|
|6 Circular RNA CELF1 drives immunosuppression and anti-PD1 therapy resistance in non-small cell lung cancer via the miR-491-5p/EGFR axis|unclear / 无映射 → **unknown**|circCELF1-miR491-EGFR的NSCLC细胞/鼠机制，患者组织相关；摘要未详述antiPD1耐药实验，治疗特异性证据强度未知。 窗口与标题均提示immunosuppression/antiPD1 resistance，但缺模型与实验；说非PD1轴不等于与目标免疫耐药无关。 理由错误：circRNA-EGFR可通过免疫抑制影响antiPD1抵抗；可见标题有antiPD1 resistance，不在PD1通路本体不等于与耐药目标无关。|
|7 Circulating Low Density Neutrophils Are Associated with Resistance to First Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|LDN前瞻监测NSCLC一线PD1单药及CT+IT队列、ex vivo机制；基线LDN关联原发耐药与HGF/cMET免疫抑制，非随机组合疗效证明。 窗口只有一线ICI背景与机制未明，丢失LDN、队列、ex vivo和原发耐药结果；标题也被裁掉LDN对象。|
|8 Circulating Low Density Neutrophils Are Associated with Resistance to First-Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|LDN研究的preprint版本，前瞻队列/蛋白组/ex vivo；与上一出版版本重叠，不能当独立样本/复现。 窗口也是治疗背景，丢失关键LDN对象和设计；未知不足不能计推荐有效。|
|9 Circulating Low Density Neutrophils are Associated with Resistance to First-Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|第三LDN版本只有题名；无摘要，不能用另一个版本自动补全模型实际所见。 标题裁掉LDN对象，无摘要；版本相同主题不等于独立证据。|
|10 Clinical and molecular features of acquired resistance to immunotherapy in non-small cell lung cancer|unclear / 无映射 → **unknown**|1201患者PD(L)1获得性耐药及IFN/antigen-presentation改变，含多鼠模型/in vitro IFNγ机制；临床和模型须分层，是固定高级目标核心候选。 窗口只取研究动机和1201患者，丢失IFN、antigen-presentation和模型交叉验证；完整来源有具体机制，不能把短窗未知写成来源没有。|
|11 Dual inhibition of IDO1/TDO2 enhances anti-tumor immunity in platinum-resistant non-small cell lung cancer|unclear / 无映射 → **unknown**|cisplatin/platinum-resistant NSCLC代谢IDO1/TDO2与KYN、co-culture/鼠模型及antiPD1组合；铂耐药不是PD1耐药，作免疫抑制相邻机制需明确界限。 窗口含NK/CD8、Treg/MDSC及AT-1074（原文如此），丢失鼠、platinum-selected定义与组合方案；不能直接替换耐药治疗对象。|
|12 High-dose ascorbic acid synergizes with anti-PD1 therapy in non-small cell lung cancer in vitro and in vivo models|unclear / 无映射 → **unknown**|高剂量ascorbic acid+antiPD1在H460/CD8共培养和LLC1小鼠增敏/免疫蛋白组；未显示经确立原发/获得性PD1耐药模型，也不是患者治疗效果。 标题被截断为某acid，截掉in vitro/in vivo models，窗口是ICI临床背景；模型证据类型unknown未保住疾病治疗/实验类型。|
|13 Non-small-cell lung cancer|unclear / 无映射 → **unknown**|仅疾病名，无摘要；不能确认PD1耐药机制或文献类型。 无摘要，题名未截断；某次理由称题名截断不符合输入标记。|
|14 P2.05-17 A Novel Autoantibodies Panel Predicted the Prognosis of Advanced Non-Small Cell Lung Cancer Receiving Anti-PD1 Combined With Chemotherapy|unclear / 无映射 → **unknown**|autoantibodies panel/PD1+chemo/prognosis的会议题名，缺摘要；与机制目标是否相关未知，不能把预后当耐药因果。 标题截断，缺摘要。|
|15 Resistance to KRASG12C Inhibitors in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|KRASG12C inhibitor resistance是sotorasib/adagrasib靶向治疗原发/继发耐药，非PD1/PDL1免疫耐药；不能因NSCLC和resistance共现泛化。 完整可见title足以辨治疗对象；现有拒绝直接归免疫节点的理由边界合理，最终仍是unclear。|
|16 Sex-specific cytokine signatures as predictors of anti-PD1 therapy response in non-small cell lung cancer|unclear / 无映射 → **unknown**|24血浆cytokine/chemokine与response/PFS/OS的性别分层相关和聚类；用于观察性证据/biomarker局限比较，不是PD1基础通路机制。 窗口可见patient plasma采集前/中及profiling，但裁掉sex-specific、correlation/results；c1 foundation错配，应证据评估/微环境候选。|
|17 Spatial transcriptomics of macrophage infiltration in non-small cell lung cancer reveals determinants of sensitivity and resistance to anti-PD1/PD-L1 antibodies|unclear / 无映射 → **unknown**|TAM IHC152患者、16空间转录组及三独立数据集，CD163关联PFS/OS；CSF1R在responders高且可能非适当靶点，不能由TAM关联推出阻断疗效。 窗口保留TAM/ICB resistance及患者调查目的，丢失样本、关联设计、CSF1R反直觉结果；与目标相关但强度无法从窗口核。|
|18 The Applications of PD1 Monoclonal Antibody in Non-small Cell Lung Cancer|unclear / 无映射 → **unknown**|泛PD1应用综述含机制/疗效/不良事件/组合，但没有具体耐药路径和设计细节；初学可背景，高级价值未证实。其将Atezolizumab纳入PD1 mAb列举有靶点分类疑点，本审不外查。 窗口仅PD1/PDL1恢复T细胞和drug resistance背景；没有足够具体机制，不宜判新增治疗方案。|
|19 The role of the transcription factor Blimp-1 in T cells in anti-PD1 immunotherapy in non-small cell lung cancer 2258857|unclear / 无映射 → **unknown**|患者组织/PBMC观察与Lck T细胞Blimp1缺失NSCLC鼠+PD1阻断，Treg/T-effector机制；这是免疫逃逸机制候选，不等于患者疗效已证实。 窗口明确murine antiPD1与patient Blimp1表达，丢失缺失实验、Treg与效应细胞结果；任务潜相关，不该因为非核心PD1轴排除免疫耐药。 理由错误：完整源明确提出TME/Blimp1限制抗PD1免疫反应的机制；不能说不是resistance任务，window只是不够完整。|

前置核查：presentation→microenvironment不是普遍必需前置：内在抗原呈递/IFN与外在TME机制可并行分支；共现和生物相互作用不能建立必学顺序。 高级persona声明已熟悉基础，原graph仍把基础节点active/foundation；应把已知背景和新增研究能力区分。输入未提供完整prompt，不能断言已知背景没有发送给模型。

持久化方向：0；无方向不等于已证明不存在有用探索。

### medicine-growth-v1-r3 — failed

目标：比较NSCLC抗PD1/PDL1耐药中肿瘤内在机制与微环境机制的证据强度和研究设计局限。 已有基础：熟悉肿瘤免疫、PD1/PDL1通路和临床研究基本设计。

论文计数：{'passed': 0, 'failed': 3, 'unknown': 17, 'not_evaluated': 0}；方向计数：{'passed': 0, 'failed': 0, 'unknown': 0, 'not_evaluated': 0}。有内容/映射失败，不能判该完整案例科学正确。

|# / 论文|实际输出 → 本审|完整来源和窗口核查|
|---|---|---|
|0 234P Plasma cell free DNA hydroxymethylation profiling reveals anti-PD1 treatment response and resistance biology in non-small cell lung cancer|unclear / 无映射 → **unknown**|会议题名有NSCLC、anti-PD1 response/resistance与cfDNA 5hmC，但无摘要，样本和设计未知。 标题截断，无摘要。|
|1 Abstract 3660: Plasma cell free DNA hydroxymethylation profiling reveals anti-PD1 treatment response and resistance biology in non-small cell lung cancer|unclear / 无映射 → **unknown**|31 NSCLC患者151纵向血样，cfDNA 5hmC与RECIST应答相关；是观察性biomarker/pathway关联，不是耐药因果验证或已验证临床预测工具。 窗口抽到作者名单/引用题名，丢失31/151、RECIST、IFN/EMT与设计；不是原来源无摘要。|
|2 Abstract 6527: Ginseng polysaccharides circumvent acquired resistance to anti-pd1 immunotherapy in patients with non-small cell lung cancer|unclear / 无映射 → **unknown**|GP口服与继续PD1药物的获得性耐药NSCLC病例系列，5例再应答/ORR50%，无对照、会议初步数据；适合分析设计局限，不证明疗效或建议用药。 窗口仅trial目的与入组条件，丢失case series、5例/50%、结果及无对照；不能说已克服耐药。|
|3 Anti-PD1/PD-L1 Immunotherapy for Non-Small Cell Lung Cancer with Actionable Oncogenic Driver Mutations|unclear / 无映射 → **unknown**|oncogenic EGFR/ALK/BRAF/MET驱动突变与TME、PD1抵抗的综述，兼有临床数据；直接匹配内在机制-微环境交叉。 窗口丢失驱动基因和综述设计，仍有TME/抗PD1疗效；不能从短窗判缺少任何耐药联系。|
|4 CD155 expression impairs anti-PD1 therapy response in non-small cell lung cancer|covered / PD1/PDL1免疫轴 → **failed**|CD155/TIGIT与antiPD1应答的回顾性IHC观察研究，CD155阳性ORR/PFS关联；来源标题impairs并不能把关联升级成机制因果或联合靶向疗效。 窗口保留研究问题，丢失observational/retrospective、IHC、ORR/PFS及TIGIT无关联；covered基础免疫轴掩盖证据任务。 理由错误：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。CD155/TIGIT与antiPD1应答的回顾性IHC观察研究，CD155阳性ORR/PFS关联；来源标题impairs并不能把关联升级成机制因果或联合靶向疗效。 窗口保留研究问题，丢失observational/retrospective、IHC、ORR/PFS及TIGIT无关联；covered基础免疫轴掩盖证据任务。 判失败：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。CD155/TIGIT与antiPD1应答的回顾性IHC观察研究，CD155阳性ORR/PFS关联；来源标题impairs并不能把关联升级成机制因果或联合靶向疗效。 窗口保留研究问题，丢失observational/retrospective、IHC、ORR/PFS及TIGIT无关联；covered基础免疫轴掩盖证据任务。|
|5 Cancer cell-derived exosomal circUSP7 induces CD8+ T cell dysfunction and anti-PD1 resistance by regulating the miR-934/SHP2 axis in NSCLC|unclear / 无映射 → **unknown**|NSCLC exosomal circUSP7→miR-934/SHP2→CD8功能抑制，实验机制与回顾性临床关联混合；不是基础PD1轴本身，也不是临床治疗效果验证。 窗口保留SHP2/miR及may promote resistance，题名含CD8 dysfunction；能够候选归微环境/证据，不能把may与clinical association变成确认疗效。|
|6 Circular RNA CELF1 drives immunosuppression and anti-PD1 therapy resistance in non-small cell lung cancer via the miR-491-5p/EGFR axis|unclear / 无映射 → **unknown**|circCELF1-miR491-EGFR的NSCLC细胞/鼠机制，患者组织相关；摘要未详述antiPD1耐药实验，治疗特异性证据强度未知。 窗口与标题均提示immunosuppression/antiPD1 resistance，但缺模型与实验；说非PD1轴不等于与目标免疫耐药无关。|
|7 Circulating Low Density Neutrophils Are Associated with Resistance to First Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|LDN前瞻监测NSCLC一线PD1单药及CT+IT队列、ex vivo机制；基线LDN关联原发耐药与HGF/cMET免疫抑制，非随机组合疗效证明。 窗口只有一线ICI背景与机制未明，丢失LDN、队列、ex vivo和原发耐药结果；标题也被裁掉LDN对象。|
|8 Circulating Low Density Neutrophils Are Associated with Resistance to First-Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|LDN研究的preprint版本，前瞻队列/蛋白组/ex vivo；与上一出版版本重叠，不能当独立样本/复现。 窗口也是治疗背景，丢失关键LDN对象和设计；未知不足不能计推荐有效。|
|9 Circulating Low Density Neutrophils are Associated with Resistance to First-Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|第三LDN版本只有题名；无摘要，不能用另一个版本自动补全模型实际所见。 标题裁掉LDN对象，无摘要；版本相同主题不等于独立证据。|
|10 Clinical and molecular features of acquired resistance to immunotherapy in non-small cell lung cancer|unclear / 无映射 → **unknown**|1201患者PD(L)1获得性耐药及IFN/antigen-presentation改变，含多鼠模型/in vitro IFNγ机制；临床和模型须分层，是固定高级目标核心候选。 窗口只取研究动机和1201患者，丢失IFN、antigen-presentation和模型交叉验证；完整来源有具体机制，不能把短窗未知写成来源没有。|
|11 Dual inhibition of IDO1/TDO2 enhances anti-tumor immunity in platinum-resistant non-small cell lung cancer|unclear / 无映射 → **unknown**|cisplatin/platinum-resistant NSCLC代谢IDO1/TDO2与KYN、co-culture/鼠模型及antiPD1组合；铂耐药不是PD1耐药，作免疫抑制相邻机制需明确界限。 窗口含NK/CD8、Treg/MDSC及AT-1074（原文如此），丢失鼠、platinum-selected定义与组合方案；不能直接替换耐药治疗对象。|
|12 High-dose ascorbic acid synergizes with anti-PD1 therapy in non-small cell lung cancer in vitro and in vivo models|covered / PD1/PDL1免疫轴 → **failed**|高剂量ascorbic acid+antiPD1在H460/CD8共培养和LLC1小鼠增敏/免疫蛋白组；未显示经确立原发/获得性PD1耐药模型，也不是患者治疗效果。 标题被截断为某acid，截掉in vitro/in vivo models，窗口是ICI临床背景；模型证据类型unknown未保住疾病治疗/实验类型。 理由错误：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。高剂量ascorbic acid+antiPD1在H460/CD8共培养和LLC1小鼠增敏/免疫蛋白组；未显示经确立原发/获得性PD1耐药模型，也不是患者治疗效果。 标题被截断为某acid，截掉in vitro/in vivo models，窗口是ICI临床背景；模型证据类型unknown未保住疾病治疗/实验类型。 判失败：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。高剂量ascorbic acid+antiPD1在H460/CD8共培养和LLC1小鼠增敏/免疫蛋白组；未显示经确立原发/获得性PD1耐药模型，也不是患者治疗效果。 标题被截断为某acid，截掉in vitro/in vivo models，窗口是ICI临床背景；模型证据类型unknown未保住疾病治疗/实验类型。|
|13 Non-small-cell lung cancer|unclear / 无映射 → **unknown**|仅疾病名，无摘要；不能确认PD1耐药机制或文献类型。 无摘要，题名未截断；某次理由称题名截断不符合输入标记。|
|14 P2.05-17 A Novel Autoantibodies Panel Predicted the Prognosis of Advanced Non-Small Cell Lung Cancer Receiving Anti-PD1 Combined With Chemotherapy|unclear / 无映射 → **unknown**|autoantibodies panel/PD1+chemo/prognosis的会议题名，缺摘要；与机制目标是否相关未知，不能把预后当耐药因果。 标题截断，缺摘要。|
|15 Resistance to KRASG12C Inhibitors in Non-Small Cell Lung Cancer|unclear / 无映射 → **unknown**|KRASG12C inhibitor resistance是sotorasib/adagrasib靶向治疗原发/继发耐药，非PD1/PDL1免疫耐药；不能因NSCLC和resistance共现泛化。 完整可见title足以辨治疗对象；现有拒绝直接归免疫节点的理由边界合理，最终仍是unclear。|
|16 Sex-specific cytokine signatures as predictors of anti-PD1 therapy response in non-small cell lung cancer|covered / PD1/PDL1免疫轴 → **failed**|24血浆cytokine/chemokine与response/PFS/OS的性别分层相关和聚类；用于观察性证据/biomarker局限比较，不是PD1基础通路机制。 窗口可见patient plasma采集前/中及profiling，但裁掉sex-specific、correlation/results；c1 foundation错配，应证据评估/微环境候选。 理由错误：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。24血浆cytokine/chemokine与response/PFS/OS的性别分层相关和聚类；用于观察性证据/biomarker局限比较，不是PD1基础通路机制。 窗口可见patient plasma采集前/中及profiling，但裁掉sex-specific、correlation/results；c1 foundation错配，应证据评估/微环境候选。 判失败：把具体耐药/治疗增敏/观察性biomarker统一归PD1/PDL1免疫轴foundation，丢失对象、机制分支与证据能力；应视论文分别映射微环境/证据评估或限定为相邻实验。24血浆cytokine/chemokine与response/PFS/OS的性别分层相关和聚类；用于观察性证据/biomarker局限比较，不是PD1基础通路机制。 窗口可见patient plasma采集前/中及profiling，但裁掉sex-specific、correlation/results；c1 foundation错配，应证据评估/微环境候选。|
|17 Spatial transcriptomics of macrophage infiltration in non-small cell lung cancer reveals determinants of sensitivity and resistance to anti-PD1/PD-L1 antibodies|unclear / 无映射 → **unknown**|TAM IHC152患者、16空间转录组及三独立数据集，CD163关联PFS/OS；CSF1R在responders高且可能非适当靶点，不能由TAM关联推出阻断疗效。 窗口保留TAM/ICB resistance及患者调查目的，丢失样本、关联设计、CSF1R反直觉结果；与目标相关但强度无法从窗口核。|
|18 The Applications of PD1 Monoclonal Antibody in Non-small Cell Lung Cancer|unclear / 无映射 → **unknown**|泛PD1应用综述含机制/疗效/不良事件/组合，但没有具体耐药路径和设计细节；初学可背景，高级价值未证实。其将Atezolizumab纳入PD1 mAb列举有靶点分类疑点，本审不外查。 窗口仅PD1/PDL1恢复T细胞和drug resistance背景；没有足够具体机制，不宜判新增治疗方案。|
|19 The role of the transcription factor Blimp-1 in T cells in anti-PD1 immunotherapy in non-small cell lung cancer 2258857|unclear / 无映射 → **unknown**|患者组织/PBMC观察与Lck T细胞Blimp1缺失NSCLC鼠+PD1阻断，Treg/T-effector机制；这是免疫逃逸机制候选，不等于患者疗效已证实。 窗口明确murine antiPD1与patient Blimp1表达，丢失缺失实验、Treg与效应细胞结果；任务潜相关，不该因为非核心PD1轴排除免疫耐药。|

前置核查：presentation→microenvironment不是普遍必需前置：内在抗原呈递/IFN与外在TME机制可并行分支；共现和生物相互作用不能建立必学顺序。 高级persona声明已熟悉基础，原graph仍把基础节点active/foundation；应把已知背景和新增研究能力区分。输入未提供完整prompt，不能断言已知背景没有发送给模型。

持久化方向：0；无方向不等于已证明不存在有用探索。

## 未评及限度

人类专家审查、真实用户价值和满意度、完整论文/公开记录真实性、模型收费/账本、产品资源测量、源码原因均not_evaluated。仅由标题/摘要不能确立研究质量、可重复性、实用价值或个体治疗效果。未强制unknown为有用，也未由输出结构或逐字引用通过推导科学正确。
