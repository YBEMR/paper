本轮仅读仓库历史，未读取用户本机F盘的新native日志，也未使用Library附件中的未访问内容。没有求解、构模、热评价或Git写操作。所有下列运行成本是**历史档案中的原运行成本**；本轮云端JSON/归档读取另行记录，不能冒称本机本次native结果。

先更正历史文字：`base_long_diagnostic01/input_instance.json`及warm/prefilter/K187归档的9个共享Stage身份共有**66模式**：A.main为12，B.main/C.main各9，其余6身份各6。两场景各6次Stage执行、合12次的口径不变。2026-11-10比较报告中的72模式为文字误记，本轮未回写旧报告。本机新R1的模式数仍未知，不能用旧66自动代替；须核原输入/hash。

|已尝试事项及版本|真实数字与结果|支持的判断与限制|原始证据|
|---|---|---|---|
|1. 旧12执行R1的调度强化、辅助连续化、能量有效下界；`21c483b9`、`10743402`、`5efaebd9`/`323d8822`|原91,844变量/75,825整数声明/1,172,563行/8,331,273非零；聚合后613,164行/7,771,874非零；辅助连续化后6,422整数声明；能量强化后614,943行/7,835,918非零，根LP由0提高至0.740331755956 J。四个900s档仍无预算内可解码整数候选或SAFE。|有松弛与首解困难的证据，不是仅因Python未构完。行少47.7%不代表运行必快；根LP收紧仍未获首解。原生最终0节点/0可行点/空解；迟到done却报1且仍空，不把计数当可用解。|`research/chapter3_experiments/results/base_long_diagnostic01..04/result.json`、各`diagnostic_events.jsonl`和`matlab/request_000001.response.json`；源码分别在各`source_snapshot/`。|
|2. 旧12执行R1已经有现场SAFE初解和x0；`5ba07816`、`a92b34e5`|`base_warm_diagnostic01`于59.938s获初始SAFE；290.328s收到solver向量、290.766s合法、292.297s完整SAFE，仍等于本次seed；900s最终U仍1.632464816557 J。|不能再解释为从未给MILP初解。它是确定性最短设备/H-M-L模板/EDF构造，不是增强HEFT终解；有SAFE上界不等于证明最优。|`research/chapter3_experiments/results/base_warm_diagnostic01/result.json`、`diagnostic_summary.json`、`matlab/`；原实现`initial_schedule.py`、`initial_point.py`。|
|3. 同旧R1输入期限前置过滤；`89a8d2fb`|base配对选项6,422→1,681，变量91,844→29,599，行614,943→200,205，实际非零2,127,851；事件852/929→287/296。构模29.578→19.188s、首SAFE46.594→28.063s，最终U相同，0严格改善。|可证明超期选项删除及事件目录压缩确有工程收益；不等同更低能耗。保留精确数学调度，不意味着重建外包后新旧浮点LP逐点/逐字节等价。不能与auto-L策略改变混算。|`research/chapter3_experiments/results/prefilter_diagnostic01/base__R1__current/result.json`及`base__R1__prefilter/result.json`；本轮也读取对应输入。|
|4. 构模已多次优化，K187/C01仍呈不同瓶颈；缓存链`bb53928a→720194e6→7bbe9996→d8705146→6b8edfd6`|K187（auto-L、仍12执行）事件287/296，共581区间，完整27,971变量/176,953行/1,983,981非零，历史构模12.093s。C01各6执行但事件1,246/1,162、共2,406区间；300s时仅部分114,334变量/590,495行/9,524,633非零，未进入MATLAB；热条件行组装274.953s，系数查找生成17.269s。|C01该档有构模瓶颈，不能归因原生solver；也不是每次只有Stage数量决定规模。两个不同输入不能当单因素加速实验。此处仅引用历史档案，不将旧构模诊断冒充本机新native完成记录。|K187 `research/chapter3_experiments/results/whole_long_budget01/method/build_progress.jsonl`；C01 `research/chapter3_method_entry_executor/results/real_entry01_analysis/raw_artifacts.tar.gz`内`slots/whole_milp__method/worker/method/build_progress.jsonl`（本轮重新核成员SHA，末行`CONSTRUCTION_INTERRUPTED`）。|
|5. 后来的自然auto-L六执行档有具体数值表示/交付修复；`0f55a39b`，余量方案subject `454488dc`|原10,956变量/613整数/70,513不等式有Fraction精确可行见证，原生仍报−2；3,797对精确反向不等式改62,919不等式＋3,797等式后根LP/初解进入正常路径。300s的较好向量首次约303.080s才可观测，未收为有效收益。新600s调用留30s原生交付余量，578.500s完成SAFE，U=0.849921625896 J，根578.672s/进程586.906s。|这是后来的**4身份/36模式、两场景共6执行、β1.3/auto-L**自然小实例，不是原12执行hold-R1的同例加速。修复过一个具体数值/交付缺口，不证明本机本次慢也是同因，不保证30s普适充分或更多预算必最优。|`research/chapter3_experiments/results/natural_full_numeric_diagnostic01/summary.json`、`exact_witness.json`、`equality_representation.json`；`natural_delivery_execution01/summary.json`及slots原始worker记录。|

后续七方案收束又是β1.0/auto-L六执行、4身份36模式：t50原实际7,568变量/48,719行/484,290非零，构模4.672s、排他solver等待536.985s、根576.375s/进程583.391s。这用于说明归档实例已换档，**不是无损压缩把原12执行R1直接降到7,568变量的证据**。本轮只读了原t50记录作口径边界，不据它猜本机新R1耗时。

下一最小诊断应先收齐**同一次已有本机运行**的以下材料，而不是立即补跑：

1. 实际input/config、运行入口与核心源码SHA、支持传播/期限过滤/auto-L等flags，以及按场景的Stage执行/模式/候选/事件计数。由此识别究竟是旧12执行R1、后续六执行小例还是新本机变体。
2. 根时钟起点、构模完整/部分状态、阶段墙钟、矩阵shape/nnz、MATLAB ready、请求发布及`intlinprog_entered`证据。没有进入原生的运行不能诊断原生分支/割瓶颈。
3. 实际MATLAB/Optimization Toolbox版本、完整options、原生日志stdout/警告/错误、init/iter/done回调、response及退出码；保留rootLP/heuristics/cutgen/branching的真实事件和时间基准。只有完成回调不能分摊所有内部时间；0节点不证明分支树爆炸或启发式未尝试。
4. x0长度/哈希、原行数值接纳、物理SAFE回执、是否收到不同向量及其接收/合法/SAFE时间；同时保留incumbent/bound/gap原值、最终向量、超时/取消与清理记录。原生MaxTime与方法根预算不同，晚到向量不倒算为预算内收益。
5. 若有异常−2或初解冲突，保留实际导出payload及native接收载荷，或能追溯的尺寸/数组hash/等式映射检查。历史Cloud缺失的MAT/NPZ不能用摘要替代成“已重新独立核验”。不能通过放宽容差、删小系数或把近似反向行当等式来制造改善。

R2023b原生relativegap使用`100*(U−L)/(|U|+1)`，不等于物理能量`(U−L)/U`；内部界/终态也不是独立最优性证书。没有完整root/cut迭代/耗时、数值条件或对称诊断时，将相应原因保留为假设。

[结构化摘录](history_excerpt.json)保留字段来源，[源SHA](source_hashes.json)及[实际提取命令](command.json)可追踪。本轮读取31份源/归档成员，2026-11-11 01:45:04.912088–01:45:05.919618 UTC，命令墙钟1.007547s；这1秒是本轮静态读取成本，不是任何求解性能。当前工作区其他任务的新源码/文件未改动，历史原件未改动。
