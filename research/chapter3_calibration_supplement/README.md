# 28条件补充期限诊断执行入口

独立于旧校准批次。当前只完成实现、人工/模拟预检与冻结，真实执行须另获用户批准。

## 固定入口

冻结目录：[results/frozen_supplement01](results/frozen_supplement01/plan.json)。

- 28条件：16重复菱形S4＋12错峰S7，来自20个既有根。
- 每条件3份H/M/L频档参考表，总84份族表／672份场景表。
- β=1.0、1.3、1.6、2.0全部保留；不自动冻结正式β。
- 每条件60秒、整批1800秒，末10秒预留停止和留档；0重试。
- 原映射、任务响应、画像、期限来源不变；旧64份父项与对照只读，不重新构造。
- 不调用MILP、HEFT、SA或热积分，不生成正式50根，不恢复暂停实验。

以下命令只检查冻结内容，不启动诊断：

    & 'F:/Anaconda3/python.exe' -B -m research.chapter3_calibration_supplement.runtime inspect --freeze research/chapter3_calibration_supplement/results/frozen_supplement01

将来获批后，保存与plan.json字节SHA绑定的独立用户批准文件，再调用：

    & 'F:/Anaconda3/python.exe' -B -m research.chapter3_calibration_supplement.runtime execute --freeze research/chapter3_calibration_supplement/results/frozen_supplement01 --output research/chapter3_calibration_supplement/results/supplement_execution01 --approval <单独批准文件路径>

approval_template.json的approved=false；模板不能执行，也不能将本轮准备授权填成运行授权。execute与内部worker均核查计划、批准、源码、Python身份和一次性凭据；不提供续跑/补跑入口。审批文件用于记录用户批准，不是外部身份认证机制。

## 计时、状态和证据

整批从执行入口开始处理冻结协议起计时，公共源码/归档核验、逐槽公共检查、所有条件与收口都计入1800秒。每条件从目录/槽位账本准备前计时，包含Python子进程启动、worker源码核验、读档、变换、3表构造与独立合法性检查、4β统计、共同W、落盘和接纳。各条件截止不晚于整批截止前10秒。

超期是有效观察，继续下一条件；输入/来源/构造/时间结构错误、超时、迟到、非有限时钟或证据损坏均停止。余项标NOT_RUN，不计为超期或原问题不可行。若实际收口越过整批上限，标STOPPED_BATCH_OVERRUN，不追加工作。停止前已经完成的条件仍保留，批次状态与逐条件状态分开。

每条件保存call_claim、worker_claim、日志、进度、输入与完整证据gzip、摘要和result；批次保存ledger、status、28项终态与汇总。hash校验不通过的内容不进入有效比较。只处理自己启动的单个Python子进程，worker禁止再启动子进程和科学后端。

## 模块和预检

| 文件 | 作用 |
|---|---|
| protocol.py | 28清单与来源绑定、42源快照、冻结/批准校验 |
| condition.py | 原H/映射/期限核对，新增条件3表及4β共同窗口 |
| analysis.py | 精确期限统计、S4/S7配对、状态与分层汇总 |
| runtime.py | 串行一次性调度、根/条件计时、停止与留档 |
| run_checks.py | 仅人工夹具和模拟进程，拦截真实C根排程 |

[最终预检](results/preparation_precheck03/checks.json)：120项＋105条子项全部通过；包含原87项回归、新33项接口/汇总/生命周期检查。42份源快照，1290份旧源和档案前后hash一致。01临时目录权限导致10项错误；02同码118项通过；03补冻结回读及人工worker回执/重复启动检查后120项通过，记录全部保留。

可复跑人工检查，输出须使用新目录：

    & 'F:/Anaconda3/python.exe' -B -m research.chapter3_calibration_supplement.run_checks --output research/chapter3_calibration_supplement/results/preparation_precheck_NEW

S4的“合理难度”由各β下族/场景/请求准时情况、余量和β临界值描述，不设新的达标阈值。S7按相同请求的相对响应和余量比较，不能直接比较不同释放下的绝对完成时刻。参考超期不证明原优化问题无解。这里不计算能耗或温度，也不声称正式算法输入适配已完成。
