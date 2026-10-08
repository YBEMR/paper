# CP1：E-only与EML一次配对核验

2026-10-08；对应讨论稿K.21、证据E456。**E-only新增实现通过核验；本次两法安全能量相同，EML多评价的8张表均超期。** CP1全部全体中点／最晚表已由E455证明不能满足给定转换期限，因此本轮只提供实现一致性和额外评价成本记录，不承担等待节能或主线研究价值验证。

## 方法与复用边界

`compare.py`将原`continuous_planner/planner.py`加载到隔离的模块中，两法使用相同的原搜索函数和相同计时包装。E-only仅替换代表生成接口：用精确有理数沿依赖与已选冲突方向传播最早起点，不计算中点／最晚表；EML仍调用原代表生成函数。全部选项、结构查询、原求解器设置、联合评价、查询去重、独立下界和停止规则保持一致。原源码、输入及历史结果未改。

原输入中的三代表协议不被覆盖；每次调用的`method.json`单独登记实际代表策略。生产搜索不读取预检参考答案，不共享两法候选、缓存或见证。每法独立Python／MATLAB进程，固定顺序E-only→EML。

相同限额为总120 s、最多4个结构、单MILP查询15 s、单评价20 s且受总剩余预算约束。输入加载、模块加载、MATLAB启动、建模、查询、构造、缓存和评价都计费；快照、结果写入、进程收尾和事后复核单列。达到结构上限即停止，不用剩余时间补跑。

## 结果

| 项目 | E-only | EML |
|---|---:|---:|
| 结构数 | 4 | 4 |
| 完整代表评价数 | 4 | 12 |
| 持续安全且U1能量有效 | 4 | 4 |
| 已确认期限违规 | 0 | 8 |
| 最佳安全能量上界 | 105.1561068032451 mJ | 相同 |
| 原域独立下界 | 28 mJ | 28 mJ |
| 首个安全输出 | 10.735 s | 12.578 s |
| 总计费用时 | 12.782 s | 20.250 s |
| 其中MATLAB启动 | 8.360 s | 9.031 s |
| MILP查询累计 | 2.031 s | 2.657 s |
| 联合评价累计 | 2.376 s | 8.514 s |
| 停止原因／最优性 | 4结构上限／未证 | 4结构上限／未证 |

四个结构签名完全对应，均为全CPU-L、不同前驱次序。对应E表、评价状态和完整能量区间逐项相同；两法最终能量区间也相同，比较器记录`overlap_or_tie`。不能把U−L₀写成已知最优差距，未查连续安排仍保留覆盖未决。

本次额外评价累计多6.138 s，总用时多7.468 s；后者还包含启动和求解波动，不全归因于多查8表。只运行一次，不报告统计加速。代表生成记录为0 s是计时分辨率下的数值，不表示构造零成本。分项为诊断记录，不假定精确加总为总耗时。

## 检查与工件

- `results/precheck01/checks.json`：31/31。576个选项／顺序构造的E与旧实现一致（含重复等价结构，不称576个唯一结构或完整连续域）；真实R2023b后端；E失败、未决、安全之后继续查询；接口异常、中断、已提交违规保留；缓存隔离和源码身份。
- `results/pair01/`：两次独立调用，原始矩阵、求解器输出、选项／许可、时间表、评价和事件日志；每法保存输入与源码快照。
- `results/postcheck01/checks.json`：70/70。全部16表的精确合法性、证据身份及预算内完成时间；8份安全输出重新接受完整联合评价；共同签名一致；上下界来源和未查域保留。
- `results/postcheck01/summary.json`：可机器读取的对照汇总；`summary.csv`为阅读副本。
- `SHA256SUMS.txt`：新包工件校验。旧包单独校验结果见`archive_integrity.json`。

复核只重放保存方案，不搜索、不修复，也不把复核结果补作运行预算内证据。

## 可复跑入口

从项目根目录执行；输出目录必须不存在。下列命令是复现说明，本轮不再次执行配对：

```powershell
python -B research/continuous_planner_compare/compare.py precheck --output research/continuous_planner_compare/results/precheck_new
python -B research/continuous_planner_compare/compare.py paired --output research/continuous_planner_compare/results/pair_new --receipt research/continuous_planner_compare/results/precheck_new/checks.json
python -B research/continuous_planner_compare/compare.py postcheck --output research/continuous_planner_compare/results/postcheck_new --receipt research/continuous_planner_compare/results/pair_new
```

配对入口要求预检全部通过且源码／输入／规则哈希匹配。此入口面向原CP1，不构成任意平台或参数的通用验证器。

## 本轮收敛

E-only在CP1提供了与EML相同的安全输出，适合作为已接通的简洁对照。保留EML及所有历史结果，不据此声称一般模型下只需最早表。当前共同温度盒覆盖全部选项，热筛选不活跃；下一项仅明确主线关系验证的问题与必要输入条件，再与用户讨论，不自动改参数找优势。
