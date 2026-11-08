# 第四章 R2/R5 主对照：增强 HEFT、ON 与原 SA 五种子

本轮新执行器完成全部 **14 次方法＋14 次复评**。两例中 ON 的最终能量均低于增强 HEFT，也低于每个 SA 种子的最终安全能量；本轮 SA 的完整安全解复评成功率均为 5/5。较早达到中等质量的速度并非全面占优：R2 有四个 SA 种子比 HEFT 更早达到 HEFT 的最终能量水平。所有结果都保留，不以最佳 SA 种子代替中位表现。

这是两个已经用于分析的同族实例上的有界比较，不是未见实例泛化验证、普遍优越性、新颖性、统计显著加速或最优性证明。原模型与物理参数没有修改，未开展 C01、MILP 或其他扩展。没有推送、合并或修改主分支。

## 冻结与实际执行

- 工作目录 `/workspace/paper`；工作分支 `chapter4/r2-r5-validation-20261107`；基线提交 `183701e3394454ad588f538085bc06f08e7621a3`。新增执行器在工作区实现，按哈希与源码快照冻结，未冒称已提交。
- [新计划](execution/plan.json) SHA-256：`a1cc8e22b5f27be319e03dec7f21ea97efacd48e917933f2d768db39d159aa99`。冻结 494 项源码/配置/预检身份及 2021 个原归档文件，均通过末尾校验。旧提案仍保持未授权、不可执行状态，未直接沿用旧版本绑定。
- R2、R5 的输入、原始配置和有效配置哈希与既有 R2/R5 相同；方法内重新独立展开输入并计费，不读历史候选，不跨调用共享缓存或安全初解。冻结输入副本见 `execution/frozen_inputs/`。
- 实际批次起止（UTC）：**2026-11-08T03:24:25.135959+00:00 — 2026-11-08T04:16:44.832579+00:00**；批次内部墙钟 **3139.696660 秒**。外部命令墙钟 **3140.213893 秒**。
- 顺序：R2 HEFT、SA101、ON、SA102、SA103、SA104、SA105；R5 SA105、SA104、SA103、SA102、ON、SA101、HEFT。每项只执行一次，无退款、替换或重试。
- 每次方法根上限 300 秒，初始化、候选生成、合法性、内部电热评价和记录开销均在同一绝对截止内；完整 SAFE 的形成时间必须严格早于截止。复评另用新进程及最多 60 秒根。解释器和标准启动模块导入统一排除，选定科学导入在根内；序列化/汇总在停止后进行，不产生新搜索证据。
- 原算法自然停止后即结束，不为凑足 300 秒空转；SA 沿原算法耗尽预算。协作检查点不是硬实时终止。实际根和整个进程时间均保存，不能用“300 秒上限”替代实际成本。

## 最终能量与安全成功率

表中能量是完整电热能量区间上界的显示值，单位 J；完整精确上下界保存在各次 `method/result.json`、[summary.json](execution/summary.json) 与 [audit.json](audit.json)。显示舍入不代表区间宽度为零。SA 中位数和范围均按五个成功安全结果的上界计算；成功定义为正常停止前有完整 SAFE 档案且新复评通过，不表示证明最优或搜索覆盖完成。

| 实例 | 增强 HEFT | ON | SA 中位数 | SA 范围 | SA 安全解复评成功率 | ON 较 HEFT 节能 | ON 较 SA 中位数节能 |
|---|---:|---:|---:|---:|---:|---:|---:|
| base__R2 | 0.955459934953 | 0.859309627158 | 0.878889761803 | 0.867823438030—0.887495909207 | 5/5 | 10.063249% | 2.227826% |
| base__R5 | 0.917706681081 | 0.856824091351 | 0.883404202299 | 0.866983953215—0.887084529167 | 5/5 | 6.634210% | 3.008828% |

本轮 ON 上界也严格小于各 SA 结果的下界，排序不依赖显示舍入或区间重叠。SA 五种子的总额度是每例 5×300 秒，不能将其中最好结果当成与一次 ON 同成本的单次表现。

## 全部运行与评价成本

所有表行均有完整 SAFE 复评。HEFT/ON 为原算法自然完成；十次 SA 均明确保留 `BUDGET_EXHAUSTED` 状态，仍有截止前形成的完整安全档案。技术失败、数值停止、外部进程超时、无安全解和复评失败本轮均为 0；不是把这些失败类别从分母中移除。

| 实例 | 方法/种子 | 最终上界 J | 方法根 s | 方法进程 s | 首次形成自身最终质量 s | 评价尝试 | 返回凭证 | 完整 SAFE | 缓存命中 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base__R2 | HEFT | 0.955459934953 | 18.104931 | 18.400014 | 18.095 | 36 | 36 | 36 | 0 |
| base__R2 | SA101 | 0.884310254946 | 300.005303 | 302.958784 | 236.261 | 447 | 447 | 446 | 76 |
| base__R2 | ON | 0.859309627158 | 20.723986 | 21.021378 | 20.712 | 38 | 38 | 38 | 0 |
| base__R2 | SA102 | 0.878889761803 | 300.017478 | 303.288645 | 238.298 | 489 | 489 | 488 | 85 |
| base__R2 | SA103 | 0.887495909207 | 300.004672 | 303.703207 | 63.285 | 493 | 493 | 492 | 120 |
| base__R2 | SA104 | 0.868894037511 | 300.006009 | 303.731479 | 269.834 | 510 | 510 | 509 | 109 |
| base__R2 | SA105 | 0.867823438030 | 300.004888 | 303.664772 | 210.731 | 526 | 526 | 525 | 103 |
| base__R5 | SA105 | 0.887084529167 | 300.004521 | 303.940908 | 299.575 | 520 | 520 | 519 | 108 |
| base__R5 | SA104 | 0.880829239632 | 300.005248 | 303.670889 | 67.152 | 558 | 558 | 557 | 104 |
| base__R5 | SA103 | 0.883431277619 | 300.010555 | 303.935965 | 288.120 | 550 | 550 | 549 | 113 |
| base__R5 | SA102 | 0.883404202299 | 300.008478 | 303.778099 | 102.082 | 540 | 540 | 539 | 106 |
| base__R5 | ON | 0.856824091351 | 23.151049 | 23.552884 | 23.136 | 44 | 44 | 44 | 0 |
| base__R5 | SA101 | 0.866983953215 | 300.006006 | 304.594403 | 250.856 | 510 | 510 | 509 | 104 |
| base__R5 | HEFT | 0.917706681081 | 21.196623 | 21.496726 | 21.188 | 42 | 42 | 42 | 0 |

方法内合计 **5303 次实际评价尝试 / 5303 份返回凭证 / 5293 份完整 SAFE / 10 份预算耗尽未决凭证 / 1028 次缓存命中**。本轮没有直接抛异常而未返回的评价尝试，也没有热违规回执。另有 14 次复评，均为完整 SAFE；它们不混入方法内评价数。

14 次方法根实际合计 3083.249745 秒，复评根合计 13.352342 秒。最大方法检查点超出约 17.478 ms；所有接纳 SAFE 的形成时间仍严格小于 300 秒。SA 方法进程约 303–305 秒，额外部分主要是停止后的大体量记录与序列化；这些进程时间已分列，未当作额外搜索时间。

**统一口径：** `evaluation_attempts` 在实际评价函数边界递增，包含直接异常；`returned_receipts` 只计实际调用返回，包含不完整/未决凭证；`validated_SAFE_receipts` 只计共同完整校验通过、及时形成、非缓存的 SAFE。`cache_hits` 单列。原 SA 内部 `safe_receipts` 会包含缓存返回，不能与本表的物理评价次数混用。旧历史 `full_evaluator_calls` 多按已返回行统计，本轮不将该旧字段拼接成统一成本。每次调用的 JSONL 同时保存实际评价开始、完整候选哈希与候选、返回或异常边界。

## 质量随时间与速度边界

阈值在计划中预先定义：首次完整 SAFE、相对首次 SAFE 的严格区间改善、首次形成自身最终上界，以及达到本批同例 HEFT/ON 最终上界。后两种参照只作事后只读统计，不曾输入搜索。达到参照上界表示已验证候选上界不高于参照上界；不将它混称为严格区间优势。未达到保留为空，不记为 300 秒已经达到。

| 实例 | HEFT 自身最终质量形成 s | ON 自身最终质量形成 s | SA 达到 HEFT 上界：中位 s（范围） | SA 达到 ON 上界 | SA 自身最终质量形成：中位 s |
|---|---:|---:|---:|---:|---:|
| base__R2 | 18.095 | 20.712 | 14.836（11.668—26.132），5/5 达到 | 0/5 | 236.261 |
| base__R5 | 21.188 | 23.136 | 55.788（27.879—177.957），5/5 达到 | 0/5 | 250.856 |

**反向证据保留：** R2 的 SA101/102/103/104 分别约 17.476/14.836/11.668/13.940 秒达到 HEFT 最终上界，早于 HEFT 自身约 18.095 秒；ON 达到该中等阈值约 19.304 秒。因此不能把 ON 的最终能量优势解释为任意早停时刻或质量阈值上的全面优势。R5 的 SA 达到 HEFT 阈值耗时则全部更长。本轮同硬件的一次运行只支持这些现场观察，不给出稳定速度比或跨实例胜率。

SA 完整评价相位（含共同计数边界）在 R2/R5 的中位耗时分别约 290.230 / 289.941 秒，占其 300 秒根的大部分。该相位不是纯热积分微基准；其中也包含共同边界记录，不能将全部时间归因于数值核。

## 初始化、原算法与设备迁移接口

- HEFT 与 ON 各自现场执行完整增强 HEFT 初始化，按各自根计费。两例的冻结初解哈希、能量区间和初始化候选序列逐项相同，见 `audit.initialization_comparison`。这不意味着在运行时复用了答案。
- 原 SA 保留自己的 HEFT 构造/备用/随机初始化、四类动作、共享部署、概率上坡接纳、降温和最佳 SAFE 上界档案。SA 不是完整增强 HEFT 热启动版本；本轮不强迫三方法共享初解，否则会改写 SA 基线。SA 原生初始化本次均由 HEFT 构造得到 SAFE；首次 SAFE 形成约 0.499–0.604 秒，首次邻居评价约 0.510–0.617 秒，两者均不是精确的初始化结束时刻。
- 原 SA、HEFT、解码器、ON 搜索规则及电热评价器源码均未改动。新增比较层只做同一评价边界的转发、收费、记录、停止归一化和汇总；其额外开销计入各方法根，未声称记录零开销。
- 真实运行共记录 **1086 次设备迁移候选实际评价**，其中 **1042 次完整 SAFE 的部署不同于初始部署**。完整合法性检查仍要求共享部署在全部场景一致、设备/频档合法。本轮补足了此前 5 秒冒烟未覆盖真实 mapping 动作的证据，但这些计数不等于逐次 SA 当前态接纳数。

## 复评计时修正与安全语义

新执行器在全部方法和复评结果中统一设置真实 `timing.clock_origin`，科学导入、源身份检查、输入读取均在各自原绝对根内；复评新增 `complete_post_evaluation` 独立相位。此前短冒烟 `post_return.json` 中通用的 imports-excluded 标签不再用于本批；历史原始文件保持原字节，没有重写计时数据。

每次正常安全结果使用新进程、新 60 秒根调用同一个原连续电热评价器，检查全部场景/节点/原窗口的完整 SAFE、候选与输入身份、能量区间相交以及输入/结果未被修改。它检验保存候选的复现与完整性，**不是独立数值实现或实测校准**。数值未决、技术错误、身份漂移、复评失败会保留结果并停止后续槽；本轮未触发这些停止。热违规不添加惩罚能耗，未决/无安全解不作为不可行证明。

## 检查、环境与证据位置

新增最终 **20 项**守卫测试通过，覆盖三方法真实绑定身份路径（人工算法与凭证）、统一边界计数、合法 SA 迁移、缓存、直接异常、错误 SAFE、停止归一化、质量时间、条件中位数、14 槽独占消费、方法/复评故障与超时停止及修正后的复评计时。另有旧 109 项阻塞回归、21 项 SA 适配回归、12 项旧验证入口检查通过，共 162 项最终测试。这些不是 162 个研究算例。

中间第二轮新增到 20 项时，一个三方法 worker 测试的三项子用例失败；测试夹具将预算类替换成工厂 Mock，破坏了原生命周期的类身份检查。随后改用保留类身份的人工预算子类，最终同一生产源码通过 20 项测试。失败日志 `unit_run02/test_output.txt` 原样保留，最终结果为 `unit_run03/`；各轮均无真实算法/热积分。第一轮 19 项通过记录也保留。

只读审计 **30794 项断言通过**，审计主体用时 31.467668 秒：复核所有评价边界与候选哈希、完整 SAFE 与形成时间、合法部署、最佳档案、初始化独立一致性、全部统计和复评区间。它调用原凭证与调度检查代码，不重新热积分、不运行新搜索、不构成第二个独立电热实现。

环境：Linux-6.18.57-x86_64-with-glibc2.41；Python 3.12.14；NumPy 2.3.5；SciPy 1.17.0；5 CPU。线程环境对所有方法/复评均固定 OMP/OPENBLAS/MKL/NUMEXPR 为 1。启动前可用内存约 16.64 GiB、空闲磁盘约 29.23 GiB，满足预先资源门。MATLAB/Octave 不可用，本任务不依赖它们，未安装软件。完整环境 ID 与解释器路径见计划。

完整根目录：`/workspace/paper/research/chapter4_scheduler/results/main_comparison_20261108/`。

- [逐组指标 CSV](metrics.csv)、[精确汇总 JSON](execution/summary.json)、[完整只读审计](audit.json)。
- 每组原始结果及输入：`execution/calls/<槽ID>/method/{result,input_instance,input_config}.json`；原始配置另在该组 `input_raw_config.json`。
- 评价边界与完整候选：各组 `method_evaluation_journal.jsonl`；复评凭证为 `post_receipt.json`。
- 统一方法/复评结果：各组 `method_return.json`、`post_return.json`；完整命令/起止/环境/进程墙钟：`worker_command_started.json`、`worker_command_return.json`、`post_command_started.json`、`post_command_return.json`。标准输出和错误分别为同组 `worker_stdout.log`、`worker_stderr.log`、`post_stdout.log`、`post_stderr.log`。
- 批次开始/结束、消费清单及无重试状态：`execution/batch_started.json`、`execution/batch_return.json`；源码快照：`execution/source_snapshot/`。

实际主要命令如下，均在 `/workspace/paper` 执行；完整起止与日志为根目录 `command_NN_{started,return}.json`、`command_NN_stdout.log`、`command_NN_stderr.log`。前十条命令记录如下，报告生成及最终清单另见完成记录。

| 命令记录 | 实际命令 argv | 命令墙钟 s | 退出码 |
|---|---|---:|---:|
| command_01_return | `python -B -m research.chapter4_scheduler.comparison.precheck --out research/chapter4_scheduler/results/main_comparison_20261108/unit_run01` | 0.487903 | 0 |
| command_02_return | `python -B -m research.chapter4_scheduler.blocking.run_precheck --out research/chapter4_scheduler/results/main_comparison_20261108/regression` | 2.848770 | 0 |
| command_03_return | `python -B -m research.chapter4_scheduler.validation.sa_precheck --out research/chapter4_scheduler/results/main_comparison_20261108/sa_regression` | 0.612354 | 0 |
| command_04_return | `python -B -m research.chapter4_scheduler.validation.precheck --out research/chapter4_scheduler/results/main_comparison_20261108/legacy_validation` | 0.259038 | 0 |
| command_05_return | `python -B -m research.chapter4_scheduler.comparison.precheck --out research/chapter4_scheduler/results/main_comparison_20261108/unit_run02` | 0.474154 | 1 |
| command_06_return | `python -B -m research.chapter4_scheduler.comparison.precheck --out research/chapter4_scheduler/results/main_comparison_20261108/unit_run03` | 0.547005 | 0 |
| command_07_return | `python -B -m research.chapter4_scheduler.comparison.run prepare --out research/chapter4_scheduler/results/main_comparison_20261108/execution --checks research/chapter4_scheduler/results/main_comparison_20261108/unit_run03/checks.json` | 2.111667 | 0 |
| command_08_return | `python -B -m research.chapter4_scheduler.comparison.run batch --out research/chapter4_scheduler/results/main_comparison_20261108/execution` | 3140.213893 | 0 |
| command_09_return | `python -B -m research.chapter4_scheduler.comparison.run summarize --out research/chapter4_scheduler/results/main_comparison_20261108/execution` | 4.348586 | 0 |
| command_10_return | `python -B research/chapter4_scheduler/results/main_comparison_20261108/analyze.py` | 33.798431 | 0 |

## 可以支持与尚不能支持的结论

本轮支持：在原 R2/R5、原完整电热评价和本次冻结实现下，ON 用 38/44 次评价得到比增强 HEFT及五个原 SA 种子更低的完整安全能量；原 SA 的合法设备变化和上坡当前态语义得以保留；新比较层的时间/计数/失败口径可追溯。R2 的中等质量到达时间反例同时保留。

本轮不支持：所有任务、紧热约束或未见实例上均占优；增强 HEFT 的迁移/调档/重排本身是新贡献；算法全局最优；同一评价器复评即独立物理正确性验证；单次 HEFT/ON 运行形成稳定加速估计。未增加实例或依据结果调整参数，原六组记录与旧提案保留。下一步应据实整理第四章算法和实验叙述，不自动扩展研究批次。
