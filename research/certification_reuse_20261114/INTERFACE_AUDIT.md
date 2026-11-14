# 数学与认证接口核查

所有链接固定到0de4d191966294dc673c21ed244616f1b5a6a85c。以下是静态推导及接口审查，不是对尚未实现的增量评价器签发认证。

## 代码与计时的实际边界

|位置|已核行为|对本诊断的影响|
|---|---|---|
|[method.py:128](https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/method.py#L128)|先完整validate_schedule，再查完整候选缓存；未命中才进入complete_continuous_evaluation|外层合法性时间包含功率段；缓存也不绕过合法性|
|[schedules.py:197](https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter3_experiments/schedules.py#L197)|按所有开始/结束事件切段，处理共享频域、立即低频空闲、按节点漏电斜率和全窗口尾段|阶段名、单任务能量、结束时刻相同都不足以证明功率史相同|
|[schedules.py:254](https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter3_experiments/schedules.py#L254)|合法性、共享部署一致性及功率段生成在同一入口完成|现有计时不能拆出纯合法性/纯功率生成|
|[thermal.py:349](https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter3_experiments/thermal.py#L349)|再做一次validate_schedule；各场景从其entry独立传播；全部安全后加权汇总|场景间不是热状态串接；零权重场景也必须完整通过|
|[thermal.py:122](https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter3_experiments/thermal.py#L122)|验证C/G、节点、模型有效区间、功率守恒和完整窗口；构造9维矩阵|这些检查也在完整评价计时中，没有独立秒数|
|[thermal.py:254](https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter3_experiments/thermal.py#L254)|每事件段按ceil(4×norm(A)×duration)分面板；18阶Taylor；每面板4个峰值和4个谷值包络|面板是运算单位，不是热采样点；连续安全不能靠缓存几个温度点替代|
|[interval.py:120](https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/v1_evaluator/interval.py#L120)|60位定向Decimal、逐阶矩阵向量乘法、余项界|不能用无向舍入/普通浮点缓存替代|
|[thermal.py:281](https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter3_experiments/thermal.py#L281)|温度积分坐标进入温度修正能耗；提交完整面板后累计；末尾热平衡区间交叠核对|积分与温度传播共用Taylor，多次中断不能拼成假完整窗口|
|[thermal.py:396](https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter3_experiments/thermal.py#L396)|before_aggregate_commit检查预算后生成完整SAFE形成时刻|组件旧时间不等于新完整候选形成时间|
|[receipts.py:26](https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter3_experiments/h02_pair_preflight/receipts.py#L26)|核对输入/候选身份、全场景覆盖、区间精度、政策与及时性|复用数值证据不能跳过新候选回执验证|
|[timing.py:35](https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter3_experiments/timing.py#L35)|全根单一绝对deadline，嵌套phase扣除子耗时|只可相加exclusive_s；不能相加父/子墙钟重复计费|
|[comparison/core.py:30](https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/comparison/core.py#L30)|评价调用外围写START/RETURN日志；START写盘发生在实际评价前|complete_continuous_evaluation也含观察器开销，逐次journal差值不等于纯热核耗时|
|[method.py:359](https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/method.py#L359)|seen含初始化缓存，重复完整候选在assess前跳过|实际cache_hits=0不说明上游无重复；未保存独立skip计数|
|[graph_core.py:148](https://github.com/YBEMR/paper/blob/0de4d191966294dc673c21ed244616f1b5a6a85c/research/chapter4_scheduler/graph_core.py#L148)|复制完整基准，只改指定场景后再次全局校验|解释搜索阶段的场景局部性；实际统计仍以已评价载荷为准|

## 相同场景为什么可以复用

固定平台、物理参数、场景entry和window，代码中的场景动力学仅依赖本场景功率段。若完整分段功率相同，确定性ODE解、系统能量、连续峰/谷温相同。旧场景完整外包证据因此仍有效；本轮对重复且当前完成的场景，剔除elapsed/completed时间戳后，其保存数值字段逐项完全一致。

但任务合法性是另一项命题：共享部署等约束涉及全候选，必须重新检查。旧场景结果只能作新完整证明的组件，不把旧完整回执改个candidate_sha256就使用。新对象应保存组件来源哈希、原场景证明及形成时刻、当前验证时刻；重新核对场景集合（包括零权重）、权重、加权能量精度、候选输入身份及总deadline。

本轮统计故意使用比物理必要条件更强的key：同一root内完整input/config/accuracy/source不变、同scene、绝对事件边界、域OPP、基准/活动功率分项、节点漏电斜率、参考温度、外部功率完全相同；只忽略不进入ODE的active_stage_ids标签。两个不同任务标签只有在上述全部物理量相等、各自任务合法性成立时才被视作相同热输入。

## 前缀检查点要保存什么

固定事件和面板分割、初态、系数、精度及数值实现时，相同前缀生成相同区间状态。精确复制此内部状态，不额外计算任何区间外包，也不额外扩大宽度；后续传播仍承担原实现已有的区间包络累积。

检查点至少需要：

1. 规范化绝对功率前缀与完整上下文身份；covered_until、段号、面板号、面板分割及数值协议。
2. 内部缩放温升theta的Decimal上下端点、精确常量坐标；积分坐标按原面板规则归零。
3. 截至该边界的四类energy_parts、每节点node_energy、theta_integrals。后者用于最终守恒核对，不能仅存总能耗。
4. 全前缀peaks、minima、真实时间点见证、已验证模型区间、violations/seen_violation及完整覆盖状态。
5. 来源证明、预算root、原提交时刻，以及当前调用的实际新增运算计数。状态只能在原after_panel_commit完整边界保存。

**当前归档缺口明确**：trace只保存time_s、segment和输出温度区间，没有各面板累计能量、积分、峰/谷包络快照、内部theta或Taylor系数。最终场景汇总不能倒推出任意前缀。不能从温度折线做梯形积分补齐，也不能把模型重新积分伪装成只读复用。本轮只核对原轨迹，未尝试恢复检查点。

输出温度区间再减ambient、除100可能因外向舍入增加宽度；多来源包络取凸包/逐次合并会更宽。取中心或压为float则可能丢失真实解。后续原型须保留内部Decimal端点、完全相同切分，并重新检查全窗口误差目标；不能以“仍低于温限”替代能量区间精度要求。不能把复用前缀的累计误差重新清零。

## 后缀支配只提供条件界

在一个功率段，未缩放热状态满足

`dT/dt = A T + b,  A = C^{-1}(diag(lambda) - G)`。

已检代码要求C对角正、G的非对角元非正，故A为Metzler矩阵；有限时间状态转移矩阵非负，不需要额外假定A稳定。相同绝对后缀、相同lambda/b和合法模型区间内，`T_new(t0) <= T_old(t0)`逐节点成立则未来仍逐节点有序。区间充分条件为`upper(T_new) <= lower(T_old)`，比较最高温一个标量或区间仅有重叠均不够。

由于lambda>=0，热状态更低时该相同后缀的温度漏电能量也不高于旧值。但这只给条件上界：它不是新轨迹、不是新能量的高精度双边区间，也不能复用旧前缀能量。完整回执还需要峰/谷包络宽度、下侧模型有效区间和最终守恒核对；旧后缀积分与峰值证据目前也没有独立归档。

本批平台有效区间[20,100]°C，ambient=25°C。若入口各分量>=25且区间内节点功率非负，25°C可用作比较下界不变集，帮助证明下侧有效性；仍需在新的接口中绑定并验证这些条件，不能仅由“比旧状态冷”推出合法。全SAFE所要求的峰/谷区间宽度以及1e-6量级能量误差，也不会由一个保守上界自动满足。

248个搜索改变场景的88个严格公共后缀中，39个满足新冷的强区间充分关系，只说明它们值得条件审查；本轮不把这些面板计入节省量。旧完整汇总不能隔离后缀峰值和温度修正能量；仅功率函数末尾相同但切分点不同的情形，还可能没有该时刻的已存入口区间。

## 统一预算、误差与证据身份

- 当前cache属于同一CompleteRecorder/root，保留现成完整候选SAFE；不跨运行复用uuid、root_start/deadline、旧完整形成时刻。
- 增量新候选必须先验证完整候选合法性和上下文，确认组件曾在本根及时形成；新增传播、缓存验证、查找与汇总都计入同一原预算，不能缓存命中就重新开60/300秒计时器。
- 新完整SAFE仅在剩余场景、窗口、误差、有效域及汇总核对完成且当前时刻严格早于deadline时形成。旧组件时间戳作为来源保留，新完整证据有自己的完成时刻；截止后可沿原约定只读审计和转移已形成的完整证据，不能补齐未完成部分或给组件拼接结果追认旧时间戳。
- 原panels/refinements为整根累计运算计数。缓存覆盖不是新增物理运算，不能把旧累计值重复相加；若仍保留原全局panel/refinement上限，需明确“实际新增调用计数”与“证明覆盖面板数”，不静默改变停止规则。
- 本轮准入范围只有同root。跨root/进程持久缓存需要独立身份、时钟和预算契约，当前不推荐直接接入。

## 复核边界与负结果

同输入、候选SHA、上下文、原始顺序、缓存来源先于当前调用、完整SAFE在原预算内及源文件Git blob身份均核对；无新物理或方法调用。只读脚本直接使用原legality中的功率段、原trace中的已提交面板，不导入冻结评价器。

11项解释风险均检查：分层避免Simpson混合；不作生态推断；承认候选已被原方法筛选（Berkson）；不作碰撞变量调整；不推断总体命中率（基率）；无挑极端后重测（均值回归）；保留全部预算未决和零前缀（幸存者）；全量而非挑最高相似度（多重寻优）；先冻结比较口径并保留脚本修正记录（分析路径）；不把面板重合因果解释为实测提速；不从时差反推复用收益（反向因果）。这些是范围控制，非新原型正确性验收。

新科学计算：0。静态分析成功运行两次约16秒，第二次增加“同前缀温度字段/同功率场景证据完全一致”核对；此前一处脚本括号错误在统计开始前修正。没有重跑历史实验、缩短温限、替换样本、追加预算或重新认证任何候选。
