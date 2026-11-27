# 证据、计费与离线复核

从本目录运行 `python -B verify.py --manifest` 即可逐文件核对 SHA-256，并复核 196 个原运行单元、910 个完整合法末层候选、另批 344 个匹配项及 93 组配对。只用 Python 标准库，无需重新搜索、认证或联网。原始计时位于 [measurements](measurements/)，逐项说明见[实测附表](MEASUREMENTS.md)。`python -B benchmark_summary.py` 可从原数据重新生成相同的计时汇总。

| 账目 | 计量和实际停止 |
|---|---|
| 物理及匹配微基准 | 上限 480 单核秒。实际保守扣费 **309.139 s**，包括失败、目标盲预热、退出、核验和恢复间隙。前三个进程分别遇到动态模块源码识别错误、Windows 状态文件替换冲突、监督进程读状态文件异常。第三次一直扣到确认无遗留工作进程的时刻；随后跳过已通过单元。243 个主测单元、24 个补充单元、2 个纯传播键计数均完成。I09 首层首轮的原／精简计时在同一进程内完成，独立探针在恢复后运行。核、顺序、探针扰动与测量脚本版本可追溯。[计费回执](measurements/budget.json) · [脚本版本恢复索引](measurements/versions/index.json) |
| 只读批处理 | 预留 120 单核秒，实际保守扣费 **59.718 s**，包括重新提取开发与独立路线最后动作。归档审计协议原拟分两次执行，后将外批对照、冻结依赖校验、开发集和停止点字段补全分开执行；这几次都是读原数据。合计 **368.857 / 600 s**。源文件查阅、Git 操作、编写报告及读取摘要的校验不计入研究调用。无新增端到端搜索，未追加对未知池的连续认证。[只读计费](archive/budget.json) |
| 原始和精简物证 | 本批新计时在临时目录执行真实写入、关闭和读回。计时、身份、物理指标及原始事件字节指纹另存；与冻结物证相同的计划和大轨迹可按原路径取回。原／精简主臂的时间戳和计时字段允许不同。两流必要交付仍完成每份 HOT 的数值判决和每份 SAFE 的物证留存。省下的是部分记录成本。 |
| 停止与解释 | 主批 8 流，每流 3 对；第二层仅预登记的 3 流。追加 I01/I04 的协议在读取主批部分结果后、补充测量前登记，两流均为已知成功；传播键计数是额外诊断。所有计时臂均未运行后续搜索。余量没有用于扩大样本、实现缓存、调热评分或补齐历史未知标签。|

## 定位原计划和记录

1. 在 [U4-a](https://github.com/YBEMR/paper/tree/0231bc8b1e54977cb617f53a03e64df84fbf7cca/research/u4a_integrated_fast_scheduler) 中取 `results/<case>/runs/<method>.json`。其 `journal` 是有序分片，文件名为解压后的 SHA-256。按 [archive/routes.csv](archive/routes.csv) 和 [archive/development_routes.csv](archive/development_routes.csv) 的分片顺序回查。某些未完成动作没有独立时间戳，报告保留最后归档动作，切断时正在运行而尚未记账的子函数记作未知。
2. 每个已测计划在 [inputs.jsonl](measurements/inputs.jsonl)、[短名单原始记录](measurements/delivery.jsonl) 或 [原末层证书表](archive/terminal_identities.csv) 中有输入和计划身份。精确物理见证在同一原案例的 `physical/plans.jsonl.gz` 中，以 `certificate.plan_sha256` 定位。按该条的 `blocks` 顺序、`block-index.json.gz` 的分卷与偏移解压，再比对 `trace_sha256`。前 14 列为物理事件输入，31 列全体为连续轨迹。积分与温度上界以原证书数值字段为准。
3. [基础池](archive/base_pools.json.gz) 给出按原整数参考能量和配置字节破平重建的完整有序配置，以及原短名单与实际认证；[候选标签](archive/pool_labels.csv) 仅列原档可证范围。平行研究的严格违规见证和离线补证逐行另列。它们发生在原运行之后。[外批逐项映射](archive/other_batch_coverage.csv)
4. 只读复算的默认布局为同一父目录内的 `U4a_worktree`、`U3b_worktree`、`U3c_worktree`、`U4b_worktree` 和本批工作树。基线和提交见报告附表一。本机原启停文件另在 `U4a_raw`；异机无该目录时读取已归档的 [起点表](archive/archived_clock_origins.csv)。预先物化的 `U3a_inputs` 可用 U3-a 的 `prepare_inputs.py` 从冻结提交准备，199 个依赖的逐文件 SHA 在 U3-b 的 `registration/frozen_sources.json`。微基准所用 `U3b_compute_cache` 仅为已编译的 Numba 代码，不含案例配置、物理状态或结果；精确环境见本批 `environment-*.json`。
5. 需要在另一份副本中重新生成只读表时，`archive_audit.py` 的执行次序为 `routes`、`physics`、`context`、`identities`、`development`。原归档只读进程固定在逻辑核 0，可用 `AUDIT_CPU` 指向其他可用核。`archive_budget.py` 为本批只读进程的监督入口。匹配计算由 `benchmark_budget.py` 管理，组合及固定工作阶段见[主预登记](PROTOCOL.md)、[必要交付](PROTOCOL_DELIVERY.md)与[传播键](PROTOCOL_PROPAGATION.md)；本批完成后的只读复核使用第一个命令即可。
