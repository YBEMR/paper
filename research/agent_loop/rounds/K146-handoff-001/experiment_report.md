# K146交接：已有方案差异分析，等待外部审查

本轮只是K.146已有只读分析的交接，不是新实验。原始研究提交为`701ffa4d5e7dbd45bfba548cda4a50e8bc8b8f25`；本交接冻结提交由`requests.json`登记完整SHA。状态：`RESULT_COMMITTED → WAITING_REVIEW`。真实实验开关关闭。

## 结果与出处

| 项目 | 已存事实 | 原始入口 |
|---|---|---|
| 任务与实际调用 | K146只对比已有数据；研究、优化器、热评价均0次 | [K146事实](../../../chapter3_experiments/results/linked_heft_gap_analysis01/facts.json) |
| 联动完整SAFE | K142 U=0.962885037941 J | [K142结果](../../../chapter3_experiments/results/fair_comparison_preparation01/linked_n1/result.json) |
| HEFT完整SAFE | K145 U=0.881087997281 J | [HEFT结果](../../../chapter3_experiments/results/heft_sa_followup01/heft/result.json) |
| 账面差异 | 0.081797040660 J；活动0.056607632、基准0.020300000、温度修正0.004889409 J，公共项不变 | [组成与完整安排](../../../chapter3_experiments/results/linked_heft_gap_analysis01/summary.md) |
| 搜索范围 | 首遍固定A/pre，二遍开放A/pre但固定本地main/post；HEFT精确方案不在两域 | 同上，及manifest绑定的源码 |
| 可靠性范围 | 原AB/AC三Stage、共享A具体单元、400 ms、5 ms起点与精确结束、auto-L及连续热标准保持 | manifest输入、源文件与存档回执 |

K142与K145是不同批次，以上是方案账差，不是同期四方法排名或单因素因果。K142联动第一遍219.953秒，二遍含准备77.687秒、无新增完整U；MATLAB启动72.297秒已计费。K145 HEFT正常完成43.250秒，首完整SAFE1.125秒，首严格改善12.266秒，最终U在43.234秒形成。K146没有重新求解、解码、热计算或产生新SAFE。方法级全部成本、完整Stage安排、400 ms及尾段热回执、四节点峰值、分项、原生请求／预算截止／末候选未决均沿用原档案，**不把K146的0调用写成原研究成本为0**。

## 原始证据与局限

- [K142执行及分析](../../../chapter3_experiments/results/fair_comparison_preparation01/execution_k142/summary.md)、[K143预算分类](../../../chapter3_experiments/results/budget_end_review01/summary.md)、[K145执行](../../../chapter3_experiments/results/heft_sa_followup01/k145_summary.md)保存原计时与连续SAFE证据；由manifest绑定原结果及其报告。
- 已存10次解码LEGAL、6次场景评价SAFE，0热拒绝，二遍仅发布warm；这不证明域穷尽、热反馈增益或延长预算必有收益。
- K140同seed设备曾达到0.910240996773 J，说明设备固定仍有已知空间；不能把全部差距归因于设备选择。
- L0未闭合，局部solver-reported状态不是全域最优证书。旧档案不改写，不拼接四法对照。
- 本执行端内部代码审查不等于外部ChatGPT审查。当前没有由外部审查方写入的真实批准。

唯一待审事项见[next_proposal.md](next_proposal.md)：先只读核查“5开1闭”的决策范围和成本，不批准实现或运行。

## 发布边界补充

原301份本地旧工件的未变检查包含被.gitignore排除的MAT二进制。它们不强制上传，不作为云端可读取证据；本地哈希单列于validation/local_only_unpublished_artifacts.json。机器manifest只绑定本提交实际存在的源码和结构化JSON/CSV/报告。外部可核已发布数据，但不能据此声称已读取未上传原生MAT。首版将本地文件误列为Git对象依赖，已修正并保留失败记录；没有修改原档案或补跑。
