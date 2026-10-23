# K171：P0联动法每次构模的实际选项域回放

结论：**可精确恢复R1—R5共20次构模的实际Stage—设备—OPP—起点列域**。独立脚本只读原归档，用标准库与有理数枚举标签并执行已存声明的交集；503项核对通过，0构模、0优化、0热评价、0新候选／研究调用。

入口：[facts.json](facts.json)、[可复跑脚本](extract_domains.py)。脚本默认拒绝覆盖，可用`--output <新文件>`重算。原69份读入文件及11份相关生产源码前后hash不变；源码与P0原执行、续接两份声明均一致。

## 1．恢复的域与原过滤

逐次按原顺序恢复：原始合法模式及release/grid/window起点 → 共享部署设备预滤 → N1或linked条件 → 期限删项 → 第二阶段闭锚删项。

| R | 阶段 | AB最终列 | AC最终列 | 本阶段期限删除AB／AC | 本阶段闭锚删除AB／AC |
|---|---:|---:|---:|---:|---:|
| R1 | 1 | 167 | 137 | 289／309 | 0／0 |
| R1 | 2 | 216 | 213 | 647／655 | 64／61 |
| R2 | 1 | 198 | 137 | 252／309 | 0／0 |
| R2 | 2 | 153 | 166 | 670／699 | 107／70 |
| R3 | 1 | 135 | 137 | 329／309 | 0／0 |
| R3 | 2 | 227 | 240 | 616／606 | 77／74 |
| R4 | 1 | 135 | 163 | 329／274 | 0／0 |
| R4 | 2 | 204 | 214 | 665／638 | 60／75 |
| R5 | 1 | 198 | 110 | 252／343 | 0／0 |
| R5 | 2 | 177 | 196 | 626／672 | 121／62 |

全部构模合计：邻域交集后13783标签，原期限预滤已删9489，余4294；第二阶段闭锚已删771，最终3523列。全部3523列上界为1，**没有保留在矩阵中但被期限设为ub=0的列**。这些原先已删的标签不能计作后续新下界剪枝收益。

第一阶段每场景开放B／C的main、post；所有设备由本次fresh seed固定，其余OPP和起点按seed关闭。第二阶段每场景开放A的pre、main、post及B／C的pre；所有设备仍取原seed，关闭的B／C main、post取第一阶段最后完整SAFE代次的OPP和起点。开放copy保留该固定设备上过滤后仍存在的OPP／起点。

闭锚过滤只执行原规则：同设备重叠、同域不同OPP重叠、开放前驱越过关闭后继起点、开放后继早于关闭前驱终点；开／开组合关系仍由MILP约束处理。第一阶段没有预先执行闭锚删项，不能事后把其冲突标签当原已删列。

## 2．供下界回放消费的字段

`facts.builds`以`build_key=(case_id,phase_index,scene_id)`标识，共20项：

- `phase_condition`：两个场景全部copy固定的具体设备，以及关闭copy的OPP；不加入起点，不锁定另一场景开放copy的当前OPP。
- `opened_rows`、`closed_rows`：copy／shared／request身份，设备、关闭OPP／起点及来源；`modes`中列明每个实际残留(unit,opp)的`options_nonzero`、精确`starts_ms`、0基`option_columns`。y列位于辅助列之前。
- `counts`：原合法模式展开、共享设备预滤、邻域交集、期限实删、闭锚实删、剩余列、ub0列分别登记。
- `warm_rows`与`all_scene_warm_options`：**条件锚**，第一阶段为seed，第二阶段为冻结的第一阶段完整SAFE锚。
- `actual_x0`：该build实际归档的局部初始化candidate、source、局部candidate hash、来源完整snapshot hash、数值接纳及注入状态。没有重构x0数值向量或重新热验。20份局部candidate均属于精确恢复的列域，且局部标签均与对应条件锚相同；完整snapshot hash仍单独保留，不把全局代次视为相同。

原phase condition、每copy邻域计数、期限删量、闭锚逐条removals、闭锚输入／输出全选项hash、剩余列及事件数均重现；最终变量／二元变量／行数与原日志互核。**辅助矩阵未重构，总变量及行数只是原日志与原摘要互核，不是重新构造验证。**

## 3．时间及证据边界

`first_build_log_at_s`来自option_expansion第一条日志，晚于进入builder；`model_completed_at_s`为原构模返回时间，另存`phase_started_at_s`。原函数入口精确时间未保存。拟论证“构模前已有U”的反事实删项时，不能把构模中或构模后才形成的U倒用；需结合原时间线，采用能保证早于builder入口的已成完整U。

这是**实际物化标签域**，不是全部联合可行调度集合、连续热安全证明或新算法加速证据。未实施新剪枝、未改原生产代码／参数／结果、未运行研究。

## 4．源码与开发记录

- 原起点展开：`inputs.py:268—320`；共享设备／邻域／期限／闭锚交集：`milp.py:785—881`；期限ub0另在`milp.py:1097`。
- N1成员规则：`neighborhood.py:199—237`；linked成员规则：`linked_neighborhood.py:128—165`；闭锚冲突：`anchor_preelimination.py:17—151`。
- 构模及实际初始化归档：`neighborhood_method.py:345`起；第二阶段锚冻结：`linked_method.py`的`linked_condition`。
- 首轮`facts_run01.json`保留20个失败：脚本错误预期每build只有一条MODEL_CONSTRUCTED。实际`milp.py:1119`报告complete时observer记一次，`neighborhood_method.py:357`的finish再记一次；两条物理计数相同。修正为核对原双记录及其一致性后，最终`facts.json`503项全通过，未改任何原日志。

最终facts SHA256：`f2683170584bd44363111f55c307d7a5fbcbb9df94a0ca7bc4651b2b218ef876`。脚本SHA256：`9c693818a554361aa9a62bb0baa6cda333722a44770693d0b63aef80f0e98641`。
