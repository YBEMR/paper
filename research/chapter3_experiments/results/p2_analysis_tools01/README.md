# P2只读结果汇总工具

仅读取已保存JSON，不导入科学模块，不调用求解器、构模或热评价。P2必须已有process_terminal.json；未结束时拒绝且不创建输出。COMPLETED和停止批次均可汇总，未启动槽保留NOT_STARTED。

在仓库根目录执行：

```powershell
F:/Anaconda3/python.exe -B research/chapter3_experiments/results/p2_analysis_tools01/analyse_p2.py --out research/chapter3_experiments/results/p2_execution01/analysis01
```

输出facts.json、逐槽CSV、两阶段/场景组成/节点峰温CSV、SA分布、P0/P2分条件对照、安全U与独立L0随时间图。输出目录须新建，不覆盖旧结果；--no-plots可省略绘图。

- U来自原方法回执，post只另列接纳状态，不替换原U。
- 初始与第一/第二阶段能量由完整SAFE回执提取，阶段没有新回执时保留进入阶段的能量。
- 只对有原完整安全回执的安排列能量，无U不填0；技术状态、post状态分别保留。
- 比较统计另要求正常/已核截止状态且post通过；即使保留原安全U，post或执行异常仍不加入质量排名。worker终态与ledger消费数分别保存，claim已成而账本未更新的槽不伪装未启动。
- 原生内部界保留来源和作用域，不聚合局部界冒充全域界；图中只放独立L0。
- feedback按各真实搜索调用提取，忽略最终scene别名；热评价去重只计存档对象，不称精确热评价调用总数。
- SA五次逐条与安全分布保留，五次最小值仅描述，不当一次同预算竞争者。
- P0/P2是两个真实初温条件；安排/能耗变化不是同一固定安排的高温因果复算。

每次分析保存所读工件hash及工具hash，验证224项冻结源；与P0对照仅读已归档facts，不能为后续算法免费初始化。

开发验证：在本目录执行`F:/Anaconda3/python.exe -B -m unittest test_pure -v`。仅运行合成记录/算术夹具，不读取未完成P2批次。

已验证范围（2026-10-22）：7项纯夹具通过；仅读P1已完成R1的整体MILP、联动、HEFT、SA101四份代表回执，与既有facts共43项字段/两阶段能量逐项相同，见validation01.json及validate_representatives.py。SAFE曲线使用completion_metrics中的completed_at_s/safe_upper_bound_J，未以raw其他时间字段替代。没有读取/分析RUNNING P2账本，没有对P2绘图，未作全40份或实际P2结果验证；待主代理确认终态后再执行。

## P2终态执行与补充核对

确认P2终态后已生成analysis01。本批热接纳30项、SAFE曲线末值40项、解释55项只读核对通过，对应review_thermal_acceptance.py、review_safe_curves.py、review_interpretation.py及同名JSON；没有新增求解/热评价或修改原U。检查脚本默认独占写入结果文件，复核新版本时另存工具/输出目录，不覆盖旧记录。

原safe_energy_and_independent_bound.png绘出全部完整SAFE评价，SA后续评价值可上升，不能当作已知最佳U退化。plot_best_safe.py另生成best_safe_upper_bound.png：对原记录取运行最小上端，40/40末值与原U精确相同，原图/原脚本保留。图是后处理的已知安全见证上界，不声称每次SAFE都触发算法正式更新。

五题同一HEFT中间候选在P0安全、P2严格超温，最终HEFT安排却五题相同；R1相同最终安排的增耗与温度项增量一致。严格超温、时间预算未决、MILP反馈及最终选择分别解释，见interpretation_review.json。
