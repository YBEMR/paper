# 有证书的不可达联合状态剪枝：实现、验收与完整R1静态配对

已完成本轮受控实现与验收，随后仅运行一次完整auto-L R1的OFF/ON静态构模。实际减少 **2,938个状态、2,938个变量、29,380条电热行**，与此前预测完全一致；非零数减少320,242。**开启剪枝构模反而更慢**：17.185567s，对照6.976845s，主要增加严格门关闭审计成本。没有LP/MILP求解或求解加速结论；本轮停止，不自动上传、推送、合并或继续优化。

## 实现范围与版本

基于 `7631a16d420fbd8711af1e6cb2f35bc03cf9700d`、`9d972848adee5db8351d8f3be9638319bf0331d3` 及归档 `chapter3_support_autol_lp_20261111/autol_build/rev02/`。工作区旧HEAD仍为052c0b01，因此使用固定提交内容及逐文件哈希绑定实际版本，不冒充从旧HEAD运行相同源。

- 正式 `research/chapter3_experiments/milp.py`：新增默认关闭、严格bool的 `prune_joint_states=False`，仅支持已声明auto-L；SHA256 `43e259d03ce5c65e38a9fb1148fdd45acfecb3b4fb132e1f6d14ea34963e65b4`。
- 新增 `research/chapter3_experiments/joint_state_support.py`：实际导出结构行的必要支持证书、状态过滤、门关闭精确盒审计；SHA256 `d4f7ee5916d5bb935f11852a5969d04379e11adde1e015b8e248cdb6f03c979c`。
- 新增 `research/chapter3_experiments/test_joint_state_support.py`：独立结构/状态、数值行及完整物理对照；SHA256 `41705b3acbbaaf6d906d1d543fbceeda0a078f9d1fc2d320bc93d6f3b471e2ec`。

原选项支持传播未改。完整R1始终保留AB/AC各6次Stage、共12次、66原模式、设备及频档、5ms起点网格和非整数结束、400ms窗口、β1.3、50°C入口和80°C温限、独立场景及原物理参数。没有改写原条件电热等式导出函数或引入Benders。修改前后源码及diff在 `implementation/`；实际输入字节绑定旧归档哈希。

剪枝位于每事件区间候选状态生成后、w及电热行创建前。每个非L域须有同区间同OPP活动option见证，按(Stage,unit)分组穷尽必要支持积。仅在全部组合都被严格证书排除时删除；无证明或超限一律保留，不把局部支持存在当完整可达。L仍允许低频活动或空闲。保留完整candidate_states用于原能量变量上界，故没有顺手缩小变量盒、改变M或物理系数。

## 数值验收门与等价条件

完整R1配对开始前，以下验收全部通过并以源码/证据SHA绑定在 `full_static/acceptance.json`，之后才冻结217份运行源码。配对方案SHA256为 `a7ab9d4af043d07ea4a29d562ae31201b3d929f7e3bc9a47956021202bd18929`。

1. 对已归档拟删状态的29,380条原电热行，固定门为0，用实际binary64 A/b/lb/ub转为精确Fraction求全盒最大残差，0失败。最小正余量 `277/4722366482869645213696`，约5.86570316e−20；没有用1e−9容忍正违反。
2. 原2,938份证书的54,440个阻断组合在实际binary64结构行重放通过。12个Stage一热组和8条dependency行提供数值前提；29,928个同Stage组合由精确一热否定，24,512个依赖组合由导出行路径和的一热子域最小值否定。最小路径余量0.0013333333333329733，另按每路径行放宽1e−9后仍为正。只读追溯确认：生产2418个路径证书中2392个用于最终删状态，另26个未用于最终删状态（AB14、AC12）；实际删除状态的完整语义名集合与此前预测逐项相同，另见prediction_identity_check.json。
3. 原18,311条域一热、auto支持、活动锁、联合一热和边际行逐项与目录相同，系数和RHS精确为±1/0，allowance=0；rho/w共13,614个界为[0,1]。因此原y取精确0/1时，这些行确定对应频态和联合态。
4. 下述完整小域集合、物理、存活行、强化约束及负例全部通过。

生产实现继续fail-closed：每个删状态以原系数、同一实际变量盒和原affine导出器，在隔离的临时Model重建其原10条条件行，严格复核门为0时冗余。探针只换列编号，不向正式模型添加行；任何正违反即抛错，不能返回未经核验的ON模型。完整ON再次复核29,380条，均通过；全部实际路径证书也超过每路径行1e−9参考余量。

**本轮补齐的等价层级**：针对冻结R1、原y为精确整数的binary64约束解释。旧整数可行点中，被证书排除的w只能为0；删去这些w及门关闭冗余行后，存活行按变量名精确相同。新旧能量强化行都被各自存活状态原能量行在同一变量盒上蕴含，因此不能额外排除原整数辅助点。反向以删w=0扩展也满足旧行，支持原整数解投影保持。不能据此宣称整个LP松弛多面体相同，也不承诺任意求解器近整数/行容差接受管道相同。容差检查是独立参考，不是等价定义或物理参数修改。

## 独立小域与回归

物理小域保留原R1全部12次Stage、双场景及原mode数值，只在独立fixture声明原模式/起点子域；实际完整R1科学输入未修改。fixture中A.main/A.post有两种原合法起点，C.post有原H/L两种模式，原非整数9.6ms持续时间保留；没有手改duration/power来制造案例。冻结32个完整组合、240s总测试和最多64次热评价（单次≤10s），实际远未用满。

- 7项新测试＋8项旧纯结构回归全部通过。
- 32个完整组合的独立合法身份集合12→12，228个逐区间状态投影保留；小域模型488→486变量、1609→1589行，仅删2状态/20行。
- 12个合法完整方案各在OFF/ON真实评价一次，共24次，均SAFE。能量上下界、峰温及完整科学字段完全相同；只剔除计时字段。两侧共用原物理评价器，**不是独立热实现**。独立部分为结构合法性、状态投影、原数值行/盒审计。
- 原options/events/共同变量盒和存活物理行按语义名重编号后完全相同；20条旧删行的门关闭冗余和53个新能量强化active-state蕴含检查精确通过。
- cap0保留全部状态、零margin保留、篡改一热拒绝、一ULP正违反拒绝、生产门审计人为失败时无法返回模型，均通过。另有tiny-positive exact margin与容差参考不一致的边界测试，不混为近整数管道保证。

测试共5次fixture构模尝试，包括预先固定的故意失败负例；没有完整未缩域R1构模。旧结构回归为266有限目录完整合法集合186→186，不增加热调用。证据在 `validation/REPORT.md`、`execution/plan.json`、`results.json`、`complete_candidate_sets.json`及逐方案OFF/ON物理回执，具体文件以该目录清单为准。

## 完整auto-L R1一次静态OFF/ON配对

两组均开启既有propagate_support，沿用同一baseline_flags；唯一差异是prune_joint_states。OFF并非旧hold-last或传播关闭组。原始输入/选项/事件相同，无初始化或热评价；每worker300s预算、380s外部回收保护，各运行一次，无失败、超时或重跑。

|指标|剪枝OFF|剪枝ON|减少|
|---|---:|---:|---:|
|选项|1,125|1,125|0|
|事件区间AB/AC|215/209|215/209|0|
|联合状态AB/AC|4,861/4,937|3,397/3,463|1,464/1,474|
|状态总数|9,798|6,860|2,938|
|变量|19,857|16,919|2,938|
|温度传播行|78,384|54,880|23,504|
|完整能量行|19,596|13,720|5,876|
|电热行合计|97,980|68,600|29,380|
|全行数|124,338|94,958|29,380|
|全非零数|1,311,146|990,904|320,242|
|实际整数y|1,125|1,125|0|
|能量强化行/证书|424|424|0|

OFF全部归档NPZ数组及变量名逐项、逐字节相同，说明默认关闭没有漂移原数值表示。ON共同变量lb/ub/c及原整数变量名集合完全相同；删除的2,938列均为w。以旧删w=0代入并去掉对应29,380物理行后，**94,534个存活非强化行**按(tag、变量语义名、binary64系数及RHS)的多重集完全相同。两侧各424份能量下界证书，按导出数字的精确有理盒证明全部通过；不要求新旧强化行文本相同而跳过其来源。完整证据在 `full_static/comparison.json`、`execution/{off,on}/energy_certificate_checks.json`、`energy_bound_certificates.json`、`preprocessing.json`、NPZ及row_tags中。

|耗时/s|OFF|ON|
|---|---:|---:|
|原选项扩展（构模内）|0.043827|0.046171|
|原选项支持传播（构模内）|0.046683|0.043618|
|构模|6.976845|17.185567|
|矩阵导出|0.479766|0.392544|
|导出能量强化证书检查|0.570011|0.441292|
|worker内全程（最终result写入前）|9.420930|21.502668|
|外层命令全墙钟|9.747082|23.958376|

ON新增支持上下文准备合计约0.003808s、区间支持过滤约1.430318s、删状态门关闭审计约10.764056s。审计仍需为被删状态生成原物理系数和预览行，因此首版并没有省去这部分系数工作。组件位于父阶段内部，不可再与全构模重复相加。实际证明是矩阵缩减，而不是构模或求解加速；单次观察不能外推所有平台成本。

## 时间、命令、结果与限制

工作目录 `/workspace/paper`；Python3.12.14、NumPy2.3.5、SciPy1.17.0、Linux。本轮未安装依赖。下列为2026-11-11北京时间UTC+8：

|活动|实际开始—结束|耗时|
|---|---|---:|
|归档门关闭行验收|16:06:54.459107—16:06:57.173469|2.714365s|
|正式实现准备与封存|16:09:04.814431—16:15:10.780503|约365.966s（含编写/检查）|
|归档依赖数值验收|16:09:32.652762—16:09:36.743233|4.090498s|
|归档控制行验收|16:12:01.539437—16:12:07.624152|6.084738s|
|唯一测试批次|16:15:39.420927—16:15:51.542964|12.122046s|
|主代理验收放行|16:17:10.608375|六项结果hash绑定后放行|
|完整R1静态配对批次|16:17:41.084003—16:18:14.790920|33.706917s|
|静态结果比较|16:18:26.985519—16:18:31.396429|4.410918s|

初期只读准备未完整打点，不回填总起点；master_plan记录时间、各活动回执及最后completion_record共同提供可追踪跨度。准备及纯检查有并行，不能把耗时相加作为整个任务墙钟。

主要实际调用如下；完整重定向和worker argv分别在各子目录commands.json/command_receipts.json/full_static/*.command_receipt.json：

```sh
python3 research/chapter3_certified_state_pruning_20261111/numeric_gate/audit_archived_gate_zero.py freeze
python3 research/chapter3_certified_state_pruning_20261111/numeric_gate/audit_archived_gate_zero.py
python3 research/chapter3_certified_state_pruning_20261111/numeric_gate/audit_archived_dependency.py freeze
python3 research/chapter3_certified_state_pruning_20261111/numeric_gate/audit_archived_dependency.py
python3 -B research/chapter3_experiments/test_joint_state_support.py run --output research/chapter3_certified_state_pruning_20261111/validation/execution
python3 -B research/chapter3_experiments/test_option_support_structural.py --output research/chapter3_certified_state_pruning_20261111/validation/old_structural_regression
python3 research/chapter3_certified_state_pruning_20261111/full_static/run_pair.py freeze
python3 -u research/chapter3_certified_state_pruning_20261111/full_static/run_pair.py run
python3 research/chapter3_certified_state_pruning_20261111/full_static/compare_pair.py
```

`numeric_gate/`保存前置证明/逐行CSV，`implementation/`保存修改前后及diff，`validation/`保存完整输入/集合/物理回执及测试日志，`full_static/`保存冻结源/输入/验收plan、OFF/ON原矩阵和日志以及比较。实际生产测试入口另有freeze动作，控制行审计另有调用，精确调用以各commands记录为准。只读生产审计汇总首次临时脚本遇到空审计无states字段而KeyError，改为get('states',[])后完成；不涉及构模或科研调用重试，未隐去该后处理异常。

本轮验收限于上述冻结版本/配置与可审计必要性证明。没有求解器运行结果、最优性或能耗改善结论；小域物理一致不等于遍历全部R1时间表或独立热实现。功能保持默认关闭，未来输入/代码/数值盒变化必须重新审计；若门不通过应停止，不得用容差掩盖。原历史文件不覆盖，本轮本地保存，不推送或合并。
