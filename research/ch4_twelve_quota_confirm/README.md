# 低成本配额生成的完整任务流确认

研究结论见[中文决策报告](REPORT_zh.md)，逐流数值见[附表](APPENDIX_zh.md)。[预登记](PROTOCOL.md)记录输入、资源、切换规则、统计口径和停止条件。

## 离线复核

在本目录依次执行 `python -B summary.py` 和 `python -B phases.py`，可从本轮证书和日志重建全部对照表。随后执行 `python -B verify.py --git-inputs`，核对冻结 Git 树中的输入文件及全部证据。归档内已有全部表；仅校验现有档案时可直接执行 `python -B verify.py`。使用 `--restore CASE PLAN_SHA NEW_DIRECTORY` 可恢复一份完整排程、连续证书和 NumPy 温度事件矩阵。`figures.py` 绘制能耗阶梯，`appendix.py` 从表格生成中文附表。绘图需 Matplotlib 和中文字体；恢复矩阵需 NumPy。

| 数据 | 解释 |
|---|---|
| [逐次结果](results/cells.csv)、[逐次能耗配对](results/paired_runs.csv)、[逐流能耗](results/flow_pairs.csv) | J 为完整系统焦耳，lo／hi 为同一证书的能耗区间。空能耗表示未得到按时安全证书。能耗区间相交计为平。 |
| [首解配对](results/first_safe_pairs.csv)、[首解汇总](results/first_safe_summary.csv)、[开发流及其余样本](results/cohorts.csv) | 首解节时为 A 减 B。相对节时为同一次配对节时除以 A 首解时间。胜负只在双方共同成功时比较。 |
| [达标逐次记录](results/quality_targets.csv)、[达标配对](results/target_pairs.csv)、[全分母及配对差](results/target_pair_summary.csv)、[命中来源](results/target_stages.csv) | 每条流按同期 A60 的成功证书上界中位数建立目标。搜索交付记作 search/physical，调频交付记作 map序号/direct。首次命中按运行计一次，所有命中按交付证书次数计。 |
| [构造与调频时序](results/stage_timing.csv)、[各次构造](results/construction_passes.csv)、[映射调用时序](results/map_timing.csv) | 时间均从本单元启动起算。首次完整池为构造器返回有合法终端的整池时刻。调频开始取完成交接后进入直接调频调用的时刻。局部改善以当前种子为参照，全局改善以在手安全排程为参照。空结束时刻表示截止前未观测到完成。 |
| [路径与映射配对](results/path_pairs.csv)、[未完成种子的异次见证](results/unfinished_seed_witnesses.csv) | 以双方首份已认证完整排程核对逐窗设备、频档及分类型配额。此证据定位已返回排程的分歧；完整束的最早内部分歧只有日志记录时才可断言。异次见证要求另一次运行在同一流、完全相同的种子排程上完成直接调频并达到目标。 |
| [逐次失败来源](results/failures.csv)、[阶段开销](results/formal_costs.csv)、[资源账本](results/accounts) | 构造截止、完整空池、认证中断和已认证超温分别记录。未认证候选保留未知。CPU 涵盖监督器及回收的后代，实际墙钟另列。 |
| [能耗阶梯](CURVES_zh.md)、[改善点](results/improvements.csv)、[证书索引](results/certificates.csv)、[物理证据](results/physical) | 每条线从首次按时安全交付开始，最后持有的结果延至预算终点。同一完整排程按工况去重，保留排程、热证书及经字节指纹核对的连续事件块。每次交付的时间保存在原始记录中。 |

正式运行入口 [run.py](run.py) 使用上一轮的中性预热、独立派生、轻量计数和整棵进程树保护。沿用 `FAST_SCRATCH` 的冻结运行环境和 `TRANSFER_ROOT` 的驱动，新的 `WARM_ROOT` 必须是尚未创建的账本目录。汇总与核验无需重新启动求解。归档后的 [collect.py](collect.py) 仅从本轮原始工作区提取截止前交付的证书与计时，不调用调度器。
