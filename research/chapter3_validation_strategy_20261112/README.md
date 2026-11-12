# 完整 R1 验证策略修订

本阶段只读复核保存数据并更新实验协议，新增原生调用、热评价、构模及代数变换均为 **0**。

- [成本与失败报告](REPORT.txt)：互补门控精确等价性保留，求解收益未验证，不作为正式默认表达，不重复相同 OFF。
- [A/B/C 验收规则](ABC_PROTOCOL.txt)：三组独立；普通超时不阻断其他组；全部阶段在相同总预算内完成。
- [单次 ON 提案](ON_diagnostic_proposal.json)：300 秒总窗、原生 240 秒、一次、无重试。输入和参数已绑定；**未授权、未执行**。独立单次适配器与纯控制测试须在批准执行前完成，不调用历史四槽程序。
- [机器可读复核](cost_failure_audit.json)、[来源绑定](source_bindings.json)、[只读审计程序](audit_saved.py)。261 个历史冻结文件及已发布证据 ZIP 校验通过；完整文件数和 SHA 见 JSON。

本目录不含原生实验执行入口；规范示例不是执行器测试。报告保留未知，不用内部计数、外部初解或传输层 SOLVED 状态冒充求解器 SAFE 方案。

原始依据为提交 [12bd7bd](https://github.com/YBEMR/paper/commit/12bd7bdf507d9c5f2ccb0aac0f41efad702bdd3a) 的 [互补门控归档](../chapter3_stable_expression_20261112/README.md)。此前 [严格可行性诊断](../chapter3_r1_exact_fixed_feasibility_20261112/README.md) 及 [等式配对记录](../chapter3_equality_pruning_pair_20261112/README.md) 保留原结论边界。本次仅替代未来执行策略，不改写旧冻结规则或失败事实。

复核命令：在保留既有 `work/stable_expression`、`work/equality_pair_source` 和 `work/publish_repo` 的工作区，使用 Python＋SciPy 执行 `python audit_saved.py WORKSPACE NEW_OUTPUT_DIRECTORY`。输出目录必须不存在；程序只读旧材料，写入新目录。它验证已归档证书的身份，读取四个保存 MAT 统计规模，不重新构模、求解或运行物理评价。原始大文件不重复上传；对应旧归档及来源 SHA 已绑定。
