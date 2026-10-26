# 第三章插图与数据口径

六幅新增图均为可编辑的TikZ源码，由第三章各小节直接引用。无字体、位图素材或需要下载安装的外部图形包。

| 图形源文件 | 论文位置 | 内容身份 | 重要限制 |
|---|---|---|---|
| `ch3-shared-scene.tex` | 3.2.1 | H02 R1/H的Stage具体设备部署，A+B与A+C | 只示意设备映射，省略实际运行工作点和时间 |
| `ch3-hardware-layers.tex` | 3.3.1 | 正式四节点平台结构 | 三种硬件粒度不同，CPU基准不能重复计算 |
| `ch3-fixed-events.tex` | 3.5 | 3.5约束教学示例中的Stage与未选备选项 | 数值为教学例，不是P0/P1/P2冻结输入 |
| `ch3-interior-peak.tex` | 3.6.2 | 内部峰值可能超过端点的概念曲线 | 非仿真采样、非某次实际热违规图 |
| `ch3-h02-gantt.tex` | 3.7.2 | H02 R1 H与R规划的A+B场景真实候选 | 时长按**相同真实H**参数计算；两套表中给出的能量均为A+B/A+C整套方案总能量 |
| `ch3-c19-schedules.tex` | 3.7.3 | C19并行P/接力S中CPU预处理及共享域H档 | 其他Stage省略但完整安排模式相同，结论为静态数学见证 |

原正文保留了方法流程图 `fig:solver-flow` 和50/78°C能量分项图 `fig:exp-thermal-parts`，本轮新增后正文共有8幅图。

数据依据：
- [H02四槽精确候选记录](../../chapter3_experiments/results/response_information_resume01/analysis01/facts.json)：筛选R1两槽中A+B场景，按Stage、具体设备、OPP、start_ms读取。图中块宽使用冻结config_v01.json的H响应及OPP，重建真实H下的合法运行时长；没有使用R规划误差预测时长冒充真实时长。
- [冻结模式、Stage响应及功热参数](../../chapter3_experiments/config_v01.json)：R1基础条件，正式运行通过auto_low_immediate_v1适配；裸配置历史hold-last字段不能直接用于复现正式结果。
- [C19完整数学时序和证明](https://github.com/YBEMR/paper/blob/db34b46bc2499fcd10f6f7ec6235cd0b6b89555a/research/hetero_thermal_pilot/C19_C12机制迁移与C17下界强化_面向主线7数学算法交接_20261022.md)：安排P的B.pre在0ms，安排S在10ms；CPU域H驻留各15与25ms；完整加权系统能量差严格大于3.254mJ。

新增图均不等于新调度运行、新温度积分或新增实验结果。论文中的系统能量与热安全结论沿原有归档证据表述。
