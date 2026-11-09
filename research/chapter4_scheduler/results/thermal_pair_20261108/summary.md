# C01 原ON的50°C/78°C初温配对记录

两组均完成独立原生增强HEFT安全初始化并自然完成原ON搜索，最终解经同评价器新进程复评完整SAFE。78°C组实际出现4个有超温点见证的候选，均在HEFT初始化阶段；ON阶段未产生严格能量改善，保留安全初解。结果支持本例初温会改变候选可行性，未展示新增ON热引导或热修复收益。

|入口初温|初始化安全解 J|最终能耗上界 J|最终峰温上界 °C|最小温限余量 K|方法根/进程 s|post根 s|
|---|---:|---:|---:|---:|---|---:|
|50°C|0.882913165881|0.839132424261|53.530888863445|26.469111136555|21.942085/22.345905|0.531879|
|78°C|0.908129637265|0.908129637265|78.461183750964|1.538816249036|20.161202/20.538066|0.583621|

所有精确能量上下界、分场景能量分项/峰温区间、初始化及最终候选哈希、时间和违例证据见 `metrics.json` 与各 `method/result.json`；表中为能量上界四舍五入。温限余量定义为所有场景/节点中最小的80减峰温上界，不等于接近最优点的约束活跃性证明。

## 实际评价与不同失败类型

|初温|初始化物理SAFE/超温/未决|ON物理SAFE/超温/未决|物理评价总数|缓存命中|ON完整候选/严格改善|
|---|---|---|---:|---:|---|
|50°C|44/0/0|3/0/0|47|0|3/1|
|78°C|40/4/0|1/0/0|45|9|1/0|

方法内合计92次实际评价：88份完整SAFE、4份THERMAL_VIOLATION、0份UNRESOLVED/热预算未决，另9次缓存命中；缓存不计为新热积分。另两次最终解复评均完整SAFE。无技术故障、进程监督超时、迟到SAFE接纳、补跑或扩例。两组均远早于300秒自然停止，未补齐预算。

78°C组的四个超温点如下。这些是原仿真评价器实际形成的连续模型区间点见证，不是实测温度，也不是仅因峰温上界高于80而推定超温。非SAFE候选没有可排名的加权能量。

|候选来源|场景/节点|窗口内时刻 ms|点温度区间下界 °C|凭证形成时间 s|
|---|---|---:|---:|---:|
|heft:eft|C1/GPU0|96.100000|80.625950797543|0.165445|
|heft:energy-pass:shared-unit|C2/CPU1|144.600000|81.363551925994|2.888038|
|heft:energy-pass:shared-unit|C2/CPU2|144.600000|81.104654034861|3.297561|
|heft:energy-pass:execution-opp|C1/GPU0|125.000000|80.013251668338|9.610658|

初次贪心EFT候选在50°C为完整SAFE、在78°C为GPU0超温，候选SHA均为 `b2e5804c0591563ebc758d46f5b559d355d5c0c05633d0686d6b73452669624a`。这也是两组实际物理评价候选集合唯一的交集，无额外重评；热组96.1ms点温度下界80.625950797543°C。其余候选序列因原HEFT的安全检查与严格节能规则而分化，不能视为同一固定候选集合的逐项比较。

78°C初次EFT超温后，原HEFT的rank0构造为重复候选，不追加物理评价；rank1原生后备构造获得安全解，随后完成原有设备/频档/起始时刻改进。最终安全初始化能量即最终ON能量，两个候选哈希一致。没有增加新的热修复、热优先排序或改邻域。50°C组初始化后ON有一次严格改善；热组没有，不能把原HEFT安全过滤写成新增ON的热引导收益。

结构不可行没有记成超温：

- 50°C：HEFT局部构造失败 `{'NO_LEGAL_EFT_INSERTION': 9}`；ON构图共183次，结构拒绝 `[{'state': 'RECONSTRUCTION_REJECTED', 'reason': 'SKELETON_DEADLINE_OR_WINDOW_EXCEEDED', 'count': 165}, {'state': 'RECONSTRUCTION_REJECTED', 'reason': 'SKELETON_DIRECTED_CYCLE', 'count': 12}]`。这些没有生成可评价候选，不是热违例或全局不可行证明。
- 78°C：HEFT局部构造失败 `{'NO_LEGAL_EFT_INSERTION': 10}`；ON构图共125次，结构拒绝 `[{'state': 'RECONSTRUCTION_REJECTED', 'reason': 'SKELETON_DEADLINE_OR_WINDOW_EXCEEDED', 'count': 123}]`。这些没有生成可评价候选，不是热违例或全局不可行证明。

## 模型语义与输入审查

沿用原四节点连续RC模型：`C dT/dt=-G(T-Ta·1)+baseline+activity+k(T-Tref)`。环境与参考温度均25°C，原功耗模型声明有效范围20–100°C，80°C温限不变。原配置已有78°C初温条件。78°C处在声明范围且低于温限；正热容、对称接地被动导热矩阵的有理数检查通过。各场景原本独立重置入口状态，78°C是外部给定的均匀热启动状态，L入口频档/无未完成任务不要求温度处于稳态。

物理限制：参数及20–100°C范围均为原抽象仿真的自设声明，并非本轮实测或校准；没有证明真实芯片在78°C处的精度。额外初始储热 `sum(C)×28=6.16 J` 来自外部状态，预热成本不在230ms运行能耗中。两组能耗差同时受温度修正与调度变化影响，本轮未分离两者贡献，也不把热组能耗更高直接解释为算法退化。

原候选无关共同输入合同固定50°C，原文件和校验器均未改。新桥先严格验证原合同，然后只改两场景各四节点入口和对应config默认初温。逐叶对比确认config仅1处、instance仅8处变化，其余字节语义一致；新派生输入使用自己的哈希，不伪造旧provenance。场景ID、实例ID、C1/C2双场景、230ms实际窗口（config默认400ms保留）、72模式、DAG、请求期限、部署/CPU频域规则、auto-L、精度及物理参数全部保留。

原文件 `07e458f3f811746f78931a340d258e230a8de4afb62ac0140459feff6a7bf80a`；派生输入/config哈希：

- 50°C：instance `b292ced36fec69f4aa97c39edce6df7df58a27b9cec85135ad77a7e0cf4b8f48`；config `15ca987441165a0e994ddbe073874ef23c76ee6ec26d4eecfa41b436ca0c6c83`。
- 78°C：instance `e5eda4223df601fb54cde9906329df06934146f6c765cb84ae6be7694ac530b0`；config `5eb465a98dd56744d3cf9c25c33f14529fd07f4866de3fb57508aac2904fe39f`。

完整SAFE要求两场景全230ms连续温度上包络不越80°C、合法调度及共享部署/资源/频域/时限全部满足，并形成预算内准确加权能量。只有模型有效范围内的实际点区间下界高于80才称可核验超温；模型有效范围未决、峰值包络不确定、精度/预算或结构失败不替代热违例。若无安全初始化，原方法会停止该组，不能称ON完成。本次两组该分支未发生，仅人工测试覆盖该停止语义。

## 冻结、执行、计时与日志

基线 `0a01ae35320507618df58dcb19f111548eafc971`，分支 `chapter4/r2-r5-validation-20261107`。方案创建 2026-11-08T14:50:27.760550+00:00，SHA256 `baecff131d1522a4f1762382f48f54c3b1a75e82d7937f708ad6368a6bed7f80`；532项源码/输入/检查身份与3930个旧结果文件绑定保护，结束后核对保持。`execution/source_snapshot/`、`original_common_input.json`、`frozen_inputs/T50/`和`T78/`可复核。原算法、评价器、旧输入及历史结果未改。

任务首个带时间工件 2026-11-08T14:45:23.567904+00:00。真实批次 2026-11-08T14:50:38.740729+00:00–2026-11-08T14:51:25.664315+00:00，46.923633秒；外层启动/预检另见 `command_05_return.json` 的48.774601秒。两次独立原ON各300秒绝对根，含科学导入/身份检查/读取派生/原生初始化和内部全部评价；解释器启动、落盘/序列化另报进程墙钟。两次正常安全解各最多一次60秒同评价器post，不是独立数值实现。预定顺序50再78，日历上限1200秒，无重试或预算转移。

环境：Linux-6.18.57-x86_64-with-glibc2.41，Python 3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]，numpy 2.3.5 / scipy 1.17.0，5CPU，OMP/OpenBLAS/MKL/NUMEXPR固定单线程；资源预检通过，未安装依赖或调用MATLAB/MILP。

实际主要命令（cwd `/workspace/paper`；完整精确argv、起止及stdout/stderr见 `command_01`–`command_07` 记录）：

```text
python -B -m research.chapter4_scheduler.thermal_pair.precheck --out research/chapter4_scheduler/results/thermal_pair_20261108/unit_run03
python -B -m research.chapter4_scheduler.thermal_pair.run prepare --out research/chapter4_scheduler/results/thermal_pair_20261108/execution --checks research/chapter4_scheduler/results/thermal_pair_20261108/unit_run03/checks.json
python -B -m research.chapter4_scheduler.thermal_pair.run batch --out research/chapter4_scheduler/results/thermal_pair_20261108/execution
python -B research/chapter4_scheduler/results/thermal_pair_20261108/analyze.py
```

各组精确起止/参数：`execution/calls/<slot>/worker_command_started.json`、`worker_command_return.json`、`post_command_*.json`；日志为同目录 `worker_stdout.log`、`worker_stderr.log`、`post_stdout.log`、`post_stderr.log`；逐次完整候选日志 `method_evaluation_journal.jsonl`，原始结果 `method/result.json`。

最终19项输入/根计时/真实接口绑定下人工算法凭证/无SAFE停机/故障及无重试检查通过，未调用真实搜索或热积分。首轮夹具仍给78°C入口使用50°C假峰温，被原SAFE校验拒绝；仅修人工夹具，失败记录保留。随后两轮通过（末轮补准确证据类型标签），不把重复执行累加成独立覆盖。真实批次结束后1046条只读断言通过，包括逐份SAFE及超温见证、完整合法性、9处温度差异、初始化/ON状态、统一计数、复评能量相交和冻结副本；强制禁止新搜索/热积分，实际0。

## 结论边界

本例热启动确实使原贪心候选由SAFE变为有见证的超温，原HEFT后备与改进阶段仍找到安全初解；最终热组温限余量约1.539K。ON热组完成声明邻域检查但没有严格能量改善，保留原解，这是本轮需要保留的无收益结果。不宣称最优、普遍性、紧热情况下新增算法有效或热引导收益；没有OFF消融，也没有新热修复。

本轮范围完成即停止，不扩例、调参、补跑、推送或合并。下一步仅建议据实将“温度改变候选可行性，但热组增量邻域未获益”的证据与限制纳入第四章，不自动启动其他验证。
