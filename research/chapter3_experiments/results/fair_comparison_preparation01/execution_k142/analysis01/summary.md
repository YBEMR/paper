# K142：冻结原基准四方法存档核查

实际消费 2/4 次，控制器状态 BLOCKED；四方法对照未完成，不能形成四法排名；已经核实的完整安全输出保留。

| 方法 | 完整SAFE能量/J | 首SAFE/s | 方法耗时/s | 热反馈行 | 方法／调用状态 |
|---|---:|---:|---:|---:|---|
| whole_milp | 1.084886371304 | 53.985 | 300.032 | 0 | SAFE／COMPLETED |
| linked_n1 | 0.962885037941 | 2.265 | 300.015 | 0 | SAFE／TECHNICAL_BLOCK |
| heft | NA | NA | NA | NA | NOT_RUN |
| sa101 | NA | NA | NA | NA | NOT_RUN |

| 方法 | 共享A.pre | 共享A.main | 共享A.post |
|---|---|---|---|
| whole_milp | CPU2 | NPU0 | CPU1 |
| linked_n1 | CPU1 | NPU0 | CPU1 |
| heft | NA | NA | NA |
| sa101 | NA | NA | NA |

| 方法/场景 | 能量/J | 基准/J | 活动/J | 公共/J | 温度修正/J | 各Stage工作点 |
|---|---:|---:|---:|---:|---:|---|
| whole_milp/AB_offset_0ms | 1.054246685811 | 0.547950000000 | 0.274000000000 | 0.120000000000 | 0.112296685811 | A.pre=H；A.main=H；A.post=H；B.pre=H；B.main=H；B.post=H |
| whole_milp/AC_offset_0ms | 1.115526056796 | 0.550500000000 | 0.330900000000 | 0.120000000000 | 0.114126056796 | A.pre=H；A.main=H；A.post=H；C.pre=H；C.main=H；C.post=H |
| linked_n1/AB_offset_0ms | 0.946109231401 | 0.524500000000 | 0.195491105985 | 0.120000000000 | 0.106118125416 | A.pre=H；A.main=H；A.post=H；B.pre=H；B.main=L；B.post=L |
| linked_n1/AC_offset_0ms | 0.979660844481 | 0.522400000000 | 0.230898222479 | 0.120000000000 | 0.106362622002 | A.pre=H；A.main=H；A.post=H；C.pre=H；C.main=L；C.post=L |

能量比较仅使用预算内完整原输入SAFE区间，严格优劣条件为较优方案上端小于对照下端；L0差距与solver-reported界分列。所有源代码、输入、协议、原始结果的哈希已核对；分析没有执行新的候选解码、热计算或优化。
联动版固定本次fresh seed设备，其余三方法保留原合法设备自由度；本次比较预算内可用输出，不宣称等覆盖、全局最优、随机稳定排名或普遍性能。
[能量与独立L0曲线](energy_bounds.png)。完整时间表、峰温包络、阶段归因、原生停止延迟及原始异常分别保存在本目录CSV和facts.json。

联动版末轮AC在300秒截止前未完成完整数值门与回调发布覆盖核对，因此按预先规则停止后续HEFT和SA；已有完整SAFE保留。该轮已存两项数值门均accepted=True，尚无数值拒绝证据。原生终态晚回执只作耗时／退出诊断，不能补作预算内方案。详见technical_boundary.json。
