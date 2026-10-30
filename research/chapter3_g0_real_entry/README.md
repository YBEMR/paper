# G0一次性真实入口：工程准备完成

本目录已实现受控REAL入口；**工程就绪不等于科研批准**。原SIMULATION入口保留。没有可用用户批准文件，未创建真实claim，当前禁止科研启动。

| 接口 | 本版合同 |
|---|---|
| launch_contract / gating | 原输入、最终源码/可执行文件、预算、外部用户批准hash；原子单次claim、分角色worker票据；REAL拒绝假依赖 |
| real_runner / actual_worker | 新Python方法/post，独立MATLAB会话；复用原ProcessMonitor/host_gate，不复用旧队列；0重试 |
| worker / G0Budget | 唯一300秒根追溯至监督器启动方法进程前，包含导入、准备和读输入；阶段一仍150秒。post唯一60秒包含启动到回收 |
| persistence / RealArchive | 完整SAFE逐代原子落盘及seal；崩溃后只读校验原身份、全场景覆盖、能量、原根/阶段截止，不补积分或能量 |
| 原数学路径 | 原Model/选项/系数、PARTIAL、原x0/反馈和C增广；科学源码及容差不动 |

[最终执行计划](results/real_entry_plan01/plan.json)、[就绪回执](results/real_entry_plan01/readiness.json)、[最终66项](results/entry_final01/checks.json)、[旧32项回归](../chapter3_g0/results/manual08_entry_regression/checks.json)。66项含17项新增执行边界及49项接线回归；新检查全是假进程、人工账本与模拟授权，0真实科研。测试中的假APPROVED文件不能通过真实计划核对，不是科研批准。

真实入口为 `python -B -m research.chapter3_g0_real_entry.real_runner`，必须另给plan、approval、approval-sha256和全新output四项。不能使用PENDING模板，不能用模拟runner代替。当前最终计划固定C01一次300秒，正常完整SAFE最多一次60秒post，方法进程480秒/整批720秒。

[当前报告](../G0一次性真实入口实施与最终预检_20261030.md)列明启动条件及残余风险。当前资源快照物理可用1.995GiB，低于2GiB门槛；资源须在日后获批启动前重查。实际OS/MATLAB传输、原生数值兼容及真实连续SAFE均尚未实跑，工程预检不提供算法质量结论。
