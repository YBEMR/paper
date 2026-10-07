# 68号运行说明

入口：`research/matlab_config_value_src/run_milp68.m`。MATLAB R2023b，工作区偏好目录`.runtime/matlab_prefs`。

```matlab
addpath('F:/by/11111/research/matlab_config_value_src')
p = run_milp68('precheck');
f = run_milp68('frozen', fullfile(p,'receipt.mat'));
```

预检凭据绑定全部验证目录顶层MATLAB源码及53号两份JSON。正式执行原10项，每项顺序为no_repair、milp_engineering，各独立60秒，输入重新加载计费。方法内部不读取历史结果。未完成／超时不重跑加预算。

MILP列为Stage、模式、起点三元组；系数使用0.25 ms时间单位和0.0625 mJ活动能量单位，启动仍1 ms。唯一选择、依赖及全部真实区间冲突用稀疏矩阵表达。热检查使用原b64连续峰温包络；最终候选明确违规后加入完整赋值排除，不增加温度切面、修复或对称删除。

独立认证下界默认L0；内部lowerbound与gap另存solver_trace，非独立证书。safe_upper须经过完整合法性、能耗双算及热包络核对。相等于L0才标independent_optimal；solver_converged_safe仅表示求解器数值收敛且输出经热安全核对。solver_reported_infeasible不等于独立已证无解。不存在合法Stage选项时可直接证明网格无解。

回调对新整数候选评价，缓存仅在一次方法调用内存在；rootlp的fval不当整数候选。每轮MaxTime只获总预算剩余量。回调与返回后检查墙钟，预算外新信息不升级证据；停止延迟仍计实际调用耗时。

`solver_inclusive`包含回调中的解码和热检查，因此不可与thermal/decode子计时直接相加。检查点持久化、事后复核和图表输出在方法预算之外，不补搜索。输入加载时间计入总调用及首解时间；嵌套事件保留方法内相对时间，input_setup_s单列。

结果保存在`milp68_reports/`新的时间戳目录，含源码／输入快照、环境、预检、逐方法MAT、summary.csv、输出复核、时间表、内部界和U/L轨迹图。旧源码和历史结果保持不变。

本轮正式结果：`frozen_20260927_113720_286`。20次方法调用完成，原MAT不改；正式准入凭据为`precheck_20260927_113432_803`（124项）。方法运行后的导出容器修复及诊断计时器修复在audit.json中记录，当前可用源码凭据为`precheck_20260927_114309_369`（125项）。不以当前代码哈希替换正式快照哈希。

已知记录限制：原5项回调检查候选的MILP调用中，嵌套timer覆盖使solver_inclusive分项偏小。预算、总墙钟、首个安全时间独立使用clock，不受影响；当前源码已修复。不重跑研究案例。cost_diagnostics.csv列出无效标志及由原每轮剩余预算／返回时间戳导出的调用区间，后者包含回调及检查，不是内部LP单独耗时。检查点序列化在预算外，但本次未逐次测量其时长。

`summarize_saved.py`将MAT原始事件／状态读为JSON并核对历史哈希；`finalize_saved.py`核对保存结果、版本并生成诊断表；`plot_saved.py`只从保存轨迹生成figure_01—10.png，增加点标记以显示很短的安全见证轨迹。三者均不搜索或热修复。

`bounds_units_*.csv`列为方法时间、认证下界、安全上界，能量为0.0625 mJ单位；`solver_trace_units_*.csv`列为方法时间、轮次、系统内部下界、系统内部fval、原relativegap、节点数，其中能量同单位、原relativegap按R2023b原口径保留。JSON中的嵌套事件时间为方法内部相对时间，需加input_setup_s；CSV轨迹及总首解时间已包含输入开销。无有限上界的Inf不是实际能耗。
