# K.196：完整链小域整体MILP结果

日期：2026-10-26。**原整体MILP在300秒内找到了新整数调度，完整安全能耗从1.088852 J降至0.986251 J，改善9.422857%，达到K.194受限域的ε最优参照。** 本次为正常时间截止，无构模或数值状态冲突；求解器本身没有证明最优。

## 1．实际执行与结果

沿K.195冻结入口执行1次whole方法和1次独立post，无补跑。原受限AB／AC完整三Stage链、H响应、400 ms窗口、5 ms起点子集、四节点、CPU共享频率域、50／80°C、auto-L、温度漏电及原期限／权重不变。未导入K.194见证、缓存或历史最优解作为初解。

| 观察项 | 结果 |
|---|---:|
| 同次构造器初解 | 1.088852027249 J；68.547秒形成完整SAFE |
| 第一份整数回调 | 78.765秒收到；与初解相同，不能算新调度 |
| 第二份整数回调 | 85.703秒收到；88.437秒完成连续安全评价 |
| 新方案完整安全能耗 | **0.986251057947 J** |
| 相对自身初解 | 少0.102600969302 J，改善**9.422857%** |
| K.194独立穷举参照 | 0.986251057947 J；两者上界精确相同 |
| 与枚举下界的差距上界 | 约2.15×10⁻²⁹ J，低于预声明ε＝10⁻⁶ J |
| 唯一独立post | 完整AB／AC、完整窗口均SAFE；复现同一能量区间 |
| 热反馈新增行 | 0 |

“达到小域ε最优”来自独立穷举参照与本次完整SAFE回执的比较，不是将求解器退出状态改称最优。它只覆盖冻结受限域，不扩大到原完整P0域或连续启动域。

## 2．新调度改了什么

跨场景共享部署仍为A.main→NPU0；B.main→NPU0、C.main→GPU0也未改变。求解器主要联合调整工作点和起点：

| 场景／Stage | 初解：工作点／起点ms | 新方案：工作点／起点ms |
|---|---|---|
| AB、AC的A.main | H／10 | M／15 |
| AB的B.main | H／40 | M／50 |
| AC的C.main | H／30 | M／35 |
| AB、AC的A.post | H／40 | H／95 |
| AB的B.post | H／75 | H／95 |
| AC的C.post | H／75 | H／95 |

全部前处理不变。两个场景的后处理分别在95 ms共同启动，缩短了CPU域高工作点活动时间的并集；main采用M档降低活动及相应基准功率。温度相关能量仍按完整轨迹计算，节能比例以上表完整系统能耗为准，不单独归因给某一项。最终方案与枚举见证相同，仅列表排列不同。

## 3．规模、时间与退出原因

实际模型为2201变量、72个Stage整数选择、9215行、65167个非零项。原78项仅删除6个必超期项，未固定A.main设备，也未使用分解、邻域或增广数值表达。

| 计时或求解信息 | 实测 |
|---|---:|
| 构模 | 5.015秒 |
| MATLAB启动 | 61.391秒，计入方法根预算 |
| 求解器进入事件收到 | 方法第73.906秒 |
| 原生MaxTime | 226.1961秒，由共同根剩余时间派生 |
| 原生intlinprog调用墙钟 | 230.661秒；其中内部最终计时226.634秒 |
| 方法证据截止 | **300.000秒** |
| 截止后清理 | 11.328秒；不接纳新候选或能耗 |
| 方法返回墙钟／方法子进程墙钟 | 311.484／313.656秒，后者还含导入等执行层成本 |
| 独立post墙钟 | 2.594秒，低于60秒上限 |
| 整批实际日历 | **318.297秒**，低于480秒上限 |

预算内第293.031秒，日志记录20000节点、下界约0.875217333 J。最终原生回执在截止收口期间归档：exitflag＝2，因MaxTime停止，21189节点，2个可行点，报告相对gap＝5.590115%。这些原生界不是独立连续热能耗证明。

原接纳状态为`NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST`：根截止时最后请求未决，最终向量未用于新接纳；保留的是第88.437秒已经完整确认的SAFE。原生回执与输入矩阵未出现此前“初点数值通过、却报告无解”的冲突。方法根没有延长，但原生停止及进程清理并非硬实时零延迟，实际墙钟如上列出。

## 4．审查与论文意义

归档分析及内部独立审查各19项通过：源／输入／原生选项身份、整数候选归属、预算内完整SAFE、原矩阵残差、同域参照及一次post均核对。第二份候选与初解相比有16个Stage整数列变化，对应8个场景内Stage选择变化；原矩阵最大违规约2.13×10⁻¹⁴，整数误差为0。

第三章现在具备“独立穷举小域参照＋同域整体MILP实际生成改善方案”的证据。可以写该实例在300秒预算内达到ε最优参照；不能写求解器在300秒内证明最优。此例未触发热反馈，仍不能补充反馈节能收益的结论。

本次无需继续延长小域预算或恢复大域数值诊断。下一步建议先将小域参照及MILP结果用于第三章求解正确性展示；是否开展同域HEFT／原C质量比较，另行讨论，不自动增加调用。主线⑧的热目标、异构资源、共享部署及规模期限实验保持独立。

## 5．证据入口

- [冻结准备与原预算](完整链小域整体MILP执行准备_K195.md)，[执行计划](chapter3_experiments/results/small_whole_preparation01/plan.json)，[本次资源预检05](chapter3_experiments/results/small_whole_preparation01/prelaunch_k196_recheck05.json)。
- [方法接纳及计时](chapter3_experiments/results/small_whole_execution01/method_return.json)，[完整原结果](chapter3_experiments/results/small_whole_execution01/method/wrapper_raw_result.json)，[不可变回调日志](chapter3_experiments/results/small_whole_execution01/method/diagnostic_events.jsonl)。
- [原生最终回执](chapter3_experiments/results/small_whole_execution01/method/matlab/request_000001.response.json)。原矩阵／初点载荷`method/matlab/request_000001.mat`及原生向量`request_000001.native.mat`在本地同目录留存；`*.mat`受忽略规则保护，不上传。仓库保存其hash、JSON回执及[归档范围](chapter3_experiments/results/small_whole_execution01/archival_scope.json)，未强制添加或更名绕过规则。
- [独立post完整回执](chapter3_experiments/results/small_whole_execution01/postcheck.json)，[post接纳](chapter3_experiments/results/small_whole_execution01/post_return.json)，[整批终态](chapter3_experiments/results/small_whole_execution01/terminal.json)。
- [纯归档分析](chapter3_experiments/results/small_whole_execution01/analysis.json)，[可复跑分析脚本](chapter3_experiments/results/small_whole_execution01/analyze_saved.py)，[内部独立审查](chapter3_experiments/results/small_whole_execution01/internal_review_k196.json)，[K.194参照](chapter3_experiments/results/small_exact_execution01/reference.json)。分析脚本仅读JSON、hash和有理数，不再次求解或积分；重读可调用`analyse()`，不覆盖原`analysis.json`。

`post_return.json`中`new_physical_evaluation=false`只描述其内部回执一致性检查函数；本次post实际执行了1次新的完整物理评价，保存在`postcheck.json`，并未生成新的优化上界。

## Material Passport

ID：K196；类型：单输入受控求解实验；状态：已运行、完整安全结果已复核、有限域ε质量已核实。证据范围：声明的抽象模型与受限选择域。独立审查：本任务子代理的内部只读复核，不是外部审查批准。未进行统计总体排名或物理硬件验证。
