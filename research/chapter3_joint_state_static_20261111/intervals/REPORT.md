# 最新 auto-L 完整 R1：逐区间联合状态与电热行计数

本子任务从已有归档选项以 Fraction 精确重建事件和半开区间，仅做静态文件/算术检查；没有重新构模、调度构造、热评价或任何求解调用。全部 424 个区间的状态 tuple、顺序及变量索引与归档 w 变量逐项相同。

## 身份与开关

- 固定提交：`7631a16d420fbd8711af1e6cb2f35bc03cf9700d`；归档七文件逐个 Git blob 相同。
- 来源：`research/chapter3_support_autol_lp_20261111/autol_build/rev02/`。原始完整 R1，AB/AC 各6次Stage执行、共12次、66模式，保留400ms窗口、5ms启动网格和非整数结束。
- 本表专指 `execution/on`，`propagate_support=True`。`fix_late_options`、`aggregate_opp_locks`、`relax_auxiliary_integrality`、`strengthen_energy_lower_bounds`、`prefilter_deadlines` 为 True；`cumulative_precedence`、`preeliminate_closed_anchors` 为 False。
- idle_policy=`auto_low_immediate_v1`；资源域顺序 CPU/GPU/NPU，各域3频档；温节点顺序 CPU1/CPU2/GPU0/NPU0。
- 冻结 `milp.py` SHA256：`f34809ad6d8e15d4639af8cdcfb62b3ebb4603772e513289280ccdefa783fefb`。全部216份冻结源文件及2份输入哈希校验通过，具体见 summary.json。

## 计数

|场景|选项|事件|区间|状态块|温度行|能量行|两者合计|
|---|---:|---:|---:|---:|---:|---:|---:|
|AB_offset_0ms|603|216|215|4861|38888|9722|48610|
|AC_offset_0ms|522|210|209|4937|39496|9874|49370|
|合计|1125|426|424|9798|78384|19596|97980|

对场景 s 的区间 l，令 D 为 CPU/GPU/NPU，active 为原选项在 [left,right) 上的活跃集合。代码先对每域构造 P[d]={L}∪{该域 active 选项频档}，再生成 S[l]=×d P[d]。事件端点包含每个选项精确起止，所以 start≤left<end 等价于该选项覆盖整个区间；活动候选不等于最终被选中的任务。

每个 `(场景,区间,状态)` 块依次建立4个温度传播仿射关系和1个完整区间能量仿射关系。每个 `affine_conditional_eq` 发出 upper/lower 两条条件外包行，因此温度行数=9798×4×2=78384，完整能量行数=9798×1×2=19596，合计9798×10=97980，占所有124338行的78.8013%。这48990组上下行不应误算为97980个独立条件等式，也不应把浮点外包行等同精确算术等式。

源码证据：冻结 milp.py 1033–1056 行含 possible 的生成、笛卡尔积、joint one-hot/边际；1091–1111 行含逐状态四温节点及一能量的条件行。逐字摘录及 SHA 保存在 source_formula_excerpt.json。由同一算术另核对 joint_unique=424×2=848、joint_marginal=424×3域×3频档×2=7632；均等于归档 family counts。

## 区间分布

|单区间状态块数|AB区间数|AC区间数|
|---:|---:|---:|
|1|2|1|
|2|1|2|
|3|6|4|
|6|1|4|
|9|38|24|
|18|2|2|
|27|165|172|

- AB 在区间索引2–166（时间10–113ms）有165段各27块，共4455块，占AB块数91.65%。最短间隔0.1ms，14段；142段小于1ms。最后 [156.6,400)ms 没有活跃选项，只保留 L/L/L 一个状态，但仍有完整尾段电热行。
- AC 在索引2–173有172段各27块，共4644块，占AC块数94.07%。最短间隔1/6ms，9段；159段小于1ms。最后 [143,400)ms 无活跃选项，只保留 L/L/L 一个状态。
- 两场景都没有小于0.1ms的区间。短间隔来自合法非整数结束与其它事件交错，不应为缩模随意四舍五入、删除事件或剪去空闲尾段。
- 逐区间完整状态/对应 w 列索引见 interval_states.json；易读全表见 interval_counts.csv；按精确长度的区间频数见 duration_histogram.csv。长度均为毫秒，源码中相应事件单位为秒，二者精确乘1000转换。

## 检查、运行与限制

实际命令（工作目录 `/workspace/paper`）：

```sh
python3 -B research/chapter3_joint_state_static_20261111/intervals/analyze_intervals.py > research/chapter3_joint_state_static_20261111/intervals/stdout.log 2> research/chapter3_joint_state_static_20261111/intervals/stderr.log
```

实际分析开始 2026-11-11T07:33:54.132401+00:00，结束 2026-11-11T07:33:55.022757+00:00，脚本墙钟 0.890371541s。对应北京时间15:33:54.132401–15:33:55.022757（UTC+8）。Python及操作系统见 summary.json。stdout.log/stderr.log 保留完整输出，本次退出码0。

纯检查包括：固定提交七文件 blob 身份，冻结输入/源 SHA，精确半开区间覆盖400ms，所有424区间/9798状态的 tuple/顺序/索引相同，温度/能量及joint辅助行计数一致。它们没有求解一个可行调度，也没有证明生成笛卡尔积内每个状态可达；状态不可达性由其它子任务单独分析。此处不把缓存命中数当状态数量，不据行数占比推断求解加速。
