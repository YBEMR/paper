# D280：唯一一次保存 C_noheur 观测诊断

**单次批准已消费：O0/O1 通过，O2 未建立；没有新调度或严格节能。**

按 D279 冻结计划启动 1 个 MATLAB、进入 1 次 intlinprog，原生 MaxTime=519 秒。完成根 LP，报告下界 0.7452555210277564，返回完整双场景 SAFE；23780 维向量全部等于初解，能耗仍约 **1.0848863713 J**，0 个报告节点，无独立最优性证明。

Profiler 收到 219 个函数和 2306 条历史事件，未截断。历史时间戳呈毫秒粒度，冻结的三标记偏移区间相差 0.8224 ms、无共同交集，未在事后放宽验收。主要函数耗时仍在受保护 slbiClient 中，不能区分割、探测 LP、分支及数值处理。Python 工作进程的 CPU/读取开销和重复读事件路径另行披露，尚不能据此认定原生停滞的原因。

科学快照于 550.985 秒封存，真实总墙钟 554.438 秒；5 个自有进程均退出，25 项只读核对通过。实际 0 次 R1 构模、0 次独立 LP、2 次完整评价、0 次重试。

**按协议停止参数扫描和重复观测，不提出缺乏 O2 依据的参数干预。** 本次没有证明更优调度不存在或 MILP 路线不可行。研究目标仍是不同原生调度、合法、完整 SAFE、严格降低完整能耗。

- [报告：结果、异常、成本、未知项及停止决定](REPORT.txt)
- [运行审计](audit.json)、[只读语义复核](semantic_review.json)
- [本次已消费批准](approval_consumed.json)
- [原始执行与保存输入 ZIP](raw_execution.zip)、[逐文件身份](raw_artifact_inventory.json)、[归档验证](delivery_verification.json)
- [审计代码](audit_root_tail_observation.py)、[语义复核代码](review_root_tail_observation.py)
- [交付校验和](SHA256SUMS)

主体为 [D279 冻结提交 223097d](https://github.com/YBEMR/paper/commit/223097d2749249552087cca42336dda3ab2dd49a)，计划 SHA-256 为 fa49d83b3252108de870e3930739ceb3a27cfc56b65d03ec4decf7cb5aa8f0bc。执行账本已消费，禁止复用。

字段解释依据：[MathWorks R2023b profile](https://www.mathworks.com/help/releases/R2023b/matlab/ref/profile.html)。未解码或分发 MathWorks 受保护源码。
