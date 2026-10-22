# K168：beta_1.0__R2整体增广原生技术诊断冻结提案

**状态：待用户确认；当前研究调用、预算预留、claim均为0。** 本轮仅设计、读旧输入和纯预检，不构造原R2、变换旧大载荷、启动MATLAB、求解或热积分。准备入口的run无条件拒绝；旧批次授权、claim和自造approval都不能启动它。

## 目的与固定条件

只回答：新的whole增广数值接口能否在原R2条件下完成原生请求与回执接纳，原先“显式x0通过工程数值检查、原生−2/空向量”的冲突是否再次出现。不测试算法排名、节能改善或连续反馈收益。

原`beta_1.0__R2`完整AB/AC三Stage链、跨场景共享部署及全部合法设备/工作点/起点保持；不固定共享A到NPU，不借局部分解、闭锚或60秒scene时片。H响应、50°C入口、80°C温限、beta1.0、400ms窗口、5ms启动集合、auto-L及完整功热模型不变。

输入绑定原冻结声明中R2的raw/config/instance canonical身份及原存档JSON文件hash。将来执行必须在本次方法内fresh_input重建并核对身份，不把旧JSON安排、原x0、SAFE、参考答案、热缓存或任何其他方法结果作为输入。现阶段读旧参数JSON仅为冻结依据，不生成候选。

## 准确预算（本提案尚未生效）

| 项目 | 上限与计费含义 |
|---|---|
| 新研究方法调用 | **1次×300秒＝300方法秒**，独立诊断槽，不占用/恢复原24槽 |
| 原生请求 | **0或1次**，实际max_rounds=1，无后续重求、重启或补跑；不能保证一定进入native |
| 方法根时钟 | 输入加载前开始；fresh输入、独立L0、原完整构模、MATLAB启动、最多原3次初始化尝试/x0构造与连续复核、原/增广导出、hash/日志/传输、求解、callback/final完整核查均计入同一300秒 |
| 原生MaxTime | 仅当次请求的剩余根预算，不能另领300秒；实际耗时与停止延迟另列 |
| 证据截止 | 严格300秒；迟到向量/温度/能量仅诊断，不能形成预算内SAFE或新U |
| 进程清理 | 沿现MatlabSession.close最多40秒清理窗口，仅停止本调用拥有的进程；不是研究时间 |
| 方法返回监督 | 槽启动后420秒仍未返回则触发停止/清理未决；300+40之外仅允许等待已开始操作停止、保存既成记录，不得再计算 |
| 整项日历监督 | **480秒（8分钟）**，从独立受控槽启动计；覆盖解释器导入、启动治理、方法、清理、只读归档及核对。达到上限停止受控工作，清理未证完成则记录未决，不追加时间或调用 |
| 预算外post热复核 | **0次、0秒**，不继承旧批次每例60秒post；事后只读核对既成证据 |

解释器导入按原计时口径不计300方法秒、计入480整项时钟；MATLAB启动计入300。300后最多180秒整项余量只供工程监督/清理/只读保存，不能兑换成科研。40/420/480是合作停止及监督界，不是硬实时进程已退出的保证；超界或进程隔离不确定时如实保留故障/未决。

授权后新建一次性诊断claim，进入方法前即消费本次300秒额度；未进入native、正常截止、数值/技术失败均消耗这一次，不退还、不补跑。原期限组16已消费/24未启动及原账本不改，不将新结果回填第16槽，不借原已过绝对日历。当前没有授权文件或claim，协议不自行授权。

## 冻结调用配方

保留现`deadline_dispatch.execute`对whole使用的fresh_input、身份检查、独立L0及同一MethodBudget；只以本提案whole薄入口替换其entries.whole。`recipe.py`给出可纯检查的依赖绑定，未执行真实入口：

1. `WholeAugmentedContext(session_factory=partial(MatlabSession, cut_max_iterations=10))`。
2. `execute_formal_milp(..., seconds=300, feedback_kind='conditional', session_factory=context.session_factory, diagnostic_solver=partial(context.solve_formal_diagnostic,max_rounds=1), model_builder=partial(build_model,prefilter_deadlines=True,cumulative_precedence=False))`。
3. `execute_warm`继续叠加原四FLAGS：fix_late_options、aggregate_opp_locks、relax_auxiliary_integrality、strengthen_energy_lower_bounds均True；不增加新强化、模板或搜索规则。
4. `_InitialSession`仍在增广session外；原初始化最多3次，只在本次调用内重新构造。没有SAFE_POINT_READY或剩余时间不足时允许0次native后结束。

现`execute_whole_augmented`未暴露max_rounds，不能直接加一个无效参数后声称单请求。旧formal入口还会写固定outer_round_limit=50，诊断必须另存actual_max_rounds=1/native_request_limit=1及实际请求数，保留旧标签的来源说明，不把标签当实际执行上限。达到一次后即结束；原最后候选若有严格热违规，仍沿原反馈时机记录有效行，但不再次求解。

原R2023b选项保持：AbsoluteGapTolerance=0、RelativeGapTolerance=0、ConstraintTolerance=1e−9、IntegerTolerance=1e−6、IntegerPreprocess=none、LPPreprocess=none、CutMaxIterations=10、Display=off、原OutputFcn及其余默认设置，实际opts归档。仍检查原/增广全行、link及原坐标合法性和完整连续热安全，不靠容差调整、舍入或忽略尾变量提高接纳率。

本轮只实现准备登记与纯配方绑定，**没有真实launcher**。用户确认后，按此配方落实一次性claim/监督入口并冻结其新增管理源；启动前核对应预检、源码、输入及预算身份，不能改变已确认配方或自行增加研究预算。

## 判据与保存字段

| 状态 | 本次可作判断 |
|---|---|
| 构模/初始化/增广未完成，0native | 诊断未完成；登记阶段成本和原因，不声称接口通过或故障消失 |
| 已提交但无solver_entered证据 | worker/传输阶段未决；不能写已进入intlinprog |
| x0原行通过且worker收到 | 只证明本次数值接纳和传递，不证明solver实际保留x0 |
| 原生返回具体向量且原/新/link通过 | 在本次请求条件下，返回向量接纳链可用；不证明新解、节能或全域最优 |
| 初始点已过工程数值检查且显式传入，仍再次−2/空解或矛盾状态 | 同族数值状态冲突再现，保留全部原生证据；不是独立无解证明，仍不能据此认定solver已接纳x0 |
| 正常时限/无整数返回/清理延迟 | 数值可用性或优化状态未决，不把“未再报−2”当修复通过 |
| 新向量被数值门拒绝、身份/接口故障 | 分类记录并结束，保留先前完整SAFE，不放宽标准或重试 |
| 预算内完整场景/窗口连续热SAFE | 可保存安全U及形成时刻，区分初始化/solver候选；不补预算外post，不形成性能排名 |
| 热违规或热未分辨 | 分别保存真实见证/未决；单条失败不排除配置，未分辨不驱动排除 |

保存阶段独占耗时、原/增广规模及可改写/保留行数、同次标签/映射/hash、原生/派生回执、callback、数值接纳、首次候选/SAFE时间、内部界、终态/取消与进程清理。done.numfeaspoints=1不足以单独证明x0已被保留。solver-reported界/退出、独立L0、安全U严格分列；内部界高于U保留异常。

旧R2仅作历史诊断参照，不读其向量初始化，也不将两次表现当严格因果配对。一次成功不证明普遍修复；一次未触发热反馈不追加温度扫描。结果不并入完整40次公平排名，不自动续24或追加其它实验。

## 本轮完成条件

纯预检核准备态零消费、未授权run拒绝、单槽/300/单请求绑定、源码/输入/协议漂移拒绝、新目录不覆盖、旧claim/账本不可挪用；不复跑旧26、不导入或执行科学构造。提交本协议、声明、零消费账本、纯检查与独立审查，供用户确认预算和范围。状态始终PENDING_USER_CONFIRMATION。
