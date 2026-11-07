# 第四章：原 SA 的完整凭证记录适配与工程预检

本轮已实现独立 SA 适配器，并通过针对性测试、旧流程回归和一次预先限定的真实轻量冒烟。未运行正式方法对比、未扩大实例或种子、未提交或推送、未合并。原 SA、HEFT、解码器、电热评价器和旧六槽实验入口均保持原字节。

工作目录 `/workspace/paper`；工作分支 `chapter4/r2-r5-validation-20261107`；起止 HEAD 均为 `d47bfda700ce76df31d9aae0aea97d01279b501f`。本目录以此前 UTC+8 日期命名；以下时间统一使用原始日志的 **UTC**。本轮最早现场记录为 2026-11-07 17:04:56 UTC；结束时间、环境及文件清单见 `completion_record.json`。

## 问题与最小改动

原图重构记录器完成初始化后会设置 `current`，随后要求候选部署等于冻结部署。这是 OFF/ON 的既有搜索边界；直接用于原 SA 会以 `FIXED_DEPLOYMENT_DRIFT` 拒绝合法设备迁移。

新增 `research/chapter4_scheduler/validation/sa_adapter.py`：

- `SARecorder` 复用原完整合法性、电热 SAFE 凭证、输入/候选哈希、全部场景/节点/时间窗、能量区间、形成时间及技术错误检查。它不冻结 SA 的部署；每个候选仍必须满足原跨场景共享部署一致性。
- 最佳 SAFE 上界档案与原 SA 内部当前态分开。所有通过完整检查的 SAFE 凭证原样返回给原 SA，允许原算法按既有概率接受能耗更大的安全当前态。旧字段 `incumbent_replaced` 在本适配器中只表示最佳档案更新，新增 `best_archive_replaced` 明示语义，不能解释成 SA 当前态接纳。
- `execute_sa` 原样调用 `sa_method.run_sa`，明确传入整数种子，不生成或重置其 RNG；保留原四类动作、解码范围、降温参数、接纳准则及本地缓存。
- 一次调用只使用调用者的原绝对截止时间，包含输入、上下文校验、原生初始化、候选生成和评价；输出序列化单独计时。支持不超过 300 秒的调用根，短预算仅用于明确标记的工程预检。
- 全候选请求、实际评价调用尝试、返回凭证、缓存命中、完整初始 SAFE 快照、最佳解、异常和时间均保存。评价器直接抛异常的调用也计入尝试数，不能用返回凭证数代替调用数。
- `dispatch_with_sa` 是新增四方法 API。HEFT/OFF/ON 仍转交原入口；旧六槽批次未被扩展，未启用此前 14 槽提案。

真实绑定必须使用原 `run_sa` 和 `evaluate_candidate`。记录器只在评价边界增加计数与日志，原实参和返回值不变。数值未决或技术凭证错误按共同完整证据规则停止并保留此前安全档案；热违规只作为拒绝见证，不添加虚构惩罚能耗。发现安全档案后发生技术错误，档案可保存，但不能因此把失败调用当成正常研究结果。

## 自动检查及其性质

最终新增 **21 项**测试通过，见 `unit_run02/checks.json`、`unit_run02/test_output.txt`。首轮 `unit_run01` 也为 21/21；随后补充“评价器抛异常也计费”的边界计数断言，再完成最终轮，并未用首轮结果代替修改后验证。

覆盖合法迁移、跨场景迁移不一致、较差 SAFE 返回、重叠区间的最佳上界档案、缓存隔离、完整热违规拒绝、零权重场景仍需完整 SAFE、凭证身份和参数突变、截止前形成但稍后转交的 SAFE、截止后形成的 SAFE、数值未决、根时钟/截止/输入漂移、明确种子、错误保留及四方法分派。

其中一个差分测试对种子 101、102 各做一对执行：原 SA 分别接旧 `CandidateRecorder` 和新适配器，候选哈希序列及完整 SA 元数据完全一致，并覆盖上坡接纳。总计四次原 SA 函数体调用使用人工任务、替代 HEFT 构造、人工时钟和虚构能量凭证；不是物理实验，也未证明实际运行开销为零。测试守卫禁止真实热积分、真实 HEFT、求解器和网络。

原阻塞流程 **109 项**和原验证入口 **12 项**均通过，见 `regression/` 与 `legacy_validation/`。这些也是人工夹具检查；不把 142 项测试称为 142 个研究算例。

另有 `audit.py` 的 **65 项只读检查**全部通过：核对原记录、输入和源哈希，对冒烟候选重新进行调度合法性及完整凭证验证，核对 SAFE 时间、最佳档案、预算和复评区间。没有重新积分，也没有运行新搜索；不会独立验证连续热模型的数值正确性。受保护的既有分析、机制、设计及执行文件 **1298 个**均未改变；所有已跟踪文件与 HEAD 一致。

## 唯一一次真实轻量冒烟

`session_start.json` 在结果前固定了 R2、种子 101、方法 5 秒、最多一次复评 5 秒、禁止重试。`smoke/plan.json` 又冻结 22 个源码哈希、输入/配置、环境和性质，先于真实调用保存。预检重新展开原 R2 输入，无评价或安全答案复用；方法调用内再次独立加载并收费。原始输入、配置和原始配置哈希均与已保存 R2 验证相同，未调整物理参数、可选设备/频档、约束或截止。

| 项目 | 实际记录 |
|---|---|
| 方法进程命令起止 UTC | 2026-11-07 17:19:05.709740 — 17:19:10.846549 |
| 方法命令墙钟 | 5.136660326 秒，包含解释器及存档等 |
| 方法根计费时间 | 5.005044330 秒；协作检查点超出约 0.005044330 秒，非硬实时终止 |
| 方法结果 | `SAFE` 档案，`BUDGET_EXHAUSTED` 正常截止 |
| 初始化 | 原生 `sa_initial_heft`，一次构造；不是增强 HEFT 的完整能量改进流程 |
| 第一份完整 SAFE 形成 | 原方法根 0.544586586 秒 |
| 首次邻居评价请求 | 原方法根 0.557167311 秒；不能当作精确初始化结束时间 |
| 实际评价尝试 / 返回凭证 | 10 / 10；其中 9 个完整 SAFE，第 10 个为预算耗尽 `UNRESOLVED` |
| 候选请求 / 缓存命中 | 10 / 0 |
| 原 SA 动作 | 提出 OPP 6 次、delay 4 次，其中一次解码失败；mapping 和 priority 均未提出 |
| 接纳 | 原生元数据记录 8 次邻居接纳，含 1 次上坡接纳 |
| 初始安全能量 | 约 1.0749003218912554 J；精确上下界保存在初始快照 |
| 最佳安全能量 | 约 1.0628117013850227 J；完整精确区间保存于 `method/result.json` |
| 最佳 SAFE 形成 | 原方法根 4.565429096 秒，早于 5 秒截止 |
| 复评进程命令起止 UTC | 2026-11-07 17:19:19.136578 — 17:19:19.898431 |
| 复评命令墙钟 / 根计费 | 0.761738632 / 0.657393117 秒 |
| 复评 | 一次原评价器全 SAFE，区间与方法结果相交；无再次搜索 |

这只是接口、收费、记录和停止语义的工程检查；上述能量不能用于与历史 300 秒 HEFT/OFF/ON 排名，也不计算相对优势。`formal_comparison_result` 始终为 false；`usable_as_research_evidence=true` 只表示正常停止前保留了有效完整 SAFE 凭证，不授权把本次冒烟当成正式比较。

**真实设备迁移尚未覆盖。** 本次固定短运行未提出 mapping 动作，未更换种子、加时或重试以补出所需结果。针对性人工测试和差分重放验证了该接口语义，仍不等于真实任务上的迁移证据。

## 环境、命令与完整路径

Linux 6.18.57 x86_64 / glibc 2.41；Python 3.12.14；NumPy 2.3.5；SciPy 1.17.0；5 CPU。MATLAB/Octave 不可用，本轮不依赖它们，未安装软件。完整环境 ID、解释器路径见 `smoke/plan.json`。

所有命令工作目录均为 `/workspace/paper`。以下 `O` 表示 `/workspace/paper/research/chapter4_scheduler/results/sa_adapter_preparation_20261108`。除首条直接记录外，各命令通过 `python -B "$O/command_runner.py" command_NN <实际命令>` 执行；`command_NN_started.json` / `_return.json` 记录实际 argv、cwd、起止与退出码，同前缀 `_stdout.log` / `_stderr.log` 保存完整输出。

| 日志前缀 | 实际主要命令（输出目录简写 O） | 命令耗时秒 |
|---|---|---:|
| command_01 | `python -B -m research.chapter4_scheduler.validation.sa_precheck --out O/unit_run01` | 0.558705 |
| command_02 | `python -B -m research.chapter4_scheduler.validation.sa_precheck --out O/unit_run02` | 0.591930 |
| command_03 | `python -B -m research.chapter4_scheduler.blocking.run_precheck --out O/regression` | 2.873303 |
| command_04 | `python -B -m research.chapter4_scheduler.validation.precheck --out O/legacy_validation` | 0.337425 |
| command_05 | `python -B -m research.chapter4_scheduler.validation.sa_smoke prepare --out O/smoke --checks O/unit_run02/checks.json` | 0.149426 |
| command_06 | `python -B -m research.chapter4_scheduler.validation.sa_smoke method --out O/smoke` | 5.136660 |
| command_07 | `python -B -m research.chapter4_scheduler.validation.sa_smoke post --out O/smoke` | 0.761739 |
| command_08 | `python -B O/audit.py` | 0.308799 |

关键原始文件：

- `/workspace/paper/research/chapter4_scheduler/results/sa_adapter_preparation_20261108/smoke/plan.json`
- `/workspace/paper/research/chapter4_scheduler/results/sa_adapter_preparation_20261108/smoke/method/result.json`
- `/workspace/paper/research/chapter4_scheduler/results/sa_adapter_preparation_20261108/smoke/method/input_instance.json`
- `/workspace/paper/research/chapter4_scheduler/results/sa_adapter_preparation_20261108/smoke/method/input_config.json`
- `/workspace/paper/research/chapter4_scheduler/results/sa_adapter_preparation_20261108/smoke/method_return.json`
- `/workspace/paper/research/chapter4_scheduler/results/sa_adapter_preparation_20261108/smoke/post_receipt.json`
- `/workspace/paper/research/chapter4_scheduler/results/sa_adapter_preparation_20261108/smoke/post_return.json`
- `/workspace/paper/research/chapter4_scheduler/results/sa_adapter_preparation_20261108/audit.json`

## 尚存边界

1. 未实现或执行正式 14 槽对比批次。本适配器可供后续冻结方案调用，不能据此认为正式实验已经批准或完成。
2. 公平预算应按同一外部根计费，原生初始化也计入；HEFT、OFF/ON 的完整 HEFT 初始化与原 SA 的构造初始化确实不同。强制共享增强 HEFT 初解会构成另一 SA 变体，不能静默改写原 SA。种子、初始快照、完整评价次数、失败和超时均需保留。时间预算相同不表示评价次数相同，额外记录开销也计入本方法根。
3. 复评调用同一个连续电热评价实现，验证可复现性而不是独立数值实现。当前测试没有现实温度测量或算法普遍有效性的证据。
4. `post_return.json` 的 `timing.clock_origin` 继承 `MethodBudget.summary()` 的通用“imports excluded”文本，标签不准确；本次 worker 源码、单调根和相位记录明确将选定导入计入 5 秒根。原始日志保留，不改写；分析应以真实根和相位记录为准。方法侧适配器已正确覆盖该标签。
5. 方法完整评价数现在包含没有返回凭证的异常尝试；历史旧流程的 `full_evaluator_calls` 多从已返回行统计。未来正式汇总应分列“尝试”“返回”“完整 SAFE”“缓存”，避免混用定义，不能修改历史原始数据来掩盖差异。

下一步可以基于这些接口冻结正式比较执行器及统一汇总字段；当前阶段停在工程准备，不启动新批次。
