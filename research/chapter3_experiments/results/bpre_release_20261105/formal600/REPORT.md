# B.pre 已保存正式执行结果

本报告只汇总本批次各方法预算内获准留存的安全能耗上界 U；保留七个预定方法行。后验检查只验证同一候选，不替换方法 U。本报告生成阶段未重新运行模型、求解或物理评价。

控制器状态：`COMPLETED`；批次状态：`COMPLETED`。控制器 UTC：`2026-11-04T14:09:17.983119+00:00` 至 `2026-11-04T15:15:59.539739+00:00`；实际耗时 4001.5566668999963 秒。

| 任务 | 状态 / 控制器状态 | 原因 | 留存 U（J） | SAFE 来源 | 方法秒 | 清理秒 | 后验 SAFE / 同候选 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| whole_milp | SAFE / NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST | wall_time_limit | 1.053921934894 | initial_constructor | 600.016 | 20.500 | SAFE / true |
| heft | SAFE / NORMAL_COMPLETION | DECLARED_SEARCH_COMPLETED | 0.920195499984 | heft:energy-pass:one-start-delay | 32.094 | — | SAFE / true |
| sa101 | SAFE / NORMAL_TIME_LIMIT | METHOD_BUDGET_EXHAUSTED | 0.888383460510 | sa_neighbour_mapping | 600.000 | — | SAFE / true |
| sa102 | SAFE / NORMAL_TIME_LIMIT | METHOD_BUDGET_EXHAUSTED | 0.872689095847 | sa_neighbour_opp | 600.016 | — | SAFE / true |
| sa103 | SAFE / NORMAL_TIME_LIMIT | METHOD_BUDGET_EXHAUSTED | 0.874320571656 | sa_neighbour_delay | 600.015 | — | SAFE / true |
| sa104 | SAFE / NORMAL_TIME_LIMIT | METHOD_BUDGET_EXHAUSTED | 0.874343922742 | sa_neighbour_delay | 600.000 | — | SAFE / true |
| sa105 | SAFE / NORMAL_TIME_LIMIT | METHOD_BUDGET_EXHAUSTED | 0.876377450247 | sa_neighbour_delay | 600.000 | — | SAFE / true |

表中“—”表示该字段未提供或没有获准留存的 U，不表示零。CSV 保留原始 U 字符串和未舍入耗时。

Whole MILP 的 `integer_solver_entered=true`，`milp_improved_initial_upper_bound=false`，选中来源为 `initial_constructor`。初始化器留存的安全上界不能表述为 MILP 求解器的优化改进；本报告不宣称全局最优。

Whole 原生清理状态为 `forced_closed`，原生隔离为 `VERIFIED`，父进程观察树清理核实为 `true`。保留 forced 状态，清理耗时单独列出。

SA 的五个 seed（101–105）均有获准留存的安全 U。它们是在同一实例上的五次随机运行：均值 **0.877222900200 J**，范围 **0.872689095847–0.888383460510 J**，样本标准差 **0.006374564615 J**（n=5，分母 n−1）。这些统计不表示跨实例性能或全局最优性。

## UTC 与耗时

以下 root 起点和科学期限由单调时钟与 UTC 锚点映射得到；slot 结束包括清理和序列化。CSV 另存首次观测时间，首次观测不视为执行起止。

| 任务 | root 起点（映射 UTC） | 科学期限（映射 UTC） | slot 结束（映射 UTC） |
| --- | --- | --- | --- |
| whole_milp | 2026-11-04T14:13:17.081665+00:00 | 2026-11-04T14:23:17.081665+00:00 | 2026-11-04T14:23:40.574160+00:00 |
| heft | 2026-11-04T14:23:51.909086+00:00 | 2026-11-04T14:33:51.909086+00:00 | 2026-11-04T14:24:24.394120+00:00 |
| sa101 | 2026-11-04T14:24:36.918740+00:00 | 2026-11-04T14:34:36.918740+00:00 | 2026-11-04T14:34:41.289777+00:00 |
| sa102 | 2026-11-04T14:34:53.007593+00:00 | 2026-11-04T14:44:53.007593+00:00 | 2026-11-04T14:44:57.672014+00:00 |
| sa103 | 2026-11-04T14:45:09.719416+00:00 | 2026-11-04T14:55:09.719416+00:00 | 2026-11-04T14:55:14.721841+00:00 |
| sa104 | 2026-11-04T14:55:26.803529+00:00 | 2026-11-04T15:05:26.803529+00:00 | 2026-11-04T15:05:31.209930+00:00 |
| sa105 | 2026-11-04T15:05:42.088904+00:00 | 2026-11-04T15:15:42.088904+00:00 | 2026-11-04T15:15:46.322586+00:00 |

计时说明见 [whole_clock_evidence.json](whole_clock_evidence.json)。其中保留旧 `clock_origin` 文案，并记录本次 `clock_contract`、ticket 与安装后预算的对应关系。该附录报告的 `all_clock_identities_match=true`。

## 审计状态

独立保存证据审计状态：**PASS**，见 [final_batch_validation.json](final_batch_validation.json)。审计范围：Terminal saved-evidence audit only; no physical evaluation, algorithm, solver or process control.。

## 执行命令与证据

控制器实际 argv（JSON 参数数组，保留参数边界）：

```json
[
  "<LOCAL_PATH>",
  "-B",
  "-m",
  "research.chapter3_experiments.bpre_formal_entry",
  "run",
  "--plan",
  "<LOCAL_PATH>",
  "--approval",
  "<LOCAL_PATH>",
  "--out",
  "<LOCAL_PATH>"
]
```

逐槽位执行记录见 [execution_records.json](execution_records.json)。各 method/post 使用同一 worker 入口；具体参数由冻结 launcher 源码与对应 ticket 重建，不属于独立的操作系统命令捕获。一次性 token 在展示参数中遮蔽。实际身份、状态与起止证据见该记录；本导出器只引用文件及其哈希，不重新构造命令。

执行归档状态：`ARCHIVED`；槽位记录 14/14，存在证据问题的槽位数 0。

固定输入 SHA256：`abeea5c1e71edbeb45e56615351047fbcfc7220f189955ff7f0643670d7dc76c`；配置 SHA256：`d0905539bf9c9acba7a598a72bc05e8c5f7cac805d29e5f15837c47b18c09fdb`。摘要声明共同输入与精度；实际准入检查以独立审计为准。

完整标量表：[comparison.csv](comparison.csv)。摘要、审计与计时证据的文件哈希如下：

| 文件 | SHA256 / 状态 |
| --- | --- |
| formal_summary.json | 4d28411679ab805a649fd2a0880af87afff9368b55c419a5dd7bebde6984d3ed |
| final_batch_validation.json | ddc3b5c72edc5835d2de09cd65dfae6f1accb2d05709f154ed55f9cefc8af6ff |
| execution_records.json | eeb756c7a26d1d7cbadf926de9fe4a0888b920593c3c59b8f47f9f6868851a41 |
| whole_clock_evidence.json | 0ce21b0629c536a43bfdad7dfd852831e7a1ce9e141a58d5b7b421b0cce57169 |

报告生成 UTC：`2026-11-04T15:16:59.197353+00:00`。本导出只读取已保存摘要和外部证据文件。
