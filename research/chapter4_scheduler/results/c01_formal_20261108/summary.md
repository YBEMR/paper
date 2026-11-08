# C01 七次正式方法比较

记录生成：2026-11-08T08:49:49.306070+00:00。本轮读取真实七次调用及七次复评结果，不加入新搜索或热积分。

固定 C01 C1/C2 上，ON 最终能耗为 0.839132424261 J，较本轮增强 HEFT 降低 4.958669%；相对原 SA 五种子中位降低 8.165123%。七次均保有完整 SAFE 解并通过同评价器新进程复评，未重试或替换种子。仅为已见 C01 的固定预算观察。

## 每次结果

|方法/种子|最终能耗上界 J|方法根秒|进程秒|post 根秒|实际评价/完整 SAFE/缓存|停止|
|---|---:|---:|---:|---:|---|---|
|HEFT|0.882913165881|21.151|21.550|0.620|44/44/0|SEARCH_COMPLETED|
|SA101|0.972948766276|300.005|304.659|1.031|547/546/86|BUDGET_EXHAUSTED|
|ON|0.839132424261|22.014|22.423|0.588|47/47/0|SEARCH_COMPLETED|
|SA102|0.904969407525|300.005|304.311|0.955|570/569/113|BUDGET_EXHAUSTED|
|SA103|0.914628079901|300.015|304.507|1.063|556/555/116|BUDGET_EXHAUSTED|
|SA104|0.913740455829|300.008|304.304|1.079|575/574/110|BUDGET_EXHAUSTED|
|SA105|0.862143883771|300.006|304.193|0.956|569/568/90|BUDGET_EXHAUSTED|

SA 成功安全解条件中位数 0.913740455829 J，范围 0.862143883771–0.972948766276 J，完整安全解及复评成功率 5/5。五次合计预算1500秒，只报告逐种子及中位/范围，不以最好种子冒充一次300秒表现。

精确能量上下界、停止与原生搜索计数见 `metrics.json`、`metrics.csv`、各 `method/result.json` 和 `method_return.json`；表内上界仅为便于阅读的四舍五入。安全成功率不代表优化胜率或最优性。

## 达到质量的时间

|方法/种子|首份完整 SAFE 秒|首次严格优于首解秒|首次自身最终质量秒|达到本轮 HEFT 上界秒|达到本轮 ON 上界秒|
|---|---:|---:|---:|---:|---:|
|HEFT|0.532|7.265|21.142|21.142|未达|
|SA101|0.577|1.091|294.073|未达|未达|
|ON|0.509|7.085|20.715|19.940|20.715|
|SA102|0.516|0.963|286.507|未达|未达|
|SA103|0.544|1.018|120.004|未达|未达|
|SA104|0.598|1.065|275.468|未达|未达|
|SA105|0.599|1.886|83.124|81.004|未达|

SA 达到 ON 阈值的种子：[]；达到 HEFT 阈值的种子：[105]；比 HEFT 自身更早达到 HEFT 最终质量的 SA 种子：[]。阈值在结果后统一从本轮 HEFT/ON 上界抽取，仅用于只读分析，不作为搜索停止或参数选择条件。

## 计时、评价与比较边界

每次真实方法根均为300秒，从worker入口单调时钟开始，包含选定科学模块导入、冻结身份验证、候选无关输入读取、原生初始化、全部内部结构操作和完整连续电热评价；根不重置。解释器与标准启动导入以及最终序列化另记进程墙钟，因此进程时间可略大于300秒。采用原有协作式截止，末尾未决凭证保留；只能接受300秒前形成的完整SAFE。自然完成的方法保留实际耗时，不补齐预算、不共享余量。

post 每次独立最多60秒，含自己的身份核验、结果读取和完整评价；不进入方法排名时间。评价器与方法内相同，属于复评，不能称独立实现验证。物理尝试/返回/完整SAFE/热违例/未决/缓存分列；SA原生含缓存评估数不混作实际热积分次数。

HEFT 与 ON 各自现场完成相同增强HEFT初始化，核对初解哈希与初始化候选序列一致；未共享对象、缓存或已有答案。原SA使用自己的原生构造/初始化、映射与频档/顺序邻域及上坡接纳。三方法共同输入、合法域、评价、总cap一致，原生初始化与停止策略允许不同；这不是统一初始搜索状态或只改变单个邻域的消融。

方法内实际评价合计 2908，返回 2908，完整SAFE 2903，返回未决 5，缓存 515；另七次完整SAFE复评。完整统计见 `audit.json`。

## 输入、实现与冻结证据

仓库基线 `183701e3394454ad588f538085bc06f08e7621a3`，分支 `chapter4/r2-r5-validation-20261107`。本轮新增 `c01/formal.py` 及两个针对性测试入口，直接调用原300秒主对照分派，不使用短根HEFT包装层。原算法、物理模型、评价器和历史输入不改。冻结计划 `0153d10c54326731f8066fe09d8d7088ef9c5a516668ee2a97681fe1a9371bb4`，形成于 2026-11-08T08:22:26.230636+00:00，早于批次。

输入来自 `research/chapter3_method_entry_preparation/results/frozen_entry02/common_input.json`，原文件SHA `07e458f3f811746f78931a340d258e230a8de4afb62ac0140459feff6a7bf80a`，实例 `precheck_C01_s1_2`，canonical实例/config哈希 `b292ced36fec69f4aa97c39edce6df7df58a27b9cec85135ad77a7e0cf4b8f48` / `15ca987441165a0e994ddbe073874ef23c76ee6ec26d4eecfa41b436ca0c6c83`。保留C1/C2、实际230ms窗口、显式DAG、8共享Stage/12次执行、72合法模式、5ms开始格点与精确持续时间、原期限、50°C入口/80°C温限、原四节点平台及auto-L。config默认400ms保留但不覆盖实际230ms。未读取历史参考调度用于初始化。

`execution/source_snapshot/` 保存所有非results冻结源副本，另保存 `frozen_common_input.json`、`frozen_config.json`、`frozen_instance.json`；524项源码/配置/检查身份和1117项旧文件保护在批次前后匹配。

## 实际运行与可追溯文件

任务首条时间记录为 `session_start.json` 的2026-11-08 08:12:04 UTC；正式批次 2026-11-08T08:22:37.232554+00:00 至 2026-11-08T08:48:52.933237+00:00，实际 1575.700758 秒。方法及post各自实际起止/命令见 `execution/calls/<slot>/worker_command_*.json`、`post_command_*.json`，日志见同目录 `*_stdout.log`、`*_stderr.log`、`*_evaluation_journal.jsonl`。无漏跑、无补跑，按HEFT、SA101、ON、SA102–105预定顺序串行。

环境：Linux-6.18.57-x86_64-with-glibc2.41，Python 3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]，numpy 2.3.5 / scipy 1.17.0，5 CPU；OMP/OpenBLAS/MKL/NUMEXPR固定单线程。资源预检通过。无MATLAB/Octave，未安装软件、调用MILP或改变环境。

主要命令（cwd `/workspace/paper`，完整精确argv/起止/耗时见 `command_01`–`command_12` 的started/return JSON）：

```text
python -B -m research.chapter4_scheduler.c01.formal_precheck --out <R>/unit_run02
python -B -m research.chapter4_scheduler.c01.lifecycle_precheck --out <R>/lifecycle_regression
python -B -m research.chapter4_scheduler.c01.precheck --out <R>/c01_regression
python -B -m research.chapter4_scheduler.blocking.run_precheck --out <R>/graph_regression
python -B -m research.chapter4_scheduler.comparison.precheck --out <R>/comparison_regression
python -B -m research.chapter4_scheduler.validation.sa_precheck --out <R>/SA_regression
python -B -m research.chapter4_scheduler.c01.formal prepare --out <R>/execution --checks <R>/unit_run02/checks.json
python -B -m research.chapter4_scheduler.c01.formal batch --out <R>/execution
python -B -m research.chapter4_scheduler.c01.formal summarize --out <R>/execution
python -B <R>/analyze.py
python -B <R>/extract_metrics.py
```

`R=research/chapter4_scheduler/results/c01_formal_20261108`；均经 `command_runner.py command_NN ...` 记录，非新运行指令。首轮10项及快照补全后的最终10项检查均保存，不把重复运行加算成20项覆盖。最终新增10＋回归15/17/109/20/21，共192项人工/模拟检查通过，性质不等同真实算法性能。

结束后 20630 条只读断言通过：重算调度合法性、核对SAFE闸门/两场景230ms覆盖、候选/输入身份、预算内凭证、SA五种子参数与最佳安全档案、初解独立一致、post能量相交、统一评价计数与完整冻结副本；强制禁止新优化/积分调用，实际为0。核查复用原SAFE检查逻辑，不是独立数值实现。

## 结论限制与下一步

C01此前已用于接线与短冒烟，因此不称盲测、独立新任务族或普遍性验证。本轮没有OFF组，ON相对HEFT的收益不能单独归于阻塞边；也没有全局最优证明或真实芯片测量。七组最终各场景峰温上界最高 54.683230°C，原温限80°C；这不展示紧热边界收益或热约束主导收益。各场景能量分项与峰温区间保存在 `metrics.json`。

本轮七次范围完成即停止，不扩例、调参或自动追加消融，不提交/推送/合并。下一步建议把R2/R5与本C01证据合并整理为第四章算法与有界对照叙述，保留不同任务结构、原生初始化、预算和因果归属限制。
