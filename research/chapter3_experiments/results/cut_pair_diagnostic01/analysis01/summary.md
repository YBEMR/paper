两设置均未证实相对各自完整初始化的严格节能改善。

仅报告固定共享部署H=a；严格改善按各自完整初始化下端比较，不能把较小求解器目标当作真实节能。

| CutMaxIterations | 状态 / 原因 | 完整初始能量（J） | 最终U（J） | 本次严格改善 | 首SAFE / 首严格改善（s） | 方法 / 清理（s） |
|---:|---|---|---:|---|---|---|
| 10 | SAFE / SCENE_SEARCH_SEQUENCE_COMPLETE | [1.08082345, 1.08082345] | 1.08082345 | False | 22.358999999938533 / None | 160.48399999993853 / 5.952999999979511 |
| 1 | SAFE / SCENE_SEARCH_SEQUENCE_COMPLETE | [1.08082345, 1.08082345] | 1.08082345 | False | 23.719000000040978 / None | 160.9220000000205 / 6.905999999959022 |

初始化收益、后续MILP上界下降和区间严格分离在CSV/JSON中分列。无SAFE时不填能量；曲线仅用已保存、预算内完整SAFE聚合，止于实际方法停止时刻。

Cut=10：NO_DIFFERENT_DECODED_CANDIDATE_OBSERVED；预算内不同于x0的原生向量：False；实际原生设置：[10]。
Cut=1：NO_DIFFERENT_DECODED_CANDIDATE_OBSERVED；预算内不同于x0的原生向量：False；实际原生设置：[1]。

首请求事后对照（反馈后的模型另列，不混为首模型）：

| 场景 | 数组指纹相等 | 其余选项原始相等 | 排除预算派生MaxTime后的其余设置相等 |
|---|---|---|---|
| AB_offset_0ms | True | False | True |
| AC_offset_0ms | True | False | True |

逐请求phase、rootLP/内部界、节点、原始gap、x0/事件向量比较和全部选项差异见summary.json。R2023b原生relativegap按100(U−L)/(|U|+1)保留；独立L0/La与物理能耗区间分开。
仅此固定H=a的两次诊断，不代表16部署搜索；K116不作control。未复算热、LP或求解；未从预算外raw结果补U。单次配对不推断总体胜率，反馈记录不证明反馈收益。
