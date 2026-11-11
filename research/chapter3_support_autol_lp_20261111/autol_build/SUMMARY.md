# auto-L 完整 R1 的前置支持传播静态核查

完整模型及矩阵均已形成。传播后选项1681→1125，变量27971→19857，约束176953→124338，非零数1983981→1311146。两侧保留 AB/AC 各6次Stage执行、66个合法模式、400ms窗口及完整电热行；没有初始化、候选热评价、LP/MILP求解。当前记录只支持静态规模结论与一次构模观察，不能证明调度改善或统计加速。

科学输入取自 `research/chapter3_experiments/results/whole_long_budget01/method/{input_config,input_instance}.json`，沿用已有完整R1 auto-L输入，而非后来的六次总执行收束实例。当前冻结 `inputs.build_instance(config,'base__R1')` 生成对象与旧归档实例完全相同。与11月10日hold-last基线逐键核对，配置和实例只有 execution_rules 不同，明确采用 `auto_low_immediate_v1`、空域立即回L、零额外开销；平台参数、任务、模式、β1.3、50°C初温、80°C温限、5ms启动及非整数结束时间全部保留。这是两套控制语义的区分，不将旧hold-last LP当作本次auto-L的性能配对。

身份：

- auto-L input_config字节SHA256：`132323b4b18dd514b9baa929543d235ff91bb07026a60e7b629e1adb6aaaa5e2`。
- auto-L input_instance字节SHA256：`01eacb2a653d56419c32f38740021a787ea01ac9e7ade407bef2edd81ec6ef89`；规范化实例SHA256：`989697215b8609cb855b17234ed5d5532d8155c7b382a743de618cfcc8901e27`。
- milp.py：`f34809ad6d8e15d4639af8cdcfb62b3ebb4603772e513289280ccdefa783fefb`。
- option_support.py：`fe33351662dcdc7f50136c3601af022bd831ce8a41ae6e92810b46b09f5efbf8`。
- test_option_support.py：`59e62b15f8a325ddc69fdac291169cdfeccfd92a111e1a05551fd90461abd557`。

归档范围为当前实验目录根级py/m/json文件及interval内核，共216项；该计数范围与以前含额外诊断入口的217项冻结不同。两次入口修订间，这216项科学源码哈希和2项输入哈希完全相同，结束时原目录216文件逐项未变。执行从 frozen/ 树导入，不从历史矩阵或候选初始化。

初始计划SHA256：`f21a55691a7446e60428c570356f75e6317099fa1b4c20c7e50ac1ba9c8a2fab`，声明OFF→ON各300秒方法预算，批800秒/进程380秒外部保护。首次OFF已完成构模、导出和矩阵归档，但结果JSON归档时 `platform.platform()` 尝试调用uname子进程，被广义禁止子进程的防求解守卫拒绝，进程退出1；ON因而未启动。原失败stderr、progress、NPZ、options及变量名全部保留，没有重跑OFF。故OFF的“归档失败”必须与“模型构建成功”分别报告。

修订入口仅将平台元数据缓存到防启动守卫之前，并适配新目录的repo路径；没有改科学函数或输入。修订计划SHA256：`1d46656a5dccee571dd82acd44e865d1de9b600da94912f13029fd2c740de599`；原拟配对launcher未执行，实际范围由 `rev02/scope_amendment.json` 收窄为仅ON一次。ON使用同300秒方法时钟成功。该次直接exec未另外应用原计划380秒进程watchdog，实际只依赖300秒合作检查且7.75秒内完成；已在 `on_execution_receipt.json` 披露，不能声称另有被执行的硬实时保护。

|静态指标|OFF（已有工件恢复）|ON（新入口一次）|
|---|---:|---:|
|选项|1681|1125|
|变量|27971|19857|
|整数声明|1681|1125|
|约束行|176953|124338|
|实际导出矩阵非零数|1983981|1311146|
|AB事件 / 区间|287 / 286|216 / 215|
|AC事件 / 区间|296 / 295|210 / 209|
|AB联合状态块|6855|4861|
|AC联合状态块|7204|4937|
|联合块合计|14059|9798|
|系数集合|515|541|
|affine miss|5736|5348|
|option_expansion阶段，含期限过滤|0.041836496 s|0.047805601 s|
|支持传播函数内部计时|关闭|0.049769126 s|
|输入起计至构模完成的observer时标|8.203577931 s|7.254621063 s|
|完整model_construction独占时长|未归档，未知|7.254188751 s|
|矩阵导出独占时长|未归档，未知|0.494401980 s|
|方法总计时|未归档，未知|7.749387331 s|

OFF的规模与nnz从最后完整BuildObserver记录及已保存NPZ交叉核对；联合状态块由变量名中 `w:<scene>:<interval>:<state>` 的总数恢复。没有重新构模来填空缺计时。ON的完整运行结果在 `rev02/execution/on/result.json`，OFF恢复范围与原始文件哈希在 `off_recovered_static.json`。不把两个入口的工程差别和缺失OFF阶段计时隐藏成完整端到端速度对照。

ON共删除556项，后继支持246、前驱支持310、共享设备支持0；3轮包括最终固定点检查，空域0。每项删除证明与完整选项在 `rev02/execution/on/deletion_proof.json` / `options.json`。没有频档或起点跨场景强制相等，没有资源两两支持或Benders。保留其余成熟优化：fix_late_options、aggregate_opp_locks、relax_auxiliary_integrality、strengthen_energy_lower_bounds、prefilter_deadlines；cumulative_precedence和preeliminate_closed_anchors关闭。两侧科学开关仅propagate_support不同。

实际OFF子进程为2026-11-11 **10:49:35.094836–10:49:45.304053 UTC+8**（原记录02:49:35.094836–02:49:45.304053 UTC），进程10.209261秒，退出1。OFF方法时钟起点10:49:35.574628。ON方法执行为 **10:51:40.539754–10:51:48.579944 UTC+8**（02:51:40.539754–02:51:48.579944 UTC），包含末尾归档；方法总7.749387秒，已形成工件的归档另0.290907秒。新入口预先缓存平台信息在方法计时前，属于环境采集，不作为科学计算收益。

环境为 Linux6.18.57 x86_64/glibc2.41、Python3.12.14、NumPy2.3.5、SciPy1.17.0。前后科学构模顺序OFF→ON，两侧过程中未与主代理的LP任务并行；已通知其在静态计算结束后才启动LP。

主要实际命令：

```bash
python3 -B research/chapter3_support_autol_lp_20261111/autol_build/freeze_and_launch.py freeze
python3 -B research/chapter3_support_autol_lp_20261111/autol_build/freeze_and_launch.py launch
python3 -B research/chapter3_support_autol_lp_20261111/autol_build/rev02/freeze_and_launch.py freeze
python3 -B research/chapter3_support_autol_lp_20261111/autol_build/rev02/run_static.py --variant on --plan-sha256 1d46656a5dccee571dd82acd44e865d1de9b600da94912f13029fd2c740de599
```

另有只读Python片段核对原输入、恢复最后progress与NPZ计数/变量名前缀、检查216项原源码哈希并生成比较CSV。这些是已保存工件核对，没有新构模或求解。精确argv/cwd与进程时间见 `off_command.json` 和 `rev02/on_execution_receipt.json`；首次失败见 `off.stderr.log`；所有科学构模过程见各execution目录的build_progress.jsonl。汇总表 `static_comparison.csv`，完整性检查 `completion_checks.json`。

本子任务不包含独立小域枚举（由并行域验证子任务给出），也不对传播正确性作普遍经验性证明。本轮静态规模缩减值得继续研究，但是否改善完整MILP成本仍须结合独立LP诊断及后续另定完整方法实验判断。本子任务没有推送或改写历史。
