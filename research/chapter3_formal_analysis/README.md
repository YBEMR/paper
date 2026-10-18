# 第三章正式对照的只读后处理

本目录独立于冻结的 `chapter3_experiments` 源码。只读取清单、调用记录和已经形成的连续热能耗回执；不导入求解器、解码器或热评价器，不补搜索、不重算温度、不修改原结果。

```powershell
F:/Anaconda3/python.exe research/chapter3_formal_analysis/analyze_formal.py --input research/chapter3_experiments/results/formal_comparison01 --out research/chapter3_formal_analysis/results01 --plots
F:/Anaconda3/python.exe -m unittest discover -s research/chapter3_formal_analysis -p test_analysis.py -v
```

原批次停于第5项后，续行只允许原清单尚未启动的110项。完成后显式合并：

```powershell
F:/Anaconda3/python.exe research/chapter3_formal_analysis/analyze_formal.py --input research/chapter3_experiments/results/formal_comparison02 --prior-input research/chapter3_experiments/results/formal_comparison01 --out research/chapter3_formal_analysis/results02 --plots --entry-temperature-audit --receipt-state-audit
```

合并前核对原15问题／115项、旧5项claim与调用、剩余110项的原顺序及全部job字段；禁止重复、漏项、换输入或换预算。续行声明必须绑定旧目录、旧manifest、旧源码签名和旧记录哈希，源码差异仅限声明的归档／续行入口及测试。每行保留来源批次与源码版本指纹，**不宣称两批采用同一源码**。原SA103技术失败继续单列审计，不能被续行替换或补记为正常完成；续行入口3项验收也不改写原8项验收。

- `calls.csv`：115项逐调用状态、SAFE上界、L0差距、求解器内部界／gap、首SAFE、种子与MILP后续改善归因、反馈和计时。未完成／中断／未决均保留。
- `condition_method_success.csv`：分条件、分方法成功数；同时给预定调用数和技术正常完成数两个分母。`completed_calls`专指技术通过；`invoked_calls/terminal_calls/batch_execution_finished`分别标记已启动、已有终态、执行是否结束。`rate_is_final`指全部已有终态，`technical_acceptance_complete`才指技术全部通过。SA75次不是75种任务。
- `sa_per_problem.csv`：五种子逐项、成功比例、成功种子能量中位数及最小—最大范围；失败不填零，不以最佳种子代替SA整体。
- `HEFT_normalized_common_success.csv`：仅双方都有SAFE时计算同一问题 `U_method/U_HEFT`；另列能量区间比。HEFT没有SAFE时分母为空，全部对应比值缺失。
- `timeline.csv`：已存SAFE U、独立L0、原样solver-reported进展分别登记。`certified_gap=(U-L0)/U`是共同L0所给的最优差距上界，不是已知真实最优差距；内部gap采用求解器原生单位，不与该上界混排。内部界高于U保留异常，不截成零。
- `timing_phases.csv`：方法实际执行的互斥阶段耗时，含协作式停止的超时部分；证据截止仍是300秒。进程墙钟、清理另列，首次安全时间包括本次构模／启动／种子成本。
- `energy_components.csv`：全窗加权基准／活动／公共／温度修正能耗；由保存轨迹分开执行期与尾段的前三项。当前回执没有分段温度积分，**执行期和尾段总能耗暂不可拆分**，不使用温度采样插值补造。
- `preserved_SAFE_audit.csv`：即使worker后续归档失败，已完整落盘、输入身份和候选回执一致、预算内形成的SAFE仍单列保留。缺最终`call_id`允许在此审计层按清单、问题、方法、种子及输入核对；不因此修复worker退出码、控制器技术检查，不计入正式成功率或SA统计。
- 三张图：共同成功的HEFT归一化能耗、所有成功调用的首SAFE、预先固定R1三个条件的U／界轨迹。SA画成功种子的中位数／范围或逐点，不画最佳种子。
- `--entry-temperature-audit`：另读同R的base／initial_78已验收HEFT评估数组。只剥离问题条件标签及入口温度，核其余输入相同；按完整候选canonical hash及内容匹配。记录50°C完整SAFE和78°C预算内严格超温点的配对、节点、时刻、温度包络、温限和形成时间。`entry_temperature_pair_audit.json`保留完整候选与回执索引，CSV逐条保存点见证。只证明声明入口下约束作用；访问交集有选择偏倚，不证明全局最优、配置选择改变、反馈收益或新颖性。无匹配保留为空，不扩大候选或补热计算。
- `--receipt-state-audit`：仅读取已存评价状态／原因，区分因预算中断的未分辨、非预算未分辨及显式数值错误；技术失败调用另作审计层。历史候选未分辨不等于最终调用没有SAFE，也不自动算数值错误。

分析可以读取运行中的目录，但只有控制器已完成并通过技术检查的调用计入正式成功数。结果已落盘但控制器未接收的调用单列；中断后的未运行项不是失败能量或不可行证明。最终解释应在调用完成后进行。

这些是已保存证据的一致性核对，不是新的独立热安全复算。失败或热未分辨保留原状态；本脚本不会将求解器最优／无解退出升级为独立证书。
