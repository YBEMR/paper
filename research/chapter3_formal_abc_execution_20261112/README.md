# 完整 R1 A/B/C：批准的一轮已完成

**C 取得根 LP、原生有限下界及原生 SAFE 返回；返回内容仍为共同初解，没有严格节能。A/B 普通超时、最终向量为空。**

| 组 | 原生 MaxTime | 根 LP 完成证据 | 原生返回完整 SAFE | 严格能耗改善 | 实际总墙钟 |
|---|---:|---|---|---|---:|
| A：期限过滤 | 438 s | 未观察到 | 未建立 | 未建立 | 549.266 s |
| B：加选项支持传播 | 472 s | 未观察到 | 未建立 | 未建立 | 547.437 s |
| C：再加联合状态剪枝 | 456 s | 269.657 s 进入 heuristics | 是，同初解 | 否 | 548.969 s |

C 原生下界 0.7452555210277564 J，非独立严格证书。返回完整能耗约 1.084886371303711 J，与共同初解区间完全相同；无新调度、无最优性证明。可以据此报告本轮第二级剪枝的原生进展增益，不能写成节能、可靠加速倍数或普遍求解能力结论。

实际 3 次独立构模、3 个 MATLAB 会话、3 次 intlinprog、4 次完整双场景评价；总墙钟 1646.156 秒。无调参、无重试、无额外 LP 探针。各组重新初始化与认证，全部准备成本已计入；普通超时未阻断后续组。授权已消费，全部科学运行停止。

- [完整研究报告](REPORT.txt)、[分层结果汇总](RESULTS.json)、[完整成本](COSTS.json)
- [60项执行审计](audit/audit.json)、[16项原生文件身份核对](audit/native_artifact_audit.json)
- [冻结方案](../chapter3_formal_abc_preflight_20261112/executor/plan.json)、[已消费批准](evidence/approval_consumed.json)、[批次回执](evidence/batch.json)
- 分组十层证据：[A](evidence/A/layered_scientific_evidence.json)、[B](evidence/B/layered_scientific_evidence.json)、[C](evidence/C/layered_scientific_evidence.json)
- [完整矩阵、精确证书、原生 MAT/JSON、回调、初解与 SAFE 证据包](R1_ABC_execution_evidence.zip)、[成员身份](artifact_manifest.json)、[包内校验和](SHA256SUMS)

A/B 的结束回调计数为1、最终输出计数为0且返回空向量，差异如实保留，不以计数代替候选。15个已观察自有进程均退出，218个科学来源/输入和19个执行器文件身份不变。审计只读归档，没有追加求解或热评价；未来运行须重新明确目标并另获授权。
