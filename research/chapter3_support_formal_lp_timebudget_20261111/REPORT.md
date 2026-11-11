# 正式传播测试与旧 hold-last 时间预算 LP 配对

双方仍无可审核返回向量或接口目标值，停止反复求解器诊断；本轮不支持传播改善求解表现，也不启动或冻结新的完整 MILP 配对。下一步仅建议分析剩余事件—联合状态电热表达的规模及数值瓶颈。

## 范围及版本

绑定已推送提交 `37c9b12efb29f5970dfab1b8922d12ccbedaae75`。本地原工作区仍以旧 HEAD `052c0b01` 为基础，保留此前未提交改动；本轮将公开归档的 509 个文件逐一按 Git blob 核对，并在完成时再次复核这 509 个文件及 95 个原始结果文件没有变化。使用原完整 R1 的两份 hold-last 归档矩阵，仅移除整数限制；未改任务规模、物理参数、目标、任何矩阵系数及变量界，未改基线算法，未引入 Benders。

正式 `option_support.py`、旧 `test_option_support.py` 与 `milp.py` 本已存在，并与归档字节一致，故保留原样。新增正式 `research/chapter3_experiments/option_support_test_oracle.py` 与 `test_option_support_structural.py`，将独立有限目录正确性检查纳入可复用测试入口。传播开关默认 False，严格检查 bool，在 mode/event/联合状态构建前运行；本轮开关检查是 AST 合同及抽取 guard 的执行，不冒充完整模型端到端回归。

## 测试

8 个 unittest 全通过，266 个有限目录逐项比对完整结构合法调度集合，累计合法项 186→186，Cartesian 完整组合 342→221，512 条删除证据重放通过。覆盖等号、非整数结束、5ms 起点、跨场景同设备而不同频档/起点、多轮、空域、并发/共享 CPU 频域、非空固定点但资源不可行，以及篡改证明、畸形输入与预算中断。所有旧目录身份和逐项合法集合与已发表记录一致。

266 是有限目录数量，186 是跨目录累计合法项，可有重复，均非独立物理实例数量，也不是 SAFE 方案数量。旧物理集成测试保留但本轮未运行；没有新电热积分、候选热评价、完整构模或 MILP 调用。

测试实际时间：2026-11-11T14:53:54.582432+08:00 至 2026-11-11T14:53:55.266655+08:00；外层 0.684244s，测试及证据输出 0.471183s。详细证明见 `source_validation/execution/complete_schedule_sets_and_proofs.json`。

## LP 预冻结配置与结果

Python 3.12.14，NumPy 2.3.5，SciPy 1.17.0，捆绑 HiGHS 1.8.0。沿用 `highs-ds`、presolve=False、原始/对偶容差均 1e-9、steepest-devex、相同线程环境及 HiGHS 默认值。两组各一次、顺序 OFF→ON、无重试。唯一求解配置变化为 `maxiter=100000` → `2147483647`。300s 从 worker 入口计时，含导入/加载/核验/内部求解/返回点检查，沿用 2s 收尾预留及 330s 外部回收保护。没有向 linprog 传 x0 或 integrality；按 MATLAB 一基 intcon 核验原整数索引后，仅不施加它。

冻结时间：2026-11-11T14:52:52.397931+08:00；方案 SHA-256：`8ff6544e39aeec81e4b98a687226b08b5af0e2c75b9cfe22705ea0ed410a13bd`。配置逐字段对照见 `lp_diagnostic/config_comparison.json`，旧/新入口差异见 `runner_changes.diff`。

OFF 原矩阵 29,599 列 / 200,205 行 / 2,127,851 非零 / 1,681 个原整数索引；ON 为 21,411 / 144,966 / 1,469,953 / 1,125。两侧 7 数组调用前后指纹不变，MAT 文件 SHA-256 不变：

- OFF `17dfec07b1b7d327e24e9ab0d1d559535104c3be91b3caf47c89cd633113e22d`
- ON `162e389a23f0b7197f72dfc455c194d04faed142fc7736e4381308a8384291c7`

|项目|OFF|ON|
|---|---:|---:|
|终止原因|time_limit|time_limit|
|迭代数|177381|261528|
|SciPy 接口目标|未提供/无法复核|未提供/无法复核|
|接口独立 best-bound 字段|未提供/无法复核|未提供/无法复核|
|HiGHS 终止日志内部目标|0.621517690|0.667538761|
|返回向量|False|False|
|原矩阵返回点残差|未提供/无法复核|未提供/无法复核|
|加载及输入检查/s|0.576631747|0.537918101|
|原生 time_limit/s|297.423361098|297.462074956|
|linprog 调用/s|297.901808233|297.760014937|
|方法计时/s|298.667709086|298.540680333|
|完整 worker 日历/s|298.887707483|298.933755124|

接口目标/向量缺失必须保留 null；这使返回点原矩阵残差无法复核，不能填零。HiGHS 日志内部目标即便有数值，也没有附带可审核返回点；本报告不将它提升为原 LP 的可行目标、最优值或有效下界。SciPy 该 LP 接口未给独立 best-bound 字段，因此明确记为未提供。两组日志的 Relative P-D gap 分别约 2.42706e-12 / 3.69282e-12，但 model_status 仍为时间截止、当前内部原始点不可行且没有可审核返回点，不能以这个极小内部 gap 宣称原 LP 已近最优。求解器 current primal_status 的 Infeasible 表示当前内部迭代点状态，不等于全问题不可行证明。没有 SAFE 调度或独立精确最优性证书。

方法计时在最终 result.json 写入及打印前采样；最后归档、进程启动/退出由 worker_wall_s 覆盖，故同时报告两种时间。原生 time_limit 采用剩余时间，原生调用可有接口检查/退出开销，不把此字段当严格实时时钟。完整两个 worker 是否各在300秒内，可直接核查 comparison.csv 与 worker_return.json。330秒只作异常回收，并非额外求解预算。

## 实际起止、命令与限制

批次开始 2026-11-11T14:53:04.622518+08:00，结束 2026-11-11T15:03:02.450293+08:00。

- OFF：2026-11-11T14:53:04.659226+08:00 至 2026-11-11T14:58:03.326736+08:00；worker 含进程退出时间另见原始回执。
- ON：2026-11-11T14:58:03.567405+08:00 至 2026-11-11T15:03:02.108034+08:00；worker 含进程退出时间另见原始回执。

工作目录 `/workspace/paper`。实际执行命令完整保存在 `executed_primary_commands.json`，测试命令另见 `source_validation/command_receipt.json`：

```sh
python3 -B research/chapter3_experiments/test_option_support_structural.py --output research/chapter3_support_formal_lp_timebudget_20261111/source_validation/execution
python3 research/chapter3_support_formal_lp_timebudget_20261111/lp_diagnostic/preflight.py
python3 research/chapter3_support_formal_lp_timebudget_20261111/lp_diagnostic/run_lp_pair.py freeze
python3 -u research/chapter3_support_formal_lp_timebudget_20261111/lp_diagnostic/run_lp_pair.py run
python3 research/chapter3_support_formal_lp_timebudget_20261111/lp_diagnostic/summarize_lp.py
python3 research/chapter3_support_formal_lp_timebudget_20261111/finalize_records.py
```

完整原生日志是 `lp_diagnostic/off/stdout.log` 与 `on/stdout.log`；各自目录同时有 stderr、claim、solver_entered、result、worker_return 凭证。`controller.*.log` 保存父进程记录。四项 LP 预检是源码接线、矩阵/索引/界/阈值和指纹敏感性检查，不含试求解。源码哈希和矩阵预检先完成；正式纯结构测试的 0.684s 外层运行与 OFF 有重叠，没有严格串行完成两步骤。这一轻量重叠及固定顺序、单次、未隔离整台机器，均限制单次耗时的因果归因；没有为了调整结果补跑。

## 后续判断

本轮只诊断旧 hold-last。新 auto-L 的静态缩减仍是独立证据：选项1,681→1,125、变量27,971→19,857、行176,953→124,338、非零1,983,981→1,311,146；它不自动意味着优化收敛加速。本轮没有新 auto-L 求解结果。

已有 `chapter3_support_autol_lp_20261111/autol_build/rev02/execution/on/result.json` 显示：ON 仍有9,798联合状态块，78,384温度传播行＋19,596完整能量行＝97,980行，占124,338行的约78.8%；另有7,632联合边际行。构模7.254s中电热行阶段6.319s，内含系数生成1.640s与条件组装4.432s，嵌套项不可重复相加。`milp.py` 按各资源域 possible 状态笛卡尔积生成联合状态，每块四温节点＋一能量条件等式共十行。这是下一步应优先定位的已知规模。

建议另行开展零求解分析：按现有矩阵和变量名统计各行族/列族/非零、事件间隔与重复仿射模板；定位小系数、近相反条件双行、极窄允许带与抵消，再检查能否在保留原调度投影可行集的条件下严格合并状态或表达。任何压缩都应先给可恢复映射/等价条件并做完整小域集合验证；不能只凭相同目标值删状态、取整非整数结束、放宽热约束。旧 K188 的极窄双行属于另一 auto-L 载荷，只能作定位线索，不能据此认定本次 hold-last 的根因。没有诊断出条件数，也没有证明数值问题是唯一原因。

上述下一步未执行；不新增完整 MILP 配对、额外 LP、参数扫描或热评价。本轮本地保存，未提交/推送/合并。
