# 联合状态严格不可达的静态必要见证诊断

原合法整数调度语义下，归档 ON 的9,798个联合状态块中，2,938个可由原约束的必要条件严格排除：AB为1,464/4,861，AC为1,474/4,937。剩余6,860个只记为“存在局部兼容见证，整体可达性未知”，不称可达或热安全。没有完整实际R1调度搜索、构模、LP/MILP或热评价，也没有向生产模型实际删除状态。

## 数据身份和前提

输入是 `chapter3_support_autol_lp_20261111/autol_build/rev02/` 的原始 `input_instance.json`、`input_config.json`、`plan.json` 和 `execution/on/{options.json,variable_names.json,result.json}`。六份输入逐字节与固定提交 `7631a16d420fbd8711af1e6cb2f35bc03cf9700d` 中同路径比较，并在结束时复核哈希不变。主工作区旧HEAD不作为本轮版本身份。完整R1每场景6次Stage、两个三Stage链，双场景共12次，原1,125个选项、所有正持续时间、原物理参数和auto_low_immediate_v1保持。

生产代码 `milp.py` 中 stage_unique、dependency、shared_link、unit_mutex、domain_unique、auto_opp_active_support、unit_opp_aggregate_lock、joint_unique、joint_marginal 是所用逻辑的出处。默认辅助变量虽连续放松，但在整数y安排下，同域活动锁和auto支持确定rho：有活动时取其唯一共同OPP，无活动时取L；非负w的one-hot和三个边际随后确定唯一联合状态。诊断用的是这一原调度/整数语义，**不是声称保留LP松弛所有点**。

每个全事件区间 `[left,right)` 内，若联合状态某域取非L，该域必有对应OPP的已选活动选项。把该域全部活动选项按 `(Stage occurrence,unit)` 归组，每组保留完整option_id列表。对每个非L域各选一组作为必要见证；L域既可空闲也可有L活动，不要求见证。归组只合并本次必要条件无法区分的见证，未改变原选项域。

若所有见证组合至少违反一条原必要关系，则联合状态不可达。阻断规则为：同一Stage只能选一个模式；同设备不可并发；正持续时间的依赖路径两端不能在同一个正长度区间同时活动；同一shared Stage的设备必须相同。任一兼容见证出现即停止并标UNKNOWN，不试图补齐实际R1完整安排。跨场景其他Stage的完整映射/依赖/热约束没有用来证明存活状态可达；忽略它们只使结果保守。

## 证书和计数

|场景|原块数|严格不可达|其余未知|
|---|---:|---:|---:|
|AB_offset_0ms|4,861|1,464|3,397|
|AC_offset_0ms|4,937|1,474|3,463|
|合计|9,798|2,938|6,860|

不可达块包含2,712个“三域均非L”块及226个“两域非L”块。前一类还可由每场景两个正持续时间Stage链的宽度2解释：三个非L域要求三个同时活动Stage，其中至少两个来自同一链，与依赖冲突。后一类是具体区间/OPP支持不足，不能只用全局宽度解释。

所有2,938份证书都完整穷举其必要见证积，共54,440个阻断组合，29,928条首次阻断归因为same_stage_unique、24,512条为依赖路径。独立重放器不调用分类器或冲突检测器，而逐项核验：见证组合覆盖完整、重复Stage真实存在、路径的每一条边来自原DAG及端点确属见证。每个证明包括区间、状态、所有支持选项身份和每个见证组合的拒绝依据，见 `certificates.json`（约37MB）。逐区间计数见 `per_interval.csv`。分布见 `proof_distribution.json`。

全扫描必要支持Cartesian规模总和为107,939；未知块遇到首个兼容见证即停止，因此不能把107,939当作全都实际枚举过。每状态归组积上限4,096、全体规模上限2,000,000、静态扫描90秒协作检查；实际无超限UNKNOWN。没有OS外部watchdog，本轮不声称其存在。该有界局部证书扫描不是实际R1全调度搜索。

若未来仅删除这些w及其条件电热门控行，潜在可移除2,938个w和29,380条电热行（每块四温节点加一能量、每式上下两行），对应原97,980条电热行的约30%。仍剩68,600条电热门控行，其他one-hot/边际/活动/能量下界行未在此估计中删除。**这不是实际重新构模后的新总行数或求解加速实测**。

## 独立小域验证与层级限制

独立全结构合法性oracle直接检查每个Stage一选、完整依赖、窗口、共享设备映射、同设备互斥及CPU共享频域，不调用本过滤器的判定助手。9个固定小例共24个完整安排，精确结构合法集合12项；逐场景逐区间检查55个合法状态投影，过滤前后完整合法身份集合保持12→12。原始小例、每个完整组合合法性、完整合法身份集合和状态投影均保存。

覆盖同一Stage多个设备模式、分数非整数结束、依赖端点等号、传递依赖、CPU1/CPU2频档冲突、L活动和L空闲、跨场景仅设备共享而时刻/频档可不同，以及同场景共享身份。另含三个独立Stage使HHH实际可达的反例，防止把本R1宽度2硬编码成普遍定律；还含局部支持存在却完整资源无解的小例，证明UNKNOWN不会升级为可达。小域只检查完整结构合法性，不声称新增物理SAFE证书；任一物理合法调度都是该结构集合的子集，必要性论证覆盖之。

生产binary64矩阵对时间/电热系数做向外放宽。精确依赖证明自动覆盖原合法整数安排，但**尚未证明对当前浮点外包矩阵全部整数辅助可行点也完全等价**。当前涉删区间最小宽度1/10ms，提供正活动重叠下界线索，不是导出误差/容差的认证。若需要在现有binary64导出层面声称完全等价，应沿每条依赖路径累加原行导出误差，核对整数y取值、所有one-hot/auto支持行的实际余量，再证明不可达的数值间隙。否则只宣称原数学调度投影无损。

将来删除w和门控行还需保留事件、选项和所有物理系数，并处理joint边际和能量下界索引。w=0时门控行仅在M覆盖完整变量盒且向外舍入有效的条件下冗余；不能因为w无整数调度见证就随意改变其他行。未实现生产缩减，也未证明新的LP松弛或数值外包等价。

## 实际执行

工作目录 `/workspace/paper`，Python3.12.14/Linux，无新安装。执行程序不导入生产milp、热核、SciPy或求解器。源码/输入哈希见 `plan.json` 和 `integrity_checks.json`。

```sh
python3 research/chapter3_joint_state_static_20261111/reachability/run_reachability.py freeze > research/chapter3_joint_state_static_20261111/reachability/freeze.stdout.log 2> research/chapter3_joint_state_static_20261111/reachability/freeze.stderr.log
python3 research/chapter3_joint_state_static_20261111/reachability/run_reachability.py > research/chapter3_joint_state_static_20261111/reachability/stdout.log 2> research/chapter3_joint_state_static_20261111/reachability/stderr.log
python3 research/chapter3_joint_state_static_20261111/reachability/validate_small_domain.py > research/chapter3_joint_state_static_20261111/reachability/small_domain.stdout.log 2> research/chapter3_joint_state_static_20261111/reachability/small_domain.stderr.log
```

静态扫描 UTC 2026-11-11 07:35:22.239794–07:35:24.263357，即北京时间15:35:22.239794–15:35:24.263357，2.023586秒。小域验证 UTC07:37:10.678778–07:37:10.681869，即北京时间15:37:10.678778–15:37:10.681869，0.003102秒。两个活动的起止、环境及结果分别见 `result.json`、`small_domain_results.json`。脚本准备及报告时间另于收束记录，不倒填为扫描时间。运行无失败或重试，输入与旧成果均未修改，没有求解、热仿真或推送。

该删除方向的优势是有直接原约束必要性证据和可审计有限覆盖；风险是只削减约30%的电热门控块、仍留大量表达，且需单独处理浮点外包等价。与更紧凑电热表达相比是否作为唯一推荐，由主报告结合其他静态证据决定；本子报告不宣称已证收敛改善。
