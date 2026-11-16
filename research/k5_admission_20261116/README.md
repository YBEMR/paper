# K5-NPU-M1：隔离交付目录

结论：**只保留建模参考；本轮停止，不开发新算法或扩模。** 先读[中文报告](REPORT.md)，再查[冻结协议](PROTOCOL.md)。不是RK3588硬件节能实验。

## 文件索引

| 文件 | 内容 |
|---|---|
| inputs.json、parameter_grid.json | 带来源边界的模型输入与全部1944个预定组合 |
| PROTOCOL.md、freeze.json | 运行前规则、参数选择原则和参数哈希 |
| code_freeze.json、source_ledger.json | 科学代码身份、公开来源提交/blob及阅读范围 |
| stage1.py、stage1_results/ | 25组核组精确算术、资源合法性和增量能量比较条件 |
| experiment.py | 普通列表/局部改进、固定模式对照、同域枚举与普通完整搜索；独立于旧代码 |
| verify.py | 独立有理数事件进度、完整事件能量、热卷积及60位Decimal核验 |
| analyze.py | 预声明的只读结果汇总和图表 |
| run_pipeline.py、execution_receipt.json | 共同600秒硬超时控制、原始执行命令、每进程计时与退出状态 |
| read_saved.py、run01/posthoc_summary.json | 明确标为事后的只读分类计数；零新物理评价与搜索 |
| run01/cases.csv | 1944项全部结果，不可行/无收益项完整保留 |
| run01/methods.csv | 1944×9=17496行；失败或违规的差距为空 |
| run01/catalog_sigma_*.json | 每慢化档1600原始基因的合法映射、1168条去重时间表；340个冲突基因由规则排除 |
| run01/all_candidates.npz | 1944×1168条候选完整能量、NPU峰温和热状态，未只保留赢家 |
| run01/selected_trajectories.jsonl | 每个返回完整方案的NPU分段端点、CPU pre/post、窗口、核组/起止及方法归属 |
| run01/summary.json、analysis.json、ablations.csv | 总结、方法统计、逐慢化/期限计数 |
| run01/independent_verification.json | 2270592条候选全量交叉核对和2729条高精度轨迹记录 |
| *_run.log、run01/progress.jsonl | 原始执行/进度日志 |
| run01/*.png | 全网格可行性、热约束代价和安全配对能量差距；已目视检查 |
| MANIFEST.json | 所有交付文件SHA256；自身不递归列入 |

## 复现

Python 3.12.4、NumPy 1.26.4、Matplotlib 3.10.0；不需要SciPy求解器、MATLAB、RKNN或开发板。依赖只有NumPy和绘图时的Matplotlib，核心模型使用标准库与NumPy。原命令、Python路径和系统信息在execution_receipt.json。

在本目录中，针对**新输出目录**可运行以下命令；不覆盖run01及冻结记录：

```text
python experiment.py replay01
python verify.py replay01
python analyze.py replay01
```

这些命令重复原输入和有限时序域。能量、峰温、合法性应在记录容差内一致；墙钟、进程号和时间戳不要求一致。experiment.py拒绝已存在的输出目录，不自动续跑。

需要原600秒统一预算控制时，在一个新空目录复制本目录的*.py、inputs.json、parameter_grid.json、PROTOCOL.md、freeze.json、code_freeze.json和source_ledger.json，运行`python stage1.py`再运行`python run_pipeline.py`。控制器拒绝已有run01或execution_receipt.json。代码中stage1的0.6928471秒是本次已观察到的保守记账值；跨机器复现应另行记录实际阶段一时间，不能声称复现原耗时。原目录保持只读。

## NPZ与连续轨迹的解释

`all_candidates.npz`使用`numpy.load(..., allow_pickle=False)`读取。`case_ids`按parameter_grid.json冻结次序；第二轴为对应慢化档目录的sid。数组`energy_J`、`peak_C`、`thermal_state`形状均为1944×1168；热状态0安全、1违规、2未决。热安全不等于期限可行：期限由cases.csv及目录内两请求结束时间加post=5.7275 ms判定。不要把热状态0全部当作合法解。

温度端点不是粗时间采样。事件来自NPU两项起止、0与W；每段恒功率，已给定τ、κ和活动功率，端点间函数为`T∞+(T起−T∞)exp(−Δt/τ)`。单节点单调性给出连续峰值；CPU前后处理在本轮热边界外。NPU无任务的尾段仍带0.2 W基准，系统仍带1 W公共基准。不能将该单节点端点规则用于多节点耦合RC。

`methods.csv`中的`energy_J`对完整但超期/超温候选也保留原始值；只有status=SAFE时的`gap_to_E_percent`有意义。空结果表示该方法没有返回完整安全方案；D的失败不是全域不可行证书。A/B/C_repair的无解只针对其固定映射子域，E/F的无解仅针对声明的1168条有限时间表。E0是诊断消融，无独立求解计时。

## 证据完整性

全部科学输入/程序在首次热计算前冻结；原始运行一次成功，无重试。独立核验为同一助手的独立实现，不是外部审批。核组时延公开实测仅限原来源；core1/core2等效、并发语义、固定频率、CPU时长、功率、RC、入口与温限均未由硬件标定。目录不包含任何旧论文或MILP的修改。
