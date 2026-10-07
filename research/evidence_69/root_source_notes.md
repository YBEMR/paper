# 69号主核查：来源边界与检索记录

日期：2026-09-27。只读论文、官方说明及公开仓库；未执行推理、调度搜索、性能测试或热仿真。

## 阅读范围

| 来源 | 本次实际核查 | 限制 |
|---|---|---|
| [HeteroInfer，arXiv:2501.14794v2](https://arxiv.org/html/2501.14794v2)，2025-10-04；SOSP 2025，DOI [10.1145/3731569.3764808](https://doi.org/10.1145/3731569.3764808) | §3、§4.2–4.4，§5.1、5.7–5.8、§6；HTML正文及公式 | 已在15号/E35读过，本轮复核，不算首次发现。主要计算对象GPU–NPU，CPU是控制面。§4.4的目标已含同步与copy项；§4.3已有持久共享buffer与睡眠后轮询，不能说忽略交接。Table 3有性能示例，不等于成套CPU–NPU模式、功率与RC库。未取得本论文配套源码/原始profile入口。 |
| [Is Your NPU Ready for LLMs? Dissecting the Hidden Efficiency Bottlenecks in Mobile LLM Inference，arXiv:2607.05475v1](https://arxiv.org/html/2607.05475v1)，2026-07-06 | §3.1、3.3–3.4，§5.1、§7.1–7.3、§8，正文及Table 8标签 | 预印本；也是15号/E35旧来源。PowerBench按QPT power zones计量，不能把框架名称当测量边界。§7已有调用/轮询/休眠及主机调频优化，不再把该关系单独立题。冷却隔离协议不证明持续热失效；Table 8为estimated。本次未取得PowerBench原始数据包。 |
| [Intel Open Edge Platform 2026.1官方说明](https://docs.openedgeplatform.intel.com/2026.1/edge-ai-libraries/dlstreamer/dev_guide/heterogeneous_systems_guide.html) | Overview、Platform、Workload Distribution Strategy、Case 2/3、Key Takeaways、Notes and Caveats | 新增非论文直接来源。说明共享SoC功率预算，实例中NPU启用伴随GPU频率变化；页面自身限制为特定pipeline。不能把TDP管理等同热阈值触发，不能把示例定性表当BIDENT同设备同工作负载参数。 |

上述两篇旧论文均有可读公开正文，不需要用户重下。未以网页搜索到的同名GitHub项目作为代码证据：`yang123-cloud/bident`研究网络流量检测，与推理BIDENT无关。

## 重点检索词

本轮采用定向检索，并非系统综述。实际关键词包括：

```text
CPU NPU heterogeneous inference scheduling memory contention profiling energy thermal paper 2024 2025 2026
"CPU" "NPU" "contention" "inference" "scheduling"
"concurrent" "NPU" "power" "scheduling" thermal energy inference
"concurrent" "package power" "NPU" inference
"inference" "thermal" "switching cost" heterogeneous configuration
"CARIn" "current" design switching energy
"CARIn" "switching" "energy" heterogeneous inference transition current design
"BIDENT" "package power" concurrent
"BIDENT" heterogeneous operator mapping github dataset
"Is Your NPU Ready for LLMs" PowerBench code
"Characterizing Mobile SoC for Accelerating Heterogeneous LLM Inference" paper code
```

两组子核查的题名/作者/仓库检索及原文定位见同目录notes。BIDENT检查v1后发现v2，采用v2修正范围；不是两篇独立论文。

## 筛读账本

深入核查固定为6篇：BIDENT、HaX-CoNN、CARIn、Phoenix、HeteroInfer、Is Your NPU Ready。HaX-CoNN、Phoenix、后两篇已在旧记录中出现，不能包装成全新发现。以下额外来源只作题名/摘要/出版页筛读，不据此判断正文遗漏：

| 来源 | 筛读处置 |
|---|---|
| [When NPUs Are Not Always Faster: A Stage-Level Analysis of Mobile LLM Inference，2026](https://arxiv.org/abs/2605.27435) | 阶段偏好已有测量线索；框架/精度/设备不匹配，不与另一LLM论文拼成一套数值。 |
| [Phase Matters: Characterizing Heterogeneous Vision-Language Inference on a Mobile SoC，2026](https://arxiv.org/abs/2606.27906) | 仅筛摘要，不据此提出额外热机制。 |
| [arXiv:2607.16473，eNPU，2026](https://arxiv.org/abs/2607.16473) | 硬件/控制条件与当前无硬件条件不匹配，未深入。 |
| [Multi-dimensional scheduling parameter search for efficient multi-model inference on underground mine edge devices，2026](https://doi.org/10.1016/j.eswa.2026.132563) | 出版页摘要提示并发、优先级与NPU分配已有搜索；未查全文，不断言其温度/功率缺失。 |
| [Inference framework supporting parallel execution across heterogeneous accelerators，2025](https://doi.org/10.1016/j.sysarc.2025.103508) | 出版页摘要，批处理/异构加速已有直接方法；不恢复旧批方向。 |
| [PartitionTuner: An operator scheduler for deep-learning compilers supporting multiple heterogeneous processing units，2023](https://doi.org/10.4218/etrij.2021-0446) | 检索摘要/出版入口；只作算子映射已有工作的提示，不借摘要判遗漏。 |
| [Multi-objective reinforcement learning scheduling framework for heterogeneous AI chips: Energy-efficient and latency-aware edge-cloud collaboration，2026](https://doi.org/10.1007/s44443-026-01248-7) | 旧Shao材料再次命中，本轮不重读、不计新候选。 |

新来源筛读按论文去重至多8篇：CARIn、BIDENT及上述前6项；深入6篇（包含4篇旧来源）。检索返回但未纳入筛读的专利、博客、综述聚合与同名项目不作为论文事实证据。官方说明另计1项。无新增第7篇正文深读。

## 反证边界

- 现有“固定模式能量与时序无关”的结论依赖61号的活动功率可加等假设；新候选只能审查其适用范围，不推翻原条件证明。
- 公共基准重复属于计量问题；若修正是所有方案的同一常数，不会改变排序。不能凭此宣称并发活动功率有非加性交互。
- 主机在NPU执行时有开销，不等于该开销无法预先纳入合法模式；单一联合表或现有调度可能足够。
- 同一时刻的package能量/功率不能给出CPU、NPU各自注热；缺节点边界时只能做条件性热推导。
- 两篇LLM来源、Intel官方示例与BIDENT的硬件/软件/粒度均不完全相同。本轮只配对机制，不拼接实测平台。
