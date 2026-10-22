# K166：whole整体MILP接入既有增广的接口兼容审查

**存在一条范围可控的接口路线，但现有局部封装不能直接插入whole。** 建议只保留“whole完整模型与评价／反馈循环不变，在数值请求边界增加增广、原坐标投影和证据分层”的路线。不借入单场景分解、60秒局部时片或callback超温立即取消策略。本轮只读源码，没有构模、变换原大payload、求解或热评价；尚不能声称实际whole载荷可通过增广，更未证明故障修复或性能改善。

## 当前链路与唯一拟接入位置

现whole调用链是：`execute_formal_milp → execute_warm／execute_milp → solve_with_initial_witness → _InitialSession → solve_formal_diagnostic`。共同模型包含全部场景及共享部署；`Recorder`直接解码完整候选，再经`evaluate_model_candidate`核对完整输入、全部场景及完整窗口。安全U来自该评价器，既有安全初始方案在后续数值失败时仍会保留。

拟议包装次序应为：

> 原完整模型、原完整SAFE及原x0 → `_InitialSession(whole增广session(native), 原x0)` → 本请求补变量与接纳 → native；callback／final向量经本请求的原／增广／链接核对后，只把原坐标交回whole Recorder。

`_InitialSession`必须在增广session外层，才能让它注入的原维x0进入增广处理；若次序反过来，内部初始点包装器可能把未扩维x0直接交给增广载荷。新增包装不重新构造初始方案，不跨调用共享见证或缓存。

## 最小接口差距表

| 接口 | 能继承什么 | 必须补的薄层及边界 | 源码定位 |
|---|---|---|---|
| whole Recorder绑定 | 原模型、accuracy、同一budget、folder和完整评价器均已存在 | whole目前硬建`Recorder`，没有factory绑定点；只包装session会使增广context找不到recorder。需显式、可选择的whole recorder绑定，默认whole路径保持原样 | `formal_milp.py:100–118`；`augmented_method.py:219–250` |
| 初始x0 | 原SAFE构造、完整热核对、原坐标补齐和原数值接纳；仅首请求注入 | 可继承`append_complements`及请求初始点检查；原x0不改，补变量无法按既有精确要求生成时记未决，不重造候选或自动补跑 | `initial_point.py:101–126、175–220`；`augmented_method.py:399–410` |
| callback／final投影 | `validate_projected_vector`及`_Request.assess_vector`已核对原行、增广行、链接与目标；whole后续逻辑二值／完整合法性／热评价可保留 | 需whole版数值门：不能把原生增广向量直接送入原decoder；现`AugmentedSession`的返回x仍是增广坐标，局部版依靠专用Recorder投影，不是session自动返回原坐标 | `augmented_payload.py:215–278`；`augmented_method.py:154–197、267–277、441–459`；`milp.py:1123–1173` |
| 多场景评价与U | whole `Recorder.assess`已评价完整输入，缓存键也是完整候选；`solve_with_initial_witness`保留旧完整SAFE | 保留whole evaluator与全场景weighted U；不使用单scene `on_safe`、局部重新评价与局部汇总接口，也不将局部U升级为整体U | `diagnostic_search.py:61–136`；`milp.py:1320–1325`；`initial_point.py:233–258` |
| 事件处理与热反馈时机 | 可继承事件编号／hash核对、数值门及原whole最终候选反馈循环 | `AugmentedPartialRecorder.poll`依赖slice/current_prefix，`PartialRecorder`会排队并取消callback违规。不能整体套用，否则改变whole反馈时机。whole数值门只增加数值事件核对；超温仍按原whole循环添加原行 | `partial_method.py:93–195`；`augmented_method.py:279–341`；`formal_milp.py:140–160` |
| 动态追加反馈行 | 每轮`model.as_solver_dict()`导出当前原模型；context每请求读取当前names／row_tags并建新mapping | 每请求重绑矩阵及标签hash，不能缓存旧维数／旧mapping。现反馈tag为`continuous_thermal_feedback`／`certified_scene_assignment_exclusion`，不在增广选择的两个物理前缀内，应原样保留，不扩大增广目标行族 | `formal_milp.py:111–118、145–160`；`milp.py:1259–1317`；`augmented_payload.py:19`；`augmented_method.py:226–250` |
| 单一预算与故障 | `AugmentedSession`要求同一MethodBudget；原MATLAB入口、MaxTime、事件读写、owned-worker清理可保留 | 所有转换、复制、hash、接纳、投影和日志计费。保留failure latch，不重试。既有`_Request.fail`可能覆盖budget取消文案；whole旧审计不能仅凭文案推断截止，需按完整原生请求／根时钟／数值与隔离链区分正常到时和真未决，旧U不清空 | `augmented_method.py:140–152、394–485`；`matlab_bridge.py:561–716`；`method_runner.py:137–177` |
| 原生回执与派生接纳 | 原生MAT、Python JSON、事件及内部界保持原样；每请求mapping／admission／矩阵身份已有格式可借鉴 | whole旧审计要求`round == 原生.python.json`。增广session会追加admission或派生consistency，直接使用会造成身份错。建议原生返回单列`native_rounds`，循环消费的派生round及admission另存，按编号／hash配对，用薄审计器核对两层，不能过滤字段后假装原件完全相等 | `augmented_method.py:382–391、441–459`；`p0_batch/audit_whole.py:181–199` |
| 内部界与独立界 | 补变量目标系数为零，保留原目标；whole原生界仍按完整模型目标单位记录，原独立L₀来源保持 | 不套用局部子问题的unweighted scene界或Lₐ；solver内部界、全场景安全U及独立L₀继续分列。增广行接纳不是严格MILP可行／最优证明 | `augmented_payload.py:145–174`；`diagnostic_search.py:125–136`；`deadline_batch/deadline_dispatch.py:20–26` |

`AugmentedMethodContext.prepare/fail/summary`及数值请求内核对多场景没有专门限制，原`Recorder`也提供其所需的model／budget／folder字段。真正不能直接继承的是context现成的`recorder_factory`、`AugmentedPartialRecorder`及局部汇总生命周期。建议只借这些已有数值内核，增加whole语义的薄绑定和审计；不另做一套调度求解框架。

## 本轮结论与未验证项

静态接口分析支持继续讨论这一条可选路线；它至少需要whole recorder绑定、投影事件门和原生／派生证据审计三处有限适配。**不能把“只改session_factory”当成可执行方案，也不能将局部增广已运行等同于whole已支持。**

尚未核定实际whole行的选择覆盖、补变量可表示性、动态行追加后的逐行等价、运行成本及原生接纳变化；本轮未读取原大MAT来变换，也未实现适配或新测试系统。任何后续实现／小域检查／原生技术诊断均需另定范围；原16次与24次未启动状态不变。
