# AC 等价矩阵120秒MILP有界验证

**返回点与原初解位级相同，无优化增益。没有独立全局最优证明；本轮不是正式对照。**

## 条件及身份

原完整三阶段AB/AC输入下，仅取AC原场景、固定共享映射A.pre=CPU1/A.main=NPU0/A.post=CPU1。原模型payload哈希 `7c6454a946273f5ccc2d76b0ebfa264a2fee7ce326de537b474db9bb493c6e1c`，4994对精确反向不等式转为等式，原14014变量不变。

本次重新构造原模型并逐行验证证书；转换后的9组数值数组（包括原x0）与上次保存AC请求一致。原输入、目标、设备频档/时刻候选、容差及预处理未变。复用的是用户明确指定的同一个已保存初解，没有重新HEFT或使用迟到点。初解在本次调用内重新通过原数值行及原完整AC连续SAFE，费用计入根预算。

唯一求解参数变化为每次intlinprog MaxTime由约29.359秒升至120秒；总根由180秒显式扩为300秒，以包含导入、检查、构模、证书、初始化复核、启动、求解、回调和完整SAFE验收。原生MaxTime是软上限，实际值 120。MaxFeasiblePoints=1、RootLPAlgorithm=dual-simplex、两项预处理none、原容差均保持，实际完整选项见AUDIT.json。仍保留热违规取消、用户取消、2GiB资源门以及20秒宽限/40秒清理；只有1个worker/1个请求，不自动重试。

## 实际结果

- 根开始：2026-11-06T22:30:38.662348+08:00；结束含清理：2026-11-06T22:33:21.082985+08:00。
- 总耗时：162.422秒；方法停止：158.81199999997625秒；求解调用壁钟：117.2503857秒。
- exitflag=1；返回向量长度=14014；与原x0位级相同=True。
- 原生终止信息：找到最优解。

Intlinprog 在根节点处停止，因为目标值在最佳值的间隙容差范围内，options.RelativeGapTolerance = 0。intcon 变量是容差范围内的整数，options.IntegerTolerance = 1e-06。。
- 原初解SAFE上界：1.11552605679623175741683718098829548113756214128981679975898 J；最好完整SAFE上界：1.11552605679623175741683718098829548113756214128981679975898 J；上界改善=False。
- 最低可用内存：3.2696876525878906GiB；清理=graceful_closed；完整清理通过=True。
- 原输入/基线漂移：[]；源矩阵不变=True；错误=None。

回调和最终点在实际Recorder.assess入口先用原完整数值行检查，再按原模型解码并调用原连续电热评价。相同候选的完整原场景SAFE可在本次调用内按身份复用，缓存命中明确记录。若只返回初解，不能把已有初解SAFE称为MILP优化贡献；若返回不同点，仅有数值目标下降也不能冒充原SAFE能耗改善。无论原生exitflag为何，此单次反馈/单映射调用都不自动获得原完整物理问题的独立最优证明。

## 命令及证据

在本报告目录执行：

```powershell
& '${PYTHON_EXE}' -B -u .\run_once.py > .\execution.log 2>&1
```

完整启动argv在runtime/LAUNCH.json；逐样本内存在runtime/resources/memory.jsonl；进程身份在runtime目录和matlab/closed.json；原生请求、原生返回MAT、回调/终值JSON和日志在matlab/；原完整场景SAFE及候选在scene_receipt_*.json，原行准入在original_admission_*.json。EQUIVALENCE.json保存证书和数值数组一致性，RETURNED.json保存调用者所见响应，RESULT.json/AUDIT.json为汇总。

本轮无其他映射、无重复短LP、无正式HEFT/SA对照、无历史覆盖、无提交推送。相较此前29秒诊断同时扩大了明确记账的总根预算，因此不能直接用包装总耗时声称公平算法优势。

## 原生状态内部不一致，不能采信最优声明

原始exitflag=1且消息称根节点零间隙容差内最优，但同一output保存relativegap=16.63925、absolutegap=0.352008；实际RelativeGapTolerance=0、AbsoluteGapTolerance=0。rootlp事件的松弛目标0.7635183800868108与返回初解1.115526056796232也存在明显差距。这些值如实保留，不能将exitflag=1当作可信最优证明，包括不能直接声称浮点MILP已证最优；状态登记/MaxFeasiblePoints等内部关系未查明，未通过改参数或重跑掩盖。

本次记录到rootlp事件的求解器time=116.1127512秒，显著晚于此前约29.36秒时限，为AC短时调用没有完成根LP的解释提供了直接新证据。此后仍仅交付原初解，无优化收益。
