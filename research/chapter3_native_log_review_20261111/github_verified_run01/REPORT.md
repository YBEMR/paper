# R1 本机 OFF/ON 原生日志复核

已从固定提交 `2fc52c63814d06b039e24a3bde887a2b411be298` 取得原始结果包并核验。结论是：支持传播显著减少模型规模；这一单对中 ON 在300秒预算内完成根 LP 阶段并产生一个完整 SAFE 候选，但该候选与现场初解相同，节能改善为0。OFF 没有预算内有限下界或 solver SAFE。两组都没有全局最优证明，也都没有对 intlinprog 内部采用 x0 的独立观测。

这是原始工件的只读审计，包含已有矩阵的数值残差检查，没有构模、调用求解器、重新进行热积分或更改历史结果。此前上层 `REPORT.md` 记录的是取件受阻时的阶段状态；本目录新增取得原始包后的证据，不覆盖旧记录。

来源是 [GitHub 固定结果目录](https://github.com/YBEMR/paper/tree/2fc52c63814d06b039e24a3bde887a2b411be298/research/r1_native_local_results_20261110/run01)。原 ZIP 为13,690,438字节，SHA-256为 `b0aab1f9d62df45634400a45b526fc5a8652eaa9d4ef594270df20f7998a79f1`。安全解压得到95个文件，共57,675,943字节。原执行清单93项、内层迁移包清单269项、计划中217项运行源码和2项输入哈希全部匹配。原迁移包 SHA-256为 `8e799aa5b50de04dd0683af9864859e30051133f6d7aa9661e5550345e788f73`；本机计划 SHA-256为 `0830d2d6c546e99f2a7a93de84c86f477a6cbc37f5b44b3e8eb5d28774b1c1bb`。各项检查见 `verification_checks.json`。

下文路径均相对于 `raw/local_records/`，冻结源码位于 `raw/input_bundle/R1_support_local_matlab_20261110.zip` 内。没有执行包内任何入口。

本机控制调用真实起止为 **2026-11-10 12:07:03.602530–12:17:53.707488 UTC**，控制器记录650.110秒、退出码0。窗口对应 UTC+8 的20:07:03–20:17:53。环境为 Windows 11、Anaconda Python3.12.4、NumPy1.26.4、SciPy1.13.1、psutil5.9.0，MATLAB23.2.0.2365128（R2023b）；两侧 ready.json 均确认工具箱 checkout。冻结计划里的 NOT_STARTED/NOT_CHECKED 是启动前状态，不代表后续未启动。OFF→ON各一次、独立 Python 进程、各一次原生请求，没有补跑。

|指标|OFF|ON|
|---|---:|---:|
|合法选项数|1,681|1,125|
|变量数|29,599|21,411|
|约束行|200,205|144,966|
|约束非零数|2,127,851|1,469,953|
|AB/AC事件数|287 / 296|216 / 210|
|AB/AC控制区间数|286 / 295|215 / 209|
|系数集合数|621|678|
|affine cache miss|7,560|7,494|
|构模独占耗时|18.969 s|19.250 s|
|MATLAB启动耗时|7.484 s|8.969 s|
|现场初解SAFE形成，方法时钟|27.469 s|29.766 s|
|完整x0形成，方法时钟|29.344 s|30.781 s|
|首次原生入口事件收到，方法时钟|33.156 s|32.766 s|
|solver候选完整SAFE形成|无|291.469 s|
|方法总计时|300.016 s|300.016 s|
|另计清理耗时|20.469 s|20.562 s|
|最终完整SAFE能量上界|1.63246481655731864640098853403740765520284997579506076426707 J|相同|
|严格节能改善|无|无|

选项减少33.076%，变量减少27.663%，行减少27.591%，非零数减少30.918%。传播本身耗时0.063秒，删除556个选项，其中后继支持规则246个、前驱支持规则310个；本例没有跨场景共享设备规则删除。三个传播轮次包含最终固定点检查，没有空域。仍不能从这些删除推断整个问题已经逻辑可行，最终SAFE来自完整评价。

本机这一对并未呈现构模加速：ON构模反而多0.281秒。affine miss仅少66个（0.873%），两侧都发生3次cache clear；这不是全局唯一状态计数。系数集合621→678；系数查询/生成独占耗时5.103→5.829秒，条件电热行10.766→10.884秒，已有能量下界强化1.775→1.347秒。这些实测说明删选项不会按比例减少系数生成与行组装成本，但单对无法归因机器负载、缓存与事件区间变化各自的贡献。内层耗时不可与父项重复求和。以前云端11.358→10.512秒的构模观察属于另一环境，不能替代本机结果。

两侧实际 input_config.json、input_instance.json 分别逐字节相同，保留原12次Stage执行、AB/AC双场景、hold-last、β1.3、50°C初温、80°C温限、400ms完整窗口、5ms启动网格及非整数结束时间。两侧已有 fix_late_options、aggregate_opp_locks、relax_auxiliary_integrality、strengthen_energy_lower_bounds、prefilter_deadlines；cumulative_precedence和preeliminate_closed_anchors仍关闭。冻结 launcher 313–315行检查既有开关不漂移，仅令 `propagate_support = variant == 'on'`。ON重建事件与区间包围，因此不是把OFF旧浮点矩阵直接删行。

两个初解来自原 `deterministic-initial-schedule-v1` 全H短设备/负载规则，**不是增强HEFT初解**。各自现场构造、评价与完成x0的时间都计入各自300秒。两份checkpoint的物理候选重新规范化哈希均为 `3b2483cdfdd7ad79db253538a19bdce0117b80de88135c3d7a3740e1b8f00414`，评价输入规范化哈希均为 `4752bb1d799b4465e4ff6363b351a73829243c4e9d1609dff83b85e7bb035e28`。它与输入文件的原始字节哈希不是同一口径。匹配预声明候选哈希用于身份守卫，不是复用历史向量。实际 initial_guard.json 在请求前完成、请求计数为0；pair_summary的guard对象后来记录1次生命周期请求，两者不能混读为守卫发生在请求后。

独立仅读取 request MAT 并计算已保存矩阵残差：OFF/ON向量长29,599/21,411，整数索引数1,681/1,125；两侧max(Ax0−b)均为2.1316282072803006e−14，等式、上下界和整数违规为0，所有向量元素有限。JSON记录 ConstraintTolerance=1e−9、IntegerTolerance=1e−6，不曾四舍五入或修复。ON JSON中点积末位与此次SciPy重算有约2.2e−16差异，是浮点求和次序级别，不能当能量变化。该复核不是热积分或精确有理数可行性证明。

原完整SAFE收据中，AB能量包围约1.4871475568523514 J，AC约1.7777820762622859 J，等权加权后为上述1.6324648165573186 J；完整400ms包含空闲尾段。两场景全部节点峰温上界最大分别约53.129463°C和52.083547°C。ON solver候选的完整能量区间、物理候选与现场初解逐项相同。本次复核只读既有收据，没有再次积分；原收据使用共同评价器，不是另一个独立热实现。

|原生事件|OFF|ON|
|---|---|---|
|预算内init收到|方法34.703 s；数值界为空|方法33.266 s；数值界为空|
|rootlp回调|无预算内记录|方法289.828 s收到；原生time256.5607468 s；fval0.7438443586267888；lowerbound/gap为空|
|heuristics回调|无预算内记录|方法290.188 s收到；原生time256.8973234 s；U1.6324648165573186；L0.7438443586267873；gap33.75621403717943%|
|完整候选收到/合法/SAFE|均无|方法290.188 / 290.266 / 291.469 s|
|最终response|有，预算后晚到，仅诊断|缺失|
|原生最终exitflag|晚到0，x/fval为空|未知|

ON的rootlp回调可支持“求解器报告已完成根LP阶段”：MathWorks R2023b说明 phase=rootlp 是根LP已求解，且此时 fval 是根节点目标、lowerbound为空。下一heuristics回调出现整数候选和有限下界。这里的原生time是自init累计时间，不是根LP独占时间；没有专用根LP开始时标，不能声称根LP恰好花256.56秒。参见 [R2023b回调字段说明](https://www.mathworks.com/help/releases/R2023b/optim/ug/intlinprog-output-functions-and-plot-functions.html)。本次截至最后预算内回调，numnodes仍为0；不能由此推断之后直到进程结束一直没有其他内部进展。

ON的gap用同一event4中的U与L复算，`100*(U-L)/(abs(U)+1)`恰好得到33.75621403717943%。该百分比定义来自 [R2023b intlinprog output文档](https://www.mathworks.com/help/releases/R2023b/optim/ug/intlinprog.html)，不是通常直接除以U的比例。本报告没有将物理SAFE上界与native gap混算下界。L为求解器报告，不是本次独立认证的物理能量下界。

OFF预算内只有入口和init回调，不能把缺失下界写成0，也不能断言“根LP一直卡住”。晚到done事件的原生time为267.4855746秒、numnodes=0、numfeaspoints=1，但x/fval/L/gap均为空；最终response与native MAT则为exitflag0、x/fval空、output.numfeaspoints=0，消息为超过MaxTime且找不到整数可行点。保留这项计数差异，不据此声称x0已被采用或问题数学不可行。包装层status=SOLVED只表示该调用正常返回，不等于找到最优解。

OFF晚到原生调用观测耗时269.1566574秒，配置MaxTime=266.8897521000027秒，request累计272.1910323秒。配置限额与观测调用耗时不是同一量。Python的request记录为BUDGET_EXHAUSTED、budget_valid=false、accepted_for_evaluation=false，晚到文件不能追认为预算内结果。ON没有response、native MAT或done回调，因此最终exitflag/output、完整原生调用耗时、最终实际options快照均未形成。两侧源码和预声明配置一致，不等于本次两侧都留下了完整options返回。

OFF native MAT的initialPoint与request x0逐元素完全一致，response也明确provided和length，支持MATLAB收到并按冻结solve_model.m 149–150行显式传参。但其solver_acceptance明确为not_independently_observed。ON的启发式回调恰好返回同一物理方案，可能来自初解使用，也可能由内部搜索重新得到；当前证据不区分这两种来源。因此两侧“内部采用x0为incumbent”均未知。不能把Python数值接纳、worker收到、原生采用、完整热SAFE混为一项。

两侧最终safe_solution_source都仍为initial_constructor，milp_improved_initial_upper_bound和strict_energy_improvement_certified均false。ON另有一个solver完整SAFE收据不会自动改变最终解来源。VALID_PAIR仅表示两侧身份守卫、入口与清理等执行凭证完整，不表示优化成功。两侧清理均forced_closed，已捕获的各3个进程身份均确认退出；清理不增加预算内搜索额度；清理期间的迟到文件仅作诊断，不计预算内收益。MATLAB控制台日志为GB18030编码，内容仅为进程终止通知，没有额外LP进度。

Python等待独占时间为OFF269.265秒、ON267.000秒。ON等待父项实际268.281秒，内部嵌套解码0.078秒和完整评价1.203秒，扣除后才是267.000秒。这些等待均含传输/轮询，不能当纯solver CPU或根LP耗时。300秒从输入读取前开始，包含构模、MATLAB启动、现场初解、导出、原生等待和评价；导入在计时前，清理和报告在后，两侧相同。实测方法时钟超额约0.016秒；代码使用合作停止，未提供硬实时截止保证，本次没有独立定位该超额的精确来源。

既有能量下界强化已经实施。冻结milp.py 655–707行对每个场景/事件区间的状态能量析取构造共同斜率下界，1117–1122行实际加行；它利用原浮点导出行的有理数解释与变量界，追加有效不等式以加强LP松弛。新增支持传播在891–896行、事件及电热构造之前删除无支持选项，作用不同。不能把已有强化写成下一步尚未做的新招。

此前历史核查记录中，原R1已有能量强化将一次根松弛从0提高到约0.740331755956 J，仍未在相应900秒诊断中得到及时完整solver SAFE；deadline prefilter曾将6,422选项缩到1,681、构模29.578→19.188秒；另一个较小六执行模型曾通过精确相反行改等式恢复求解路径。这些属于各自输入/版本和计时口径，详见上级 `history/README.md` 的原始来源，不等于本次传播的消融。此次OFF没有有限下界，无法计算传播引起的根LP界提升；ON仍有gap也不证明既有强化无效。

建议的最小后续实验是**两份既有矩阵各一次纯LP诊断**，本轮只提出方案，未执行：冻结各自request MAT哈希，保持c/A/b/Aeq/beq/lb/ub不变，仅取消intcon的整数限制；同机器、同R2023b、显式核实相同可用LP算法和预处理选项，各300秒诊断总预算含加载与转换，原生仅使用剩余时间，晚到结果仅作诊断。记录目标、迭代/退出信息、残差、读取/调用耗时和完整配置。这能比较两份已存连续松弛在指定LP算法和预算下的求解状态、目标及耗时；单对不作统计速度结论，不能据此判断固有难度或复现intlinprog内部root过程，也不能计为端到端调度表现、完整SAFE或独立物理下界证书。复用已存矩阵只适用于这个后验诊断，不能作为完整算法比较的免费构模/初解。

若优先补运行阶段日志，可另行冻结同300秒、相同日志设置的OFF/ON诊断，保持原模型、初解和所有既有优化；它仍可能没有final response。不要为补返回贸然预留30秒却忽略本次ON约到方法289.8秒才完成根LP；缩短原生时间可能直接失去该进展。也不应预设延长预算必最优或存在可直接读取x0内部接纳的接口。上述均不是新增求解授权。

本机mock记录为24项中23项通过，1项因Windows没有创建人工symlink夹具的权限而失败（WinError1314、测试进程退出1），不是24项全过；未绕过权限或篡改测试。此次93/269/217等计数是哈希检查，不是新算法测试或新实验。`verified_metrics.json` 中抽查的上界、首次SAFE、方法耗时及响应缺失字段与原始记录一致，结论仍以原始事件和收据为准。

本次Cloud原始包下载记录从2026-11-11 02:15:36.582474 UTC开始，下载/校验/解压1.410427秒；主审计脚本实际起止和耗时见 `analysis_execution.json`，整体完成时刻见 `completion_record.json`。独立矩阵审计读取区间02:16:24.997980–02:18:17.210235 UTC；独立进度审计02:16:37.768015–02:17:54.323418 UTC。后两段包含阅读解释，不是额外模型运行时间，且相互重叠，不应相加。

主要实际命令及执行性质见 `COMMANDS.md`。可读输出为 `comparison.csv`、`callback_timeline.csv`、`phase_timing.csv`；完整选取字段在 `raw_result_summary.json`，原始逐文件身份在 `zip_member_manifest.json`。原研究源码和历史结果未改、未提交或推送。
