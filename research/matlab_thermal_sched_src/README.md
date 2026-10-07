# CPU–NPU 瞬态热调度最小验证模型（MATLAB）

2 核 CPU + 1 个 NPU、2 个推理请求的离散穷举调度模型，用于回答：

> 对于有限时长的 CPU–NPU 推理阶段，采用稳态温度约束是否会排除实际上满足
> 全过程温度上限、而且能耗更低的调度方案？

## 运行方式

在你的 MATLAB（R2023b+）中：

```matlab
cd('...\matlab_thermal_sched');
run_all      % 第一轮：正确性测试 + 主实验（稳态 vs 瞬态）+ 消融 + 参数扫描
run_round2   % 第二轮：活跃区间扫描（Phase 1）+ 调度价值指标 A/B/C（Phase 2）
             %        + 单步瞬态预测贪心对照（Phase 3）
```

所有报告（txt）与图表（png）输出到 `output\`。

## 文件结构

| 文件 | 作用 |
|---|---|
| `config_default.m` | 全部合成参数（时长/功率/温度/热网络）集中管理 |
| `thermal_build.m` | 三节点 RC 热网络（G、C、A、Ginv），支持去 CPU–NPU 耦合 |
| `enumerate_schedules.m` | 离散 1ms 网格穷举（映射×频率×启动时刻），支持移除依赖 |
| `schedule_power.m` | 每方案 1ms 粒度功率矩阵 |
| `eval_schedules.m` | 批量能耗 + 稳态/瞬态热可行性（瞬态为 0.25ms 采样约束） |
| `compute_trajectory.m` / `plot_gantt.m` / `plot_temperature.m` | 轨迹与绘图 |
| `single_node_test.m` / `boundary_tests.m` | 正确性测试（解析解、边界情况、细网格） |
| `run_main.m` / `run_ablation.m` / `param_scan.m` / `run_all.m` | 第一轮入口 |
| `scan_active_region.m` | 第二轮 Phase 1：功率×T0×τ 扫描找活跃区 |
| `scheduling_value_analysis.m` | 第二轮 Phase 2：指标 A/B/C |
| `greedy_scheduler.m` / `run_greedy_compare.m` | 第二轮 Phase 3：单步预测贪心对照 |
| `run_round2.m` | 第二轮入口 |

## 模型要点

- 调度网格 δ=1ms，非抢占，允许主动等待；阶段时长均为 δ 整数倍。
- 统一 RC 模型：C·θ̇ = −G·θ + q，稳态与瞬态使用同一套 G/C/q/T_amb。
- 能耗统一观察窗口 H=max(D_A,D_B)，空闲计 idle 功率，无 sleep/wake。
- 稳态检查：每个恒定功率区间的平衡温度 ≤ T_lim。
- 瞬态检查：0.25ms 采样轨迹 ≤ T_lim（采样点约束，非严格连续时间硬约束；
  如需更严格可调 `eval_schedules` 的 `opts.sub`）。
- 穷举为离散模型下的完整穷举（4 映射 × 4 频率组合 × 全部合法启动时刻）。

## 已知限制（如实声明）

1. 瞬态可行性是"采样点温度约束"（sub=4，0.25ms），不是严格连续时间峰值证明。
2. 穷举限于 1ms 离散网格；默认实例的0.5ms复算通过，不代表热活跃实例已通过调度网格收敛检验。
3. 参数全部为合成值，不代表真实硬件收益。

## 第三轮：主动等待基线（已实施）

```matlab
addpath('F:/by/11111/research/matlab_thermal_sched_src');
run_waiting_compare       % 按既定顺序运行15个穷举可行实例
% run_waiting_compare(8)  % 只复查第08组
```

新结果保存到源码目录下`reports_waiting/run_时间戳/`，不覆盖原`reports/`。每次保存源码快照、MATLAB版本、逐候选决策CSV、逐实例状态表、汇总CSV和MAT数据。

- `waiting_scheduler.m`：固定1 ms调度网格，从0 ms独立生成调度。候选排序为增量能耗、启动时刻、峰温、核编号；默认枚举全部剩余合法启动时刻。
- CPU候选为后继NPU预留最短执行时间；预测纳入已启动阶段，未启动阶段按空闲处理，预测至共同窗口H=28 ms。该预测不保证未来新任务可行。
- 未来候选不预留资源、不冻结其他阶段，每毫秒及每次实际启动后重新判断。所有实例固定优先级`[1 2 3 4]`、映射`A1→C1, B1→C2`。
- 同时运行原贪心和`max_wait=0`同实现对照；后者只去掉未来启动候选，其他规则保持相同。
- 决策预测使用0.25 ms采样；最终方案与最优方案集合统一用0.005 ms采样复核。细采样包含粗采样点，因此按能耗从粗网格下界起逐层细化候选，可认证细采样下的最优能耗。仍不宣称连续时间安全。
- 最优参照同时检查全映射集合和固定并行映射集合，避免把映射自由度差异误归因为等待策略。
- `first_optimal_divergence.m`：每个时刻过滤全部匹配历史，包括等待；只比较已启动阶段的核映射，核交换仅用于对称模型。
- `schedule_state_before.m`：明确区分决策前已完成、正在运行、就绪等待及空闲资源。
- `validate_schedule.m`：统一检查完成、释放、依赖、资源、截止期、温度；不完整或不安全方案不计入能耗差。
- `test_waiting_baseline.m`：首次分歧、对称性、就绪状态、初温峰值、能耗、释放和非法/不完整调度的回归检查。

首次完整运行结果：[汇总](reports_waiting/run_20260920_163834/summary.txt)。原贪心及零等待对照均为9组追平、3组多耗能、3组失败；主动等待15组全部追平，能耗均为258.5 mJ。
