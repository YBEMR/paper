# 第四章实验回顾：时间线、思路演变与当前证据

编制日期：2026-11-14（北京时间）。用途：给其他会话独立阅读、接手研究和回查证据。

**证据快照：** 仓库[YBEMR/paper](https://github.com/YBEMR/paper)，第四章分支为`chapter4/unseen-scaling-20261112`，截至[0de4d19][C0de4d19]。本文件仅整理既有实验与日志，状态为 **ANALYZED**，新增调度搜索、求解及电热评价均为0。下文报告链接固定到该快照，提交链接指向相应历史节点；本文件后续提交不改变实验冻结版本。

## 1. 先读结论

第四章已经从“在几个开发例上找到更省能的排程”，推进到“冻结方法后检查新参数根、规模成本及失败边界”。目前最合适的目标是：

> 在多场景CPU/GPU/NPU异构调度中，通过安全初始化、阻塞反馈联合重构和结构必要条件预筛，在有限预算内获得满足完整电热安全与截止期约束的高质量解，并明确性能与适用边界。

现有证据分别支持三件事：I1能在部分原有限构造失败的条件中恢复安全覆盖；阻塞反馈在部分实例中取得普通搜索在同预算下没有取得的更低终值；必要条件预筛减少明显无效构造，并在部分预算受限路径上支持更多搜索推进。三者不能用一个节能百分比合并解释。[研究目标与范围][E31]

主要限制也已显现：24 Stage搜索全部受300秒预算截断；初始化准入和评价耗时波动可能改变交接初解；额外边接纳不保证最终胜出；参数为自设抽象模型，复评复用同一数值实现。C01已有78°C候选超温证据，但尚未建立多新根、较大规模的系统紧热验证。

阅读顺序：第2节统一术语，第3节查时间线，第4节理解每次转向的原因，第5—7节看结果与边界，第8节供接手会话使用。无需先读完整仓库。

## 2. 模型、版本和实例名称

### 2.1 科学问题与算法求解范围

数学问题允许跨场景共享设备部署，场景各自选择合法OPP和执行时刻；满足DAG、设备互斥、共享频率域、截止期及连续时间热安全，最小化加权系统总能耗。

第四章沿用第三章的模式响应、合法性、auto-L功耗账本、连续RC热模型及完整区间评价。共享频率域基准不能按CPU核重复计；场景独立从各自入口温度开始，零权场景也必须安全；评价覆盖完整窗口及空闲尾段。非抢占、执行中不迁移/换频，切换/传输附加开销按原模型假设处理。已有[模型审计][E16]核对了实际运行依赖；它不等于独立证明第三章最新MILP的每一条线性化。

当前分解为：**初始化可选择及调整共享部署；交接后固定具体设备，优化场景内OPP、资源次序和有限时序模板。** 不能写成全过程持续联合搜索跨场景部署，也没有全局最优保证。

### 2.2 方法词典

| 名称 | 实际含义 | 与其他版本的关系 |
|---|---|---|
| 原C | 早期两阶段、固定设备/暖锚的MILP邻域方法，第二阶段带预消元 | 是历史方法；不等于后来的ON，更不等于ON-P |
| 增强HEFT / I0 | 原安全构造及共享设备、OPP、单步延后质量调整 | 基线已含节能调整，不能描述为纯最快结束构造 |
| I1 | 保留原构造；原默认/H/M/L均失败后最多一次期限/稀缺度排序后备；保留设备/OPP质量调整，省去单步延后，加入180秒新工作准入 | 改的是初始化，不改ON搜索；旧I0及结果保留 |
| 原ON | 从同次完整安全初解出发，以正活动能量节省模式为目标，联合关联OPP和主要资源次序；超期时最多额外反转一条阻塞路径资源边 | 额外边是联合候选的一部分，接纳后还会重新搜索 |
| OFF | 关闭ON的额外阻塞边步骤 | 仍有普通联合重构，不能当成“无搜索” |
| ON-P | 原ON加结构必要条件预筛；P仍是研究代号 | I1、搜索规则、合法候选排序、完整评价及严格接纳沿用冻结版本 |
| OFF-P | OFF加共同基础预筛 | 关闭额外边，所以没有逐条额外边预筛；不与旧OFF混名 |
| 原SA | 原生初始化、合法设备迁移、频档/顺序邻域、概率上坡接纳和最佳安全档案 | 早期正式比较保留其原生策略，未强制使用ON的增强HEFT初解 |

后续四臂写作“HEFT-I1、原ON、ON-P、OFF-P”时，四臂均独立调用同一I1；原ON指关闭预筛的搜索核心，不表示重新采用I0。

完整安全且`new.upper < incumbent.lower`才接纳；显示值相等不能代替精确区间判平。未决、结构拒绝、构造失败、超温和技术故障分别记录。完整SAFE是该仿真模型及数值合同下的证据，不是硬件实测。

### 2.3 实例身份

| 名称 | 来源及用途 | 不能怎样计数 |
|---|---|---|
| R1/R2/R3/R5 | 原合成目录中的样本编号，主要用于开发机制和早期比较；AB/AC每场景6 Stage | 不是四个平台或四个独立任务族 |
| C01 | 第三章已有显式DAG共同输入的C1/C2投影；每场景6 Stage、8个部署身份、12次执行、72模式、230ms窗口 | 接线阶段已经看过，不是严格盲测；固定周期工作包也不是新调度方法实验 |
| U01/U02 | 首批新参数根，比较6→12 Stage；U02–12后来用于诊断和设计I1 | 之后的P3/I1比较是已见实例验证 |
| U03/U04 | I1/ON冻结后的新12 Stage根，再扩展24 Stage；后来用于发现和开发ON-P | 不能再作为ON-P严格未见泛化证据 |
| U05/U06 | ON-P冻结后的新12 Stage根，随后扩展到24 Stage | 24 Stage是同根规模扩展，不再算两个全新根 |
| U07—U10 | 预登记后直接生成的四个新24 Stage根，2场景、50°C | 四臂共16次调用仍只有4个新根；完成后也成为已见根 |

“Stage”均指每场景规模。两场景下24 Stage对应48次执行，不是全问题仅24次执行。规模扩展同时增加工作量并按原规则推导期限/窗口，绝对能耗增长不能直接解释为能效退化。

## 3. 时间线：做过什么、当时回答了什么

日期优先按报告/原始执行记录；提交列是归档节点，不自动等同运行日期。尤其C01温度配对实际执行于11月8日，11月9日归档；R2/R5部分分析报告标11月7日而对应提交按北京时间已到11月8日。同一天的先后依据冻结—执行—归档链，不能仅按目录名排序。

前史属于第三章与第四章的接口：[K179方案报告][E01]回顾P0（H响应/50°C）、P1（R响应/50°C）、P2（H响应/78°C）的15对原C/HEFT，均有完整SAFE；C能耗更低分别为4/5、2/5、1/5，而HEFT在15题均更快。这些结果解释为何转向新的启发式；本文件不重新审计全部第三章模型/求解器实验，也不将其并入U系列账本。

| 阶段与时间 | 已完成内容 / 真实方法数 | 当时得到的结论 | 归档与证据 |
|---|---|---|---|
| T01 · 10-23 | 从原C/HEFT旧结果提出第四章联合重构方案；0新方法 | 原C有质量潜力，也有闭锚和原生求解成本；选择同次HEFT安全起点、直接图重建 | [abe7fa8][Cabe7fa8]；[方案][E01] |
| T02 · 10-23 | K180/181接口、人工检查和四方法准备；0真实比较 | 完整SAFE继承、频域冲突、拓扑起点传播及单根预算接通；模拟不当节能证据 | [8501ecd][C8501ecd]、[5120431][C5120431]；[接口记录][E40] |
| T03 · 10-23 | 八槽首槽原R1/C发生MATLAB启动故障，停批；宿主检查后续接剩余7方法＋7复评 | R1成对图仅改善0.003152%，R3无改善；故障首槽不补跑，不能拿历史C补成公平八项 | [fbe6900][Cfbe6900]、[8d57ad1][C8d57ad1]；[故障][E02]、[七槽结果][E03] |
| T04 · 10-24 | 固定部署/跨资源阻塞只读审查；阻塞边接口103项纯检查，0真实热评价 | R1降档同时受NPU次序和CPU后处理次序阻塞；决定每候选最多一条额外边 | [b4bd8e4][Cb4bd8e4]、[ce5d2d1][Cce5d2d1]；[审查][E04]、[实现][E05] |
| T05 · 11-07 | R1/R3原ON/OFF，4方法＋4复评 | R1 ON较OFF节能2.303917%；R3无正活动节省目标，正常保留初解 | [9c4e4a6][C9c4e4a6]；[机制报告][E06] |
| T06 · 11-07 | R2/R5各HEFT/OFF/ON，6方法＋6复评；后续算法分析和SA适配 | ON较OFF分别10.063249%、5.097310%；收益含后续普通调整 | [d47bfda][Cd47bfda]、[183701e][C183701e]；[六槽][E07]、[分析][E08] |
| T07 · 11-08 | R2/R5各HEFT、ON、SA101—105，14方法＋14复评 | 两例ON终值低于HEFT及全部SA种子；较早达到中等质量并非全面更快 | [0a01ae3][C0a01ae3]；[正式比较][E09] |
| T08 · 11-08 | C01组件迁移2候选评价；30秒生命周期3方法＋3复评；再正式7方法＋7复评 | 显式DAG接入；正式ON较HEFT节能4.958669%；工程检查与正式比较分开 | [0a01ae3][C0a01ae3]；[迁移][E10]、[接线][E11]、[正式][E12] |
| T09 · 11-08执行 / 11-09归档 | C01原ON的50/78°C各1方法＋复评 | 热组初始化出现4份实际超温见证；最终SAFE，但ON后续改善为0 | [0a82ae1][C0a82ae1]；[温度配对][E13] |
| T10 · 11-10 | 固定终解工作包：7终解整理、14场景轨迹/56节点均温、9固定周期后验；0新调度搜索 | 9周期配置7安全2超温；提供固定排程温度证据，不是周期调度优化收益 | [052c0b0][C052c0b0]；[A/B/C工作包][E14] |
| T11 · 11-12 | U01/U02×6/12 Stage×HEFT/ON，8方法、6成功复评 | 两个U02–12方法均无安全初解；其余6成功。覆盖和初始化成本先成为问题 | 冻结[7ae56e9][C7ae56e9]→结果[87f7692][C87f7692]；[预实验][E15] |
| T12 · 11-12 | P1/P2：重建四次失败，保存全H参考完整诊断1次；成本只读分析 | 全H参考SAFE，证实有安全见证而旧构造未找到；原评价耗初始化约96.77% | [3fb632a][C3fb632a]；[诊断][E17] |
| T13 · 11-12 | P3：U01–6/12、U02–6原ON/OFF，6方法＋6复评 | U01–12 ON较OFF节能3.731473%；两个6 Stage组净差0 | 冻结[fd031f8][Cfd031f8]→结果[12b1296][C12b1296]；[P3][E18] |
| T14 · 11-12 | I1最小提案、实现/82项检查；5初始化方法＋5复评（4 I1、1 I0） | U02–12恢复覆盖；U01–12同批I1少12次评价、初解能耗略增0.016609% | 方案[4c98f68][C4c98f68]→冻结[4ffbe8e][C4ffbe8e]→结果[13f7ab7][C13f7ab7]；[方案][E19]、[五次验证][E20] |
| T15 · 11-13 | U01/U02–12 ON-I1/OFF-I1配对，4方法＋4复评 | U01保持3.731473%净收益；U02终值相同，但搜索完整评价45对85次 | 冻结[b6c1a6f][Cb6c1a6f]→结果[6d67cf2][C6d67cf2]；[配对][E21] |
| T16 · 11-13 | 全新U03/U04–12各HEFT/OFF/ON，6方法＋6复评 | I1后备均成功；ON/OFF同终值，额外边方向全被结构拒绝 | 冻结[553f60b][C553f60b]→结果[d7ecc1b][Cd7ecc1b]；[新根12][E22] |
| T17 · 11-13 | U03/U04扩24，各HEFT/OFF/ON，6方法＋6复评 | 4搜索臂全耗尽预算；U03同初解ON落后OFF，U04初解不同 | 冻结[5fa8637][C5fa8637]→结果[581a77e][C581a77e]；[原24][E23] |
| T18 · 11-13 | 只读搜索路径、无效构造、初始化准入诊断；0新热实验 | 定位额外邻域成本、路径变化与180秒截断；提出必要条件预筛 | [ac7d03b][Cac7d03b]；[路径诊断][E24] |
| T19 · 11-13 | ON-P正确性：74项检查、归档合法构造/候选顺序核对；0真实方法/热评价 | 只删可证不可行方向；拒绝一条边不能误删其他修复方向 | 冻结[63d2dc9][C63d2dc9]；[正确性][E25]、[规则][E32] |
| T20 · 11-13 | U03/U04–24的ON/ON-P/OFF/OFF-P，8方法＋8复评 | 四组预筛配对构造成本下降；ON-P仍两次略逊OFF-P；U03原ON初解不同 | [69a4abf][C69a4abf]；[成本消融][E26] |
| T21 · 11-13 | 新U05/U06–12四臂，8方法＋8复评 | U05 ON-P较OFF-P节能8.811756%；U06同终解；原ON/ON-P同路径终值 | 预登记[cde5e80][Ccde5e80]→结果[e9d08fe][Ce9d08fe]；[新根12][E27] |
| T22 · 11-13 | U05/U06扩24四臂，8方法＋8复评 | ON-P较OFF-P节能7.452020%/2.954392%；较原ON一胜一平，6搜索臂全耗尽预算 | 冻结[a16515a][Ca16515a]→结果[2ad44d4][C2ad44d4]；[扩展24][E28] |
| T23 · 11-13 | U01—U06九批59方法只读综合；冻结研究目标 | 覆盖、质量、效率分别建证；已有负结果与版本差异必须保留 | [ef2550b][Cef2550b]；[综合][E29] |
| T24 · 11-13 | 预登记全新U07—U10直接24 Stage，四臂16方法＋16复评 | 全SAFE；ON-P较OFF-P四胜，较原ON三胜一平，U08比较含初解差异 | 预登记[6ef60be][C6ef60be]→结果[0de4d19][C0de4d19]；[预登记][E33]、[报告][E30] |
| T25 · 11-14 | 本时间线与思路回顾；0新实验 | 让后续会话能区分历史状态、当前证据与尚未开展事项 | 本文件 |

T11—T24中，U系列有9批既有方法实验加1批U07—U10，共75次方法调用、73份最终SAFE及完整复评通过；2次失败均为原U02–12/I0。此统计不含P1诊断、纯检查、重复读取，也不包括更早R/C01及固定周期工作包，不能称为“第四章总调用数”。[旧59次指标][E35]、[新16次指标][E37]

## 4. 思路演变：为什么做下一项实验

### 4.1 从扩MILP邻域，转向安全初解上的联合重构

早期原C在部分R样本上优于HEFT，也暴露了固定暖锚和原生求解成本。仅扩大开放选项可能增加求解时间，却没有带来更低完整安全能量。因此10月23日选择从同次增强HEFT的最佳完整SAFE出发，用资源图直接构造合法起点。[E01]

最初的单Stage/成对图结果并不强：R1成对仅从0.881087997降到0.881060223 J，R3没有改善。这个结果促使后续审查实际阻塞关系，而没有以“联合搜索已显著有效”结束。[E03]

### 4.2 从成对OPP/主次序，转向跨资源阻塞反馈

R1的目标NPU任务降档，会延长执行。只调整NPU次序，保留CPU后处理原次序，仍会超期；先单独改CPU次序又可能略增能耗，被严格下降接纳拒绝。于是把降档、主要资源次序及阻塞路径上的另一条资源关系放进同一个完整候选，维持完整SAFE和严格下降规则。[E04]

R1/R2/R5验证了这种联动可以带来收益；R3没有正活动节省目标而退出，是声明邻域的正常边界。接受后普通调整可能继续节能，因此“允许额外边后的轨迹净差”和“单条边自身能量贡献”必须分开。[E06][E07]

### 4.3 从开发例成功，转向共同输入、温度和新根

R2/R5的正式HEFT/ON/SA比较检验端到端质量；C01检验从三节点链迁移到显式DAG。SA保留原生策略，公平约束为同输入、合法域、评价和单次总cap，不能为了初解相同而改写SA。[E09][E12]

C01温度配对进一步表明：热启动会改变候选可行性，但原ON在78°C没有新增改善。11月10日工作包补充的是固定终解轨迹、均温和周期后验，不是新增热引导调度机制。[E13][E14]

开发例和工程输入已经被看过，随后才预先固定U01/U02，检查新参数和6→12 Stage成本；不将R目录号或C01工程接入冒充独立泛化。[E15]

### 4.4 从U02–12失败，转向I1覆盖与初始化成本

首批U02–12的HEFT/ON均在初始化失败，ON根本没有进入搜索。P1重建原四构造，随后独立评价保存全H参考并得到SAFE，确认“存在安全见证，有限构造未找到”；参考没有注入正式初解。[E17]

P2又发现初始化成本主要在反复完整电热评价。P3先用原ON/OFF确认搜索机制在U01–12仍有独立净收益，再单独建立I1：仅追加一次排序后备，并省去低收益尾部延后、设置180秒准入，不改ON搜索。[E18][E19]

I1五次初始化验证同时保留了覆盖改善和初解质量代价。随后配对不是重复证明初始化，而是检验“换了初解器以后，ON是否仍能搜索并节能”。U02–12最终ON/OFF相同，恰好说明覆盖恢复不等于额外终值收益。[E20][E21]

### 4.5 从12 Stage自然结束，转向24 Stage预算与路径诊断

U03/U04–12的覆盖正常，ON/OFF终值相同；扩到24 Stage后所有搜索用尽预算。U03同初解下ON较OFF能耗高3.661935%，是明确负结果；U04有初始化截断差异，不能作纯机制归因。[E22][E23]

只读轨迹诊断发现，额外邻域不仅耗构造时间，还改变后续普通机会；完整候选哈希破同分也可能使其他场景的普通次序变化。U04原初始化前49个候选相同，评价耗时波动造成OFF多准入两次，解释了初解差异。没有据此直接更改180秒或增加I2。[E24]

### 4.6 从明显无望构造，转向ON-P必要条件预筛

ON-P不改变能量目标或热精度，而是在固定状态、设备、模式和模板下，前移精确的DAG时间界、不可修复成环及单边修复必要条件。基础组合整体跳过需要证明允许的额外边也救不了；某条额外边失败只能跳过该方向。[E32]

先用人工小域和归档合法构造检查“不会误删合法候选、不会改变原排序”，再做四臂成本消融。74项检查及428个归档合法构造保持，支持结构保持性；8次开发回归支持成本收益，同时保留ON-P略逊OFF-P、初解不同和预算未决。[E25][E26]

### 4.7 从开发回归，转向冻结方法的新根重复性

U03/U04用于发现预筛，不能再承担新方法的严格新根验证。于是先固定U05/U06–12，得到一正一零的机制结果，再扩24 Stage观察预算推进。最后预登记U07—U10四个新24 Stage根及均衡四臂顺序，不筛选或替换。[E27][E28][E33]

U07—U10重复观察到预算内收益，但仍有原ON/ON-P平局、U08初解不一致及全体搜索预算耗尽。这支持保留方法并收敛证据，不支持逐例胜出、统计显著性或稳定总加速。[E30]

## 5. 关键结果：把正、零、负结果放在一起

### 5.1 早期正式方法比较

| 已见输入 | HEFT J | 原ON J | 原SA五种子中位数 J | ON较HEFT |
|---|---:|---:|---:|---:|
| R2 | 0.955459935 | 0.859309627 | 0.878889762 | 10.063249% |
| R5 | 0.917706681 | 0.856824091 | 0.883404202 | 6.634210% |
| C01 | 0.882913166 | 0.839132424 | 0.913740456 | 4.958669% |

三组来自各自同批正式比较，单次上限300秒，分别14/7次运行及完整复评全通过。ON终值低于这些SA种子；R2有四个SA种子比HEFT更早达到HEFT终值阈值。不能只给最终能量就宣称所有早停时刻更快。C01正式批次没有OFF，整体节能不能全归于额外边。[E09][E12]

### 5.2 I1覆盖与质量

| 观察 | 结果 | 能支持的范围 |
|---|---|---|
| U02–12原四构造失败；全H诊断 | 参考完整SAFE，约2.984291955 J | 旧失败不是全局无解；参考不作为正式初解 |
| U02–12首轮I1 | 2.781秒首SAFE，最终初解1.854886335 J | 恢复这个已参与诊断的失败例 |
| U01–12同批I0→I1 | 83→71次评价；196.141→177.704秒；初解1.210275930→1.210476945 J | 少工作但能耗增加0.016609%；单次墙钟不证明稳定加速 |
| U01–12 ON-I1/OFF-I1 | 1.059929087 / 1.101013097 J | 保持原机制3.731473%净收益 |
| U02–12 ON-I1/OFF-I1 | 同为1.574570189 J；搜索评价45/85次 | 搜索有效，额外终值收益0；本次工作量不同 |

I1后备还在U03–12、U04–12/24、U06–24、U09–24、U10–24的保留轨迹中恢复SAFE。只有U02–12有对应整方法I0失败批次；其余主要证据为I1内部原四构造失败后第五次后备成功，不能虚构未运行的I0对照。[E20][E21][E22][E28][E30]

### 5.3 ON-P/OFF-P的全部既有配对

A=初解排程、能量区间与初始化候选序列一致；B=初解一致但初始化序列不同；C=初解不同，仅端到端比较；D=无完整SAFE。A仍存在墙钟与预算截断，不能解释为等成本或无噪声因果试验。

| 批次/条件 | 等级 | ON-P J | OFF-P J | ON-P较OFF-P节能 | 结果 |
|---|---|---:|---:|---:|---|
| 开发 U03–24 | A | 3.985262908 | 3.984435686 | -0.020761% | 负 |
| 开发 U04–24 | B | 4.482792705 | 4.482247908 | -0.012155% | 负 |
| 首次新根 U05–12 | A | 1.375553614 | 1.508476921 | 8.811756% | 胜 |
| 首次新根 U06–12 | A | 1.795047363 | 1.795047363 | 0 | 平 |
| 扩展 U05–24 | B | 3.400087806 | 3.673864963 | 7.452020% | 胜 |
| 扩展 U06–24 | B | 3.640077098 | 3.750893175 | 2.954392% | 胜 |
| 新根 U07–24 | B | 3.448147974 | 3.729898465 | 7.553838% | 胜 |
| 新根 U08–24 | A | 5.463386563 | 5.661972938 | 3.507371% | 胜 |
| 新根 U09–24 | A | 3.988236342 | 4.205818036 | 5.173350% | 胜 |
| 新根 U10–24 | A | 3.047872878 | 3.402778352 | 10.429873% | 胜 |

描述性合计7胜1平2负；包含开发例和同根多规模，仅8个不同参数根，不能当作10个独立盲测样本计算泛化胜率。原ON/OFF的旧11组是另一版本系列：3胜5平3负，保留在[旧综合表][E29]，不能改名合并成ON-P/OFF-P。

原ON/ON-P共10组为ON-P六胜四平；U03开发组及U08新24组初解不同。去掉这两组，剩余八组四胜四平。该观察不构成ON-P普遍不劣的证明。[旧配对数据][E36]、[新根分析][E34]

### 5.4 最后一批四新根的四臂终值与成本

| 新24 Stage根 | HEFT-I1 J | 原ON J | ON-P J | OFF-P J | ON-P较同批HEFT |
|---|---:|---:|---:|---:|---:|
| U07 | 5.056740954 | 3.579157948 | 3.448147974 | 3.729898465 | 31.810864% |
| U08 | 6.781808841 | 5.756417971 | 5.463386563 | 5.661972938 | 19.440570% |
| U09 | 5.675947563 | 3.988236342 | 3.988236342 | 4.205818036 | 29.734440% |
| U10 | 4.887302451 | 3.076578241 | 3.047872878 | 3.402778352 | 37.636909% |

四臂交接初解在U07/U09/U10相同。U08原ON、HEFT、ON-P/OFF-P分别6.792667166、6.781808841、6.694812589 J；故ON-P较原ON的5.090517%终差属C级，较自身初解的18.393734%改善也不同于较HEFT的19.440570%。

16次首SAFE为5.266—8.531秒，均触发180秒准入，180.781—184.766秒交接；12搜索臂全耗尽300秒。方法内855次评价含845次完整SAFE（初始化607、搜索238）及10次预算未决；另2构造预算中断，32次原初始化构造失败。全部保留，无重试/替换。完整SAFE单次均值约3.865—6.108秒，搜索电热占38.4%—87.1%；U08原ON仅构造就耗70.720秒。

不能用“预筛多少”直接替代“省了多少热评价”。U07—U10两P臂合计拒绝2460基础、307额外方向，单臂预筛0.516—0.893秒；其中很多方向原构造器本来也会拒绝。具体证据包括：

| 原ON/ON-P共同路径 | 共同接纳数 | 共同路径构造+筛选s：原→P | 终值现象 |
|---|---:|---:|---|
| U07–24 | 14 | 23.047→14.282 | ON-P随后多3次普通接纳 |
| U09–24 | 17 | 18.515→12.957 | 同最终排程和区间，预筛终值收益0 |
| U10–24 | 23 | 13.358→10.589 | ON-P随后多3次普通接纳 |

共同路径总时间差还含评价/初始化波动。U08初解不同，不作同工作量成本归因。全部逐次指标、能耗—时间图和接纳哈希见[四根报告][E30]与[16次指标][E37]。

## 6. 温度证据究竟到哪一步

**C01热启动已有真实仿真见证。** 50/78°C最终能耗分别0.839132424261/0.908129637265 J，最终峰温上界53.530889/78.461184°C。78°C四个超温候选全部出现在初始化；其中一个与50°C相同候选在GPU0、96.1ms处有温度区间下界80.625951°C。原HEFT后备得到安全解，热组ON增量收益0。它支持温度改变候选可行性，未支持新增ON热修复收益。[E13]

**固定周期证据属于后验支线。** 11月10日对既有固定时间表核对9个周期配置，7安全、2超温；全H/AB在75ms第21轮、80ms第29轮出现超温点，85/90ms对应配置安全。没有在75ms配置运行约87ms才完成的低能模板，不能跨周期宣称算法热优化收益。A/B/C工作包中的字母也不是原C方法或第三章MILP A/B/C。[E14]

**U系列50°C规模实验的热约束仍宽松。** 最后四根全部保存评价中的最高峰温约70.323636°C、最高最终峰温66.652048°C，低于80°C。不能把较低能量自动称为紧热性能提升，也不能因多数不活跃而说温度约束从未改变可行性。

所有证据属于抽象四节点RC及温度相关功耗模型；没有真实CPU/GPU/NPU阶段级标定。每次新进程完整复评检查候选保存、安全和能量区间一致性，但复用同一实现，不是独立数值实现验证。

## 7. 当前可以写出的结论与尚缺证据

| 证据链 | 已有支持 | 仍不能推出 |
|---|---|---|
| 可行性 | U02失败诊断与安全参考；I1后备在多个条件恢复完整SAFE；U07—U10全覆盖 | 任意可行实例都能初始化、一般成功率提升、构造失败等于全局无解 |
| 节能质量 | 开发例与部分新根中ON/OFF或ON-P/OFF-P有严格区间净差；完整轨迹可解释联合重构 | 所有实例胜出、任何普通搜索都达不到、单条边独立贡献等于整体节能率 |
| 计算效率 | 必要条件只拒绝可证无效结构；共同前缀构造成本下降；部分预算内搜索推进更多 | 稳定总加速、节省筛选数等量的热评价、全邻域已搜完或复杂度阶已证 |
| 热安全 | 全场景全窗口连续包络及超温点见证；C01热组和固定周期后验 | 硬件有效性、系统紧热新根泛化、ON-P新增热引导收益 |
| 比较可信度 | 预登记、全结果/失败保留、输入与源码哈希、独立方法根及逐次复评 | 4根足够显著性、同根重复规模彼此独立、同核复评排除共同数值错误 |

U系列75方法的描述性账本：10个根、16种根×规模条件，73最终SAFE+复评，2个I0无初解；4291次方法评价=4271完整SAFE+20预算未决，不含复评及诊断。I0为13/15、I1为60/60，但队列输入与用途不同，不能作受控成功率比较。I1–12的14搜索均自然完成；I1–24的30搜索全部预算耗尽，38次I1–24调用（含HEFT）全部触发180秒准入。以上按[旧59次][E35]与[新16次][E37]相加，不把诊断/模拟/组件检查扩大为独立样本。

数值区间是计算包络，不是统计置信区间。当前不报告p值；不将单次墙钟、不同初解、不同规模或不同物理条件的结果拼成统一加速/节能率。失败实例没有按0能耗代入，也未从覆盖分母中删除。

## 8. 给接手会话的研究交接

1. **核对版本。** 先查远程第四章分支与本文件证据快照是否变化，再读[研究状态](../../RESEARCH_BRIEF.md)。旧README和报告里的“下一步”“尚未执行”是当时状态；例如[范围文件][E31]中的四新根待运行项已被T24完成，不应再次安排。
2. **保留现有方法与全部结果。** I1核心实现从4ffbe8e开始，ON-P预筛从63d2dc9冻结；6ef60be是最后四新根的入口/预登记快照，不是重新设计算法。ON-P仍为研究代号。
3. **已完成的三类验证不重做。** 旧失败诊断、I1首轮/配对、ON-P正确性与开发成本消融均已归档；U05/U06的12→24和U07—U10新24也已完成。不要为了得到相同初解或更好结果补跑。
4. **下一研究顺序是规划，不是已完成结果。** 既有用户路线为：机制证据收敛后，单独研究公平的初始化/搜索预算分配，再分别研究4场景、合理紧热条件、SA正式比较及第三章小规模精确质量参照。90/120/180秒是待预登记方案；本轮没有改预算或设计I2。不能降低HEFT初解质量后把扩大百分比全算作ON创新。
5. **新根身份会随开发改变。** U01—U10均已见；若用它们调机制，后续未见泛化需重新预登记参数根。同根24 Stage不是新的独立根。
6. **不要混入第三章同名开关。** 2026-11-14远程另一个研究分支`chapter4/r2-r5-validation-20261107`已到`a071edd`，最近D285为[第三章完整R1 CPLEX A/B/C实验][E38]。其600/550秒、原生gap、约简ON/OFF等概念不属于这里的300秒第四章阻塞边ON/OFF。主分支当时为`92cd9f1`，不代表本研究分支已合入主线。
7. **先做归因再增加机制。** 遇到失败先分初始化覆盖、结构合法性、连续评价未决、总预算及邻域范围；新增机制需要独立版本与受控比较。旧负结果不能由新正结果覆盖。

本文件是研究记录回顾，不是第四章正文，也不增加科研运行额度。后续实验范围按新的明确任务确定。

早期R2/R5/C01的原ON—SA正式比较已经完成；后续规划中的SA是面向I1/ON-P及新规模条件的新比较，不能写成“SA从未比较过”，也不能把旧结果直接充当新版基线。

## 9. 证据导航与复查口径

正文所有[E]链接均为固定提交下的原报告/指标；[C]为历史提交。完整原始输入、源码快照、评价JSONL、接纳轨迹、停止原因及post回执沿各报告链接进入。早期Cloud与后期Windows墙钟不直接比较；自然结束不强制补满预算；180秒是新工作准入而非初始化硬停止，post使用独立预算。

本次只读复核包括：远程分支/提交、历史方案和早期报告、9批59次综合指标、新16次指标及配对分层；新计算仅为描述性加总。75/73、4291/4271、ON-P两种配对胜平负均从这些表重新加总核对；没有重新调用旧分析器、调度器或电热核。更早R/C01/工程故障/固定周期分别保留，不强造一个跨阶段统一总样本。

---

[E01]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E7%AE%97%E6%B3%95%E6%96%B9%E6%A1%88%E8%AE%BE%E8%AE%A1%E4%B8%8E%E5%8F%AF%E8%A1%8C%E6%80%A7%E5%88%86%E6%9E%90.md
[E02]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/execution_report01/summary.md
[E03]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/resume_analysis01/summary.md
[E04]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E5%9B%BA%E5%AE%9A%E9%83%A8%E7%BD%B2%E4%B8%8E%E8%B7%A8%E8%B5%84%E6%BA%90%E9%99%8D%E6%A1%A3%E8%81%94%E5%8A%A8%E5%AE%A1%E6%9F%A5.md
[E05]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/blocking/README.md
[E06]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/cloud_mechanism_20261107/summary.md
[E07]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/validation_execution_20261107/summary.md
[E08]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/algorithm_analysis_20261107/summary.md
[E09]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/main_comparison_20261108/summary.md
[E10]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/c01_migration_20261108/summary.md
[E11]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/c01_lifecycle_20261108/summary.md
[E12]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/c01_formal_20261108/summary.md
[E13]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/thermal_pair_20261108/summary.md
[E14]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/evaluation_workpackages_20261110/SUMMARY.md
[E15]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/unseen_scaling_20261112/summary.md
[E16]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/unseen_scaling_20261112/preflight/model_audit.md
[E17]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/p1_p2_diagnostics_20261112/summary.md
[E18]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/p3_unseen_ablation_20261112/summary.md
[E19]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/i1/PROPOSAL_20261112.md
[E20]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/i1_initialization_20261112/summary.md
[E21]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/i1_paired_20261113/summary.md
[E22]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/unseen_i1_20261113/summary.md
[E23]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/scale24_i1_20261113/summary.md
[E24]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/scale24_search_diagnostic_20261113/summary.md
[E25]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/onp_correctness_20261113/summary.md
[E26]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/onp_cost_ablation_20261113/summary.md
[E27]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/onp_unseen_20261113/summary.md
[E28]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/onp_scale24_20261113/summary.md
[E29]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/synthesis_u01_u06_20261113/summary.md
[E30]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/onp_new24_20261113/summary.md
[E31]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/RESEARCH_SCOPE.md
[E32]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/onp/README.md
[E33]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/onp_new24/PREREGISTRATION.md
[E34]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/onp_new24_20261113/analysis.json
[E35]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/synthesis_u01_u06_20261113/runs.csv
[E36]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/synthesis_u01_u06_20261113/pairs.csv
[E37]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/results/onp_new24_20261113/all_metrics.csv
[E38]: https://github.com/YBEMR/paper/blob/a071eddb3ed93cd3b47056fc539bdb8ccbcfbadc/research/chapter3_cplex_ABC_execution_v2_20261113/REPORT.md
[E40]: https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/README.md
[C052c0b0]: https://github.com/YBEMR/paper/commit/052c0b01c9a840c2b5b6ff8018afcaf08654a24a
[C0a01ae3]: https://github.com/YBEMR/paper/commit/0a01ae35320507618df58dcb19f111548eafc971
[C0a82ae1]: https://github.com/YBEMR/paper/commit/0a82ae1cd2f6121609616e7babea76d79d6e0c0a
[C0de4d19]: https://github.com/YBEMR/paper/commit/0de4d191966294dc673c21ed244616f1b5a6a85c
[C12b1296]: https://github.com/YBEMR/paper/commit/12b1296e9089c9528e86912b6c4b3a2d030beada
[C13f7ab7]: https://github.com/YBEMR/paper/commit/13f7ab720bae62664e92e8d7b34f41bfa62eece1
[C183701e]: https://github.com/YBEMR/paper/commit/183701e3394454ad588f538085bc06f08e7621a3
[C2ad44d4]: https://github.com/YBEMR/paper/commit/2ad44d4ec153b6a518de8df13d4c632d6849d8fa
[C3fb632a]: https://github.com/YBEMR/paper/commit/3fb632a5f3b38a543e6168f89fccf09b4ea9ca1e
[C4c98f68]: https://github.com/YBEMR/paper/commit/4c98f681ae499bd8f0cd081bcc99a0e9d8281f5b
[C4ffbe8e]: https://github.com/YBEMR/paper/commit/4ffbe8e952cf6ce9fa86cf2aba4606b3978098d5
[C5120431]: https://github.com/YBEMR/paper/commit/51204311ad665107a38f716b52cc65b9eed40845
[C553f60b]: https://github.com/YBEMR/paper/commit/553f60b9991d923234ef14671a11a31915b3ec68
[C581a77e]: https://github.com/YBEMR/paper/commit/581a77ed8dafb4099d4acd186c554db03cb23969
[C5fa8637]: https://github.com/YBEMR/paper/commit/5fa8637fac2f3fba95d1c31180df18c65f11ca2f
[C63d2dc9]: https://github.com/YBEMR/paper/commit/63d2dc9f8109a7aa9e0ca18dc950c99572e9f8fb
[C69a4abf]: https://github.com/YBEMR/paper/commit/69a4abf487e7e3ed28f7bb8332449b73f927dabd
[C6d67cf2]: https://github.com/YBEMR/paper/commit/6d67cf2538280c3fee4ab5b7879570b204bb6224
[C6ef60be]: https://github.com/YBEMR/paper/commit/6ef60beb5a8b84dbf4e6b6c4d1deb1004edffc4c
[C7ae56e9]: https://github.com/YBEMR/paper/commit/7ae56e92e9693a7c1ae109cdb98010ca887d2f90
[C8501ecd]: https://github.com/YBEMR/paper/commit/8501ecd718d51575206237eba950ad42a4fa8e36
[C87f7692]: https://github.com/YBEMR/paper/commit/87f7692fad9e3ef94bdf92dfaabd695ac6b5a609
[C8d57ad1]: https://github.com/YBEMR/paper/commit/8d57ad11d254e8cb1d5d04f4d367c8a8a2d99a00
[C9c4e4a6]: https://github.com/YBEMR/paper/commit/9c4e4a621a6b4df71aba0d98fa39c03653395c35
[Ca16515a]: https://github.com/YBEMR/paper/commit/a16515a24fd41747f44faae0a75bcb8365d8cffc
[Cabe7fa8]: https://github.com/YBEMR/paper/commit/abe7fa861793fc9adf1c3fe5b31872fd2dc2715e
[Cac7d03b]: https://github.com/YBEMR/paper/commit/ac7d03b0440bec8a50ce24cf597a95fd492372c4
[Cb4bd8e4]: https://github.com/YBEMR/paper/commit/b4bd8e4c9432a474e0b95ca11f7e98a002380c12
[Cb6c1a6f]: https://github.com/YBEMR/paper/commit/b6c1a6f4cee8f05b78bdc16c4b642fcc3afa1342
[Ccde5e80]: https://github.com/YBEMR/paper/commit/cde5e801a26f3980babaf7110a485bffa62f3624
[Cce5d2d1]: https://github.com/YBEMR/paper/commit/ce5d2d19a44b354277f05519b7ef1f78bf7fb314
[Cd47bfda]: https://github.com/YBEMR/paper/commit/d47bfda700ce76df31d9aae0aea97d01279b501f
[Cd7ecc1b]: https://github.com/YBEMR/paper/commit/d7ecc1b4ed86d2d8aabece01337c6167c6291f43
[Ce9d08fe]: https://github.com/YBEMR/paper/commit/e9d08febc773b20bd3663f4e9da7259b2a65d3fe
[Cef2550b]: https://github.com/YBEMR/paper/commit/ef2550bef69e71bf975dce85edec29d355b9842d
[Cfbe6900]: https://github.com/YBEMR/paper/commit/fbe6900b6c06e2ff23e425b2f5252cc8c25e5105
[Cfd031f8]: https://github.com/YBEMR/paper/commit/fd031f852b480aeccd6f986bb652cadfb1feba01
