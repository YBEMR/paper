# D285 审计补充
继承 D284 的分层科研验收、完整成本与停止规则。新增核查：
1. 对照 control_git 的绝对路径与 hash，核验 entry_git_summary.json 中每一条读取的命令、时间、退出码、预期/实际 blob hash及原始字节文件。所有读取必须在 550 秒前完成。
2. 非零退出、timeout、OSError 的 stdout/stderr 残片必须保留；不得用后来成功的读取覆盖原始异常。
3. 检查 entry_failure.json / 早期未领取目录错误回执，确认科学工作进程确未创建，错误累计为全局停止。
4. 对照 outer_job_limits / outer_job_accounting，活动进程上限仍为 2、内存仍为 3.5 GiB，最终活动进程为 0；内层维持 1 进程与 3 GiB。
5. 控制模式必须独立目录，claim 标记不消费科研批准，所有组结论只能是入口验证；不存在 worker claim、owned_process、runtime 或 native_response。
6. 后续科研仍要求完整新构模和评价；本轮真实入口控制不能代替它们。全局停止的批次进程应返回非零退出码。

