# 第三章正式对照的只读后处理

本目录独立于冻结的 `chapter3_experiments` 源码。只读取清单、调用记录和已经形成的连续热能耗回执；不导入求解器、解码器或热评价器，不补搜索、不重算温度、不修改原结果。

```powershell
F:/Anaconda3/python.exe research/chapter3_formal_analysis/analyze_formal.py --input research/chapter3_experiments/results/formal_comparison01 --out research/chapter3_formal_analysis/results01 --plots
F:/Anaconda3/python.exe -m unittest discover -s research/chapter3_formal_analysis -p test_analysis.py -v
```

- `calls.csv`：115项逐调用状态、SAFE上界、L0差距、求解器内部界／gap、首SAFE、种子与MILP后续改善归因、反馈和计时。未完成／中断／未决均保留。
- `condition_method_success.csv`：分条件、分方法成功数；同时给预定调用数和已完成调用数两个分母。SA75次不是75种任务。
- `sa_per_problem.csv`：五种子逐项、成功比例、成功种子能量中位数及最小—最大范围；失败不填零，不以最佳种子代替SA整体。
- `HEFT_normalized_common_success.csv`：仅双方都有SAFE时计算同一问题 `U_method/U_HEFT`；另列能量区间比。HEFT没有SAFE时分母为空，全部对应比值缺失。
- `timeline.csv`：已存SAFE U、独立L0、原样solver-reported进展分别登记。`certified_gap=(U-L0)/U`；内部gap采用求解器原生单位，不与认证gap混排。内部界高于U保留异常，不截成零。
- `timing_phases.csv`：方法实际执行的互斥阶段耗时，含协作式停止的超时部分；证据截止仍是300秒。进程墙钟、清理另列，首次安全时间包括本次构模／启动／种子成本。
- `energy_components.csv`：全窗加权基准／活动／公共／温度修正能耗；由保存轨迹分开执行期与尾段的前三项。当前回执没有分段温度积分，**执行期和尾段总能耗暂不可拆分**，不使用温度采样插值补造。
- `preserved_SAFE_audit.csv`：即使worker后续归档失败，已完整落盘、输入身份和候选回执一致、预算内形成的SAFE仍单列保留。缺最终`call_id`允许在此审计层按清单、问题、方法、种子及输入核对；不因此修复worker退出码、控制器技术检查，不计入正式成功率或SA统计。
- 三张图：共同成功的HEFT归一化能耗、所有成功调用的首SAFE、预先固定R1三个条件的U／界轨迹。SA画成功种子的中位数／范围或逐点，不画最佳种子。

分析可以读取运行中的目录，但只有控制器已完成并通过技术检查的调用计入正式成功数。结果已落盘但控制器未接收的调用单列；中断后的未运行项不是失败能量或不可行证明。最终解释应在调用完成后进行。

这些是已保存证据的一致性核对，不是新的独立热安全复算。失败或热未分辨保留原状态；本脚本不会将求解器最优／无解退出升级为独立证书。
