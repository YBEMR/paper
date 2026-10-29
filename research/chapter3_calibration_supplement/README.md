# 28条件补充期限诊断执行入口

独立于旧校准批次。原唯一批次已异常停止：3个S4有效完成、25项未运行，详见[部分结果](../第三章28条件补充期限诊断结果_V1_20261029.md)。当前只修复持久化并做人工测试，没有续跑授权。

## 固定入口

冻结目录：[results/frozen_supplement01](results/frozen_supplement01/plan.json)。

- 28条件：16重复菱形S4＋12错峰S7，来自20个既有根。
- 每条件3份H/M/L频档参考表，总84份族表／672份场景表。
- β=1.0、1.3、1.6、2.0全部保留；不自动冻结正式β。
- 每条件60秒、整批1800秒，末10秒预留停止和留档；0重试。
- 原映射、任务响应、画像、期限来源不变；旧64份父项与对照只读，不重新构造。
- 不调用MILP、HEFT、SA或热积分，不生成正式50根，不恢复暂停实验。

原冻结和一次性消费凭据保留。当前源码包含后续修复，因此下列只读检查预期拒绝旧冻结，报`FROZEN_SOURCE_DRIFT`；这不是原归档损坏，也不得改旧hash使其通过：

    & 'F:/Anaconda3/python.exe' -B -m research.chapter3_calibration_supplement.runtime inspect --freeze research/chapter3_calibration_supplement/results/frozen_supplement01

原批准已消费，旧输出不得重建。本次修复没有建立剩余25项的执行清单或新批准文件；后续应单独冻结续接，明确保留已完成三项、不重跑，再确认执行范围。execute与worker原有计划、批准、源码、Python身份和一次性核查保持。

## 计时、状态和证据

整批从执行入口开始处理冻结协议起计时，公共源码/归档核验、逐槽公共检查、所有条件与收口都计入1800秒。每条件从目录/槽位账本准备前计时，包含Python子进程启动、worker源码核验、读档、变换、3表构造与独立合法性检查、4β统计、共同W、落盘和接纳。各条件截止不晚于整批截止前10秒。

超期是有效观察，继续下一条件；输入/来源/构造/时间结构错误、超时、迟到、非有限时钟或证据损坏均停止。余项标NOT_RUN，不计为超期或原问题不可行。若实际收口越过整批上限，标STOPPED_BATCH_OVERRUN，不追加工作。停止前已经完成的条件仍保留，批次状态与逐条件状态分开。

每条件保存call_claim、worker_claim、日志、输入与完整证据gzip、摘要和result。修复版worker进度写`progress/000001.json`等不可变快照，总进度写`status/000001.json`等轻量快照；文件只创建一次，不使用`os.replace`覆盖旧进度，不延迟重试。快照绑定序号和内容hash，末项损坏或缺号即报错，不退回较早进度冒充最新状态。快照中的批次状态维持RUNNING，完整完成与否只由终态确认。

单次结果和终态JSON使用排他创建并flush/fsync。记录失败仍停止；已完整接纳的条件保留，余项NOT_RUN，主错误和收口错误分别保存。最终`batch_result.json`写入失败或最后落盘跨越总时钟时，另写`terminal_failure.json`并返回非零；不覆盖或重试主文件。失败标记也无法保存时向stderr报告，不能保证故障磁盘上仍有完整终态。

读取修复版终态使用`persistence.read_terminal_record(output, exit_code=实际退出码)`：失败标记优先；坏标记不得回退成功；读取COMPLETE必须同时确认退出码为0。不能单独读取可见的batch_result就宣称成功。完整结果hash与科学接纳规则不变；只管理自己启动的Python子进程。

## 模块和预检

| 文件 | 作用 |
|---|---|
| protocol.py | 28清单与来源绑定、按当前清单保存源快照、冻结/批准校验 |
| condition.py | 原H/映射/期限核对，新增条件3表及4β共同窗口 |
| analysis.py | 精确期限统计、S4/S7配对、状态与分层汇总 |
| runtime.py | 串行一次性调度、根/条件计时、停止与留档 |
| persistence.py | 一次写入、不可变进度、严格终态读取；无科研重试 |
| run_checks.py | 仅人工夹具和模拟进程，拦截真实C根排程 |

[最终预检](results/preparation_precheck03/checks.json)：120项＋105条子项全部通过；包含原87项回归、新33项接口/汇总/生命周期检查。42份源快照，1290份旧源和档案前后hash一致。01临时目录权限导致10项错误；02同码118项通过；03补冻结回读及人工worker回执/重复启动检查后120项通过，记录全部保留。

上述为修复前历史。修复首轮[01](results/persistence_precheck01/checks.json)134/134通过；补充终态读取及最后落盘预算检查后，[02](results/persistence_precheck02/checks.json)**136/136通过**，110条子项，26.882秒。44源快照、1290旧源/档案及83份本包旧冻结/执行/分析文件前后hash一致。故障注入使用人工数据和模拟worker，真实补充条件、实际worker进程、正式算法、热积分均0。新源码不能沿用旧120项回执或旧批准执行。

可复跑人工检查，输出须使用新目录：

    & 'F:/Anaconda3/python.exe' -B -m research.chapter3_calibration_supplement.run_checks --output research/chapter3_calibration_supplement/results/preparation_precheck_NEW

S4的“合理难度”由各β下族/场景/请求准时情况、余量和β临界值描述，不设新的达标阈值。S7按相同请求的相对响应和余量比较，不能直接比较不同释放下的绝对完成时刻。参考超期不证明原优化问题无解。这里不计算能耗或温度，也不声称正式算法输入适配已完成。
