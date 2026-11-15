# 近邻方法能力矩阵

核查日期2026-11-15。本轮先复核仓库原文，再与公开作者稿/出版方页面确认题名。**四篇取得并核读模型及算法全文；Li 2018仅核到出版方摘要/引言与书目，全文缺口保留。** 不据未取得的全文断言其没有某项能力。

## 身份与阅读范围

| 简称 | 原文与定位 | 本轮阅读范围 |
|---|---|---|
| Zhou 2018 | *Thermal-aware correlated two-level scheduling of real-time tasks with reduced processor energy on heterogeneous MPSoCs*，JSA 82:1–11；[作者全文](https://faculty.ecnu.edu.cn/picture/article/1408/23/0c/a9d761e34644a4cd9f7306e31fb5/c768f3a9-e6a8-4a5b-8f82-a6949912d301.pdf) | §3.1–3.3、§4、§5.1–5.3、Theorem 1及Algorithm 1；§3.3原页核对 |
| Li 2018 | *Minimizing energy by thermal-aware task assignment and speed scaling in heterogeneous MPSoC systems*，JSA 89:118–130；[出版方](https://www.sciencedirect.com/science/article/pii/S1383762118300304)，DOI 10.1016/j.sysarc.2018.08.003 | 摘要/引言；OpenAlex该DOI记录未给开放全文。没有把标题、Li 2019引用或旧讨论当作本篇全文 |
| Li 2019 | *Minimizing temperature and energy of real-time applications with precedence constraints on heterogeneous MPSoC systems*，JSA 98:79–91；[DOI](https://doi.org/10.1016/j.sysarc.2019.07.001)，[仓库全文](https://github.com/YBEMR/paper/blob/635b21cd537d66b22f4139e995988cf86c41d736/papers/2019_Minimizing_temperature_and_energy_of_real_time_applications.pdf) | §3、§4、§5.1–5.2、算法1/2、§6.1；PDF第7页算法2与式(18)目视核对 |
| Jiang 2018 | *Energy-Efficient Scheduling of Periodic Applications on Safety-Critical Time-Triggered Multiprocessor Systems*，Electronics 7(6):98；[出版方](https://www.mdpi.com/2079-9292/7/6/98)，[开放PDF](https://mdpi-res.com/d_attachment/electronics/electronics-07-00098/article_deploy/electronics-07-00098.pdf) | §3.1–3.4、§4 MILP、§5启发式；23页全文，§3.4原页核对 |
| RT-TAS | Lee、Shin、Chwa，*Thermal-Aware Scheduling for Integrated CPUs–GPU Platforms*，TECS 18(5s):90，2019；[25页作者稿](https://rtcl.eecs.umich.edu/rtclweb/assets/publications/2019/youngmoon-TECS-19.pdf)，DOI 10.1145/3358235 | 仓库11页同题作者版本的§5.1–5.4、§6.1–6.2、算法1/2和WCRT/反转预算段；并核25页版本身份。不当作两篇独立研究 |

## 假设、动作、目标与保证

| 方法 | 任务/执行假设 | 配置与时序动作权限 | 电热处理与目标 | 保证边界 |
|---|---|---|---|---|
| Zhou 2018 | 异构MPSoC、依赖任务、共同期限；周期数/频率型时长 | 把每个处理器×频档变为虚拟核；分配到虚拟核同时选真实处理器和频率；维护真实处理器容量、拓扑关系和温限检查 | 温度相关线性漏电、瞬态一阶RC；§3.3明确采用处理器间传热可忽略的模型；最小化动态+漏电能量 | Theorem 1讨论功率因子排序下的动态能量性质；最终为受约束分配启发式，不是任意异构DAG全局联合最优证书；不能移植为共享频率域和多节点耦合下的保证 |
| Li 2018 | 出版方可确认异构处理器及任务功耗异构；具体任务/抢占/周期细节本轮未全文核实 | 第一阶段热/能量感知分配；第二阶段任务级速度优化及近似fluid调度，以减少切换成本 | 同时考虑热与功率耗散因素，优化能量与温度 | 摘要声称其调度满足任务时间约束；证明前提、跨核热耦合、共享频域和硬温限保证均待全文确认 |
| Li 2019 / ETA-TS | 单入口单出口DAG，处理器相关WCET与边通信时延；调频时长按反比缩放 | 一般问题已含映射、速度、起点；第一阶段虚拟核与任务期限引导配置；第二阶段保留映射/同处理器次序，按LFT降频并在有余量时延迟 | §3.3式(2)明确含节点间热传导；后续热负载指标在平衡/无传热特例及周期均温条件推导；温度依赖漏电；改善温度与能量 | 启发式，不是全局能量最优。不能把§4指标的简化说成整篇无热耦合；也不能把对照算法的温限检查直接当ETA-TS的完整连续安全证明 |
| Jiang 2018 | 多DAG、严格与非严格周期任务、固定映射、非抢占计算和时触发总线 | §3.4明确将映射作为输入；共同优化起点、任务频档、闲置/睡眠及通信安排；含切换等成本 | 超周期内计算+通信完整能量；温度不是其物理状态变量，模拟退火的“温度”不是芯片温度 | MILP在其固定映射模型内给最优，另有退火启发式；不是对映射也联合最优。§4逐任务频档变量未包含本实验的跨核共享域一致性关系 |
| RT-TAS | 独立周期任务、交替CPU/GPU段，CPU分区固定优先级且可抢占，GPU互斥且不可抢占，MPCP分析 | T-WFD分配CPU核；运行时协调CPU/GPU候选执行及空闲，允许有预算的优先级反转；不是自由的任意DAG映射与频率穷举 | 明确使用CPU–GPU热耦合、任务功率差异，避免热任务同时执行；目标为降低最高温度并满足期限 | 给热平衡性质与反转预算内的期限分析；不等于全局最小系统能量，也不是任意时刻硬温限的通用证明 |

## 对本轮对照的约束

Zhou的“两级”是平台工作点展开与任务分配的关联组织，**不能改写成先固定映射、之后才看频率的弱方法**。Li 2019已经具备降频、冷却等待和一般耦合热方程，不能把这些当作新增动作或建模空白。RT-TAS已经处理CPU/GPU热耦合下的执行协调，不能声称前人只做静态放置。Jiang固定映射是明确问题边界，不是其MILP求解失误。

本轮NT、D_C、D_M、TC1/2/4均为**适配基线/条件最优参照**。它们借鉴分配—调频—时序组织思想，但没有复现上述论文的任务排序、fluid调度、通信总线、MPCP、LFT更新或全部适用前提。不能用本轮差距给原论文排名。

共享频率域、合法设备模式和热耦合的组合需要逐项适配；“没有找到完全相同的组合”本身不是新颖性证据。本轮不作完整领域新颖性判定，Li 2018全文缺口也不充当研究空白。
