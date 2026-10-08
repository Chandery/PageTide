# 2026-10-08 修复盲审 C — 科学内容终审 r19

独立代理 C 仅阅读指定公共内容包。输入 SHA256：cdc53d964fd4d7f89bec96bac44198951c046cf783d88e1bb4264da95cfaff68。未读其他报告、源码、账本、排名或参考标签，未联网、调用外部AI/API或UI。逐项追踪保留在私有 blind-review-c-final-r19.json。所给摘要不是原论文外部核验。

本次不能支持科学质量通过。未知不能计通过。粗任务相关、引用字面可定位、研究科学正确是三个不同结论。

## 实际计数

18情境（三学科×两目标×三重复），审查360持久论文判断和12持久方向；每学科重复同20来源与实际窗口，共60公共记录/窗口，含明显论文版本重复，不能算60份独立研究。127batch中126原解析回复，359结果组覆盖360paper slots。

| 持久输出 | 条数 |
|---|---:|
| unknown / unclear |311|
| covered |37|
| new |12|

| 独立完整来源用途判断（不是gold标签或通过率） |条数|
|---|---:|
|direct_task_useful|171|
|foundation_or_exploration_with_explicit_use|81|
|unknown_insufficient_source|72|
|adjacent_without_established_task_use|36|

有用途但持久unknown的203条：直接140、明确补充63。这是未解决覆盖问题，并非203个已证软件误判。72条来源不足与36条邻近項未强判通过。124持久短引全部原文且窗口可定位，119处type unknown、5处observational；定位不是科学正确证据。12方向无非空needs/parent/required_by。

## 情境逐条分布

|情境|unknown|covered|new|方向审查|
|---|---:|---:|---:|---:|
|cs-growth-v0-r1|16|3|1|1|
|cs-growth-v0-r2|17|2|1|1|
|cs-growth-v0-r3|17|2|1|1|
|cs-growth-v1-r1|11|7|2|2|
|cs-growth-v1-r2|13|4|3|3|
|cs-growth-v1-r3|10|6|4|4|
|materials-growth-v0-r1|20|0|0|0|
|materials-growth-v0-r2|20|0|0|0|
|materials-growth-v0-r3|20|0|0|0|
|materials-growth-v1-r1|19|1|0|0|
|materials-growth-v1-r2|20|0|0|0|
|materials-growth-v1-r3|20|0|0|0|
|medicine-growth-v0-r1|18|2|0|0|
|medicine-growth-v0-r2|18|2|0|0|
|medicine-growth-v0-r3|17|3|0|0|
|medicine-growth-v1-r1|19|1|0|0|
|medicine-growth-v1-r2|19|1|0|0|
|medicine-growth-v1-r3|17|3|0|0|

## 科学问题与具体复现线索

- **C-F1 (high)** 311/360持久unknown；完整来源直接有用140及明确补充有用63条仍unknown，未解决覆盖，不等于203项已证误判。72来源不足和36邻近项未强判通过。 追踪：cs-growth-v0-r1/S20, materials-growth-v0-r1/M18, medicine-growth-v1-r1/D11。
- **C-F2 (high)** 医学12条持久正判都放PD1/PDL1基础轴，缺精确机制/证据位置。CD155三次以title impairs说机制但完整研究回顾关联；AA四次未保留preclinical/非已证耐药，cytokine四次是观察biomarker，circUSP7一次是跨细胞CD8。 追踪：medicine-growth-v1-r1/D5, medicine-growth-v0-r1/D13, medicine-growth-v0-r1/D17, medicine-growth-v0-r3/D6。
- **C-F3 (medium)** 全部12方向有用途但多数宽名已属planning/dynamics/evaluation，相关不等新枝。量化失败是明确可选新角度。12方向needs/parent/required_by空，未观察到新增硬前置。 追踪：cs-growth-v0-r1/S11, cs-growth-v0-r2/S2, cs-growth-v1-r1/S9, cs-growth-v1-r1/S12, cs-growth-v0-r3/S1。
- **C-F4 (high)** 短窗口丢设计/对象/结果。原回复曾混正极与Li负极、sulfide SEI与SSE、有机液态Li与全固态Li金属，及forecasting与action-conditioned dynamics；多数持久回退unknown，回退不证明用途通过。 追踪：materials-growth-v0-r1/M4, materials-growth-v0-r1/M12, materials-growth-v1-r2/M16, cs-growth-v0-r1/S18。
- **C-F5 (medium)** 124处持久短引全部可定位且可见；119 type unknown/5 observational。字面匹配不保证因果、对象、设计、新颖性和论文科学正确。 追踪：medicine-growth-v1-r1/D5, medicine-growth-v0-r1/D13, cs-growth-v1-r2/S14。
- **C-F6 (medium)** D11 medicine-v1-r2原回复标review，但人体队列+鼠机制非review；D14 medicine-v1-r1误称title截断；D2 medicine-v1-r2误说无摘要，实际选citation尾段而完整来源有摘要。 追踪：medicine-growth-v1-r2/D11, medicine-growth-v1-r1/D14, medicine-growth-v1-r2/D2。
- **C-F7 (medium)** 输入原图hard edges不是模型新添；医学presentation→microenvironment不支持科学必需，材料interface→failure也不应普适，学习建议与必要依赖需分开。 追踪：medicine-growth-v0-r1/original_user_graph/prereqs/1, materials-growth-v1-r1/original_user_graph/prereqs/1。
- **C-F8 (medium)** Drive-WM版本同方法出现覆盖/未知差异；LDN多版本不可当独立证据。medicine-v0-r1应用19组有一组含两题名，持久20paper在，不能仅按组数声称丢paper。材料v1r1一个无响应batch随后resume。 追踪：cs-growth-v1-r3/S4, cs-growth-v1-r3/S5, medicine-growth-v0-r1/D9, medicine-growth-v0-r1/D10, materials-growth-v1-r1。
- **C-F9 (investigate)** 记录可复现粗任务明确仍unknown、医学title-only unknown-design正判和原/持久taxonomy差异；未读源码，不能断言过滤规则根因。包未含整份prompt，fixed persona是否完整发送未知。 追踪：cs-growth-v0-r1/S20, medicine-growth-v1-r1/D5, materials-growth-v0-r1/M18。

## 所有持久方向

|情境 / 名称|来源|结论|
|---|---|---|
|cs-growth-v0-r1 / 潜空间世界模型规划|S11|JEPA/MPPI及policy初始化是planning/dynamics细化；宽名不证明原Map未覆盖，语言目标intro仅完整来源可证；部件不是硬前置依据。|
|cs-growth-v0-r2 / 世界动作模型测试时规划|S2|选择器/视觉质量和task成功是已有evaluation/planning细化；完整来源支持失配barrier，window只给干预。|
|cs-growth-v0-r3 / 世界模型量化评估|S1|量化失败是具体有用的可选新角度，不能泛化所有不可补救失败或当必需基础。|
|cs-growth-v1-r1 / 部分观测视觉动力学|S9|部分观测转移与state表征属现c1/c2；不可直接监督barrier在window未确证，不证明新能力。|
|cs-growth-v1-r1 / 视觉RL世界模型|S12|视觉RL世界模型高度重叠c2，进阶已知RL；应细化residual-action稳定性用途，不堆通用基础。|
|cs-growth-v1-r2 / World-Model Visual Navigation|S11|JEPA/MPPI及policy初始化是planning/dynamics细化；宽名不证明原Map未覆盖，语言目标intro仅完整来源可证；部件不是硬前置依据。|
|cs-growth-v1-r2 / Sparse Visual World Planning|S14|稀疏rollout效率可选有用、属planning细化；丢fidelity/task details是风险假设不是摘要实测失败。|
|cs-growth-v1-r2 / Progressive Visual Planning|S19|subgoal长时程/OOD直接有用但属planning细化；训练困难/compounding error是推测，不是window结果。|
|cs-growth-v1-r3 / World-Model Visual Navigation|S11|JEPA/MPPI及policy初始化是planning/dynamics细化；宽名不证明原Map未覆盖，语言目标intro仅完整来源可证；部件不是硬前置依据。|
|cs-growth-v1-r3 / Revisable Visual Planning|S13|反馈revision bridge有用、属closed-loop planning细化；与MPC实现差异不证明能力未覆盖。|
|cs-growth-v1-r3 / Sparse Visual World Planning|S14|稀疏rollout效率可选有用、属planning细化；丢fidelity/task details是风险假设不是摘要实测失败。|
|cs-growth-v1-r3 / Progressive Visual Planning|S19|subgoal长时程/OOD直接有用但属planning细化；训练困难/compounding error是推测，不是window结果。|

## 来源索引与独立判断

D = 直接有用；F = 明确用途补充/探索；A = 邻近但用途未建；U = 未知。v0/v1分别初学/进阶。

|索引|公共题名|v0|v1|科学用途与限制|
|---|---|---|---|---|
|S1|[An Empirical Study of World Model Quantization](https://doi.org/10.48550/arxiv.2602.02110)|D|D|量化对encoder/predictor及规划objective和task success的失配直接涉及模型误差评估；不是仅压缩性能。窗口只有失败尾句，没有实验设计。|
|S2|[Beyond Visual Quality: A Study of Test-Time Planning with World Action Models](https://doi.org/10.48550/arxiv.2609.24745)|D|D|同状态反事实选择、oracle和选择器干预比较视觉质量与决策效用，直接有用；窗口有干预但无完整设计和执行结果。|
|S3|[DINO-WM: World Models on Pre-trained Visual Features enable Zero-shot Planning](https://doi.org/10.48550/arxiv.2411.04983)|D|D|离线视觉patch预测和动作优化、多环境零样本规划直接比较表征/动力学/规划假设；窗口与title粗相关，不能验证OOD普适效果。|
|S4|[Driving Into the Future: Multiview Visual Forecasting and Planning with World Model for Autonomous Driving](https://doi.org/10.1109/cvpr52733.2024.01397)|D|F|Drive-WM驾驶多未来/图像奖励规划初学直接，进阶作应用对照而非长时程机器人OOD证据；窗口主要动机，和S5是明显同方法版本。|
|S5|[Driving into the Future: Multiview Visual Forecasting and Planning with World Model for Autonomous Driving](https://doi.org/10.48550/arxiv.2311.17918)|D|F|Drive-WM初学直接，进阶比较场景方法；与S4题摘近乎相同，不是两份独立科学证据，窗口没有定量设计。|
|S6|[Gradient-based Planning with World Models](https://doi.org/10.48550/arxiv.2312.17227)|D|F|梯度MPC与CEM/MPPI和policy比较，初学直接，进阶比较优化假设；窗口只是MPC背景，title给gradient，未显示稳定性/OOD。|
|S7|[HiWE: Hierarchical World Knowledge Model with Visual Keypoint Enhancement for Zero-Shot 3D Path Planning](https://doi.org/10.48550/arxiv.2609.39323)|F|A|点定位、深度与语言waypoint初学可比较视觉状态到执行接口；进阶目标动作条件预测误差/OOD用途未建立，不是latent dynamics或必要机器人基础。|
|S8|[JEPA-Bisim: Learning Robust Visual Representations for Planning with Joint-Embedding Predictive World Models](https://doi.org/10.48550/arxiv.2602.18639)|D|D|bisimulation抑背景慢特征、PointMaze/PushT干扰评估直接研究鲁棒规划；实际窗口只有latent planning动机，不能核损失和OOD结果。|
|S9|[Learning Visual Planning Models from Partially Observed Images](https://doi.org/10.48550/arxiv.2211.15666)|D|F|部分观测图像转移、latent states、heuristic/classical planner初学直接，进阶比较缺观测假设；窗口未证明显式action conditioning或完整planner评估。|
|S10|[Planning with Reasoning using Vision Language World Model](https://doi.org/10.48550/arxiv.2509.02722)|D|F|VLWM实际预测交错动作/状态并做semantic cost rollout规划，不是纯语言；进阶作抽象方案比较。窗口只留language-based modeling，细节未知合理。|
|S11|[Policy-Guided World Model Planning for Language-Conditioned Visual Navigation](https://doi.org/10.48550/arxiv.2603.25981)|D|D|policy prior warm-start JEPA/MPPI导航直接服务规划及初始化局限；窗口明确JEPA/未来latent/MPPI，无完整实验。宽名已属planning，不证明新枝。|
|S12|[ResWM: Residual-Action World Model for Visual RL](https://doi.org/10.48550/arxiv.2603.11110)|D|D|残差动作和帧差分Dreamer模型研究长时程控制稳定性；窗口是视觉RL背景，title含residual。Control Suite不是真实机器人长时程验证。|
|S13|[Revision, Not Restart: Revisable Visual Plans for Closed-Loop World-Action Models](https://doi.org/10.48550/arxiv.2609.35439)|D|D|反馈修订persistent visual future并连接控制，直接服务闭环规划；窗口支持revision bridge但不含控制监督和评估，不是仅美化视频。|
|S14|[Sparse Imagination for Efficient Visual World Model Planning](https://doi.org/10.48550/arxiv.2506.01392)|D|F|sparse attention/token rollout提高规划效率，初学比较资源假设，进阶明确效率/保真补充用途；丢细节是风险推测，摘要没有报告实测失败。|
|S15|[TRTP: a three-stage robust task planning framework for open worlds via visual-language models and digital twin simulation](https://doi.org/10.1007/s10489-026-07143-y)|U|U|无摘要，title只有VLM/digital twin任务规划；不能保证潜动力学、具体控制或研究证据，未知不算通过。|
|S16|[The Planning Limits of Latent World Models](https://doi.org/10.48550/arxiv.2609.39235)|D|D|rollout可规划范围、perfect-simulator对照、MPC/subgoal干预直接研究长时程与误差；窗口只开场，title给limits，无完整比较设计。|
|S17|[Thinking with Patterns: Breaking the Perceptual Bottleneck in Visual Planning via Pattern Induction](https://doi.org/10.48550/arxiv.2605.16848)|F|F|TWI/pattern induction有FrozenLake/Crafter/CubeBench规划，明确感知瓶颈与抽象比较用途；不是已证action-conditioned latent dynamics或长时程机器人OOD。|
|S18|[Towards Surgical World-Action Modeling: A Preliminary Joint Visual-Trajectory Forecasting for Surgical Motion Planning](https://doi.org/10.48550/arxiv.2608.20284)|F|F|手术历史观测joint image/trajectory forecasting与长horizon累积误差可作预测/控制边界比较；没有候选动作反事实预测或闭环planning，不能直接称动作条件动力学。|
|S19|[World Action Modeling with Progressive Visual Planning](https://doi.org/10.48550/arxiv.2610.02508)|D|D|子目标及action generation/replanning/OOD评估直接有用；窗口只留action-free subgoal预训练，不能误当整个方法无动作。|
|S20|[iVideoGPT: Interactive VideoGPTs are Scalable World Models](https://doi.org/10.48550/arxiv.2405.15223)|D|F|视觉/动作/reward tokens支持action-conditioned video、planning和MBRL；初学直接，进阶作生成式方案比较。窗口已明确动作条件预测与规划，全部粗相关性未知过保守。|
|M1|[(Digital Presentation) On the Origin of High Resistance at the Interface between Lithium Metal and Sulfide Solid Electrolytes](https://doi.org/10.1149/ma2022-01192mtgabs)|D|D|Li3PS4锂化分解、输运/电子变化和void直接辨化学与接触阻抗；窗口只有高阻，不能当实验operando/CCD或因果证明。|
|M2|[Challenges and optimization strategies at the interface between sulfide solid electrolyte and lithium anode](https://doi.org/10.1016/j.ensm.2023.102958)|U|U|只有sulfide SSE/Li anode策略title无摘要；设计、机制和作用未知，标题接近不等于验证。|
|M3|[Doping effects of metal cation on sulfide solid electrolyte/lithium metal interface](https://doi.org/10.1016/j.nanoen.2021.105906)|U|U|只有cation doping与sulfide/Li界面title；不臆造掺杂机制或CCD效果。|
|M4|[Electrochemically and chemically stable electrolyte–electrode interfaces for lithium iron phosphate all-solid-state batteries with sulfide electrolytes](https://doi.org/10.1039/d3ta06227a)|A|A|LiFePO4正极/SSE coating抑反应，未给Li金属负极迁移机制；interface/stability词不能使其成为目标直接覆盖。|
|M5|[Graphitic carbon nitride stabilized the lithium anode/sulfide electrolyte interface for all-solid-state lithium-sulfur battery](https://doi.org/10.1016/j.cej.2024.150887)|U|U|carbon nitride/Li anode/sulfide界面title相关但无摘要，界面层设计的作用和证据未知。|
|M6|[High Ionic Conductive, Mechanical Robust Sulfide Solid Electrolyte Films and Interface Design for All‐Solid‐State Lithium Metal Batteries](https://doi.org/10.1002/adfm.202315555)|D|D|硫化物膜及Li3N SEI抑PTFE/Li还原、800h symmetric cell稳定直接有用；PTFE还原不是SSE分解，窗口截掉SEI/稳定性，不证明CCD。|
|M7|[In situ formed LiF-Li3N interface layer enables ultra-stable sulfide electrolyte-based all-solid-state lithium batteries](https://doi.org/10.1016/j.jechem.2023.01.007)|U|U|LiF-Li3N layer title接近目标但无摘要，ultra-stable不代表可靠机制、长期或必需前置。|
|M8|[Insight Into All‐Solid‐State Lithium‐Sulfur Batteries: Challenges and Interface Engineering at the Electrode‐Sulfide Solid Electrolyte Interface](https://doi.org/10.1002/aenm.202504926)|F|F|Li-S ASSLSB综述明确覆盖正/负界面、应力导电网络与膜，可区分两端问题及策略；窗口只review结尾，不是具体机制/CCD原始证据。|
|M9|[Interface failure mechanisms and engineering strategies in sulfide and halide solid electrolytes for lithium metal solid-state batteries](https://doi.org/10.3389/fbael.2026.1844424)|D|D|Li金属/sulfide/halide枝晶、分解、void、机械失效直接构建机制分类；窗口已有失效对象，不能以无新任务否定已有failure用途。|
|M10|[Interfaces in Sulfide Solid Electrolyte-Based All-Solid-State Lithium Batteries: Characterization, Mechanism and Strategy](https://doi.org/10.1007/s41918-022-00176-0)|U|U|硫化物solid-state界面title无摘要；对象和研究证据未定，不判科学通过。|
|M11|[Lithium–sulfur cells with a sulfide solid electrolyte/polysulfide cathode interface](https://doi.org/10.1039/d2ta07806f)|A|A|SSE/多硫化物正极液固charge-transfer设计，未研究Li金属界面或明确转移用途；材料名不等于学习能力。|
|M12|[Metal Sulfide Artificial Solid-Electrolyte Interface for Improved Lithium Anode Stability](https://doi.org/10.1149/ma2022-022162mtgabs)|F|F|金属硫化物人工SEI、均匀Li沉积、EIS/SEM与symmetric cell可作基础设计比较；metal sulfide SEI不等于sulfide SSE，目标体系未证。|
|M13|[New Types of Binder for Ceramic Solid Electrolyte Films: Sulfide Electrolyte, Lithium Metal, Interfaces and Cyclability](https://doi.org/10.1149/ma2025-017771mtgabs)|D|D|硫化物膜binder/密度柔性/压力/枝晶crack直接研究机械接触；会议摘要>700cycle未给完整压力/统计/CCD，window只有问题。|
|M14|[Ni-Rich Layered Oxide Cathodes/Sulfide Electrolyte Interface in Solid-State Lithium Battery](https://doi.org/10.1021/acsami.4c05609)|A|A|Ni-rich oxide cathode/SSE界面综述没有Li负极用途或迁移机制；不能因共享SSE就当负极前置。|
|M15|[Simultaneously in-situ fabrication of lithium fluoride and sulfide enriched artificial solid electrolyte interface facilitates high stable lithium metal anode](https://doi.org/10.1016/j.cej.2021.133193)|U|U|LiF/sulfide artificial SEI title无摘要，不能自动当sulfide SSE体系。|
|M16|[Stable Interface between Sulfide Solid Electrolyte and Room-Temperature Liquid Lithium Anode](https://doi.org/10.1021/acsnano.3c03532)|F|F|PEO/Li3PS4-S保护SSE/ether-based有机液态Li负极可比较固液/固固边界；不是室温熔融元素Li或全固态Li金属，不能直接归目标反应。|
|M17|[Study of the Cathode/Electrolyte Interface in an All-Sulfide-Solid-State Battery Using Lithium-Rich Transition Metal Sulfide](https://doi.org/10.1021/acsami.4c18890)|F|A|Li-rich sulfide cathode的ex/in situ XPS初学可练表征证据，进阶负极目标用途未建；cell含Li金属但实际检视positive electrode，不是operando或负极不降解。|
|M18|[Sulfide-Based Solid-State Lithium-Sulfur Batteries: An in-Depth Study of the Li-Electrolyte Interface](https://doi.org/10.1149/ma2023-024551mtgabs)|D|D|Li6PS5Cl/Li7P3S11对Li稳定性与EIS/XPS/ToF-SIMS层析直接有用；window明确compare/assess/characterize。GCIB abrasion不是cycling operando。|
|M19|[Tailoring the Interface between Sulfur and Sulfide Solid Electrolyte for High-Areal-Capacity All-Solid-State Lithium–Sulfur Batteries](https://doi.org/10.1021/acsenergylett.3c01473)|F|A|S8/SSE的多硫化中间体改善ionic contact与力学，初学可比较输运/接触；进阶未有Li界面层/CCD用途，高容量不证明负极稳定。|
|M20|[Thin, flexible sulfide-based electrolyte film and its interface engineering for high performance solid-state lithium metal batteries](https://doi.org/10.1016/j.cej.2021.132991)|U|U|薄柔sulfide film/interface工程title无摘要，机制和效果未知，不强判负或通过。|
|D1|[234P Plasma cell free DNA hydroxymethylation profiling reveals anti-PD1 treatment response and resistance biology in non-small cell lung cancer](https://doi.org/10.1016/j.annonc.2023.09.2957)|U|U|cfDNA hydroxymethylation/PD1 response resistance title无摘要；不能借相似版本自动补证。|
|D2|[Abstract 3660: Plasma cell free DNA hydroxymethylation profiling reveals anti-PD1 treatment response and resistance biology in non-small cell lung cancer](https://doi.org/10.1158/1538-7445.am2024-3660)|D|D|31患者151samples纵向5hmC与immune/IFN或EMT关联直接比较临床关联和机制证据；window选成作者citation/title重复，来源实际有摘要。|
|D3|[Abstract 6527: Ginseng polysaccharides circumvent acquired resistance to anti-pd1 immunotherapy in patients with non-small cell lung cancer](https://doi.org/10.1158/1538-7445.am2025-6527)|D|D|获得性PD1耐药继续PD1加GPs、初步response/微生物代谢改变可审case series证据；登记号/to investigate不证明RCT、因果或疗效，window无结果设计。|
|D4|[Anti-PD1/PD-L1 Immunotherapy for Non-Small Cell Lung Cancer with Actionable Oncogenic Driver Mutations](https://doi.org/10.3390/ijms22126288)|D|D|driver突变改TME和PD1 resistance，review机制与临床直接有用；只放PD1基础抹掉关键耐药分支。|
|D5|[CD155 expression impairs anti-PD1 therapy response in non-small cell lung cancer](https://doi.org/10.1093/cei/uxac020)|D|D|CD155/TIGIT与PD1 response回顾IHC关联直接比较机制假设；window说whether affects unclear，title impairs不等于因果或PD1/PDL1轴本身。|
|D6|[Cancer cell-derived exosomal circUSP7 induces CD8+ T cell dysfunction and anti-PD1 resistance by regulating the miR-934/SHP2 axis in NSCLC](https://doi.org/10.1186/s12943-021-01448-x)|D|D|癌exosome circUSP7-miR934-SHP2抑CD8功能直接研究跨细胞免疫抑制；tumor来源不等于仅intrinsic，patient关联不是临床干预证明。|
|D7|[Circular RNA CELF1 drives immunosuppression and anti-PD1 therapy resistance in non-small cell lung cancer via the miR-491-5p/EGFR axis](https://doi.org/10.18632/aging.203576)|D|D|circCELF1-miR491-EGFR细胞/鼠及人体表达研究immune escape；title明确antiPD1 resistance。非PD1轴不能排除耐药旁路，人体组织不是疗效证明。|
|D8|[Circulating Low Density Neutrophils Are Associated with Resistance to First Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer](https://doi.org/10.3390/cancers14163846)|D|D|LDN前瞻队列及ex vivo/proteomics研究primary PD1 resistance；window只背景且title删LDN，不能核机制或保证CT+IT疗效。|
|D9|[Circulating Low Density Neutrophils Are Associated with Resistance to First-Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer](https://doi.org/10.1101/2022.04.27.22273598)|D|D|LDN/HGF-cMET临床及ex vivo directly有用；与D8/D10高度相似版本，不算多份独立证据，window无LDN和实验设计。|
|D10|[Circulating Low Density Neutrophils are Associated with Resistance to First-Line Anti-PD1/PDL1 Immunotherapy in Non-Small Cell Lung Cancer](https://doi.org/10.2139/ssrn.4114255)|U|U|SSRN LDN/PD1 resistance无摘要，本条科学判断未知；不借D8/D9强补。应用合并结果组不等于丢paper。|
|D11|[Clinical and molecular features of acquired resistance to immunotherapy in non-small cell lung cancer](https://doi.org/10.1016/j.ccell.2023.12.013)|D|D|1201患者IFN/antigen presentation与鼠IFN处理复现直接比较因果边界；不是review，window仅acquired resistance cohort开头。|
|D12|[Dual inhibition of IDO1/TDO2 enhances anti-tumor immunity in platinum-resistant non-small cell lung cancer](https://doi.org/10.1186/s40170-023-00307-1)|F|F|platinum-resistant KYN/IDO1/TDO2及NK/CD8/Treg/MDSC、PD1 combo可探索代谢逃逸；platinum resistance不是PD1 resistance或临床方案证据。|
|D13|[High-dose ascorbic acid synergizes with anti-PD1 therapy in non-small cell lung cancer in vitro and in vivo models](https://doi.org/10.3389/fimmu.2024.1512605)|F|F|AA与antiPD1在H460/CD8和LLC1鼠增敏/proteomics可比较机制和设计；非已证PD1耐药人群/临床疗效，window title有in vitro但持久quote丢限制。|
|D14|[Non-small-cell lung cancer](https://doi.org/10.1038/s41572-024-00551-9)|U|U|title只有NSCLC疾病名，无摘要；实际title未截断，不能核目标机制。|
|D15|[P2.05-17 A Novel Autoantibodies Panel Predicted the Prognosis of Advanced Non-Small Cell Lung Cancer Receiving Anti-PD1 Combined With Chemotherapy](https://doi.org/10.1016/j.jtho.2023.09.544)|U|U|autoantibody panel预后/PD1化疗title无摘要；预后预测不等于耐药机制，window另删掉对象。|
|D16|[Resistance to KRASG12C Inhibitors in Non-Small Cell Lung Cancer](https://doi.org/10.3389/fonc.2021.787585)|A|A|KRASG12C inhibitor耐药没有明确PD1 link，当前用途未建；不声称KRAS生物学永远与免疫无关。|
|D17|[Sex-specific cytokine signatures as predictors of anti-PD1 therapy response in non-small cell lung cancer](https://doi.org/10.3389/fimmu.2025.1583421)|F|F|sex-specific plasma cytokine response/PFS/OS可作biomarker关联及混杂限制比较；window人体profile可支持observational，不等于PD1轴机制因果。|
|D18|[Spatial transcriptomics of macrophage infiltration in non-small cell lung cancer reveals determinants of sensitivity and resistance to anti-PD1/PD-L1 antibodies](https://doi.org/10.1136/jitc-2021-003890)|D|D|TAM/CD163/spatial genes/独立数据直接研究PD1 resistance TME；CSF1R方向复杂，不能简单抑制或把driver措辞当临床因果。window已有TAM/NSCLC/ICB task。|
|D19|[The Applications of PD1 Monoclonal Antibody in Non-small Cell Lung Cancer](https://doi.org/10.54254/2753-8818/2025.ld26454)|F|A|初学可了解PD1 axis/Tcell恢复与证据区别；进阶基础已知、泛疗效安全review未给具体耐药用途；Atezolizumab靶点分类需人工复核。|
|D20|[The role of the transcription factor Blimp-1 in T cells in anti-PD1 immunotherapy in non-small cell lung cancer 2258857](https://doi.org/10.1093/jimmun/vkag141.638)|D|D|patient Blimp1表达与Treg/CD8、鼠Tcell靶向和PD1 blockade直接研究immune escape；window同时鼠和patient，非人类干预疗效或基础轴课。|

## 分歧与人类验证边界

没有读取其他代理结果，不能声称代理一致或列实际跨代理分歧。本审查与系统判断的分歧逐条保留。应保留S7、S14、M12、M16、M17、M19、D17、D19的补充用途边界，不应为了代理一致率强制为正/负。

领域人员应复核原论文、版本关系及设计限制。医学要区分关联/因果、鼠/临床、对照与混杂；材料需明确SSE/SEI、电极相态、CCD与operando；CS需核动作条件、预测/闭环及长时程/OOD。本文不做患者治疗建议。

包展示fixed persona、actual map及fragment但不是整份prompt，persona是否完整发送无法核实。软件问题给出了内容记录中的具体复现线索，未读源码，不断言过滤器根因。没有修改产品或原包。

## 全部原回复新增方向（包括未持久者）

27个原提议均逐条审查：9 new_branch、18 new_task。4个原提议含非空needs，共8关系，未有可核必要性证据；这些没有作为新硬前置持久。parent挂载本身不视作科学依赖证明。

|情境 / 原方向|来源|科学用途、新颖性和前置审查|
|---|---|---|
|cs-growth-v0-r1 / 手术世界-动作联合建模|S18|有明确forecasting误差比较用途，但未证明action-conditioned反事实建模或闭环控制；不能将手术领域名称当超出dynamics的核心新能力。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v0-r1 / 潜空间世界模型规划|S11|JEPA/MPPI及policy初始化是planning/dynamics细化；宽名不证明原Map未覆盖，语言目标intro仅完整来源可证；部件不是硬前置依据。 未见可核对的科学必要性证据；视觉/dynamics/planning等部件或有益学习背景不是必需前置的证明。|
|cs-growth-v0-r1 / 可修订视觉计划|S13|反馈revision bridge有用、属closed-loop planning细化；与MPC实现差异不证明能力未覆盖。 未见可核对的科学必要性证据；视觉/dynamics/planning等部件或有益学习背景不是必需前置的证明。|
|cs-growth-v0-r2 / 手术世界-动作建模|S18|有明确forecasting误差比较用途，但未证明action-conditioned反事实建模或闭环控制；不能将手术领域名称当超出dynamics的核心新能力。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v0-r2 / 世界动作模型测试时规划|S2|选择器/视觉质量和task成功是已有evaluation/planning细化；完整来源支持失配barrier，window只给干预。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v0-r3 / 交互式视频世界模型|S20|动作条件video/planning有明确用途，但通用交互世界模型已由dynamics/planning覆盖；新方向名称不证明独立能力。 未见可核对的科学必要性证据；视觉/dynamics/planning等部件或有益学习背景不是必需前置的证明。|
|cs-growth-v0-r3 / 视觉规划感知瓶颈突破|S17|pattern/TWI有感知和planning探索用途，但VLM符号/图像推理不证明需先学action-conditioned latent dynamics。 未见可核对的科学必要性证据；视觉/dynamics/planning等部件或有益学习背景不是必需前置的证明。 特别是c2动作条件动力学，当前TWI/pattern来源并未证明其必要性。|
|cs-growth-v0-r3 / 世界模型量化评估|S1|量化失败是具体有用的可选新角度，不能泛化所有不可补救失败或当必需基础。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v1-r1 / 部分观测视觉动力学|S9|部分观测转移与state表征属现c1/c2；不可直接监督barrier在window未确证，不证明新能力。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v1-r1 / 视觉RL世界模型|S12|视觉RL世界模型高度重叠c2，进阶已知RL；应细化residual-action稳定性用途，不堆通用基础。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v1-r1 / 潜在世界模型规划评估|S16|planning limits直接是现有evaluation/planning的研究问题，粗title/opener能辨主题但不证明新任务或定量barrier。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v1-r1 / 交互点运动规划|S7|HiWE是视觉点定位/语言waypoint控制；初学可选接口比较，进阶目标的world-model long-horizon/OOD用途未建，不能新增该机器人应用必需能力。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v1-r1 / 手术世界动作建模|S18|有明确forecasting误差比较用途，但未证明action-conditioned反事实建模或闭环控制；不能将手术领域名称当超出dynamics的核心新能力。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v1-r2 / 交互点运动规划|S7|HiWE是视觉点定位/语言waypoint控制；初学可选接口比较，进阶目标的world-model long-horizon/OOD用途未建，不能新增该机器人应用必需能力。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v1-r2 / 手术世界动作建模|S18|有明确forecasting误差比较用途，但未证明action-conditioned反事实建模或闭环控制；不能将手术领域名称当超出dynamics的核心新能力。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v1-r2 / World-Model Visual Navigation|S11|JEPA/MPPI及policy初始化是planning/dynamics细化；宽名不证明原Map未覆盖，语言目标intro仅完整来源可证；部件不是硬前置依据。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v1-r2 / Revisable Visual Planning|S13|反馈revision bridge有用、属closed-loop planning细化；与MPC实现差异不证明能力未覆盖。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v1-r2 / Sparse Visual World Planning|S14|稀疏rollout效率可选有用、属planning细化；丢fidelity/task details是风险假设不是摘要实测失败。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v1-r2 / Progressive Visual Planning|S19|subgoal长时程/OOD直接有用但属planning细化；训练困难/compounding error是推测，不是window结果。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v1-r3 / Contact-Aware Motion Planning|S7|HiWE是视觉点定位/语言waypoint控制；初学可选接口比较，进阶目标的world-model long-horizon/OOD用途未建，不能新增该机器人应用必需能力。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v1-r3 / Surgical World-Action Modeling|S18|有明确forecasting误差比较用途，但未证明action-conditioned反事实建模或闭环控制；不能将手术领域名称当超出dynamics的核心新能力。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v1-r3 / World-Model Visual Navigation|S11|JEPA/MPPI及policy初始化是planning/dynamics细化；宽名不证明原Map未覆盖，语言目标intro仅完整来源可证；部件不是硬前置依据。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v1-r3 / Revisable Visual Planning|S13|反馈revision bridge有用、属closed-loop planning细化；与MPC实现差异不证明能力未覆盖。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v1-r3 / Sparse Visual World Planning|S14|稀疏rollout效率可选有用、属planning细化；丢fidelity/task details是风险假设不是摘要实测失败。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|cs-growth-v1-r3 / Progressive Visual Planning|S19|subgoal长时程/OOD直接有用但属planning细化；训练困难/compounding error是推测，不是window结果。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|materials-growth-v1-r3 / 硫化物-液态锂界面保护|M16|可选比较固液保护界面；ether-based有机液态Li不是目标all-solid Li metal，不能直接在Li-metal反应之下当已覆盖新任务。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
|materials-growth-v1-r3 / 硫化物-多硫化物正极界面|M11|多硫化物正极/液固界面没有当前Li金属负极目标用途；把不同材料界面名称放transport parent不证明新学习能力。 没有显式needs；parent为分类挂载不能自动当科学必要前置。|
