# 共享映射 MILP 通路交接：证据与停止边界

> 发布传输说明：6个文本文件统一为LF换行，原始JSON数据、源码字符及科学结果未改变。发布字节哈希以MANIFEST为准；报告中的原输入/worker哈希指本机原件。详见[换行转换记录](TRANSPORT_NORMALIZATION.json)。本机执行环境在发布前断开，因此本交接不宣称这些文件与原件字节相同。


本包整理 2026-11-06 已完成的本机 Windows / Python 3.12.4 / MATLAB R2023b 诊断，供其他会话只读审查。**没有产生新的实验；初解采纳、启动与停止策略这条排查线已经停止。源码快照和历史命令不构成新的运行授权。** 不应自动重跑、增加时间、改容差、换求解器或联系第三方。

主要结论是：同一个 MATLAB worker 连续处理 12 个玩具请求已成功；原完整 AB/AC 子模型多次及时返回了完整响应，却没有返回可准入的求解器向量。保留的物理 SAFE 解来自当次现场初解构造器，不能算作 MILP 找到的解或优化贡献。当前没有全局最优、全局不可行或算法性能比较的证明。

## 阅读顺序与文件范围

先看本页，再查各证据目录的摘要、审计及原始响应；文件实际清单和字节校验以 [MANIFEST.json](MANIFEST.json) 为准。来源与代码版本映射见 [source_index.json](source_index.json)。

| 包内目录 | 主要证据及用途 |
|---|---|
| [evidence/toy12/](evidence/toy12/) | SUMMARY、逐请求结果、传输审计、启动与清理：12 次玩具通信成功 |
| [evidence/soft10/](evidence/soft10/) | SUMMARY、AUDIT、driver 审计、原 condition 字段提取（完整SAFE回执保留）及两景响应：10 秒软帽 |
| [evidence/soft30/](evidence/soft30/) | 同上，另含单参数差异：30 秒软帽 |
| [evidence/control_A/](evidence/control_A/) | 保留普通场景计时取消的实际记录；CONTROL_RESULT 中 A 臂 |
| [evidence/control_B/](evidence/control_B/) | 仅抑制普通场景计时取消的实际记录；CONTROL_RESULT 中 B 臂 |
| [evidence/ab_probe/](evidence/ab_probe/) | RESULT_AUDIT、driver审计、原响应与原生向量自检：唯一 AB 探针 |
| [inputs/](inputs/) | 原冻结配置与完整实例，各次重新读取，没有用旧候选初始化 |
| [sources/](sources/) | `.m.txt` 与 `.py.txt` 等脱敏审查快照；不是可直接执行的完整环境 |

若包内包含早期离线报告，其中“native 未启动”是该报告写成时的阶段状态；后续实际运行以相应 SUMMARY、CONTROL_RESULT、RESULT_AUDIT 与运行回执为准。不要混淆离线测试与真实 MATLAB 结果。

## 固定的问题与预算

原配置 SHA-256：`132323b4b18dd514b9baa929543d235ff91bb07026a60e7b629e1adb6aaaa5e2`；原完整实例 SHA-256：`01eacb2a653d56419c32f38740021a787ea01ac9e7ade407bef2edd81ec6ef89`。

原实例按 AB→AC 排序，每景 6 次执行，共 12 次；A/B/C 均保留 pre/main/post 完整任务链，原 β=1.3、场景权重、平台、电热参数、频档及启动时刻域保持。仅选择一个共享设备映射：`A.pre=CPU1, A.main=NPU0, A.post=CPU1`。这是声明顺序中的首个历史条件，用于验证接口；不是按此次能耗择优选择，也不是遍历全部共享映射。固定这三个设备不等于固定频档、调度时序或全部设备选择；未加入投影、删 Stage 或额外候选域裁剪。

完整 AB/AC 诊断各用同一个 180 秒端到端根预算，覆盖入口核验、导入、构模、现场初解、连续 SAFE、向量补全/数值准入、MATLAB 启动、求解/回调、原场景验收、聚合及方法归档。每景最多一请求、一个 worker lifetime。10/30 秒是原生求解软帽，不是另发一个独立场景根；`options.MaxTime` 不是硬壁钟中断，实际调用可能稍长，但不能延长根预算或接纳根截止后的新证据。清理按原 20 秒宽限/40 秒总上限单列，不重开方法预算。资源门槛为可用内存 2 GiB。

## 已完成的实际运行

下列时间均为 2026-11-06 UTC（北京时间加 8 小时）。不同记录的启动点类型明确列出；“方法/清理”来自根计时审计，不应由 MATLAB 启动时间反算。

| 记录 | 已记录启动点 | 结束记录 | 方法/根内用时；清理 | 实际结果 |
|---|---|---|---|---|
| toy12 | 控制器 09:14:52.500362 | 09:15:28.422199 | 总根 35.922 秒；清理 3.907 秒 | 同 worker 12/12 独立单变量请求通过，含第 10–12 请求；向量与目标已核 |
| soft10 AB/AC | MATLAB launch 10:01:29.853325 | runtime final 10:02:37.416840 | 方法 78.140 秒；外层清理约 3.844 秒 | 两景 exitflag=0，x/fval 空 |
| soft30 AB/AC | MATLAB launch 10:30:03.296033 | runtime final 10:31:44.007606 | 方法 111.000 秒；外层清理约 3.734 秒 | 两景 exitflag=0，x/fval 空 |
| control A | Python 11:15:33.994288 | 11:17:32.844059 | 方法 114.812 秒；清理 4.016 秒 | 两景 done 实际 stop=true；均空返回 |
| control B | Python 11:18:51.869783 | 11:20:38.157103 | 方法 102.984 秒；清理 3.281 秒 | 两景 done 实际 stop=false；均空返回 |
| 唯一 AB 探针 | 根入口 11:51:00.045712 | 包装结束 11:52:23.210092 | 方法 79.015 秒；清理 4.157 秒 | MaxFeasiblePoints=1，仍空返回 |

toy12 的目标是玩具代数值，不是论文能耗；该成功只证明这一次请求序列跨过了第 10 项，不能证明历史启动崩溃或 K116 第 10 请求 Permission denied 的根因已经解决，也没有覆盖完整物理模型 SAFE。

soft10/soft30 的 AB 模型为 8,738 变量、40,078 行；AC 为 14,014 变量、90,260 行。soft10 实际 MaxTime 约 9.438/9.282 秒，调用壁钟约 10.775/9.743 秒；soft30 实际 MaxTime 约 29.453/29.203 秒，调用壁钟约 30.453/29.609 秒。两景均真实进入 intlinprog、完整响应在根内结算并正常清理；但没有可供新候选评价的 x，因此 `accepted_for_evaluation=false`、严格 `native_technical_pass=false`。

## 停止策略控制实验能说明什么

A/B 两臂共用同一套新加停止决策日志的冻结源码（429 文件），各自新根、新 worker 和现场初解。A 保留原普通 `SCENE_SLICE_END` 取消；B 只抑制该普通计时取消，保留热违规、资源、用户、根/worker 停止和清理。历史未加诊断日志的 soft30 仅作参考，不能当作与新 B 臂完全同版本的单因素对照。

记录保留原 `publish → callbacks 追加 → 停止检查` 顺序及四项左到右短路读取。每次实际 stop、已读条件和值、未读原因最终存入 MAT/JSON；日志失败不会改变已决定的停止布尔，但会阻止技术通过。诊断有额外赋值与记录开销，不能声称计时完全无扰动。

A 两景实际发布普通取消，done 读到 cancel=true 并返回 stop=true；B 两景确实触发了抑制，done 四项均 false、实际 stop=false。四个请求最终仍全部 x/fval 空、exitflag=0，输出报告 MaxTime，最终 numfeaspoints=0、numnodes=0。因 B 的实际 stop=false 仍空返回，普通计时取消不是这次空返回的必要条件；但不能外推所有停止策略均无影响。每臂只运行一次，A 后 B，机器负载、启动和实际 MaxTime 有差异，不作速度比较或根因定论。

## 唯一 AB 初解探针及未解矛盾

此探针仅运行原完整输入中的 AB 子模型，AC 未构模/求解，不能声称完整双景 SAFE。180 秒根与最多 30 秒软帽保留；唯一求解策略变更为 `MaxFeasiblePoints=1`，`Display='iter'` 用于观测，普通场景计时取消按 B 配置抑制。原预处理、算法、约束与整数容差和数学模型未改变。

启动前和请求时模型 payload SHA-256 均为 `affa9501fc75d8ee6ccc314b3b3043dce88a704f0c63d50691df9ebda7d27001`。8738 维 x0 在该次根内由原构造器现场生成，原连续 SAFE、补全和 Python 数值准入通过；native MAT 的 initialPoint 与本次提交向量字节一致。MATLAB 对原数组自行计算最大不等式残差 `2.1316282072803006e-14`，等式、上下界及整数违规均 0，满足原 ConstraintTolerance=1e-9、IntegerTolerance=1e-6；`c'*x0=1.0461208468704055`。这是我们自己的原生输入自检，**不是 intlinprog 内部采纳初解的证书**。

实际选项 MaxTime 约 29.453 秒，intlinprog 调用壁钟约 31.339 秒；init/done 实际 stop 均 false。最终原生 MAT 与 JSON 的 x/fval 仍空，exitflag=0，日志仅报告 MaxTime，没有足以定位内部阶段的迭代输出。done 回调中的 `numfeaspoints=1` 与最终 `output.numfeaspoints=0` 不一致，且没有与该计数绑定的向量、目标或可行性凭据；这一矛盾仍未解释，不能据此宣布初解已被采纳、被忽略或被拒绝。`solver_returned_point=false`、`solver_candidate_safe=false`、`native_technical_pass=false` 如实保留。

## SAFE 解与能量的来源

完整双景诊断中，现场初解的 AB/AC 上界约为 1.046120846870406 J / 1.115526056796232 J。原权重聚合的上界为 **1.08082345183331871430416362243374659121963251848651500438105 J**，来源严格为 `initial_constructor`；`inner_MILP_improved_initial_upper_bound=false`。相同数值是各次现场调用的确定性结果，不是允许读取旧候选的依据。

唯一 AB 探针只保留 AB 局部初解上界约 1.046120846870406 J，未生成完整双景上界。新驱动分别核查模型视图和同候选的原场景 SAFE，不会用早先初解 SAFE 替代一个未经验证的求解器返回候选。原 `condition/result.json` 中 `state=SAFE` 可以表示保留的初解；外层严格技术状态仍可能失败。`status=SOLVED` 只表示原生调用完成，不保证 x 非空，更不代表最优。

## 历史命令入口与审查限制

历史工作目录均在 `${TASK_ROOT}` 的各独立任务目录内。`${PYTHON_EXE}`、`${MATLAB_EXE}` 为机器相关占位符，不包含公开凭据。实际命令索引见各证据中的 COMMAND 与 EXECUTION_RECORD，源码快照通过 source_index 定位。

| 运行 | 历史 Python 入口语义 |
|---|---|
| toy12 | `${PYTHON_EXE} -B -u -c "... staged_probe_prepared.run_probe(...) ..."` |
| soft10/soft30 | `${PYTHON_EXE} -B -u -c "... native_entry_prepared.future_native_single_mapping(...) ..."` |
| control A/B | `${PYTHON_EXE} -B -u control_validation_20261106T111353Z/run_arm.py A` 或 `B` |
| AB 探针 | `${PYTHON_EXE} -B -u native_ab_entry.py` |

这些是既有调用的识别摘要，省略部分不是可执行命令。实际 MATLAB 由冻结桥接以 `${MATLAB_EXE} -batch ...` 启动；完整桥接、参数、现场初解和验收关联应结合冻结源码及原回执审查，不能只运行 `.m` 文件复现整个协议。PowerShell 包装命令的退出值也不能代替 Python 原 PASS 或 MATLAB cleanup 回执。

本包公开的是已脱敏的审查材料，排除了私人绝对路径、真实进程标识、授权/会话标识及动态偏好数据；必要的替换记录和来源哈希以清单为准，不能把脱敏后的字节哈希冒充原始文件哈希。离线测试只证明软件控制边界，不证明新的物理 SAFE。现有证据不足以确定 intlinprog 内部阶段、初解 incumbent 登记机制或全域求解性能；用户已叫停本条排查，后续会话应先读证据和保持停止状态，不自动启动新实验。
