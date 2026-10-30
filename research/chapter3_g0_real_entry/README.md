## 当前有界收束版本（2026-10-30）

新增`phase_public_startup_bounded_settlement_v1`：[隔离实现与十组验收报告](../G0有界收束_隔离实现与十组人工验收_20261030.md)、[89项最终回执](results/settlement_final02/checks.json)、[逐文件审计](results/settlement_final02/artifact_audit.json)。已发布请求正常取消后，最多10秒控制收束计入原根；跨phase不重置截止，迟到候选/目标/回调不接纳。数值/原生错误或提交前占号未发布不能恢复。旧PUBLIC/LEGACY版本保留；`prepare.freeze(..., bounded_settlement=True)`仅准备未批准的新版本计划，默认仍是旧PUBLIC。`phase1_stopped_s`可含边界控制，150秒优化截止以scope记录为准。本版仅人工验证，未批准真实调用，无新真实claim。以下为历史版本说明。

## 当前公共启动版本（2026-10-30）

`phase_public_startup_v1`已隔离实现：[实施与七组验收报告](../G0阶段公共启动_V2隔离实现与七组人工验收_20261030.md)、[79项最终回执](results/public_startup_final01/checks.json)、[逐文件审计](results/public_startup_final01/artifact_audit.json)。同根phase公共启动后再分slot；phase1从未启动、有及时S0时保留phase2唯一首次启动，启动失败禁止重试。启动总览/互斥分项/最终close分别记录。旧`legacy_slot_startup_v1`保留用于回归及来源追溯。旧plan及claim不可复用；本版未生成新科研批准，0真实算法/MATLAB/积分。以下为历史修复和入口状态。

## 当前修复版本（2026-10-30）

scope封存/恢复、post前异常闸门和READY读取诊断已作限定修复；[人工验收报告](../G0恢复停机与READY诊断_限定修复及人工验收_20261030.md)、[72项检查](results/recovery_repair02/checks.json)、[源码检查点](results/recovery_repair02/repair_version.json)。新checkpoint为v2，旧真实结果未重放或升级。旧real_entry_plan01已消费且源hash不再匹配，不能复用；本修复检查点不是新科研批准。实际启动延迟和局部求解接入仍未解决，算法/时限/预算均不变。

以下为先前一次性入口合同与历史准备状态，原批准不得据此再次执行。

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
