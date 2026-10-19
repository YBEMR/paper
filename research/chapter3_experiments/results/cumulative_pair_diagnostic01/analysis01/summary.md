本次两版均未证实相对各自完整初始化的严格节能改善。

固定共享部署H=a，CDF False/True均Cut10；K119不作为control。

| CDF | 初始U（J） | 最终U（J） | 严格改善 | 首SAFE/新legal/严格改善（s） | 方法/清理（s） | 状态 |
|---|---|---|---|---|---|---|
| False | 1.080823451833 | 1.080823451833 | False | 26.234 / — / — | 249.875 / 6.265 | SAFE / SCENE_SEARCH_SEQUENCE_COMPLETE |
| True | 1.080823451833 | 1.080823451833 | False | 26.375 / — / — | 167.782 / 6.109 | SAFE / SCENE_SEARCH_SEQUENCE_COMPLETE |

表内能量和时间为舍入展示；严格改善使用facts.json保存的原始能量包络比较。

首模型只读数组核对：

| 场景 | 旧A/b前缀相同 | 追加行/nnz | ±1且rhs0且仅旧y | 其他数组相同 | 其余设置相同（MaxTime单列） |
|---|---|---|---|---|---|
| AB_offset_0ms | True/True | 99/9306 | True | True | True |
| AC_offset_0ms | True/True | 91/7350 | True | True | True |

CDF False：NO_DIFFERENT_DECODED_CANDIDATE_OBSERVED；非空原生向量对本次x0：True；反馈 0 条/0 行。

CDF True：NO_DIFFERENT_DECODED_CANDIDATE_OBSERVED；非空原生向量对本次x0：True；反馈 0 条/0 行。

first_new_legal只由不同已解码安排与同source、预算内LEGAL完成日志核定；缺失写未知，不使用原生可行点数代替。
U只引用已存预算内完整SAFE回执；曲线止于实际方法停止时刻。phase/节点/原生界/rawgap、每个非空向量对x0比较、派生MaxTime差异及CDF构模组件见facts.json。
旧前缀相等/追加结构是事后数组核对；不重新认证可行域或求解。CDF行数/非零数不自动代表运行瓶颈或加速。单次配对不推断总体胜率，也不证明热反馈收益。
