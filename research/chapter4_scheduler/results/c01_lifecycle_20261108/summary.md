# C01 完整生命周期接线与短预算端到端冒烟

本轮已把候选无关的 `load_c01` 接入完整增强 HEFT、ON 和原 SA 生命周期，完成固定三次真实路径运行及各一次复评。HEFT 自然完成原能量改进过程；ON 完成自己的 HEFT 初始化并进入真实图重构和评价；SA101 发生真实邻居搜索与上坡接纳，在 30 秒截止时保留最佳安全档案。三份最终候选均通过完整双场景、230 ms 的 SAFE 复评。

**本轮是工程接线与覆盖验证，不是正式 C01 对照。** 不计算方法胜率、统计中位数、正式节能比例或稳定加速比。只使用既有 C01 C1/C2 投影和一个 SA 种子，没有扩展任务族或重复运行。R2/R5 主对照与上轮 C01 组件记录全部保留，未提交、推送或合并，未修改主分支。

## 接线与原算法边界

- [输入加载桥](../../c01/input.py) 保持原字节：加载原候选无关共同合同，保留 `precheck_C01_s1_2` 身份、C1/C2 显式 DAG、8 个共享 Stage、全部 72 个设备/频档模式、5 ms 起点、230 ms 实际窗口、原期限/释放/物理平台/50–80°C/auto-L。配置旧默认 400 ms 没有覆盖实例窗口；不读旧参考解、构造候选或上轮冒烟结果作初解。
- 新增 [dispatch.py](../../c01/dispatch.py)：将加载桥接入 HEFT、ON、SA 各自原生初始化和完整记录路径，独立计费、独立输入与缓存。ON 直接调用原 `execute_reconstruction` 并传入同一个根的秒数，SA 直接调用原 `execute_sa`。
- 旧 `validation.lifecycle.execute_heft` 只接受 300 秒根。新增隔离的 [heft_lifecycle.py](../../c01/heft_lifecycle.py)，只把入口预算守卫、迟到 SAFE 判定和耗尽标记改为使用调用者的 `(0,300]` 根；原 `run_heft`、完整记录器、搜索、接纳及归档逻辑不变。没有修改旧入口来绕过历史冻结。具体差异见 [heft_budget_bridge.diff](heft_budget_bridge.diff)。
- 新增 [entry.py](../../c01/entry.py) 是独立 C01 工程执行层。输入留档是共同合同来源、文件/内容哈希与实际窗口，不伪造 P0 的 raw-config 三元组，也没有把 C01 塞进旧 R2/R5 十四槽计划。
- 复用原完整 SAFE 门及共同 `EvaluationJournal` / `normalize`，统一评价尝试、返回凭证、物理完整 SAFE、未决和缓存口径；原 SA 的动作、RNG、原生构造初始化、概率上坡当前态与最佳上界档案保留。

本轮不存在名义 300 秒、实则用其他时钟截断的预算转换。三方法真实 `seconds`、绝对 deadline 和统一结果上限都是 **30 秒**，选定科学导入、输入读取、原生初始化、候选生成和内部评价都在同一根内。只有新 C01 HEFT 包装层允许短根；其 300 秒行为与原包装层的完整结果、候选评价序列逐项一致，测试仅剔除了每次自然不同的调用 token。

## 预先冻结与范围

最早现场观察为 **2026-11-08 05:58:54 UTC**。`session_start.json` 在实际结果之前明确限定：HEFT、ON、SA101 各一次、各 30 秒，正常完整安全结果各最多一次 10 秒复评，整包 240 秒；不加时、不补跑、不换种子。若短根未覆盖某阶段就按未覆盖报告。

[独立计划](execution/plan.json) SHA-256：

```text
1073fb9bcad5909df51e84383fc86387227d02c0fb80d66d161aafcfbdb88ff0
```

该身份于 **2026-11-08 06:08:39.182031 UTC** 保存，早于真实启动。基线为 `183701e3394454ad588f538085bc06f08e7621a3`，工作分支 `chapter4/r2-r5-validation-20261107`；新增未提交代码按源码快照与哈希冻结，不冒称已提交版本。514 项源码/配置/预检身份与 956 项既有文件保护通过前后校验。

原共同输入文件 SHA-256 为 `07e458f3f811746f78931a340d258e230a8de4afb62ac0140459feff6a7bf80a`；instance 内容哈希为 `b292ced36fec69f4aa97c39edce6df7df58a27b9cec85135ad77a7e0cf4b8f48`，config 内容哈希为 `15ca987441165a0e994ddbe073874ef23c76ee6ec26d4eecfa41b436ca0c6c83`。三条路径都在自己的根内重新加载同一完整输入，不共享结果或免费初始化。

## 实际端到端结果与覆盖

批次真实起止：**2026-11-08 06:08:45.722168—06:10:08.816973 UTC**，内部墙钟 **83.094899 秒**。外部批次命令起止 06:08:44.482834—06:10:08.857232，墙钟 **84.373972 秒**，包含额外启动和外层校验。三方法与三复评各消费一次，全部正常返回，无技术/数值故障、无外部 watchdog 超时、无退款或重试。

| 路径 | 停止状态 | 方法根实际秒数 | 方法进程秒数 | 实际评价 / 返回 / 完整 SAFE | 缓存命中 | 复评根秒数 |
|---|---|---:|---:|---:|---:|---:|
| 增强 HEFT | SEARCH_COMPLETED | 21.504308 | 21.984057 | 44 / 44 / 44 | 0 | 0.839188 |
| ON | SEARCH_COMPLETED | 25.823081 | 26.403301 | 47 / 47 / 47 | 0 | 0.555891 |
| 原 SA101 | BUDGET_EXHAUSTED，有完整安全档案 | 30.011796 | 30.520327 | 56 / 56 / 55 | 5 | 0.574378 |

实际覆盖由原始相位、完整候选和元数据确认：

- **HEFT**：原 `run_heft` 完整完成，除初次构造评价外，有 43 次能量改进阶段的真实评价，完成 SAFE 初解冻结。
- **ON**：独立完成同样的 HEFT 初始化。初解哈希及初始化候选序列与单独 HEFT 相同，但在自己的根内重新运行。随后进入节能目标、构图与真实评价；记录 183 次构图试探、3 个图候选和 3 次图阶段完整评价。原严格接纳规则接受一次带附加资源边的候选，证明该分支实际触达；不能据工程样本把它升级为正式收益对照。
- **SA101**：原算法返回原生搜索元数据，发生 60 次邻居候选请求、70 次解码尝试，其中 10 次解码失败；59 次安全邻居试验、53 次邻居接纳，含 10 次上坡接纳。7 次真实设备映射候选通过完整 SAFE；共享部署和合法设备/频档仍由原校验器检查。未更改随机种子、动作或降温参数。

方法内合计 **147 次实际评价尝试、147 份返回凭证、146 份完整 SAFE、1 份截止未决凭证、5 次缓存命中**。没有直接异常但未返回凭证的实际评价，也没有热违规回执。SA 内部 `receipt_SAFE=60` 含 5 次缓存返回，不能将其当作 60 次真实物理 SAFE 评价。

所有被接纳 SAFE 的形成时间严格早于各自 30 秒截止；SA 约 11.796 ms 的检查点超出如实记录，没有接受截止后形成的目标值。三次复评另计，均为完整 SAFE，方法内计数不含复评。

诊断性最终安全能量上界分别为：HEFT **0.882913165881 J**、ON **0.839132424261 J**、SA101 **0.979512055770 J**。完整精确上下界和形成时间见各组 `method/result.json` 与 [engineering_summary.json](engineering_summary.json)。这些值只留作重放、身份与复评一致性检查；本轮不据三次短运行作方法排名、节能比例或泛化结论。

## 时间、停止与复评一致性

所有方法和复评均使用同一计时定义：解释器和标准启动模块导入统一在进程墙钟另列；选定科学导入、身份核查、输入和实际算法计入方法根。停止后只做既有证据归档和汇总，没有另开搜索或挪用复评预算。两种自然完成的方法没有为了凑满 30 秒空转。

统一结果中的 `evaluation_attempts` 在实际评价边界计数，异常也计；`returned_receipts` 包含未决；`validated_SAFE_receipts` 仅计及时形成且完整校验通过的非缓存 SAFE。缓存单列。方法正常耗尽预算可保留先前完整 SAFE；初始化未完成、无安全结果及已进入/未进入 ON/SA 分支分别记录，不将它们混称为全问题不可行或穷尽搜索完成。技术、数值、身份、复评错误会保存诊断并停止后续槽；本轮没有触发。

每次复评均是新进程、新 10 秒根，重新读取该方法自己的完整输入与最终候选，调用**同一原评价器**，核对完整 SAFE、候选/输入身份、区间相交和文件/实参不变。`clock_origin` 与 `complete_post_evaluation` 相位正确记录；它不是独立数值实现或实测校准。旧 C01 组件记录及其两份 SAFE 没有被当作本轮初解或复评。

## 测试与只读核查

新增 **15 项生命周期测试**一次通过，覆盖：

- 300 秒下与原 HEFT 包装层在完成、截止、技术失败和无 SAFE 情况下的完整结果/候选评价序列一致；短根及 deadline 一致性、耗尽标志、迟到 SAFE 拒绝、及时档案保留。
- 三条真实生命周期接口的原根/原参数传递；三条 worker＋post 路径使用人工算法和虚构完整凭证的端到端验证，返回统一计数与 C01 合同留档，不生成 P0 raw-config。
- 评价器直接异常尝试的计费与安全档案保留、后续路径锁停；固定工程计划拒绝换种子、300 秒额度或正式比较标记；逐槽独占消费、无 SAFE 跳过 post、方法/复评故障、外部超时部分日志及禁止重试。

回归 **17 项 C01 合同/菱形测试、109 项图与阻塞测试、20 项主比较入口测试、21 项 SA 适配测试**均通过，总计 **182 项最终测试**。它们是人工夹具/模拟检查，不是 182 个真实研究算例。原 SA 回归中保留的人工 RNG 差分重放也不计作实际 C01 搜索调用。

随后 [analyze.py](analyze.py) 完成 **955 项只读断言**，主体用时 **1.462706 秒**，核对全部候选与评价边界、完整 DAG/合法模式、全场景 230 ms 连续 SAFE 凭证、形成时间、三个绝对根、独立初始化、真实分支覆盖、全部计数及复评区间。没有新增优化或热积分，不构成第二个独立电热数值实现。详见 [audit.json](audit.json)。

## 环境与可追溯路径

所有命令工作目录均为 `/workspace/paper`。Linux 6.18.57 x86_64/glibc 2.41；Python 3.12.14；NumPy 2.3.5；SciPy 1.17.0；5 CPU。所有方法与复评进程统一设置 OMP/OPENBLAS/MKL/NUMEXPR 线程数为 1。启动时可用内存 17,775,722,496 B、空闲磁盘 30,724,472,832 B，资源门通过。MATLAB/Octave 不可用但本轮不依赖，未安装软件。环境 ID、解释器和逐进程环境见计划与命令记录。

证据根目录：`/workspace/paper/research/chapter4_scheduler/results/c01_lifecycle_20261108/`。下表 `O` 仅为该目录的简写，实际完整 argv、cwd、起止、退出码在 `command_NN_return.json`，输出/错误在 `command_NN_stdout.log`、`command_NN_stderr.log`。

| 记录 | 实际主要命令 | 命令墙钟秒数 |
|---|---|---:|
| command_01 | `python -B -m research.chapter4_scheduler.c01.lifecycle_precheck --out O/unit_run01` | 0.494751 |
| command_02 | `python -B -m research.chapter4_scheduler.c01.precheck --out O/c01_regression` | 0.305617 |
| command_03 | `python -B -m research.chapter4_scheduler.blocking.run_precheck --out O/graph_regression` | 2.559696 |
| command_04 | `python -B -m research.chapter4_scheduler.comparison.precheck --out O/comparison_regression` | 0.487884 |
| command_05 | `python -B -m research.chapter4_scheduler.validation.sa_precheck --out O/SA_regression` | 0.463447 |
| command_06 | `python -B -m research.chapter4_scheduler.c01.entry prepare --out O/execution --checks O/unit_run01/checks.json` | 0.955762 |
| command_07 | `python -B -m research.chapter4_scheduler.c01.entry batch --out O/execution` | 84.373972 |
| command_08 | `python -B O/analyze.py` | 1.655277 |

每个实际子进程命令按新计划调用：

```text
<实际Python解释器> -B -m research.chapter4_scheduler.c01.entry worker --out <O/execution> --slot <01_C01_HEFT|02_C01_ON|03_C01_SA101>
<实际Python解释器> -B -m research.chapter4_scheduler.c01.entry post --out <O/execution> --slot <对应槽ID>
```

实际解释器绝对路径和完整参数保存在各组 `{worker,post}_command_started.json` 与 `_command_return.json`；进程监督上限 45/20 秒是防卡死边界，不增加 30/10 秒证据预算。

关键文件：

- `execution/plan.json`、`plan_identity.json`、`input_identity.json`、`source_snapshot/`：冻结代码、输入、预算、种子和版本。
- `execution/batch_started.json`、`batch_return.json`：实际起止和一次消费清单。
- `execution/calls/<槽ID>/common_input_identity.json`：该次重新读取的原共同合同身份。
- 每组 `method/{result,input_config,input_instance}.json`：原完整生命周期结果和实际科学输入。
- 每组 `method_return.json`、`method_evaluation_journal.jsonl`：统一计数、覆盖、完整候选与评价边界。
- 每组 `post_receipt.json`、`post_return.json`、`post_evaluation_journal.jsonl`：新根完整复评。
- 每组 `{worker,post}_{stdout,stderr}.log`：子进程日志；`unit_run01/` 和各回归目录保存测试日志与源码版本。
- [engineering_summary.json](engineering_summary.json)、[audit.json](audit.json)、`completion_record.json`：只读汇总、核查和最终文件清单。

## 当前问题与下一步边界

没有发现需要改变原算法本质、模型或输入语义才能接入的阻碍。三条完整生命周期的实际接线已验证；真实 C01 ON 附加边分支与 SA 映射/上坡分支也已触达。

仍有限制：只覆盖既有 C1/C2 投影；SA 仅一个 30 秒种子，未搜索完成或形成统计性能证据；新 HEFT 包装层与旧包装层并存，未来若旧层改变，需要继续核对差异并重做 300 秒一致性测试。正式 C01 方法比较仍需新的实例/种子/预算清单及源码绑定，不能直接把本次工程计划改名或把 R2/R5 旧计划换输入执行。本轮没有启动这些后续工作，也没有合并或提交推送。
