# 同预算ON-P认证复用验证 SIC20261115

完整结果见REPORT.md；执行前协议见PROTOCOL.md。frozen/和reuse/是已核对的不可变来源副本，不需下载完整历史实验。运行环境：Windows 11、Anaconda Python 3.12.4；执行路径只使用Python标准库。全部参数及原ON-P规则保持。

实际批次分为execution/首槽和continuation/剩余11槽。首槽搜索正常结束后的内存统计故障、缺失字段、用户授权续跑及唯一统计接口修复见CORRECTION.md。两阶段原始状态分别保留；不要把execution/的停止记录改写成成功。当前support.py包含已验收修复，原版本保存在versions/v1/。

本目录源码固定后，正式12槽一次运行，每槽300秒、初始化准入180秒；外部监督330秒。预计方法总预算最多60分钟，另计启动、纯归档和只读审计。不要并行运行额外科学任务，不重用输出目录，不删除失败后自动重跑。

```powershell
python -B -X utf8 batch.py prepare --out reproduced
python -B -X utf8 batch.py run --out reproduced
```

prepare检查本轮已保存的接口验证及冻结来源；run再次检查代码/协议身份。需要独立重做接口检查时，test_interface.py的--archive参数使用0de4d19下U07 ON-P的原method/result.json，仅供有限测试；正式worker不读取该文件。检查点内核的前轮43项测试位于52c3370提交的incremental_certification_20261115/tests_v2。

每槽method/result.json及分片保存原方法结果；journal.jsonl记录实际生成的评价调用与接纳；numerical_calls.json记录精确数值语义身份；summary.json记录最终完整SAFE、初解、成本与内存。最终/初始回执保留完整trace；其他评价trace及合法性正文以精确摘要压缩。archive.read_result可按文件哈希复原分片结构；不能从输出折线恢复检查点。

本轮停止后的检查只有合同、身份和统计核对，不额外启动完整热传播或搜索。各臂独有候选没有独立无缓存物理复评；同候选交集采用精确语义一致性核查。原始负结果、技术故障及未开始槽均应保留。

只复算本次已归档结果时，在本目录运行下列命令；不会启动搜索或热传播：

```powershell
python -B -X utf8 reporting/analyze.py .
python -B -X utf8 reporting/build_report.py .
python -B -X utf8 reporting/test_interval_analysis.py
```

repair/recover_saved_evidence.py可重做首槽只读恢复，保留原数值结果并将不可恢复的CPU/内存字段标未知。repair/continue_batch.py是本次明确授权的单次续跑入口；已执行输出目录不可覆盖，不作为自动重试工具。所有原始运行代码身份由各阶段freeze.json约束；reporting/是停止后的派生统计，不进入搜索调用。
