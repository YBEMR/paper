# K131 已存数值载荷与源码只读核查

结论：尚无已证实的生产实现 bug。已定位新版 AB 的系数动态范围高于旧 N1 AB；这只是数值缩放风险线索，不能认定为本次 `exitflag=-2` 的根因。未构模、求解、启动 MATLAB、评价热轨迹，也未改表达、容差或生产源码。

| 已存载荷 | A 形状／非零数 | 最小非零 | 最大绝对系数 | 最大同行动态比 |
|---|---:|---:|---:|---:|
| 新版 AB，第 1 请求 | 39733×8525／357483 | 1.2499048653e-8 | 60.1810551641 | 4.8006480123e9 |
| 旧 N1 AB，第 1 请求 | 21376×4621／171524 | 4.9992389559e-8 | 60.1810551641 | 1.2003240123e9 |
| 旧 N1 AC，第 2 请求 | 22741×4635／189711 | 1.9993912183e-7 | 60.1582605508 | 3.0014951446e8 |

新版 AB 最大同行比位于 0 基第 13838 行，10 个非零，行内最小约 1.2499069485e-8、最大约 60.0036330767，rhs 约 60.0026331209。新版与旧 AB 最小非零 rhs 均约 4.6269174744e-20，不能将该现象当作新版独有缺陷。保存载荷未附行 tag；本轮没有重新构模来恢复 tag，具体行族未定位。原行系数、列索引及列上下界见 `scale_facts.json`。

源码核查范围为运行目录 `source_snapshot/research/chapter3_experiments/` 中对应文件所代表的生产链路：

- `matlab_bridge.py` 的 `_prepare` 将 0 基整数索引转为 1 基，稀疏阵统一为 float CSC；`savemat(..., oned_as='column')` 后发布请求。`_check_initial_point` 检查未修复的原向量，接纳依据为数值残差，并非精确证书。
- `solve_model.m` 直接传入 `p.c/p.intcon/p.A/p.b/p.Aeq/p.beq/p.lb/p.ub/initialPoint`；固定 `ConstraintTolerance=1e-9`、`IntegerTolerance=1e-6`，`IntegerPreprocess/LPPreprocess=none`。未看到额外重标度或载荷转置修改矩阵的逻辑。worker 只记录收到 x0，不独立证明求解器接纳。
- `_initial_point_status_conflict` 仅在同一请求中显式 x0 已被 Python 数值接纳、原生 `SOLVED/-2` 时设置单独冲突诊断；保留原生状态。`diagnostic_search.py` 在原预算检查后终止为 `SOLVER_NUMERICAL_CONSISTENCY_UNRESOLVED`，不会把这个状态升级为独立不可行证明。该停止行为与约定一致。
- `milp.py` 的条件行 M 来自完整有限变量盒上的区间残差；`le` 向外放宽 rhs，`eq` 导出上下两行；`as_solver_dict` 不主动缩放。区间包络只处理建模／转换误差，不认证求解器内部算术。没有仅凭源码查明条件行错误或缓存错误。

下一步只建议另立范围，研究保持原数值问题语义的最小数值处理与原生接纳诊断方案；先明确需要追加的证据和预算，再决定是否运行。当前不能据这些幅值统计直接改容差、删小系数、放松物理约束或补跑。本轮到此结束。

复算：`python research/chapter3_experiments/results/fixed_unit_pair02/numerical_scope_audit/audit_saved_scale.py`。该脚本只读取三份已存请求 MAT 并重写本目录 `scale_facts.json`，没有导入研究构模、求解或热评价模块。
