论文展示补充已完成：双面板温度图、七方案主实验表和九配置周期补充表。原A/B/C的413个工件SHA全部保持原样。未进行新调度搜索、参数扫描、提交、推送或合并。

可直接使用的文件：

- 最终论文图：[PDF](figure/AB_NPU0_startup_and_periodic_v3.pdf)、[SVG](figure/AB_NPU0_startup_and_periodic_v3.svg)、[PNG](figure/AB_NPU0_startup_and_periodic_v3.png)。采用v3；旧版及排版初稿保留。
- 图注：[中文图注与技术说明](figure/caption_v3.md)、[LaTeX图注](figure/caption_v3.tex)。
- 七方案主表：[Markdown](tables/main_experiment_table.md)、[CSV](tables/main_experiment_table.csv)；另附[完整能量分项](tables/main_energy_components.md)。
- 九配置周期补充表：[Markdown](tables/periodic_supplement_table.md)、[CSV](tables/periodic_supplement_table.csv)。CSV为带BOM的UTF-8，精确字段及来源见[映射](tables/table_data_exact.json)。

左图显示AB/NPU0的全H固定模板，以75、80、85、90 ms周期从50°C连续运行至3 s，轮间继承温度。右图为AB/NPU0、90 ms周期下三模板的稳态轨迹，从既有证据包围的周期入口传播；HEFT/MILP近乎重合，未偏移温度。原全H模板与HEFT首次构造身份不同。

既有端点不足以充作密集曲线，因此保持原时间表及物理参数，将恒功率段等价细分到最大2 ms，原核补算恰10条绘图路径。保存6,396个四节点向量点、25,584条节点区间和6,254个显示点：[全节点数据](figure/raw_plot_points_all_nodes.csv)、[显示数据](figure/display_curves_AB_NPU0.csv)、[原收据](figure/point_run01/)。630项断言通过，8条SAFE/2条完整超温，无失败或重试。它们是绘图传播路径，不是10次新调度实验；后续布局调整新增热调用为0。

采样中值连线不替代连续峰温、全轮安全界或违规凭证。越限后曲线仅为无热保护/关停的模型诊断；四节点整段连续包围均在20–100°C声明有效域内。新点1.572/2.310 s仍在原第21/29轮，图中1.575/2.315 s为原记录见证，四个时刻均非精确首次穿越。周期表脚注已澄清，原C未回写。400 ms系统能耗、J/周期、稳态峰温、保守全轮界和节点均温分开列示；SA五种子、六项原null及超温配置均保留，超温能耗仅诊断。科学界限向外舍入，耗时近似显示；269项表格派生断言及内部只读复核通过。

实际记录（UTC，2026-11-10）：

|环节|开始|结束|耗时|
|---|---|---|---:|
|表格派生程序|04:01:13.341432|04:01:13.352588|0.011154 s|
|原核补点批次|04:05:36.976831|04:07:54.486932|137.510117 s|
|补点命令进程|04:05:36.932046|04:07:54.504012|137.571882 s|
|只读交付检查进程|04:15:59.588313|04:15:59.699408|0.111097 s|

实际命令、环境、逐调用成本及日志见[表格记录](tables/derivation_checks.json)、[绘图记录](figure/README_delivery.md)和`figure/point_command_started.json`、`figure/point_command_return.json`、`figure/point_stdout.log`、`figure/point_stderr.log`。原周期生成程序仍未找回；本图复用已说明的C冻结模板和原热核，不是独立实现或硬件实测证书。

[最终交付检查](delivery_checks.json)587项通过；[表格复核](table_internal_review.json)与[图形复核](figure_internal_review.json)说明内部审查性质。最终PNG已目视检查，PDF经pdfinfo确认单页。v1历史清单对尚未收尾的stdout记录了空日志哈希，唯一这一项与闭合日志不同；科学文件未变，历史清单保留，全部89个绘图工件及闭合日志以[最终图件清单](figure/figure_final_manifest.json)为准。补充点证据见[说明](figure/figure_evidence_addendum.json)。本目录最终状态和清单见`presentation_completion.json`、`presentation_manifest.json`。
