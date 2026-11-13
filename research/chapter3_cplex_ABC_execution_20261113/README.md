# D284 正式 A/B/C 执行结果：控制入口失败，未进入科研计算

**状态：CONTROL_ENTRY_FAILURE。** 用户授权的单次批次已经消费；A 在受控进程内读取冻结提交身份时 Git 启动失败，B/C 按全局停止规则跳过。没有构模、CPLEX 对象、求解或热评价，没有自动补跑。

- [完整报告、分层结果、成本与未知项](REPORT.md)
- [一次性批次原始回执](execution/batch_receipt.json)
- [A 原始异常](execution/A_controller_stderr.log)
- [原始批准及主机启动](launch/approval.json)
- [只读停止审计（16 项）](analysis/summary.json)
- [纯 Git 受控入口复现](analysis/git_probe/receipt.json)
- [同限额直接 Git 主程序控制](analysis/git_direct_probe/receipt.json)

基线冻结提交：558a7726eedf82c1578bd3700dc81758aab2c4e5。两个纯 Git 控制不构成科研重试，未改变冻结执行器。当前不能将本轮解释为 CPLEX 数值失败或约简性能结果；修复入口并重新冻结后，需要新的独立执行授权。
