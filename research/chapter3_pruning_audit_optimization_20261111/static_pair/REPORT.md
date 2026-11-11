# 严格认证开销优化：唯一三臂静态配对

本次已按冻结顺序仅运行 `old_on → optimized_on → off` 各一次，随后只读比较一次，全部通过。优化ON的全部导出数组、变量名、逐行Big-M/外包元数据和冗余证明结果与原版ON完全相同。本次门关闭审计由11.120429s降至1.835565s，下降83.49%；构模加导出18.291761s→8.510929s。优化ON仍比本次OFF的7.214609s多1.296320s（17.97%），不能称总体成本已经低于OFF。没有求解器或热评价调用。

## 冻结身份与执行条件

- 基准提交：`fe6216afcd0e8d94742adbc0ff62d70651dd60ba`。
- 原版ON直接冻结上轮 `chapter3_certified_state_pruning_20261111/full_static/frozen/` 的217份源，其正式入口再与基准Git内容校验。
- 优化ON和OFF冻结本轮通过验收的217份源；仅 `milp.py` 相对原版变化，SHA256 `98c1ad5735d06e07ad8cb89e8f90e99542c1a1142ef2e7b42439fa47d5eec182`。joint_state_support.py仍为原 `d4f7ee5916d5bb935f11852a5969d04379e11adde1e015b8e248cdb6f03c979c`。
- 全部输入复用原完整auto-L R1：AB/AC各6次Stage、CPU/GPU/NPU及频档、5ms起点/非整数结束、依赖/期限/共享映射、四节点RC、50°C初温/80°C上限/400ms窗口均不改，propagate_support始终True。old_on/optimized_on状态剪枝开，off关闭；baseline_flags原样。
- 方案SHA256：`f13e40dfd56d868d46cba6f71ea045a2b2b8252993791e018ac720cc49ae7387`。
- `acceptance.json` 在实际测试与安全预检通过后由主代理创建，绑定rev2源码、5项源码hash及6份实际验收证据。此前没有完整R1预跑。rev1未获性能放行，不能与本次rev2混称。
- 每臂300s worker总预算、380s外部回收保护；独立进程、独立Model、空认证缓存启动，无旧缓存加载、无失败重跑。所有缓存/source/key准备已包含在构模和门审计区域。没有清除OS文件页缓存，因此不是机器级冷启动实验。

## 本次实际测量

|指标|原版ON|优化ON|本次OFF|
|---|---:|---:|---:|
|联合状态块|6,860|6,860|9,798|
|变量|16,919|16,919|19,857|
|行|94,958|94,958|124,338|
|非零|990,904|990,904|1,311,146|
|门关闭审计/s|11.120429|1.835565|不执行|
|支持检查/s|1.682231|1.567012|不执行|
|保留电热条件行组装/s|2.911156|2.710260|4.063633|
|完整构模/s|17.955018|8.194143|6.770417|
|导出/s|0.336743|0.316786|0.444192|
|构模＋导出/s|18.291761|8.510929|7.214609|
|导出能量证书复核/s|0.438099|0.392478|0.553363|
|证据归档/s|2.906846|2.224738|1.072267|
|worker记录时长/s|22.239911|11.738986|9.274283|
|外层完整日历/s|22.664631|12.156139|9.569153|
|导出后进程寿命峰RSS/MiB|275.640625|311.039063|282.039063|

门审计/支持/条件行组装是构模内部区域，不可再与完整构模相加；缓存细项也是门审计内部计时。原版没有缓存内部细粒度仪表，相应CSV列为null，不反推原版准备/验证时间。OFF对应区域未运行也为null，不能解释为缺失成本。

峰RSS来自Linux `getrusage(RUSAGE_SELF).ru_maxrss`，包括该进程所有先前阶段。导入前、构模后、导出后、归档后都有快照；不是某阶段增量峰值，也不能将同一进程两次峰值相减作为阶段峰值。本次优化ON峰RSS比原版ON高约35.40MiB，不能称内存开销也下降。

上轮历史门审计10.764056s只是优化目标的历史参照，本次公平比较使用本次原版ON的11.120429s；不能混用历史OFF或历史ON构模时间制造收益。本次是单次固定顺序测量，较大下降幅度可如实报告，但不是统计显著性检验，也未测求解性能。

## 严格证据及实际缓存工作

两个ON所有NPZ数组（A data/indices/indptr/shape、b、c、lb、ub、intcon）逐字节相同，变量名相同。全部行元数据canonical流SHA256均为 `86c15af46b1bbb00e25e8b7f44f5febe0d780f3513314280e994845aef87b1e6`，覆盖tag、实际RHS、Big-M、rounding_allowance、rhs_interval及gate名字，不只比较目标或行数。

原版ON和本次OFF分别与前轮已归档对应矩阵逐字节一致。三臂原选项、事件相同；两个ON界/目标/整数索引及被删2,938状态名字集合完全相同，并与冻结预测逐项相同。两ON的全部逐状态门关闭数学证书（checked_rows、gate值、最大残差、最小余量及exact-box标记）相同，共覆盖29,380行；优化记录中额外cache字段不冒充数学证书。

每侧424份能量强化证书都以实际导出数字转Fraction作完整原盒蕴含检查；所有active-state最大残差差值≤0。两ON完整强化证书及检查记录也逐项相同。

|优化ON认证工作|实际值|
|---|---:|
|严格首次miss|284个模板|
|已认证同模板hit|2,654次|
|实际重新导出并Fraction逐行认证|2,840行|
|严格证书复用后覆盖|29,380行／2,938状态|
|准备probe|38个|
|clear／identity invalidation|0／0|
|source/input/numeric环境准备/s|0.214037|
|完整键准备与查找/s|0.094719|
|probe准备/s|0.037292|
|miss模板行导出/s|0.880219|
|miss严格Fraction认证/s|0.098208|
|hit路径细项/s|0.000524|

“2,840行实审”不等于只检查了2,840/29,380行就跳过其它：首次模板按原导出和精确认证，hit以完整键证明同一系数/盒/别名布局/source/input/numeric身份，逐状态引用同一数学结果。本次冷启动的全部miss及缓存建立成本都已计入，未复用安全预检进程里的对象。完整key、source namespaces、已认证模板及stats在 `execution/optimized_on/preprocessing.json`。

精确整数模型及binary64行证据保持，不升级为近整数容差接受管道或整个LP多面体相同；本轮不运行任何LP/MILP。

## 实际时钟、命令与日志

工作目录 `/workspace/paper`，Python3.12.14、NumPy2.3.5、SciPy1.17.0、Linux，无依赖安装。北京时间UTC+8，2026-11-11：

- 批次17:14:22.015458—17:15:06.406738，44.391280s。
- old_on命令17:14:22.015655—17:14:44.680271，22.664631s。
- optimized_on命令17:14:44.680620—17:14:56.836745，12.156139s。
- off命令17:14:56.837053—17:15:06.406192，9.569153s。
- 只读比较17:15:14.400409—17:15:16.774431，2.374038s。

```sh
python3 research/chapter3_pruning_audit_optimization_20261111/static_pair/run_pair.py freeze > research/chapter3_pruning_audit_optimization_20261111/static_pair/freeze.stdout.log 2> research/chapter3_pruning_audit_optimization_20261111/static_pair/freeze.stderr.log
python3 -u research/chapter3_pruning_audit_optimization_20261111/static_pair/run_pair.py run > research/chapter3_pruning_audit_optimization_20261111/static_pair/controller.stdout.log 2> research/chapter3_pruning_audit_optimization_20261111/static_pair/controller.stderr.log
python3 research/chapter3_pruning_audit_optimization_20261111/static_pair/compare_pair.py > research/chapter3_pruning_audit_optimization_20261111/static_pair/compare.stdout.log 2> research/chapter3_pruning_audit_optimization_20261111/static_pair/compare.stderr.log
```

各臂精确worker argv、父进程时钟和退出状态在 `{arm}.command_receipt.json`；worker自身时钟、阶段、内存及环境在 `execution/{arm}/result.json`。worker时间在最终result写入/打印前采样，父进程日历另外包含写入及退出。metadata/NPZ/预处理/完整能量证书和observer日志均保存，未复写历史。freeze/run/compare各一次成功，未触发看门狗，无模型/比较重跑、无LP/MILP/候选热调用。
