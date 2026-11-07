# 第四章 R2/R5 六组验证结果

2026-11-07，用户时区 UTC+8（Etc/GMT-8）。**两题各三组均完成现场初始化、完整 SAFE 评价和一次 post，全部通过；ON 在 R2 比 OFF 节能 10.063249%，在 R5 比 OFF 节能 5.097310%。** 这是两个既有合成目录样本、每臂一次的有限验证，不代表普遍优势或稳定加速。

## 范围、环境与冻结

本轮承接用户同意执行[此前六槽提案](../validation_design_20261107/validation_proposal.json)的明确指令；没有把原 `authorized=false` 提案原位改成批准。新授权、输入、方法、评价器、源码、顺序和预算冻结在 [plan.json](plan.json)，其 SHA256 为 `c782b18d40a7b0a2878bfac7fdda1535c315bfa1d269d6e15ef418354b30d7d2`。

基准提交为 `9c4e4a621a6b4df71aba0d98fa39c03653395c35`，本地分支 `work`。本轮新增独立 `research/chapter4_scheduler/validation/` 执行封装、人工测试和本结果目录；原生产源码、物理输入、旧结果和 Git 引用均未改。没有安装软件、启动 MATLAB MILP、补跑、追加样本、提交、合并或推送。

环境仍为原 Cloud Linux 6.18.57 x86_64/glibc 2.41、Python 3.12.14、NumPy 2.3.5、SciPy 1.17.0，5 CPU。启动前约 17 GB 可用内存、31 GB 可用磁盘，原 Python HEFT／评价器和依赖可用；没有 MATLAB／Octave。本次环境 ID、解释器、包版本和资源快照见计划。没有额外的真实热评价或 HEFT 试跑作为启动探针。

R2/R5 直接由原 `config_v01.json` 的 base 条件及既有样本展开，使用原 auto-L 适配。保持完整平台、全部原设备／频档选项、66 个逻辑模式、90 个场景执行模式、AB/AC 两场景各六个 Stage、原 pre→main→post 依赖、400 ms 全窗口、5 ms 起点、50°C 入口、80°C 温限及四热节点。时长和结束时刻不取整，没有人为掩码或参数重设。

R2 输入哈希为 `bc80fdced7a8a13ffb19186d220a482abc01660cb6773be8a11b1c1780cb1314`，R5 为 `2e6f120356db5566ff4a3b64462fefff57a7e6d240957199d9e19a085391b9c1`；六槽公共配置哈希为 `15ca987441165a0e994ddbe073874ef23c76ee6ec26d4eecfa41b436ca0c6c83`。这些与事前静态提案完全一致。

## 比较是否公平

顺序预先固定为 R2：HEFT→OFF→ON；R5：ON→OFF→HEFT。每槽一个新进程、独立现场输入和独立原增强 `heft_method.run_heft`，不读历史候选，不跨调用共享缓存。该 HEFT 已包含原设备配置、频档和重排节能搜索，不是删减成纯最快结束构造器。

三组共同使用原 `blocking.CompleteRecorder`，统一合法性、完整回执、缓存、SAFE 身份、预算形成时间和能量计量。HEFT 基线完成原 HEFT 后停止；OFF／ON 直接调用原 `blocking.execute_reconstruction`，只改变 `allow_blocking_edges=False/True`。HEFT 新封装没有调用旧 `heuristic_runner` 的独立下界预计算，不声称继承其下界证书或历史封装耗时；HEFT 算法本身未改。细化阶段固定具体设备是原启发式限制，不是改变模型合法选择范围。

每槽同样 300 秒方法根，初始化、科学模块导入、身份核查、输入展开、目标、排序、图重构和全部评价均计费。正常最终 SAFE 最多一次独立 60 秒 post；六槽上限 1800 方法秒＋360 post 秒，日历 3600 秒。不延长、转移或补足自然早停余量。外层 420／70 秒进程监督不改变 300／60 秒证据截止。

实际核对：每题三组均完成初始化，完整初解候选、语义哈希、原能量端点、初始化元数据及有序初始化候选序列分别完全相同。R2 初解原始 hash 为 `4868a5427b31f1a06c2f7d0c64a14830841d64b6f47a51e1f2d73b8de37d10a1`；R5 为 `87963bbddae522dd6183df93f539ef96aa7f01d80c5f6eddd3ada04d9f9a5463`。六个调用根 token 各不相同。OFF／ON 可按相同起点下的单开关比较解释；接纳后搜索轨迹自然分化，不能声称候选序列和评价次数始终相同。

## 六组实际结果

| 实例 | 方法 | 完整初解 U/J | 最终完整 U/J | 后续严格接纳 | 方法根/s | 完整评价：初始化＋后续 | post |
|---|---|---:|---:|---:|---:|---:|---|
| R2 | HEFT | 0.955459934953 | 0.955459934953 | 0 | 23.731 | 36＋0 | SAFE |
| R2 | OFF | 0.955459934953 | 0.955459934953 | 0 | 25.422 | 36＋0 | SAFE |
| R2 | ON | 0.955459934953 | 0.859309627158 | 2 | 21.606 | 36＋2 | SAFE |
| R5 | ON | 0.917706681081 | 0.856824091351 | 2 | 22.195 | 42＋2 | SAFE |
| R5 | OFF | 0.917706681081 | 0.902844894146 | 1 | 23.202 | 42＋3 | SAFE |
| R5 | HEFT | 0.917706681081 | 0.917706681081 | 0 | 25.939 | 42＋0 | SAFE |

R2 的 ON 相对 HEFT／OFF 的节省保守下界为 **0.09615030779446965 J（10.063248523%）**。R5 的 ON 相对 HEFT 为 **0.06088258972931205 J（6.634210144%）**；相对已有改善的 OFF，则为 **0.04602080279508614 J（5.097309969%）**。完整能量区间严格分离，不由显示位数或区间重叠造成。

R2/OFF 没有改善的结果完整保留；R5/OFF 的普通重构改善也保留，没有把 ON 对 HEFT 的全部差异都归为额外阻塞边的单次直接收益。机器文件对未变候选的自身区间相减，保守差下界可能为一个极小负区间宽度；这不是实际退化，应同时看候选是否相同和 `strictly_improves_own_initial=false`。

## 实际机制与收益构成

两个 ON 结果都只改变 AB 场景，AC 完整候选逐字不变，具体设备全部保持。首次接纳均以 B.main 的 H→L 为目标，在主 NPU 任务关联对上反转次序，并额外反转 CPU1 的 B.post→A.post 阻塞边。R2 同一次候选还将伙伴 A.main 从 H 改为 L；R5 的 A.main 保持 L。原任务依赖始终保留。

首次联合动作分别严格改善约 **82.877742 mJ（R2）**、**54.613128 mJ（R5）**。之后按接纳后的新现解，普通关联动作继续将 B.pre 降至 L，分别再改善约 **13.272565 mJ**、**6.269462 mJ**；第二步没有额外边。因此总收益是允许阻塞边之后整条搜索轨迹的结果，不能全部叫作那一条边自身的能量贡献。

R2/OFF 保存了 120 次结构尝试，其中 96 次有超期诊断，未产生需完整热评价的合法候选。R2/ON 因严格接纳后重建搜索，记录 33 次结构尝试、9 次额外边尝试，实际评价并接纳两个完整候选。R5/OFF 则确实找到一种折中：B.main H→M、伙伴 A.main L→M，能量下降但没有达到共同低档。ON 通过联动获得共同低档并继续改善。完整轨迹、前后设备／OPP／起点和候选 hash 见 [detail_audit.json](detail_audit.json)及每槽原 `graph_proposals`。

| 相对自身初解的分项节省/mJ | 活动 | 域基准 | 公共 | 温度修正 | 总计 |
|---|---:|---:|---:|---:|---:|
| R2/ON | 73.284360 | 17.850000 | 0 | 5.015948 | 96.150308 |
| R5/OFF | 13.025606 | 1.020000 | 0 | 0.816181 | 14.861787 |
| R5/ON | 47.269781 | 10.500000 | 0 | 3.112809 | 60.882590 |

这是原全窗口、原场景权重的账本分解，不是另做参数消融。ON 最终最高连续峰温约为 R2 **50.012577°C**、R5 **50°C**，远低于原 80°C 温限；本轮仍没有证明紧热约束驱动收益。温度修正的变化同时受到模式漏电斜率和时序影响，本轮没有新增反事实热评价分离其独立因果份额。

## 成本、起止和计数

| 实例／方法 | HEFT 初始化含评价/s | 完整初解冻结/根秒 | 首次后续严格改善/根秒 | post 根/s |
|---|---:|---:|---:|---:|
| R2/HEFT | 23.608420 | 23.731311 | — | 0.813902 |
| R2/OFF | 24.882569 | 25.009031 | — | 0.679771 |
| R2/ON | 20.217131 | 20.327593 | 20.978717 | 0.634383 |
| R5/ON | 20.808325 | 20.916830 | 21.570675 | 0.637209 |
| R5/OFF | 20.831910 | 20.936277 | 21.609656 | 2.659557 |
| R5/HEFT | 24.586785 | 25.938758 | — | 0.697977 |

各臂**预算上限相同，评价次数并不相同**。初始化总计 234 次完整评价，后续 7 次，总方法评价 **241 次**；另有独立 post **6 次**，共 **247 份完整 SAFE 回执**，缓存命中均为 0。所有方法均为 `SEARCH_COMPLETED`，没有实际故障、超时、未得 SAFE、重试或未运行槽；这不改变预先保存这些结果的规则。ON 的少量额外评价与新轨迹并不保证它普遍更快或用更少评价。

本次方法根合计 **142.095673 秒**，post 根合计 **6.122800 秒**。批次于 **2026-11-07 21:36:41.317957+08:00** 开始、**21:39:13.006118+08:00** 结束，墙钟 **151.688201 秒**；外层启动命令进程为 151.851803 秒，差异包含解释器、监督及归档。单次墙钟有明显波动；虽然两题 ON 本次均较短，也不能凭每臂一次及不同初始化耗时给出稳定加速比。

首次资源探查为 21:29:02+08:00。原回归检查实际进程为 21:35:51.796325—21:35:55.046203，新封装检查为 21:35:55.046388—21:35:55.334575；冻结计划命令为 21:36:14.523970—21:36:15.255391。归档审计于批次之后执行，不形成任何新热评价。日志保存 UTC 原始时间，以上显示按用户 UTC+8 换算。

## 验证性质、命令和产物

原 **109/109** 自动人工夹具回归通过，新增 **12/12** 自动人工夹具测试通过；均阻断真实 HEFT、热积分、优化器及网络。新增覆盖共同根、完整回执、预算到期保留 SAFE、未完成初始化、正常无 SAFE、三臂派发、停批和禁止重试。它们不是真实任务上的节能实验。

真实实验后，**509/509 只读检查**通过；247 份完整 SAFE 回执通过原合同审计。547 项冻结源码／依赖／证据身份一致；另核对 1108 个旧保护文件，字节均未变。六份 post 在独立新进程、独立 60 秒根内，重新调用同一原 `thermal.evaluate_candidate` 与区间核；本次能量端点与各自方法结果完全相同。post 和合同检查不构成另一数值实现或外部审查，不能排除共同代码的系统性错误。

以下均以 `/workspace/paper` 为工作目录；完整 argv、cwd、开始结束、返回码及 stdout/stderr 对应 `command_01_*` 至 `command_06_*`：

```text
python -B -m research.chapter4_scheduler.blocking.run_precheck --out research/chapter4_scheduler/results/validation_execution_20261107/regression
python -B -m research.chapter4_scheduler.validation.precheck --out research/chapter4_scheduler/results/validation_execution_20261107/new_precheck
python -B -m research.chapter4_scheduler.validation.run prepare --out research/chapter4_scheduler/results/validation_execution_20261107 --checks research/chapter4_scheduler/results/validation_execution_20261107/new_precheck/checks.json
python -B -m research.chapter4_scheduler.validation.run batch --out research/chapter4_scheduler/results/validation_execution_20261107
python -B -m research.chapter4_scheduler.validation.run analyze --out research/chapter4_scheduler/results/validation_execution_20261107
python -B research/chapter4_scheduler/results/validation_execution_20261107/detail_existing.py
```

每槽的 `worker_command.json`／`post_command.json` 记录实际绝对解释器 argv，`method_started.json`／`method_return.json`、`post_started.json`／`post_return.json` 记录精确起止。子进程使用 `python -B -m research.chapter4_scheduler.validation.run worker/post --out <本目录绝对路径> --slot <冻结槽 ID>`。完整结果及输入位于各槽 `method/`，原始 post 为 `post_receipt.json`；没有用 post 数值改写方法成绩。

主要入口：[计划与环境](plan.json)、[批次终态](batch_return.json)、[完整机器汇总及 509 项审计](summary.json)、[变化轨迹与旧档核查](detail_audit.json)、[原 109 项检查](regression/checks.json)、[新 12 项检查](new_precheck/checks.json)、[执行封装说明](../../validation/README.md)。

## 限制与下一步

R2/R5 没有用于所查第四章机制开发记录，但属于同一自设参数目录，有第三章历史；不是严格盲测、外部平台或独立同分布数据。各臂一次、全部热约束宽松，没有统计稳定性、真实硬件、规模扩展、独立数值核、MILP 或全局最优依据。原回执 `formal_experiment_result=false`、方法 `coverage_complete=false` 均原样保留，不能宣称完整域覆盖。相同设备限定、一条额外边和两种模板仍限制新启发式范围。

本轮已完成并停止。下一步适合先将已保存 R1/R3 和本轮 R2/R5 整理为第四章算法定义、机制解释与适用边界；若后续需要规模或热压力验证，应另定最小范围与预算，不自动增加实验。本轮所有失败／无改善保留政策、R2/OFF 无改善、R5/OFF 有改善及全部原始结果均可复核。
