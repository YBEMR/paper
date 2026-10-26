# E1：同一真实物理模型、两种规划目标

本目录只新增评分/搜索接入/结果身份接口；原输入、HEFT构造器、合法性、热核保持。`FULL`按完整能耗评分；`OMIT_TEMP`精确累加基准、活动、外部公共功率积分。二者均要求同一个完整连续热安全回执，真实能耗字段原样归档。

- `scoring.py`：已形成回执的纯核查及新命名评分；去温度目标不做区间相减。
- `search.py`：原HEFT一轮邻域的局部接纳只改评分读取，AST规范化检查约束改动范围。
- `runner.py`：每次调用独立缓存，外层按规划分数上界择优，同分保留先出现者；真实U不是去温度组的裁决因素。
- `exports.py`：核查最终方案正是规划分数优选方案及其原真实回执；与局部严格区间下降的规则区分。
- `boundary.py`：前阶段mock合同保持关闭；实际执行链在`controller.py`／`worker.py`，由`ledger.py`与`process_control.py`提供持久消费、统一计时、STOP及进程回收。
- `mock_fixtures.py`：手写的单节点双场景测试数据，无RC矩阵；模拟SAFE不构成研究SAFE。

复跑（仓库根目录；输出必须是新目录）：

```text
F:/Anaconda3/python.exe -B research/chapter3_experiments/e1_objective/precheck.py --out research/e1_e4_validation/evidence/自选新目录
```

预检验证15份原源码/配置与固定提交完全一致，运行66项静态/mock测试，展开R1/R3参数并检查双臂仅objective字段不同。科学函数保护拒绝真实HEFT构造、热积分与外部进程；测试对原HEFT控制流的调用全部使用mock构造器。

实际执行接线与120项保护性预检已完成，见[执行控制交付](../../e1_e4_validation/E1_PROCESS_CONTROL_DELIVERY.md)。`execution_precheck.py --out <新目录>`复跑含真实mock进程的检查，科研闸门保持关闭。正式4×300秒＋至多4×60秒仍需单独确认，不继承其他分支额度；模拟SAFE不形成真实研究证据。
