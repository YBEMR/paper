# K165：R1/R2与既有数值冲突的只读历史对照

**本次更接近旧数值接纳／solver-reported状态冲突的复发，尚未定位为新的传参接口差错。** K105/K106的旧整体MILP和K131固定设备AB子问题均已有同族记录；K131已直接保存同名`NUMERICAL_ADMISSION_STATUS_CONFLICT`。原模型不同，不能把以前的局部修正自动套用于本次。

|条件|重复|变量数|MATLAB启动/s|native MaxTime/s|intlinprog调用/s|exitflag|根时钟/s|Python回执|
|---|---|---:|---:|---:|---:|---:|---:|---|
|Deadline|R1|20868|57.047|223.254|226.462|0|300.016|BUDGET_EXHAUSTED|
|Deadline|R2|23464|10.875|270.103|268.002|-2|298.391|SOLVED|
|P0|R1|27971|53.625|220.939|226.076|0|300.016|BUDGET_EXHAUSTED|
|P0|R2|32431|55.391|222.730|225.050|0|300.000|BUDGET_EXHAUSTED|
|P1|R1|18993|59.453|223.235|226.992|0|300.016|BUDGET_EXHAUSTED|
|P1|R2|23343|10.110|275.603|276.819|0|300.000|BUDGET_EXHAUSTED|
|P2|R1|27971|7.938|269.445|271.490|0|300.000|BUDGET_EXHAUSTED|
|P2|R2|32431|9.468|268.913|270.061|0|300.016|BUDGET_EXHAUSTED|

1. **传参链没有显示新的元数据丢失。** 八份定向回执都明确提供并由worker收到x0，长度、初始目标及Python接纳元数据一致；两份当前会话及六份P0/P1/P2会话的桥接与worker源码hash相同。全部使用LPPreprocess=none、IntegerPreprocess=none、ConstraintTolerance=1e−9、IntegerTolerance=1e−6及CutMaxIterations=10。此核对不等同于逐元素复核MAT数组，后者由本阶段其他只读审查负责。

2. **done计数1不是x0接纳证明。** 八份回执全部表现为init可行点计数0、done计数1、最终计数0、x/fval为空、节点数0；其中七份native退出0，仅本次R2为−2。该计数差异不是本次独有，也不能据此认定solver真正保留了一个可返回候选。

3. **根LP状态仍不可观测。** 已保存记录只有init/done等事件，未出现可读取的根LP目标或lowerbound。零节点只说明没有记录到分支树节点，不能据此定位在根LP、割或其他内部阶段，也不能称根LP独立已证无解。

4. **启动与剩余时间是关联，不是原因。** 本次R2启动10.875 s、native MaxTime270.103 s，比R1的57.047 s和223.254 s留下更长原生片；但P1 R2已有更长的275.603 s，P2 R2也有268.913 s，均为时间退出0。本组不同响应、初温、期限和模型维数，不构成同矩阵单因素配对，不能归因于“运行久了”“期限更紧”或某个参数阈值。

5. **P0/P1/P2已完成档案不否定旧冲突。** 三份40行方法终态报告均是40份可比较SAFE，未登记本次数值冲突；定向读取的六份whole原生回执均为exit0，Python按原预算拒收后续输出。这个范围未穷查所有未接纳晚回执，不能泛化为过去所有内部步骤从未冲突。

6. **历史修正的边界。** K106旧整体模型曾在x0数值接纳后exit−2；其固定逻辑对子问题支持采用LPPreprocess=none。K131在LP none下又出现同名冲突，后续局部增广适配主要处理局部物理条件行的数值表示。本次whole仍需独立核对当前payload，不能认定旧工程兼容设置已覆盖全部数值问题，更不能把LP none或局部增广写成通用正确性保证。

结论：已知异常家族复发、当前确切原因未决；未发现本次独有的初始点元数据传输损失。优先完成当前payload／接纳／原生返回一致性核对，再决定是否存在范围明确的工程修正。本核查不建议调容差、追加时间或补跑，也不把安全初始化U升级为数值求解成功。

来源：当前期限组及P0/P1/P2的八份`wrapper_raw_result.json`与`matlab/request_000001.*.json`；K106的`infeasible_audit01/summary.md`、`native_trace.md`及原response；K131的`fixed_unit_pair02/all_opp_start/result.json`、原response及分析报告；K132的`numerical_conflict_audit01/summary.md`。准确路径、JSON字段和hash见facts.json。

只读核对12项通过；新模型、求解、热评价、post均0次。
