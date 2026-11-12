# 唯一一次 ON 执行结果：原生调用前停止

用户批准执行 [7b723b1](https://github.com/YBEMR/paper/commit/7b723b13bae842eed95b33a6f5f2e1aea0775096) 的冻结方案。实际结果为 **`INSUFFICIENT_FIXED_CAP_RESERVE_NO_CALL`**。

MATLAB启动65.844秒后，总窗只剩228.953秒，不能保留原生240秒及10秒预留，因此按原计划停止。**没有调用intlinprog；这不是ON求解失败或“ON无进展”的实验结果。** 一次性记录已消费，未补跑。

- [完整报告](REPORT.txt)：成本、初解证据、未测指标及结论边界。
- [只读审计](audit.json)、[证据身份](source_bindings.json)、[审计程序](audit_saved_run.py)。
- [原始执行回执](execution/receipt.json)、[控制器](execution/controller.json)、[耗时](execution/timing_after_cleanup.json)。
- [实际批准](execution/approval_consumed.json)、[完整初解评价](execution/initial_complete_evaluation.json)、[正常清理](execution/matlab/closed.json)。
- [冻结执行器与方案](../chapter3_on_diagnostic_executor_20261112/README.md)。

完整初解评价1次、两个场景SAFE；原生请求／优化调用、新构模、变换、重试、正式A/B/C均0。方法累计71.047秒，含控制器收尾87.359秒。源文件与执行器未变；启动耗时的具体来源未知，ON原生数值表现仍未测试。下界、gap与候选无求解器产出，不填虚构数值。

`controller=COMPLETED`表示流程正常结束；`evidence_integrity=NOT_ESTABLISHED`表示缺少原生传输和选项身份，均不作求解成功或源数据损坏解释。原始记录不修改。初解与保存数组不构成新的优化收益。

复核：在原工作区执行 `python audit_saved_run.py WORKSPACE NEW_OUTPUT_DIRECTORY`。审计仅读取既有文件、计算哈希及核对已存数字，不运行求解器、物理评价或构模。归档只含科学回执与运行控制证据，不上传MATLAB偏好或临时缓存。
