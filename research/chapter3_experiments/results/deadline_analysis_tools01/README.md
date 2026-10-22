# K163期限组的只读结果分析工具

复用P2存档解析、界分列、阶段和热记录索引，另加当前期限、正常无安全U、失败种子分母及两点期限比较。来源hash见origin.json。此目录不属于科学方法，不参与候选搜索、热积分、求解或post；执行总控由主线独占。

正式分析须等待 `deadline_execution01/process_terminal.json`。冻结源码与快照逐hash一致后，读取40个预声明槽；未启动、正常无U、未决、故障分别保留，不能填0能耗。无完整SAFE或post未通过的行不能进入能耗排名。两阶段与solver-reported状态不升级为独立最优/无解。

输出拟包括40槽CSV、SA各次及成功中位数/缺失数、SAFE分母、首次安全/严格改善/MATLAB启动/阶段时间、逐请求精确截止裕量、完整能耗组成、峰温/热拒绝/反馈、已存SAFE运行最小上界与独立L0、P0 beta1.3与新beta1.0的两点比较图。P0只作已冻结条件参照，不是免费初始化。两点图不宣称普遍单调趋势。

`deadline_margins`只用已存模式时长与安排作Fraction减算，不重新验证热轨迹；正式SAFE仍由方法回执、当前输入合法性门和既定post共同确定。曲线只是已存完整SAFE评价的运行最小上端，不冒称每条评价都触发正式incumbent更新。独立L0按各调用保存形成时刻画，内部求解器界只保留原作用域。

纯手写夹具：

```text
F:/Anaconda3/python.exe -B research/chapter3_experiments/results/deadline_analysis_tools01/test_pure.py
```

原2/40停止分析已保存在旧目录的analysis01/02。K164冻结后，整个
`deadline_execution01`严格只读；下述旧入口仅保留历史解析功能，输出必须另选新目录：

```text
F:/Anaconda3/python.exe -B research/chapter3_experiments/results/deadline_analysis_tools01/analyse_deadline.py --out research/chapter3_experiments/results/deadline_analysis_tools01/old_stopped_new_output
```

预计执行层240源；若实际冻结数不同，显式指定`--expected-sources`，仍逐文件核源码和快照，不略过hash检查。当前工具开发阶段没有读取或分析未完成的本批结果。

## K164原40槽的分段联合分析

`analyse_combined_deadline.py`只读原2槽＋原序号3—40的续接，不把P0方法拼入本轮。
核对原240源、新248源、旧目录全部冻结工件及每个封存槽的artifact hash；不读取活动ledger、
未封存raw或method_return。没有result＋artifact清单的槽只记未封存，不提取其中能量。

原第二槽通过hash绑定的`cancel_adapter`审查记录取得派生正常截止状态，并用外部原预定一次
延迟post复核已有U；raw/stored/derived状态、原post缺失与有效post来源分列，不运行适配器、
求解、积分或post，不产生新U。无U的NOT_APPLICABLE不计SAFE。首SAFE、阶段、界、
精确逐请求期限裕量、25个SA种子及成功中位数/缺失数、P0两水平条件参照均单独输出。

纯夹具：

```text
F:/Anaconda3/python.exe -B -m unittest discover -s research/chapter3_experiments/results/deadline_analysis_tools01 -p "test*_pure.py" -v
```

只有封存前缀可用时（不宣告整批完成）：

```text
F:/Anaconda3/python.exe -B research/chapter3_experiments/results/deadline_analysis_tools01/analyse_combined_deadline.py --prefix --out research/chapter3_experiments/results/deadline_resume01/analysis_prefix01
```

`deadline_resume01/process_terminal.json`出现后才可作完整分析：

```text
F:/Anaconda3/python.exe -B research/chapter3_experiments/results/deadline_analysis_tools01/analyse_combined_deadline.py --out research/chapter3_experiments/results/deadline_resume01/analysis01
```

所有输出要求新目录，拒绝写入旧`deadline_execution01`目录。`--no-plots`可略过静态绘图，
不会改变证据接纳。图中缺失能量不填0，前缀图标明封存进度；P0两点比较只作独立条件比较。
