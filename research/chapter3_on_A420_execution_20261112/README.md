# 完整 R1：420秒方案唯一 ON 诊断

按用户对 `aa1dde93be928d82de17ccf775f789e80d60cc75` 的明确批准执行。原生上限240秒、方法总窗420秒、响应截止370秒；**一次已完成，授权已消费，无重试、无A/B/C**。

| 验收层 | 本次证据 |
|---|---|
| 原生入口 | 1次intlinprog，实际MaxTime=240，exitflag=2，时间限制停止 |
| 根LP | 226.407秒收到rootlp，226.688秒收到heuristics；完成有后续阶段证据 |
| 下界 | 0.7452555210277564 J，超过平凡界0；原生报告，非独立严格证书 |
| 候选 | 返回23780维向量，与回调向量一致 |
| 完整SAFE | 原／新行准入及完整双场景评价通过，312.422秒完成 |
| 新调度／节能 | 与共同初解同调度、同能耗区间；没有严格改善 |
| 实际成本 | 方法312.422秒；含清理和控制器收尾320.516秒 |
| 完整性 | 26项执行审计、5项候选核对通过；已记录自有进程全部退出 |

本次增加了“保存ON可取得原生求解进展”的证据；没有证明重复稳定性、全局最优、互补表示优势或剪枝加速。不能与历史OFF拼成性能对照。正式ABC仍需独立构模、共同表达及全成本执行器冻结，另行批准。

- [完整报告](REPORT.txt)
- [执行审计与完整成本](audit.json)
- [候选身份核对](candidate_identity_audit.json)
- [收尾进程核对](postrun_process_check.json)
- [原始文件绑定](source_bindings.json)、[包内校验和](SHA256SUMS)
- [原生MAT无损归档](execution/matlab/native_mat_artifacts.zip)、[归档成员及原字节SHA](binary_artifacts.json)：遵守仓库不直接跟踪MAT的规则，未强制添加忽略文件。
- [事后只读审计代码](audit_run.py)
- `execution/`：一次性批准及消费记录、实际请求矩阵、原生MAT/JSON输出、回调向量、完整SAFE评价、时间账本和清理证据。

## Material Passport

类型：已批准的代码诊断执行记录；研究对象：完整auto-L R1保存ON互补门控模型；来源：冻结提交aa1dde9及本包原始文件；状态：EXECUTED_ONCE_AND_AUDITED，未重复运行。核验仅检查本次来源、设置、时限、候选归因和记录完整性，不代表独立最优性认证。执行批准的原文及计划SHA保存在execution/approval_consumed.json。
