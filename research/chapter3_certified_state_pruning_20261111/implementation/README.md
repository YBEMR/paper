# 有证书联合状态剪枝：正式实现

本子任务只编辑 `research/chapter3_experiments/milp.py` 及新增 `joint_state_support.py`。没有运行完整R1构模、任何LP/MILP或物理评价。验证由独立validation与numeric_gate子任务执行，下面说明实现而不声称验收通过。

- `prune_joint_states=False` 默认关闭，严格bool；原propagate_support及其首条bool guard原样保留。开启只允许auto-L，hold-last直接拒绝。OFF不改变数值行路径。
- `SceneSupport`核对每Stage实际导出的一热双行完全精确，原option变量为整数且界为[0,1]。依赖证书对实际binary64行转Fraction，相加路径行，并对所有Stage的一选组求线性系数最小值；两端限定到候选活动见证group，其他Stage保留完整域。只有minimum_lhs−sum_rhs严格为正才否定该对见证。数值容差1e-9只是另存的参考检查，不作为数学可行域定义。
- 对候选状态所有非L域，各选一个按(Stage,unit)分组的活动见证。每个见证组合必须有上述路径或精确Stage唯一性证书，才删除状态。未找到证据、每状态group积超过4096、每scene累计理论group积超过2000000都保留。L状态不要求活动见证。没有新增unit或共享部署规则；实际上一轮2938块均可由Stage唯一性与依赖路径解释。
- 剪枝放在每区间候选states笛卡尔积生成之后、w变量/一热/边际与电热行生成之前。`meta['candidate_states']`保留完整旧states，energy上界严格按它计算，theta/q原boxes保持。
- 每个被删state在物理阶段由独立临时Model、同一已导出的boxes、原coefficients.get及原affine_conditional_eq预览原10条上下行。`verify_gate_off_rows`用实际float系数/界/RHS转Fraction计算gate=0时box最大残差，任何正残差直接ValueError，不能返回未核模型；原条件等式函数未改。此验证会继续生成已删state的系数，因此不能预先声称系数核成本减少。
- 生产模型仅对retained states建立w、电热行与能量下界spec，原 `add_energy_lower_bound` 切割生成器保持原样。preview行不写入实际model，也不参与目标或求解。

证据位于 `model.preprocessing['joint_state_pruning']['scenes'][sid]`：精确一热信息、certificate_catalogue（源行索引/hash、逐Stage minima、精确margin及1e-9参考）、interval_reports（逐状态证明或unknown/cap、门关闭row数/余量、耗时）。`construction`成本新增joint_state_support_pruning和joint_state_gate_off_audit。能量强化证书沿旧字段保存。它证明的是exact exported结构行及原integer y语义，绝不声称LP松弛全部点相同，亦不声称任意solver容差管道保持。

实施子任务自己仅执行AST parse，不主动重复其它代理的枚举、物理或静态完整测试。当前正式两文件hash见ready.json；修改前后milp和新模块snapshot/diff保留。验证冻结后承诺不再改源。没有提交或推送。
