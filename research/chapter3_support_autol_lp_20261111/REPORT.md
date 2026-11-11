# 完整 R1 前置支持传播与旧矩阵 LP 诊断

两项限定工作已执行。当前证据支持保留前置支持传播：有限小域完整结构合法集合未变，完整auto-L R1的变量减少29.009%、约束非零数减少33.913%。旧hold-last两份LP则均在预设100,000次迭代上限停止，未返回向量或目标；本轮没有取得可比较的最优松弛值或认证下界，不能据此建议立即启动完整MILP。

本轮全部材料在本目录；没有新增Stage、改变原物理参数、切换Benders、求解完整MILP、重新进行候选电热仿真或推送。静态构模生成完整电热约束及区间系数，不等于对调度候选进行电热仿真。下面两套输入、方法与成本分开解释。

实际工作使用 `/workspace/paper` 当前checkout `052c0b01c9a840c2b5b6ff8018afcaf08654a24a` 及此前已实现的未提交支持传播修改；以文件哈希而不是单独Git HEAD标识执行源码。Cloud为Linux6.18.57 x86_64，Python3.12.14、NumPy2.3.5、SciPy1.17.0。当前无MATLAB/Octave，未安装新求解器。已在执行前说明旧矩阵改用本环境已有的HiGHS1.8.0独立LP接口；两个LP的环境和配置相同，不能当作原Windows R2023b内部根LP的复现。

原 `option_support.py` 和 `test_option_support.py` 已逐字节归档至 `domain_validation/archive/`，SHA-256分别为：

```text
option_support.py       fe33351662dcdc7f50136c3601af022bd831ce8a41ae6e92810b46b09f5efbf8
test_option_support.py  59e62b15f8a325ddc69fdac291169cdfeccfd92a111e1a05551fd90461abd557
```

独立枚举不调用传播实现的内部判定函数来决定合法性。10个固定边界目录，加4个目录的全部256个子目录，共266个有限目录，传播前后完整组合累计342→221，独立结构合法谓词得到的完整合法集合逐目录一致，累计186→186。不同目录可能重复同一组合，186不是186个独立研究实例。512条删除证明均可重放，未发现反例。

覆盖边界包括依赖结束与后继开始相等、精确有理数非整数结束、5ms启动网格、并发资源互斥和CPU共享频档、跨场景同设备但不同频档/起点、多轮依赖—共享交互、空域，以及“支持固定点非空却仍存在资源冲突”的负例。完整候选、非法原因、合法集合及每项删除证据见 `domain_validation/complete_schedule_sets_and_proofs.json`，报告见 `domain_validation/REPORT.md`。原测试文件整套包含热评价路径，本轮只归档，没有全量执行；实际执行的是新的独立枚举检查。

安全论证依赖原目录覆盖待保护选择、每个Stage出现选一项、依赖使用精确结束≤开始、共享身份确实只约束设备等条件。任何原合法完整调度的已选项必然彼此提供依赖支持及跨出现同设备支持，故逐轮删除不会删除该调度的任何已选项；保留项均来自旧目录，也不会新增完整调度。在这些条件下，资源与热约束等相同附加谓词对保留选中项的论证不变。有限枚举实际核验的是声明的结构合法集合，没有重新热积分，不能写成266个SAFE实例，也不能把这一组有限检查代替普遍正确性证明。

auto-L完整R1输入来自既有 `research/chapter3_experiments/results/whole_long_budget01/method/{input_config,input_instance}.json`。当前源码从该配置生成的实例与原归档对象完全相同，AB/AC各6次Stage执行、共12次，原66个模式保留。与旧hold-last相比仅 execution_rules 使用原已有 `auto_low_immediate_v1`；平台、任务、模式和β1.3、50°C、80°C、400ms、5ms等不变。没有误用后来的六次总执行收束实例。输入与216项科学源码均已冻结，两个入口修订间源码和输入哈希相同；216与旧217是归档范围不同，不冒称同一集合。

|auto-L静态指标|OFF|ON|
|---|---:|---:|
|选项|1,681|1,125|
|变量|27,971|19,857|
|约束行|176,953|124,338|
|非零数|1,983,981|1,311,146|
|AB事件 / 区间|287 / 286|216 / 215|
|AC事件 / 区间|296 / 295|210 / 209|
|AB联合状态块|6,855|4,861|
|AC联合状态块|7,204|4,937|
|联合块合计|14,059|9,798|
|option expansion阶段，含期限过滤|0.041836秒|0.047806秒|
|支持传播内部耗时|关闭|0.049769秒|
|输入起计至构模完成的observer时标|8.203578秒|7.254621秒|
|精确构模独占耗时|缺失|7.254189秒|
|精确矩阵导出耗时|缺失|0.494402秒|
|精确方法总耗时|缺失|7.749387秒|

两侧已有fix_late_options、aggregate_opp_locks、relax_auxiliary_integrality、strengthen_energy_lower_bounds及prefilter_deadlines均保持。唯一科学开关差异是propagate_support。ON删除556项：后继支持246、前驱支持310、共享设备支持0，3轮含固定点检查，空域0。没有资源两两支持；保留原全部Stage及合法设备、频档、时间选择。

OFF已构模、导出并保存矩阵，但归档平台元数据时 `platform.platform()` 触发uname子进程，被过宽的防求解守卫拒绝，进程退出1。失败日志和已完成工件保留，没有重跑OFF。其规模、联合块及构模完成时标由原progress与NPZ/变量名恢复；未保存的精确阶段及总耗时保持缺失。随后只把平台信息缓存移到守卫前，在新 `rev02/` 入口冻结后执行尚未运行的ON一次，科学源码和输入没有修改。原配对launcher的380秒外部保护没有在该次ON直接exec上另行应用，实际使用300秒合作预算、7.75秒完成；此偏差已保留。故上述两个observer时标不能包装成完整、同入口、统计有效的端到端加速结果。

原静态计划SHA-256为 `f21a55691a7446e60428c570356f75e6317099fa1b4c20c7e50ac1ba9c8a2fab`，修订计划为 `1d46656a5dccee571dd82acd44e865d1de9b600da94912f13029fd2c740de599`，ON独立执行范围记录在scope_amendment。更完整的来源、输入哈希、失败及计时恢复边界见 `autol_build/SUMMARY.md`、`off_recovered_static.json`、`completion_checks.json` 和 `static_comparison.csv`。

旧hold-last LP使用11月10日原生配对包的两份实际request MAT，结果包固定提交为 `2fc52c63814d06b039e24a3bde887a2b411be298`，ZIP SHA-256为 `b0aab1f9d62df45634400a45b526fc5a8652eaa9d4ef594270df20f7998a79f1`。原MAT文件SHA-256：

```text
OFF 17dfec07b1b7d327e24e9ab0d1d559535104c3be91b3caf47c89cd633113e22d
ON  162e389a23f0b7197f72dfc455c194d04faed142fc7736e4381308a8384291c7
```

它们分别含29,599 / 21,411变量、200,205 / 144,966不等式、0等式、2,127,851 / 1,469,953非零数，原整数索引1,681 / 1,125项，已核对MATLAB一基索引、范围、去重及维度。七数组c/A/b/Aeq/beq/lb/ub在求解前后指纹完全相同，源MAT哈希不变；bounds按原lb/ub完整传入。没有重构模型、固定额外变量、传入x0、目标平移、手动缩放、舍入或删约束。原矩阵最小非零系数约1.2499e−8，高于HiGHS默认small_matrix_value=1e−9，没有因这一阈值而被主动预删的小系数；这不保证浮点内部算法保持精确算术。

LP计划在调用前冻结，SHA-256为 `a5e9e5624ad77713b541ac00bc97e36b40bb7729a4e48fa696174c20399240dd`。方法 `scipy.optimize.linprog(method='highs-ds')`，HiGHS1.8.0（原生日志git hash222cce7），关闭presolve、steepest-devex、原/对偶可行容差均1e−9，100,000次迭代上限；每侧300秒方法预算含科学库导入、加载、校验及数值后处理，预留2秒收尾，原生时限分别297.250114 / 297.510964秒，外部330秒watchdog。迭代和时间是两种独立停止条件。OMP/OpenBLAS/MKL环境值为1，HiGHS默认threads=0、parallel=choose不变；实际日志两侧都报告serial dual simplex，不把环境变量直接当严格线程数证明。两个LP在auto-L静态计算结束后按OFF→ON顺序、独立进程各运行一次，无额外试解或重试。

|旧hold-last LP诊断|OFF|ON|
|---|---:|---:|
|SciPy status|1|1|
|终止原因|迭代上限|迭代上限|
|迭代数|100,000|100,000|
|原生调用耗时|152.253362秒|107.615925秒|
|方法总耗时|153.158717秒|108.141228秒|
|返回向量|无|无|
|返回目标|无|无|
|原矩阵返回点残差|无可核查向量|无可核查向量|
|七数组及源文件保持|是|是|
|外部watchdog触发|否|否|

两侧信息均为 `Iteration limit reached (HiGHS Status 14)`，其中primal_status=Infeasible描述停止时内部当前点，SciPy总status不是2。本轮不能将其解释为原LP无可行解，更不能推到MILP不可行。原生日志的迭代目标和内部scaled infeasibility指标不替代最终返回向量、原数组残差或认证下界。本轮objective/residuals写null，CSV空白表示未返回，绝不是0。接口没有交出向量，因而无法完成计划中的返回点primal/dual残差审核；这一未完成项明确保留。

两侧在300秒前因额外100,000迭代上限提前结束，尚未耗尽时间预算。这个预先冻结的额外停止条件限制了诊断信息，不能因此断言“300秒也无法收敛”，也不能将107.6对152.3秒称为达到相同最优质量的加速。没有根据中间目标或旧SAFE上界反推下界；没有返回LP最优值可与旧MATLAB回调相比较。独立LP接口的算法、版本、数值实现与R2023b不同，也没有直接观测其内部根LP过程或x0接纳。方法与状态语义参见 [SciPy1.17 highs-ds官方文档](https://docs.scipy.org/doc/scipy-1.17.0/reference/optimize.linprog-highs-ds.html)。

下一步判断：前置传播已经获得明确的静态规模收益，值得保留为可开关、可追溯的约简步骤；其安全范围继续由证明条件和有限验证共同说明。完整auto-L R1尚未求解，本次旧hold-last LP又没有最优目标或可审核返回点，现阶段不足以直接开展完整MILP来声称收益。应先单独修订LP停止口径：在另一个冻结方案中让时间/收敛成为主要终止条件，避免本轮额外迭代上限先截断，再评估是否需要更多无损缩减。那将是新的诊断调用，不能在本轮追加或把旧余额自动续用。若继续研究约简，应以实际剩余事件/联合块及松弛证据为依据，不通过改任务、物理参数或转Benders制造规模优势。本轮没有执行这些下一步建议。

实际时间（用户时区UTC+8）：

|活动|开始|结束|性质|
|---|---|---|---|
|有限目录枚举|2026-11-11 10:49:04.863912|10:49:05.063800|约0.200秒，无热/构模/求解|
|auto-L OFF进程|10:49:35.094836|10:49:45.304053|10.209秒，构模导出完成，归档退出1|
|auto-L ON方法执行至归档|10:51:40.539754|10:51:48.579944|方法7.749秒，另归档约0.291秒|
|旧hold-last OFF LP方法|10:52:32.601496|10:55:05.760138|153.159秒|
|旧hold-last ON LP方法|10:55:05.988940|10:56:54.130143|108.141秒|

LP精确外层进程argv/cwd、起止、退出码在各worker_return.json，原生完整迭代日志在stdout.log；控制记录在controller.stdout.log/stderr.log。静态失败日志与范围修订全部保留，详见子报告。根目录完成与完整性记录另见 `completion_record.json`，报告整理时间不算求解耗时。

主要实际执行命令（工作目录 `/workspace/paper`）：

```bash
python3 research/chapter3_support_autol_lp_20261111/domain_validation/run_finite_catalogue_checks.py
python3 -B research/chapter3_support_autol_lp_20261111/autol_build/freeze_and_launch.py freeze
python3 -B research/chapter3_support_autol_lp_20261111/autol_build/freeze_and_launch.py launch
python3 -B research/chapter3_support_autol_lp_20261111/autol_build/rev02/freeze_and_launch.py freeze
python3 -B research/chapter3_support_autol_lp_20261111/autol_build/rev02/run_static.py --variant on --plan-sha256 1d46656a5dccee571dd82acd44e865d1de9b600da94912f13029fd2c740de599
python3 research/chapter3_support_autol_lp_20261111/lp_diagnostic/preflight.py
python3 research/chapter3_support_autol_lp_20261111/lp_diagnostic/run_lp_pair.py freeze
python3 -u research/chapter3_support_autol_lp_20261111/lp_diagnostic/run_lp_pair.py run
python3 research/chapter3_support_autol_lp_20261111/lp_diagnostic/summarize_lp.py
```

LP freeze与run的标准输出/错误按实际重定向分别归档至freeze.stdout.log、freeze.stderr.log、controller.stdout.log、controller.stderr.log。四项LP预检仅检查源码接线、原文件及数组/界、系数阈值和指纹敏感性，没有额外LP调用。所有原始目录保持原样，本轮新增完整矩阵/传播证明/日志与输出均在本目录，不自动提交或推送。
