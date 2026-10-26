# 第三章实验数据与写作依据

本文件用于追踪实验依据，不是论文正文。数值均来自已经归档的仿真、数学见证或独立小域实验；本轮仅整理现有记录并修改论文LaTeX，未启动新的MILP、MATLAB求解或热积分。K.194独立穷举和K.196整体MILP均是此前已完成的单独研究执行，不包含在P0--P2的120次方法调用中。

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

论文中的“低于”按保存的高精度安全能量区间作严格比较；表格中6位小数仅便于阅读，小于0.1%的差异不据此推断应用中的稳定优势。三批P0/P1/P2的真实执行参数不同，不能以不同批次的系统能量差充当同真实H预测信息消融。

## 比较口径与证据边界

正式P0--P2比较表中整体MILP列的15份安全安排在规定预算内均由自身初始化构造器形成；这些大域运行的求解器没有返回可评价的整数候选。另行完成的K.196受限小域实验出现了新的整数SAFE，两者不属于同一选择域，结果不能互相替代。P0/P1/P2每次300秒方法预算，H02每次120秒规划及最多一次60秒后验。SA五种子的中位数属于描述性指标，不代表一次300秒搜索。相关数据和审查定位均见上表及本工程EXPERIMENT_INPUTS.md。完整连续温度SAFE用于候选接纳；正式实验MILP外层反馈新增行数为0。这些内容只整理已有数据，不启动新实验。


## K.194与K.196的比较解释

K.194的1550份场景安排由原连续评价器逐一评价；其独立性体现在候选穷举覆盖不依赖MILP搜索，**并非使用独立实现的物理核**。场景内能量已经包含400 ms全窗口的基准、活动、温度漏电和公共功率，联合后只施加一次各1/2权重。四个共享A.main组的数量为AB/CPU1=450、AB/NPU0=650、AC/CPU1=90、AC/NPU0=360，相乘配对共274500份；没有进行274500次新热积分。

K.196在同一受限目录上只运行一次原whole方法和一次后验，实际模型2201变量、72个Stage整数选择、9215行、65167非零项。第一次求解器整数回调重复初始化；第二次才形成不同的安全调度。原生时间上限终止及求解器报告的5.590115%相对gap，**不构成求解器最优证明**；论文所称$ε$最优的依据是与K.194独立穷举区间比较。两者的根预算不同，不能做等时间算法效率排名；两者均无MILP外层新增热反馈行，不支持热反馈节能结论。本轮只整理已存来源与数值，不产生科研调用。
