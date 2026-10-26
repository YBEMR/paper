# 第三章插图与数据口径

下表汇集此前新增的六幅TikZ图与本次补充的两幅PGFPlots数据图，均由第三章正文直接引用。制图源码可编辑，使用LaTeX发行版提供的TikZ与PGFPlots，不分发字体或位图素材。

| 图形源文件 | 论文位置 | 内容身份 | 重要限制 |
|---|---|---|---|
| `ch3-shared-scene.tex` | 3.2.1 | H02 R1/H的Stage具体设备部署，A+B与A+C | 只示意设备映射，省略实际运行工作点和时间 |
| `ch3-hardware-layers.tex` | 3.3.1 | 正式四节点平台结构 | 三种硬件粒度不同，CPU基准不能重复计算 |
| `ch3-fixed-events.tex` | 3.5 | 3.5约束教学示例中的Stage与未选备选项 | 数值为教学例，不是P0/P1/P2冻结输入 |
| `ch3-interior-peak.tex` | 3.6.2 | 内部峰值可能超过端点的概念曲线 | 非仿真采样、非某次实际热违规图 |
| `ch3-h02-gantt.tex` | 3.7.2 | H02 R1 H与R规划的A+B场景真实候选 | 时长按**相同真实H**参数计算；两套表中给出的能量均为A+B/A+C整套方案总能量 |
| `ch3-c19-schedules.tex` | 3.7.3 | C19并行P/接力S中CPU预处理及共享域H档 | 其他Stage省略但完整安排模式相同，结论为静态数学见证 |
| `ch3-r1-thermal-records.tex` | 3.7.3 | P0与P2相同R1 HEFT排程在A+B场景的四节点后验温度记录点 | 0ms初始状态加14个归档记录时刻；虚线非解析连续温度轨迹，两面板纵轴不同；热安全依据完整后验 |
| `ch3-linked-vs-heft.tex` | 3.7.4 | P0、P1、P2正式组联动MILP相对HEFT的15个同输入安全能量配对 | R1--R5是类别型工作量比例，不作为递增规模扫描 |

原有方法流程图 `fig:solver-flow` 与50/78°C能量分项图 `fig:exp-thermal-parts` 均保留；此前八幅图未删除，新增两幅后第三章共有十幅图。

数据依据：
- [H02四槽精确候选记录](../../chapter3_experiments/results/response_information_resume01/analysis01/facts.json)：筛选R1两槽中A+B场景，按Stage、具体设备、OPP、start_ms读取。图中块宽使用冻结config_v01.json的H响应及OPP，重建真实H下的合法运行时长；没有使用R规划误差预测时长冒充真实时长。
- [冻结模式、Stage响应及功热参数](../../chapter3_experiments/config_v01.json)：R1基础条件，正式运行通过auto_low_immediate_v1适配；裸配置历史hold-last字段不能直接用于复现正式结果。
- [C19完整数学时序和证明](https://github.com/YBEMR/paper/blob/db34b46bc2499fcd10f6f7ec6235cd0b6b89555a/research/hetero_thermal_pilot/C19_C12机制迁移与C17下界强化_面向主线7数学算法交接_20261022.md)：安排P的B.pre在0ms，安排S在10ms；CPU域H驻留各15与25ms；完整加权系统能量差严格大于3.254mJ。

新增图均不等于新调度运行、新温度积分或新增实验结果。论文中的系统能量与热安全结论沿原有归档证据表述。

## 2026-10-26：新增归档数据图

- `figures/ch3-r1-thermal-records.csv`：读取[P0/R1 HEFT独立后验](../../chapter3_experiments/results/p0_execution01/calls/base__R1/heft/postcheck.json)及[P2/R1 HEFT独立后验](../../chapter3_experiments/results/p2_execution01/calls/initial_78__R1/heft/postcheck.json)中A+B场景`trace`，加上给定的0ms初始状态，各共15个记录时刻。将极窄认证区间的中点四舍五入至六位小数，虚线只连接归档点，不是连续温度重算；最终排程`candidate_sha256`均为`f3c14d4f6767a5cb584e37643244a0c86b9b995405c7284e31d4765dfa194e41`。连续热安全以原始独立后验为准。
- `figures/ch3-linked-vs-heft.csv`：使用[P0](../../chapter3_experiments/results/p0_resume01/analysis01/results40.csv)、[P1](../../chapter3_experiments/results/p1_execution01/analysis01/results40.csv)、[P2](../../chapter3_experiments/results/p2_execution01/analysis01/results40.csv)的`safe_U_J`逐组逐变体计算`(U_HEFT-U_linked)/U_HEFT*100`，保留六位小数，图中只比较同一输入的两种方法。三组真实响应或入口温度不同，不能把跨组差异当作频率响应信息的单因素消融。

两幅图均只使用已归档实验记录，没有运行新的优化、热积分或参数扫描。
