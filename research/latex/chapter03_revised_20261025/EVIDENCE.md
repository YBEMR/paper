# 第三章实验数据与写作依据

本文件用于追踪实验依据，不是论文正文。数值均来自归档仿真、数学见证或独立研究实验。本次只整合提交`1cbb3559`的E1--E4既存回执并修改论文LaTeX、图形，不启动新的规划、MILP或热积分。E1--E4的六批研究与K.194/K.196及P0--P2正式120次调用分别计数。

| 使用位置 | 数据和论据 | 仓库来源 |
|---|---|---|
| 整体MILP初始化SAFE来源、HEFT适配及实验方法边界 | 15个整体MILP均无预算内整数候选，最终SAFE保留于初始化 | [a983bbf写作修改建议](../../第三章ec4c806_独立写作修改建议_20261025.md) |
| 参数复现与五个负载变体 | 完整OPP、Stage响应、RC、β=1.3、H02特殊预算和auto-L历史配置区分 | [实验输入与复现口径](EXPERIMENT_INPUTS.md) |
| 章节贡献和写作边界 | auto-L、P0/P1/P2、H02、C19和反馈未触发 | [367cd6e正文修改意见](../../第三章正文修改意见_交chat主线写作_20261024.md) |
| 3.7.1、3.7.4 | 正式P0、P1、P2共120次调用、15个条件配对、方法时钟和能量排序 | [120次综合分析](../../第三章P0-P2_120次正式实验_综合分析与论文正文初稿_独立审查_20261022.md) |
| 3.7.1 | CPU1/CPU2共享域、GPU0/NPU0、OPP和四热节点等抽象参数 | [冻结仿真输入](../../chapter3_experiments/config_v01.json)（正式计算使用auto-L适配，裸配置旧hold字段不得覆盖正式策略） |
| 3.7.2 | 同一真实H模型下H/R规划信息对照；R1 H方案0.8810879973J、R方案0.9173594769J，R2轻微反向 | [H02受控对照](../../chapter3_experiments/results/response_information_resume01/summary.md) |
| 3.7.3 | C19同Stage模式、仅合法时序不同导致加权完整电热能量严格差>3.254mJ | [C19数学见证](https://github.com/YBEMR/paper/blob/db34b46bc2499fcd10f6f7ec6235cd0b6b89555a/research/hetero_thermal_pilot/C19_C12机制迁移与C17下界强化_面向主线7数学算法交接_20261022.md) |
| 3.7.3 | 相同R1 HEFT排程在P0/P2温度漏电项0.101350965→0.207116548J，17次调用热违规，最终P2全安全 | [P2归档](../../chapter3_experiments/results/p2_execution01/summary.md) |
| 3.7.3 | 52°C温限拒绝原H模板、改用M模板；外层反馈仍为0 | [K127热证据](../../chapter3_experiments/results/night_k127_run02/night_summary.md) |
| 3.7.3 新增温度记录图 | R1最终HEFT方案的P0/P2候选哈希相同；A+B场景0ms入口及14个后验温度记录点，不能替代连续热检查 | [P0原始后验](../../chapter3_experiments/results/p0_execution01/calls/base__R1/heft/postcheck.json)、[P2原始后验](../../chapter3_experiments/results/p2_execution01/calls/initial_78__R1/heft/postcheck.json) |
| 3.7.4 | P0/R3、P1/R4等联动MILP弱于HEFT的具体边界和归因 | [论文结果综合审查](../../第三章P0-P2_120次正式实验_综合分析与论文正文初稿_独立审查_20261022.md) |
| 3.7.4 新增相对能量图 | 15个条件—变体组合的联动MILP和HEFT同输入SAFE能量配对，R1--R5非规模扫描 | [P0](../../chapter3_experiments/results/p0_resume01/analysis01/results40.csv)、[P1](../../chapter3_experiments/results/p1_execution01/analysis01/results40.csv)、[P2](../../chapter3_experiments/results/p2_execution01/analysis01/results40.csv) |
| 3.7.1、3.7.4 独立小域设置 | P0 R1/H完整AB/AC三Stage链及原电热模型保留；模式--起点冻结子集78项，期限排除6项，实际72个二元选项；独立枚举与整体MILP分开计费，不向求解器传递参照 | [K.193协议](../../完整链小域独立穷举与整体MILP正式实验协议_K193.md)、[K.195方法准备](../../完整链小域整体MILP执行准备_K195.md) |
| 3.7.4 有限域能量参照 | 1550份场景安排均SAFE；匹配274500份联合方案；0.986251057947 J，严格间隙约2.15e-29 J，epsilon=1e-6 J；独立枚举根耗时931.703 s | [K.194参照](../../chapter3_experiments/results/small_exact_execution01/reference.json)、[汇总分析](../../chapter3_experiments/results/small_exact_execution01/analysis.json)、[内部审查](../../chapter3_experiments/results/small_exact_execution01/internal_review.json) |
| 3.7.4 同域整体MILP | 同次初解1.088852027249 J，新整数完整SAFE为0.986251057947 J；300 s内改善9.422857%，88.437 s完成安全评价；一次post；求解器以时间上限退出，外层反馈0行 | [K.196总结](../../完整链小域整体MILP结果_K196.md)、[冻结分析](../../chapter3_experiments/results/small_whole_execution01/analysis.json)、[完整后验](../../chapter3_experiments/results/small_whole_execution01/postcheck.json)、[独立复核](../../chapter3_experiments/results/small_whole_execution01/internal_review_k196.json) |

| 3.7.1 E1--E4实验总设计 | 六批独立HEFT适配版实验，17次规划／15次独立后验，15安全／2无完整候选，589份保存的规划内部候选评价，不属于正式120次或小域MILP实验 | [E1--E4交接](https://github.com/YBEMR/paper/blob/1cbb3559a74cd42e1c382f1cb772040429440857/research/e1_e4_validation/E1-E4_证据汇总与写作交接.md)、[17槽索引](https://github.com/YBEMR/paper/blob/1cbb3559a74cd42e1c382f1cb772040429440857/research/e1_e4_validation/evidence/consolidation_e1_e4/evidence_index.json) |
| 3.7.2 E2设备可映射集合及图 | H/R1下映射CPU、CPU+GPU、CPU+NPU、全设备时U依次1.353653/1.213262/0.988809/0.881088 J；相对CPU-only低10.37126%/26.95252%/34.91035%，物理设备始终存在 | [E2原分析](https://github.com/YBEMR/paper/blob/1cbb3559a74cd42e1c382f1cb772040429440857/research/e1_e4_validation/results/e2_res_01/analysis.json)、[E2结果说明](https://github.com/YBEMR/paper/blob/1cbb3559a74cd42e1c382f1cb772040429440857/research/e1_e4_validation/E2_RESOURCE_EXPERIMENT_RESULTS.md) |
| 3.7.2 E3共享部署对照 | 共享/可分场景A部署均0.881087997281 J、四分项区间相同；仅AB的A.post从CPU1移至CPU2，L档115ms未变；不证明共享无一般代价 | [E3原分析](https://github.com/YBEMR/paper/blob/1cbb3559a74cd42e1c382f1cb772040429440857/research/e1_e4_validation/results/e3_deploy_01/analysis.json)、[E3结果说明](https://github.com/YBEMR/paper/blob/1cbb3559a74cd42e1c382f1cb772040429440857/research/e1_e4_validation/E3_DEPLOYMENT_EXPERIMENT_RESULTS.md) |
| 3.7.3 E1温度评分消融 | FULL与OMIT_TEMP在同真H、同连续热评价下分别比较R1与R3；真实能量差16.34362665/17.44241119微焦，完整评分低0.00185490%/0.00202285%，设备/OPP相同 | [E1原分析](https://github.com/YBEMR/paper/blob/1cbb3559a74cd42e1c382f1cb772040429440857/research/e1_e4_validation/results/e1_obj_01/analysis.json)、[E1结果说明](https://github.com/YBEMR/paper/blob/1cbb3559a74cd42e1c382f1cb772040429440857/research/e1_e4_validation/E1_OBJECTIVE_EXPERIMENT_RESULTS.md) |
| 3.7.4 E4a期限系数及曲线 | β=1.0/1.3/1.6，真实R1 H下安全U=0.936682145480/0.881087997281/0.860766924353 J；相对β1.0降低5.935220%和8.104694%，不是连续扫参 | [E4a原分析](https://github.com/YBEMR/paper/blob/1cbb3559a74cd42e1c382f1cb772040429440857/research/e1_e4_validation/results/e4_dead_01/analysis.json)、[E4a结果说明](https://github.com/YBEMR/paper/blob/1cbb3559a74cd42e1c382f1cb772040429440857/research/e1_e4_validation/E4_DEADLINE_EXPERIMENT_RESULTS.md) |
| 3.7.4 E4b原方法与单回退补充 | 原HEFT单请求安全U=0.881087997281 J；双请求无完整候选UNRESOLVED。新版本仅一次期限优先构造回退，在独立双请求配对中POST_SAFE U=1.444147367589 J；不可用于旧方法规模趋势 | [E4b原分析](https://github.com/YBEMR/paper/blob/1cbb3559a74cd42e1c382f1cb772040429440857/research/e1_e4_validation/results/e4_req_01/analysis.json)、[单回退分析](https://github.com/YBEMR/paper/blob/1cbb3559a74cd42e1c382f1cb772040429440857/research/e1_e4_validation/results/e4_df_01/readonly_analysis.json)、[失败原因](https://github.com/YBEMR/paper/blob/1cbb3559a74cd42e1c382f1cb772040429440857/research/e1_e4_validation/E4_REQUESTS_CONSTRUCTION_ANALYSIS.md) |

论文中的“低于”按保存的高精度安全能量区间作严格比较；表格中6位小数仅便于阅读，小于0.1%的差异不据此推断应用中的稳定优势。三批P0/P1/P2的真实执行参数不同，不能以不同批次的系统能量差充当同真实H预测信息消融。

## 比较口径与证据边界

正式P0--P2比较表中整体MILP列的15份安全安排在规定预算内均由自身初始化构造器形成；这些大域运行的求解器没有返回可评价的整数候选。另行完成的K.196受限小域实验出现了新的整数SAFE，两者不属于同一选择域，结果不能互相替代。P0/P1/P2每次300秒方法预算，H02每次120秒规划及最多一次60秒后验。SA五种子的中位数属于描述性指标，不代表一次300秒搜索。相关数据和审查定位均见上表及本工程EXPERIMENT_INPUTS.md。完整连续温度SAFE用于候选接纳；正式实验MILP外层反馈新增行数为0。这些内容只整理已有数据，不启动新实验。


## K.194与K.196的比较解释

K.194的1550份场景安排由原连续评价器逐一评价；其独立性体现在候选穷举覆盖不依赖MILP搜索，**并非使用独立实现的物理核**。场景内能量已经包含400 ms全窗口的基准、活动、温度漏电和公共功率，联合后只施加一次各1/2权重。四个共享A.main组的数量为AB/CPU1=450、AB/NPU0=650、AC/CPU1=90、AC/NPU0=360，相乘配对共274500份；没有进行274500次新热积分。

K.196在同一受限目录上只运行一次原whole方法和一次后验，实际模型2201变量、72个Stage整数选择、9215行、65167非零项。第一次求解器整数回调重复初始化；第二次才形成不同的安全调度。原生时间上限终止及求解器报告的5.590115%相对gap，**不构成求解器最优证明**；论文所称$ε$最优的依据是与K.194独立穷举区间比较。两者的根预算不同，不能做等时间算法效率排名；两者均无MILP外层新增热反馈行，不支持热反馈节能结论。本轮只整理已存来源与数值，不产生科研调用。

## E1--E4新增对照证据边界

- 冻结来源：[提交`1cbb3559`](https://github.com/YBEMR/paper/commit/1cbb3559a74cd42e1c382f1cb772040429440857)、[汇总交接](https://github.com/YBEMR/paper/blob/1cbb3559a74cd42e1c382f1cb772040429440857/research/e1_e4_validation/E1-E4_证据汇总与写作交接.md)与[结构化17槽索引](https://github.com/YBEMR/paper/blob/1cbb3559a74cd42e1c382f1cb772040429440857/research/e1_e4_validation/evidence/consolidation_e1_e4/evidence_index.json)。这些来源原位于`codex/e1-e4-preparation`分支、交接时未合并main；正文与表图使用锁定提交的GitHub地址，不误写为main中已有研究数据。
- E1的OMIT_TEMP只省略搜索评分的温度修正项，真实H模型与温度安全门未改变，且全部最终U均按完整四分项后验计费。E2仅改变Stage映射合法集合，GPU/NPU的低档基准与热节点从未删除。E3分场景A部署的输出不满足原跨场景共享约束，虽保存能量区间相同，仍是不同时间表。
- E4a仅有三个预设$β$取值，不对未运行的期限插值推断普遍趋势。E4b原两副本构造未决是`NO_SAFE_CONSTRUCTED_WITNESS`（零完整候选），非数学不可行证书或热违规；单回退是版本不同的独立补充，不能当作原HEFT在双请求上的能量点。
- 合计17次规划、15次后验、15个POST_SAFE、2个无完整候选；规划中另存589次完整安全候选评价回执，不能把它们计作589次独立实验或温度反馈次数。本系列只有HEFT适配版与最小构造变体，无MILP求解或热反馈对照；所有数值均为抽象仿真、单次有限搜索输出，未提供最优性、总体可调度率或统计稳定性结论。 
