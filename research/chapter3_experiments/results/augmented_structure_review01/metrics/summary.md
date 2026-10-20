# K136：已有载荷结构与原生事件只读核查

仅分析K135已保存数组和回执；零求解、构模、热评价。新文件为派生统计，不是新性能结果。

| 方法／场景 | 原→发送变量 | 整数／连续 | 固定界列 | 不等式＋等式 | 非零元A＋Aeq | options | 事件／区间 | rootlp原生自报秒 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
|old_n1／AB|4621→4621|167／4454|1129|21376＋0|171524＋0|167|150／149|6.0908783|
|old_n1／AC|4635→4635|137／4498|638|22741＋0|189711＋0|137|144／143|2.2763226|
|augmented_all_opp_start／AB|8525→10925|441／10484|1882|39733＋2400|357483＋4800|441|271／270|52.0579354|
|augmented_all_opp_start／AC|13810→21006|405／20601|857|89973＋7196|889678＋14392|405|296／295|未发布|

上述整数全为[0,1]界整数，普通整数为0。固定界列仍包含在变量总数中。新版补变量均连续，整数坐标保持；新版AB／AC分别新增2400／7196个补变量及链接等式。logical_binary_variables为逻辑标签统计，不能等同于求解器整数维数。

新版条件门w为2400／7196列；原标签thermal_propagation与complete_energy条件行见facts.json细分。AB改写24000行、保留非无损物理行0；AC改写71958行、保留2行。旧版无归档labels，条件行类别计数留空；其热条件构造调用1311／1481已原样登记，不能冒充逐行标签核计。

| 方法／场景 | 非空callback事件 | 原生time／s | solver fval | 原前缀与本次x0逐bit相同 |
|---|---|---:|---:|---|
|old_n1／AB|request_000001.event_000004.json|6.2116715|1.046120846870405|True|
|old_n1／AB|request_000001.event_000006.json|48.9199128|0.9461092314007349|False|
|old_n1／AB|request_000001.event_000007.json|48.9764016|0.9461092314007348|False|
|old_n1／AC|request_000002.event_000004.json|2.3196746|1.1155260567962317|True|
|old_n1／AC|request_000002.event_000006.json|60.2881668|0.9796608444806968|False|
|augmented_all_opp_start／AB|request_000001.event_000004.json|52.1840241|1.046120846870405|True|

旧AB首次异于种子的发布为48.9199128秒，旧AC为60.2881668秒；因此把60秒直接对半分配不保证保留原改善。AC的后者超过声明MaxTime，仍是原300秒方法证据窗内保存的回执，不能改称严格60秒内形成。新版AB最终原前缀仍为x0；新版AC无非空候选发布，缺rootlp事件不能填0、认定完成或推断无解。

发送矩阵系数绝对值范围、固定界类型、原生实际耗时与声明限额见counts.csv；新版原矩阵系数范围未单独存MAT，本次不重建。连续补变量满足v=1−w，精确算术下只是坐标扩展，不能声称增强LP松弛；本表也不能把rootlp耗时差单因果归于变量／条件行增多。

原始输入范围限定47个实际读取文件，SHA-256与大小前后完全相同；见hashes_before.json／hashes_after.json。未改写MAT或历史输出。

出处：`augmented_quality_pair01/<method>/matlab/request_000001.mat`为AB，`request_000002.mat`为AC；对应`.response.json`登记原生实际耗时、options、最终向量；`.event_*.json`登记实际发布向量与time。`<method>/result.json#/scenes/<scene>/model_summary`与`construction`给出options、逻辑标签、事件／区间及核计。新版`scene_0/augmented_requests/request_000001`与`scene_1/augmented_requests/request_000002`中的mapping／labels／matrix_identities给出改写与原矩阵身份。全部相对路径、字段定位与前后哈希见facts.json及hashes文件。
