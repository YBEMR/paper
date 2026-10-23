# K.184：剩余七槽终态只读结果

R1仅HEFT／SINGLE／PAIR；R3四法。旧R1/C启动故障不补成同轮结果。

|问题|方法|状态|完整安全U/J|自身初始U/J|严格降低|方法/s|首SAFE/s|首严格改善/s|
|---|---|---|---:|---:|---|---:|---:|---:|
|base__R1|HEFT|COMPLETE_SAFE_POST_PASSED|0.881088|0.881088|False|45.016|2.782|—|
|base__R1|SINGLE|COMPLETE_SAFE_POST_PASSED|0.881088|0.881088|False|107.656|2.578|—|
|base__R1|PAIR|COMPLETE_SAFE_POST_PASSED|0.881060|0.881088|True|200.265|2.390|45.484|
|base__R3|PAIR|COMPLETE_SAFE_POST_PASSED|0.862251|0.862251|False|248.734|1.484|—|
|base__R3|SINGLE|COMPLETE_SAFE_POST_PASSED|0.862251|0.862251|False|99.359|1.890|—|
|base__R3|HEFT|COMPLETE_SAFE_POST_PASSED|0.862251|0.862251|False|50.047|1.500|—|
|base__R3|C|COMPLETE_SAFE_POST_PASSED|0.936947|1.091492|True|282.796|2.359|50.765|

初始化归因：
- base__R1 SINGLE：初始化均完成=True；最佳SAFE语义一致=True；区间完全一致=True；可按同起点解释=True。
- base__R1 PAIR：初始化均完成=True；最佳SAFE语义一致=True；区间完全一致=True；可按同起点解释=True。
- base__R3 SINGLE：初始化均完成=True；最佳SAFE语义一致=True；区间完全一致=True；可按同起点解释=True。
- base__R3 PAIR：初始化均完成=True；最佳SAFE语义一致=True；区间完全一致=True；可按同起点解释=True。

已接纳成对图变动：
- base__R1：reverse／earliest，选中['AB_offset_0ms::A_r1::A.main', 'AB_offset_0ms::B_r1::B.main']；严格下降下界0.000027774351 J；同一完整方案曾在SINGLE中评价=False。详细起点、设备／OPP和资源顺序、各能量分项差见facts.json。
- base__R3：未形成严格改善。

SINGLE／PAIR的初始项是各自独立HEFT过程的最佳完整SAFE；C是自己的构造初解，不能当成相同HEFT起点。未完成初始化或初始最佳方案不同，仅报告端到端结果，不把全部差异归因于图操作。

首严格改善指超过自身完整初始能量区间的改善；HEFT单独运行未设置‘完成HEFT后的改进阶段’，该列为空。各题各方法一次，不作统计稳定性或全域最优结论。

完整部署、工作点与起点语义hash、原C两阶段、计时、提案／复核／缓存数及原始证据文件hash见facts.json。本文只读归档并作有理数区间比较，无求解、热积分、候选复核或修复。
