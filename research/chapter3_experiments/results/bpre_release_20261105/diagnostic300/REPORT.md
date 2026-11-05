> Release note: references below to a complete original log directory, manifest, run.log or execution/ refer to the original local archive. This concise GitHub release contains only the files listed in ../MANIFEST.json; it does not include that entire directory.

# 单次 B.pre 300 秒诊断

现象复现：在固定 300 秒端到端根预算后，外部观察器于根时间 **301.125 秒**首次完整读到目标值 **0.8611053534251862** 的第二候选；响应于 **301.485 秒**首次完整读到。该候选没有进行独立热安全评价，也没有被接纳为成绩或用作初解。

本次是独立单次诊断，未替换或改写原 600 秒七方法正式对照。

## 实际执行

- 环境：已连接 Windows 本机，Python `<PYTHON_EXECUTABLE>`，原 MATLAB R2023b/intlinprog。
- 控制器：PID 37068；方法进程：PID 25312；工具会话：86272。
- 控制器 UTC：2026-11-04 16:34:35.319619–16:40:07.234680；实际耗时 331.915437 秒；退出码 0。
- 根时钟：monotonic 274512.343–274812.343，严格 300 秒。
- 映射 UTC 约为 16:34:41.192748–16:39:41.192748；这是时钟锚点映射，不是独立的操作系统执行时间戳。
- 1 次 whole_milp 方法调用；实际 1 次原生请求；0 次 post，0 次重试。
- 启动门禁：可用物理内存约 4.705 GiB，无 MATLAB 进程。

实际控制器命令（完整 argv 与起止记录另见 `run_command.json`）：

```powershell
<PYTHON_EXECUTABLE> -B <WORKSPACE>\bpre_300_diagnostic_20261104T162147Z\diagnostic_300.py run --manifest <WORKSPACE>\bpre_300_diagnostic_20261104T162147Z\manifest.json
```

## 结果与时序

| 事件 | 根时间或结果 |
|---|---|
| 初始化完成独立 SAFE | 31.860 秒；U=1.05392193489385981912871774045389183825417192626120039446194 J |
| 原生进入标记被原循环接收 | 37.703 秒 |
| 第一候选被原循环接收 | 59.266 秒 |
| 第一候选完成完整 SAFE | 60.266 秒；与初始化相同 |
| 科学截止 | 300.000 秒 |
| 协作式停止返回 | 300.016 秒；0.016 秒超出未用于接纳新证据 |
| 第二候选首次完整外部观测 | 301.125 秒；16:39:42.309123 UTC；目标值0.8611053534251862 |
| done事件首次完整外部观测 | 301.235 秒；16:39:42.427247 UTC |
| 响应首次完整外部观测 | 301.485 秒；16:39:42.669660 UTC |

第二候选的原生 `request_wall_seconds=264.7748104`，而请求剩余预算为 `263.7029999999795` 秒；原生事件自身已超过请求预算约 **1.0718104 秒**。外部首次观测时间不是精确文件发布时间，不应混淆两者。

原循环仅接收事件1–5；终态请求为 `BUDGET_EXHAUSTED`、`budget_valid=false`、`accepted_for_evaluation=false`。最终状态是 SAFE / `NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST`，留存来源 `initial_constructor`，`milp_improved_initial_upper_bound=false`。

迟到响应虽然写为 `SOLVED`，但 `exitflag=-1`，说明输出或绘图函数停止；不是最优性结论。原生 MaxTime=262.32595259997953 秒，调用耗时263.513226秒；numfeaspoints=2、numnodes=0。这次迟到 fval 和完整8887维向量均与原600秒运行的迟到输出完全相同。该比较在本次终态后进行，没有把旧结果输入搜索。

清理如实记录 `forced_closed`，耗时 **20.484 秒**，原生返回码1；原20秒正常等待、40秒总清理窗口未改变。监督watchdog未触发，清理错误列表为空。16:41:21 UTC只读核验的6个已记录进程身份全部退出。

## 同一模型与证据

- 输入SHA256：`abeea5c1e71edbeb45e56615351047fbcfc7220f189955ff7f0643670d7dc76c`
- 配置SHA256：`d0905539bf9c9acba7a598a72bc05e8c5f7cac805d29e5f15837c47b18c09fdb`
- 原冻结plan SHA256：`66263b16bfaa3026e44aa8ea5462e3c6185cef9c2ad9479e6094c0ddaedb9f57`
- 模型仍为8887变量、523二元变量、56320约束；3185项源码/输入清单终态哈希复核无差异。
- 外部入口SHA256：`6ab5650184e584d7c25fa67676d6d0d9c82c3cb9c50490ed27d10b6791d7c20d`
- 5/5离线测试与独立入口复核通过；终态14/14保存证据检查通过。

来源：`diagnostic_summary.json`（含逐文件SHA和计算）、`manifest.json`、`run_command.json`、`run.log`、`execution/controller_result.json`、`execution/observations.jsonl`、`execution/worker/raw_result.json`、`execution/worker/method/matlab/request_000001.*`、`terminal_process_check.json`。完整原始日志保留于该目录，未覆盖历史文件。

## 结论边界

这一次诊断确认了“把预算设为300秒后，低目标候选仍在截止后一点出现”的观察。它不能确定求解器最初发现该向量的真实时刻，或唯一确定内部哪个停止条件造成发布；不应把原生目标值当作安全能耗。按用户要求，本轮到此停止，不继续深究或追加实验。
