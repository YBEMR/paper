# K166：整体MILP的互补变量表达兼容性（零调用）

**结论：可继承表达层的等价变换与原行复核机制，但现有联动版增广传输不能直接作为整体MILP的即插即用替换。** 本次只读源码、作代数推导，未构模、未变换R2归档矩阵、未执行旧预检、未调用求解器或热评价。数值故障是否改善仍未知。

## 1．连续域与混合整数域的投影

对已经导出的某一行写成

\[
a_r^Tz+M_rw_{g(r)}\le b_r,\qquad 0\le w_g\le1.
\]

保留全部原变量，按使用到的gate各增加一个连续变量\(v_g\in[0,1]\)，添加\(v_g+w_g=1\)，并将所选行改成

\[
a_r^Tz-M_rv_{g(r)}\le b_r-M_r.
\]

在精确算术中，每个原可行点都唯一扩展为\(v_g=1-w_g\)；每个增广可行点代回后也满足原行。未选行、原等式与变量界全部保留，所以无论选择全部还是部分合格行，原坐标上的投影都与原可行域相同。新增变量目标系数为0，原目标不变。

证明不要求\(w_g\)为整数。原整数坐标集合保持不变时，同一结论同时适用于LP连续放松与原混合整数可行域；若原逻辑约束使\(w_g\)在整数解处取0或1，新增\(v_g\)也随之取1或0。此变换在精确算术下不加强LP界，也不增加原调度选择。

等价对象是**原已导出的binary64系数行**。它继承原表达的向外舍入和松弛范围，不会把原来的外包关系升级成精确物理方程或连续热安全证明。

## 2．整体构造与现有适配器的条件对照

| 条件 | 源码事实与范围 | 判断 |
|---|---|---|
| 每个被改写物理行仅有一个`w:` gate | `milp.py:1080—1091`的source仅由theta和q组成，target为下一事件theta或energy；`affine_conditional_eq`将单个joint gate传给条件等式（413—443） | 正常构造符合单gate来源；仍需对实际导出数组检查，不能仅凭标签推定 |
| gate系数为正 | `construct_conditional_template`取非负M（386—395），导出中零系数会被去除（289—333） | **不能静态保证每行M>0**；M=0导致无gate列，现适配器会拒绝，不应悄悄改写或丢弃该行 |
| gate连续且界为[0,1] | joint变量在1033—1034由`auxiliary`生成；836—838规定只有`relax_auxiliary_integrality=True`时为隐含二元连续变量；`var`的常见二元分支保存精确0/1界（241—257） | 当前whole默认FLAGS采用该开关（`run_initial_witness_diagnostic.py:32—33`，经`run_warm_diagnostic.py:23,82`继承）；若关闭，现适配器拒绝。gate连续是现接口条件，并非上述代数等价的数学必要条件 |
| 标签与矩阵匹配 | 严格适配器要求names唯一、长度相符、tag以`thermal_propagation/`或`complete_energy/`开头，并逐行检查单正gate（`augmented_payload.py:93—121`） | labels必须来自**同一当前model的导出顺序**；仅长度匹配不能证明身份。whole未存标签不能靠重建补作原标签证据 |
| 新右端精确保存b−M | `augmented_payload.py:119—121`用Fraction检查导出的b、M之差是否恰好可表示为binary64 | 不能仅凭当前数学构造保证全部行通过；不允许用普通减法结果代替这一条件 |
| 不可精确表示行的处理 | `augmented_method.py:25—82`只改合格行；唯一不支持原因为b−M不可精确表示时保留原行与原位 | **仍保持投影等价**；未改写行继续约束原变量，新增link只为被改写行的gate服务。若结构错误，仍应拒绝；若无一合格行，现接口也拒绝 |
| 原逻辑及强化行 | 变换只选择两个物理tag；资源、共享部署、joint唯一／边际、能量下界、反馈等行保持原表达（`augmented_payload.py:129—152`；`milp.py:1037—1041,1103—1108`） | 这些行可以含多个w；只要不误标为被改写物理行，就不构成阻断 |

`build_live_augmented_payload`的“nonphysical未变”统计包含被保留的不可精确物理行，mapping已单独说明，不能把该统计误解为所有物理行都已改写。

## 3．链接容差必须与原行复核一起使用

令\(\delta_g=v_g+w_g-1\)。在所存系数精确算术下，原行残差与增广行残差满足

\[
r_{\mathrm{old},r}=r_{\mathrm{new},r}+M_r\delta_{g(r)}.
\]

若增广行与link仅分别通过\(\tau=10^{-9}\)容差，最多只能推出\(r_{\mathrm{old},r}\le(1+M_r)\tau\)，不能推出原行也在同一容差内。例如\(M_r=60\)时这一界为\(6.1\times10^{-8}\)。实际浮点计算还存在求和舍入；代数等价不等于两种浮点接纳集合相同。

已有`validate_projected_vector`同时复核**原全行、增广全行、link、原整数坐标、目标一致性**，仍使用原`1e-9/1e-6`，不修补或舍入（`augmented_payload.py:215—267`）。只有全部通过，才返回原坐标前缀。不能为提高接纳率放宽原行，不能把“增广可行”直接交给物理解码器。

初始点另有条件：`append_complements`要求每个`1-w`本身恰好可表示为binary64（176—184）。任意连续浮点w不一定满足；失败应记接口／数值未决，不能修补原x0。已有0/1 gate则不存在该补数表示问题。

原行数值通过后，仍须原有逻辑二元核查、精确调度合法性与完整连续热能耗复核，才能形成安全U。原行检查只是工程数值接纳，不是独立MILP证书。

## 4．当前whole接线存在的具体阻断

1. `formal_milp.py:100—105`在函数内直接创建`diagnostic_search.Recorder`并绑定poll，没有`recorder_factory`参数。`execute_formal_milp`虽暴露`session_factory`（178—190），仅换成`AugmentedSession`仍不能绑定增广context。
2. `AugmentedMethodContext.prepare`要求context已持有当前recorder/model，再从中取得同次导出的names/row_tags（`augmented_method.py:226—249`）；现`recorder_factory`产生的是`AugmentedPartialRecorder`（219—221、262），其父类为面向单场景局部规划的`PartialRecorder`，不是whole的Recorder。
3. 增广session保留原生返回向量与事件：`solve`复核final向量但不把返回`x`改写成原前缀（394—459）；现有正确投影发生在`AugmentedPartialRecorder.assess`（267—277）。因此whole的**回调与final两条路径都必须在解码前经过同一原前缀门**，不能只拦回调或仅依赖decoder忽略尾列。

这属于待适配的记录器／传输接口，不是物理模型不支持。可继承的最小内容是：选择性精确行变换、同次labels与矩阵身份、原／新／link三重数值检查及失败锁存。若之后获准实施，应先做whole专用接线的纯夹具预检，再决定是否开展受控数值诊断；本次不实施、不补跑、不提前声称故障已修复。

源码hash及本次零调用边界见同目录`source_audit.json`。所有结论限于已读源码，不包含新的整规模合格行数量、性能或故障因果证据。
