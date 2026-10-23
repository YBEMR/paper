# K171：实际构模前的同次安全U时间线

5题共20次实际构模，全部找到构模开始前已经完整接纳并发布的同次安全U。第一阶段两次构模均只能使用fresh seed；第二阶段AB使用第一阶段末完整U，AC仅R3仍沿用该U，其余4题可用第二阶段AB已合并的新U。不能用方法最终U回填。

| 题目 | 构模 | 根时钟区间/s | 构模前可用完整U/J | 来源 |
|---|---|---:|---:|---|
| base__R1 | P1 AB | 0.969—2.734 | 1.080823451833 | update0／agg0，COMPLETE_FRESH_SEED |
| base__R1 | P1 AC | 3.344—6.219 | 1.080823451833 | update0／agg0，COMPLETE_FRESH_SEED |
| base__R1 | P2 AB | 138.969—140.656 | 0.962884840560 | update3／agg3，COMPLETE_ORIGINAL_INPUT_MERGED_SAFE |
| base__R1 | P2 AC | 202.359—204.969 | 0.910243818382 | update5／agg5，COMPLETE_ORIGINAL_INPUT_MERGED_SAFE |
| base__R2 | P1 AB | 1.156—3.828 | 1.078130589424 | update0／agg0，COMPLETE_FRESH_SEED |
| base__R2 | P1 AC | 4.844—8.234 | 1.078130589424 | update0／agg0，COMPLETE_FRESH_SEED |
| base__R2 | P2 AB | 145.203—147.156 | 0.950321217866 | update2／agg2，COMPLETE_ORIGINAL_INPUT_MERGED_SAFE |
| base__R2 | P2 AC | 208.797—211.156 | 0.903781691578 | update4／agg4，COMPLETE_ORIGINAL_INPUT_MERGED_SAFE |
| base__R3 | P1 AB | 1.016—3.641 | 1.091492239352 | update0／agg0，COMPLETE_FRESH_SEED |
| base__R3 | P1 AC | 4.250—7.156 | 1.091492239352 | update0／agg0，COMPLETE_FRESH_SEED |
| base__R3 | P2 AB | 138.281—140.531 | 0.999661967307 | update3／agg3，COMPLETE_ORIGINAL_INPUT_MERGED_SAFE |
| base__R3 | P2 AC | 190.891—193.719 | 0.999661967307 | update3／agg3，COMPLETE_ORIGINAL_INPUT_MERGED_SAFE |
| base__R4 | P1 AB | 1.032—3.016 | 1.087760462583 | update0／agg0，COMPLETE_FRESH_SEED |
| base__R4 | P1 AC | 3.579—7.391 | 1.087760462583 | update0／agg0，COMPLETE_FRESH_SEED |
| base__R4 | P2 AB | 140.454—142.282 | 0.966221751980 | update3／agg3，COMPLETE_ORIGINAL_INPUT_MERGED_SAFE |
| base__R4 | P2 AC | 203.844—206.407 | 0.915811084955 | update4／agg4，COMPLETE_ORIGINAL_INPUT_MERGED_SAFE |
| base__R5 | P1 AB | 0.907—3.860 | 1.077936235142 | update0／agg0，COMPLETE_FRESH_SEED |
| base__R5 | P1 AC | 4.516—7.735 | 1.077936235142 | update0／agg0，COMPLETE_FRESH_SEED |
| base__R5 | P2 AB | 139.047—140.704 | 0.963611871952 | update4／agg4，COMPLETE_ORIGINAL_INPUT_MERGED_SAFE |
| base__R5 | P2 AC | 202.079—204.891 | 0.915771456218 | update5／agg5，COMPLETE_ORIGINAL_INPUT_MERGED_SAFE |

## 证据规则

- 根时钟零点为linked入口lazy imports之前。同一budget token/start/300秒贯穿fresh seed、两阶段、两个场景。事实文件同时给出原始monotonic绝对时间的精确有理数。
- 构模区间取`timing.phase_records[phase=model_construction]`，按原始phase及场景顺序绑定。`build_scene`首条可能晚于真正开始，末条及`model_completed_at_s`可能早于phase退出，均单列保留。
- 每个U均绑定唯一`global_updates`与`aggregation_attempts`；逐项核对完整AB/AC、原输入、候选、同次预算、源hash、receipt hash、窗口覆盖及加权能量包络。可用时刻保守取formed／transferred／observer completed的最大值，严格早于build开始。
- 单场景SAFE只证明该场景；即使已经形成，也不直接当完整加权U。事实文件保留其是否进入完整aggregate的索引。
- phase末最佳只用于核对；phase2固定闭锚来自第一阶段末完整SAFE。phase2 AC启动点可来自更晚的完整合并，不等于闭锚被更新。
- 结果与wrapper_raw逐对象相等；所有读取原件前后hash一致。本脚本仅stdlib读取及算术，不调用生产函数、构模、优化或热积分。

## 供主回放使用的字段

`facts.json → cases[].builds[]`保存准确起止、可用U、chosen_update_index／chosen_aggregation_index、完整候选hash及各场景receipt／能量。主回放必须使用该build的U，不能读取`final_U_J_for_comparison_only`替代。

## 源码定位

- `neighborhood_method.py:183—247`：完整aggregate提交与global_updates／snapshot／observer。
- `neighborhood_method.py:339—343`：单场景更新后另行完整聚合。
- `neighborhood_method.py:345—396`：BuildObserver、model_construction及initial_scene记录。
- `neighborhood_method.py:604—620`：第一阶段先构造两个场景，再进入求解。
- `neighborhood_method.py:638—688`：第二阶段清除未提交局部代、逐场景取latest完整snapshot后构模。
- `linked_method.py:91—127`：只捕获完整第一阶段SAFE，第二阶段一次冻结闭锚。
- `scene_adapter.py:493—607`：单场景完整能量要求与全场景聚合身份／预算／能量接纳。
以上行号均以facts绑定的P0准备源码快照为准。

本回放只证明U当时已可用；不证明下界实际删项、构模/求解加速或新的节能收益。
