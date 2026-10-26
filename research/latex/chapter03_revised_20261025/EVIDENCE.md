# 第三章实验数据与写作依据

本文件用于追踪实验依据，不是论文正文；引用数值均来自此前已经封存的仿真或只读数学审查。本轮**未启动MILP、MATLAB、热积分或新的研究对照**，仅处理论文LaTeX及编译。

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

论文中的“低于”按保存的高精度安全能量区间作严格比较；表格中6位小数仅便于阅读，小于0.1%的差异不据此推断应用中的稳定优势。三批P0/P1/P2的真实执行参数不同，不能以不同批次的系统能量差充当同真实H预测信息消融。

## 比较口径与证据边界

整体MILP列的15份安全安排在规定预算内均由自身初始化构造器形成，真实MILP求解器虽然运行过，但没有返回可评价的整数候选。P0/P1/P2每次300秒方法预算，H02每次120秒规划及最多一次60秒后验。SA五种子的中位数属于描述性指标，不代表一次300秒搜索。相关数据和审查定位均见上表及本工程EXPERIMENT_INPUTS.md。完整连续温度SAFE用于候选接纳；正式实验MILP外层反馈新增行数为0。这些内容只整理已有数据，不启动新实验。
