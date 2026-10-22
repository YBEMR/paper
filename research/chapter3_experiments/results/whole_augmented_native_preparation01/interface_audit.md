# K168：一次whole原生技术诊断的接口与预算审查

**建议可形成一个待确认的最小协议：新建一次独立300秒方法调用，外层只允许一轮，因此至多提交一次原生请求；不重启、不恢复原24次。** 当前仅静态核查，研究调用、构模、载荷转换及热评价均为0。300秒能否容纳新增增广与接纳开销尚未实测；不能承诺必进入求解器或必修复原冲突。

## 1．推荐接线及应保持的配置

现成`execute_whole_augmented`没有`max_rounds`参数。无需增加生产接口即可在未来独立入口中使用下面的**接线约定**，本轮不实现或执行它：

1. 建立一次`WholeAugmentedContext`，其原生工厂为`partial(MatlabSession, cut_max_iterations=10)`。
2. 调用`execute_formal_milp`，传入`seconds=300`、`feedback_kind='conditional'`、`session_factory=context.session_factory`、`diagnostic_solver=partial(context.solve_formal_diagnostic,max_rounds=1)`。
3. `model_builder=partial(build_model,prefilter_deadlines=True,cumulative_precedence=False)`；`execute_warm`继续叠加原四FLAGS。不能直接调用`solve_formal_diagnostic`跳过原初始化，也不能只调用whole增广helper而遗漏预算内L₀和CUT设置。
4. loader沿原`deadline_dispatch.execute`：对`beta_1.0__R2`新读输入、验证三项规范JSON身份，并在同一个根预算内计算原完整域独立L₀、登记根时钟。不能把旧L₀、旧SAFE、旧x0或缓存读回作为免费输入。

| 配置 | 应冻结的值／含义 | 源码依据 |
|---|---|---|
| 工作负载 | 原R2、完整AB与AC，两场景各一对三Stage链，等权；A部署跨场景共享但不固定到某个旧答案 | `deadline_batch/deadline_entry.py:35`及旧输入 |
| 物理与服务条件 | 原H响应、50°C初温／80°C温限、400 ms窗口、5 ms起点、auto-L；期限β=1.0；逐请求期限不变 | 原`fresh_input`及输入身份 |
| 四FLAGS | `fix_late_options=True`、`aggregate_opp_locks=True`、`relax_auxiliary_integrality=True`、`strengthen_energy_lower_bounds=True` | `run_initial_witness_diagnostic.py:32`；`run_warm_diagnostic.py:23、67` |
| 外加构模选项 | `prefilter_deadlines=True`、`cumulative_precedence=False`；不固定部署／场景、不加邻域、不做闭合锚预消元 | `deadline_dispatch.py:27`；`milp.py:711`默认参数 |
| 初始点 | 仍从本调用生成SAFE并补齐，最多沿原初始化3次候选尝试；首个原维x0由外层`_InitialSession`注入，内部增广后传原生 | `initial_point.py:101、131、175—220` |
| 原生显式选项 | Display off，绝对／相对gap 0，约束容差1e-9、整数容差1e-6，IntegerPreprocess none、LPPreprocess none、原OutputFcn、CutMaxIterations 10 | `solve_model.m:89—124`、原R2请求与options |
| 其余原生选项 | 保持现R2023b默认，实际完整归档；不另设启发式／切面／LP参数，不新增native-only MaxTime帽 | 原R2options及`matlab_bridge.py:561` |

`run_four_method_comparison.settings()`的BUILD_OPTIONS与上述六项一致，但其SHARED是**局部联动**固定部署，不应传给整体whole。60秒单场景slice及4开2闭也不属于这次whole配置。

## 2．一次调用、一次原生请求及停止边界

一次**方法调用**包含输入展开、L₀、构模、MATLAB启动、原初始化与x0、矩阵导出、增广／身份存档、原生求解、回调接纳及完整热能耗评价。设置`max_rounds=1`把一次whole诊断限制为**至多一次**`session.solve`／`intlinprog`请求，不把每轮重新赋予300秒。

如果初始化未得完整SAFE、原x0被拒绝、增广不适用或时间耗尽，则允许0次原生进入并按实际阶段结束，不能补一次“真正进求解器”的调用。初始化最多3个候选不是3次原生求解；原代码不调用LP/MILP生成x0。最终超温仍沿原whole验证和反馈逻辑登记，可能在这一轮末尾添加有效反馈行，但不提交第二个请求。该轮数截断属于技术诊断边界，不是完整方法质量对照。

建议冻结并核查`method_invocations<=1`、新session实例数`<=1`、请求／原生进入次数`<=1`，以及重启、补跑、旧24槽消费均为0；claim在初始化前消费，不能因未进入原生而返还。

## 3．300、420与480秒分别限制什么

| 时间 | 建议含义 | 不能怎样解释 |
|---|---|---|
| 300秒 | 从输入读取前起的唯一证据预算；上述计算全部计费，超过后不补新候选、U或热判断 | 不能再给原生独立300秒；不把增广／接纳／启动免费化 |
| 清理窗口最多40秒 | 现`MatlabSession.close`已用一个40秒绝对清理窗口，只关闭本session拥有的进程树 | 不用于求解、热评价或接受迟到结果 |
| 420秒方法返回监督 | 可继承原保守看门限；到点仍未返回则终止拥有的执行树并归档监督状态 | 不是把方法预算扩到420秒；不是承诺所有底层步骤可在40秒内强制结束 |
| 480秒整项监督 | 新诊断建议将只读审计、归档与方法返回／清理都限制在该硬上限内，超过即停止并保留未完成记录 | 旧整槽还含最多60秒post；本次不自动继承额外热post授权 |

300秒是证据门，420／480秒是保护执行与清理的墙钟门。记录实际方法计算、首次SAFE、MATLAB启动、原生MaxTime／实际耗时、清理、只读审计与总日历，不把监督余量计为研究收益。旧批19200秒及其绝对截止不被重置；本次若获确认，是另一个单项诊断，原批仍16已消费／24未启动。

旧R2可说明原链路在300秒内曾到达原生：构模13.656秒完成、MATLAB启动10.875秒、初始SAFE在26.453秒、导出完成28.531秒；原生MaxTime270.103秒、原生调用268.002秒、方法298.391秒、清理6.844秒。**这些只是旧记录，不是新增广成本测量。** 新协议应接受“增广或接纳用完预算”，不得为了保证原生进入而延长。

## 4．最小冻结材料与验收

确认后至少绑定当前源码／K167最终预检SHA、原R2三项输入身份、上述六项构模开关与原生设置、300／420／480时间含义、单次claim、禁止重启及判读规则。实际启动文件必须与冻结SHA对应；本轮没有真实launcher，不能声称启动链已验收。

技术目标仅为：完整数值请求、原x0扩展、回调／final两路投影、原／新增广／link／整数／目标接纳、原生与派生回执身份，以及预算／清理是否闭合。保留原生数值冲突、0候选、0改善、无U及未决；有既成SAFE时不清除，尚未完成热复核的候选不能补成SAFE。只读审计不重建模型、不重算热、不调整容差，也不自动应用旧whole审计以忽略增广坐标差异。

本次若通过，只支持“该输入下原生数值接口可运行”；不证明K165根因、表达必然修复、不证明性能提升、最优或热反馈收益，也不自动启动原24次。
