# 第三章插图与数据口径

下表汇集第三章正文引用的可编辑图形：此前新增的六幅TikZ图、两幅归档数据PGFPlots图，以及本轮根据E2和E4a实验记录补充的两幅PGFPlots图。制图使用LaTeX发行版提供的TikZ与PGFPlots，不分发字体或位图素材。

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
| `ch3-e2-device-energy.tex` | 3.7.2 | E2 R1/H下四组处理器可映射类别的完整安全能量 | 显示适配HEFT单次输出；设备实体、功热网络和低档基准不变，并非关闭GPU/NPU功率 |
| `ch3-e4-deadline-energy.tex` | 3.7.4 | E4a R1/H下三种预设期限系数与对应SAFE能量 | 三个参数点来自各自完整后验；连线仅帮助阅读，不能外推为连续扫参曲线 |

原有方法流程图 `fig:solver-flow` 与50/78°C能量分项图 `fig:exp-thermal-parts` 均保留；前次增加两幅后共有十幅，本次再增加E2/E4a两幅，第三章现有十二幅图。

数据依据：
- [H02四槽精确候选记录](../../chapter3_experiments/results/response_information_resume01/analysis01/facts.json)：筛选R1两槽中A+B场景，按Stage、具体设备、OPP、start_ms读取。图中块宽使用冻结config_v01.json的H响应及OPP，重建真实H下的合法运行时长；没有使用R规划误差预测时长冒充真实时长。
- [冻结模式、Stage响应及功热参数](../../chapter3_experiments/config_v01.json)：R1基础条件，正式运行通过auto_low_immediate_v1适配；裸配置历史hold-last字段不能直接用于复现正式结果。
- [C19完整数学时序和证明](https://github.com/YBEMR/paper/blob/db34b46bc2499fcd10f6f7ec6235cd0b6b89555a/research/hetero_thermal_pilot/C19_C12机制迁移与C17下界强化_面向主线7数学算法交接_20261022.md)：安排P的B.pre在0ms，安排S在10ms；CPU域H驻留各15与25ms；完整加权系统能量差严格大于3.254mJ。

新增图均不等于新调度运行、新温度积分或新增实验结果。论文中的系统能量与热安全结论沿原有归档证据表述。

## 2026-10-26：新增归档数据图

- `figures/ch3-r1-thermal-records.csv`：读取[P0/R1 HEFT独立后验](../../chapter3_experiments/results/p0_execution01/calls/base__R1/heft/postcheck.json)及[P2/R1 HEFT独立后验](../../chapter3_experiments/results/p2_execution01/calls/initial_78__R1/heft/postcheck.json)中A+B场景`trace`，加上给定的0ms初始状态，各共15个记录时刻。将极窄认证区间的中点四舍五入至六位小数，虚线只连接归档点，不是连续温度重算；最终排程`candidate_sha256`均为`f3c14d4f6767a5cb584e37643244a0c86b9b995405c7284e31d4765dfa194e41`。连续热安全以原始独立后验为准。
- `figures/ch3-linked-vs-heft.csv`：使用[P0](../../chapter3_experiments/results/p0_resume01/analysis01/results40.csv)、[P1](../../chapter3_experiments/results/p1_execution01/analysis01/results40.csv)、[P2](../../chapter3_experiments/results/p2_execution01/analysis01/results40.csv)的`safe_U_J`逐组逐变体计算`(U_HEFT-U_linked)/U_HEFT*100`，保留六位小数，图中只比较同一输入的两种方法。三组真实响应或入口温度不同，不能把跨组差异当作频率响应信息的单因素消融。

两幅图均只使用已归档实验记录，没有运行新的优化、热积分或参数扫描。

## 2026-10-26：E2设备可用范围与E4a截止期限两幅实验图

本轮从外部分支已归档结果读取数值，不重新规划或积分。实验交接来自[固定提交`1cbb3559`](https://github.com/YBEMR/paper/commit/1cbb3559a74cd42e1c382f1cb772040429440857)，当时结果保存在`codex/e1-e4-preparation`研究分支，未合并到main。以下链接固定到该提交，避免用main中并不存在的路径误导查证。

- `figures/ch3-e2-device-energy.csv`来自[E2原分析](https://github.com/YBEMR/paper/blob/1cbb3559a74cd42e1c382f1cb772040429440857/research/e1_e4_validation/results/e2_res_01/analysis.json)四个`slots[].post_U_approx_J`、`peak_temperature_upper_degC`。图只绘系统能量，温度和相对CPU-only差在正文表`tab:exp-e2-resources`；物理GPU/NPU仍开低档并参与漏电计量，仅限制任务映射集合。
- `figures/ch3-e4-deadline-energy.csv`来自[E4a原分析](https://github.com/YBEMR/paper/blob/1cbb3559a74cd42e1c382f1cb772040429440857/research/e1_e4_validation/results/e4_dead_01/analysis.json)三个`slots[].post_U_approx_J`及`deadline_beta`、冻结期限。工作点组成和相对严格期限的节能百分比在`tab:exp-e4-deadlines`，不从曲线插值推断未运行的期限条件。

E1与E3使用小表及正文分析，E4b及单回退补充使用状态表，均不强行绘制不存在的多点规模曲线；具体证据链接见[EVIDENCE.md](EVIDENCE.md)。
