# 完整R1机制复核与三次有限实验

**B/C阶段差异有限重现；关闭C启发式仍只返回共同初解，没有严格能耗改善。**

| 试验 | 原生MaxTime | 根LP完成 | 原生返回完整SAFE | 不同调度且严格改善 | 实际组墙钟 |
|---|---:|---|---|---|---:|
| C复核，basic | 451秒 | 是 | 是，同初解 | 否 | 550.953秒 |
| B复核，basic | 454秒 | 未观察到 | 空向量，未建立 | 未建立 | 547.906秒 |
| C单因素，none | 473秒 | 是 | 是，同初解 | 否 | 549.453秒 |

B/C整数变量均1125，C删除2938个连续联合状态及29380条条件物理行。保存矩阵核对支持C松弛嵌入B，不能称同一LP或只比较整数数量。C的两个最终23780维原生向量均与初解逐坐标相同；下界均0.7452555210277564 J，未独立严格认证。有限重现不是可靠加速倍数或一般成功率；本次单因素策略未通过优化收益验收。

实际3次新构模、3个MATLAB会话、3次intlinprog、5次完整双场景评价，0独立LP/重试。总墙钟1648.703秒；44项控制测试、125项执行审计、42项原生核对通过。已停止科研调用，独立一次性授权已消费。

- [完整报告](REPORT.txt)、[调用前冻结方案](PLAN.txt)、[结果](RESULTS.json)、[完整成本](COSTS.json)
- [新冻结执行器与计划](executor/plan.json)、[已消费授权](evidence/approval_consumed.json)、[批次回执](evidence/batch.json)
- [矩阵机制分析](analysis/mechanism_readonly_notes.txt)、[原生事件与候选分析](analysis/native_readonly_notes.txt)
- [执行审计](audit/audit.json)、[原生文件审计](audit/native_artifact_audit.json)
- [全部科学证据包](R1_mechanism_trials_evidence.zip)、[成员身份及排除清单](artifact_manifest.json)、[交付校验和](SHA256SUMS)

已披露[未触发的停止范围边界缺陷](analysis/mechanism_latent_scope_review.txt)。本轮三份回执均无相关故障，累计范围审计通过；冻结包不回写、不复用。未来复用控制框架须修复并测试该分支，不能以现有测试数代替这一验收。
