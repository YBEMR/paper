# G0隔离实现：人工验收版

依据：`fa295f09`最终合同及用户本轮实施授权。只开放人工后端，无真实科研入口；不读取参考时间表、历史SAFE或独立HEFT结果。

| 模块 | 职责 |
|---|---|
| contract.py | 科学身份、精确时间、D0-all/cross、共享副本及参考信息隔离 |
| blocks.py | 2/4执行实例整组、H/余量/关联排序、补集种子与覆盖率 |
| budget.py | 原MethodBudget子类，同根身份、阶段/片段截止及封闭scope |
| receipts.py | 原PARTIAL接口、完整SAFE档案、视图身份、能量区间相容 |
| local_domain.py | 独立G0条件、成员关系、原选项校验及四类闭锚预消元 |
| local_model.py | 原构造函数238行数值后缀逐字保护，手给系数行回放 |
| method.py | 同次初始化、冻结D0/S0/S1、两阶段即时构模及故障收口 |

根目录执行以下人工检查，输出目录必须尚不存在：

```powershell
& 'F:/Anaconda3/python.exe' -B -m research.chapter3_g0.tests.run_checks --out research/chapter3_g0/results/manual_next
```

该入口只运行手写夹具、假HEFT/求解器/时钟、原回执接口和人工系数/功率账本；真实算法、进程启动、RC系数生成与热积分入口被拦截。`ManualLedger`的固定10 K修正是人工计量行，绝非求得的温度轨迹或物理安全证据。

最终凭据：[manual06/checks.json](results/manual06/checks.json)，32/32、180断言；[保护核对](results/manual06/protection.json)。每项有输入/源hash、断言、异常和单独回执，运行时源码快照在同目录。`manual01`—`manual05`及静态生成失败保留，未覆盖。

当前实际域：初始化最终完整锚确定D0后不再改设备，局部仅改OPP/起点；阶段一锚属于F1，阶段二锚属于F2，旧SAFE全局留档。B2先全场景原子声明，再逐场景构模。新U必须在有效截止前完成全场景聚合，已形成SAFE跨阶段继承不刷新时间。

本版每次暖启动准备重新评价人工视图，不实现跨slot视图缓存。真实系数、真实x0/反馈及原生求解默认关闭；人工PASS不说明96 Stage可完成或能够节能。下一步须另行批准小规模真实接入，不自动冻结β、S1—S7统计或50根预算。
