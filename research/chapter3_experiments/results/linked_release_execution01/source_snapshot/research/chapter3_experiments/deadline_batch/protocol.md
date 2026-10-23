# K162：β=1.0期限组准备与纯预检

材料信息（Material Passport）：academic-research-suite / experiment-agent；2026-10-22；PREPARATION_NOT_EXECUTABLE。

本阶段只准备输入、派发参数和存档检查，不构造MILP、不调用优化器、MATLAB或热积分，不生成研究候选。允许手写TEST_ONLY夹具及模拟方法返回；夹具不是新增研究实例。依据最新独立综合报告第6节优先准备期限压力，保持旧科学源码、原参数和连续热安全标准。

## 输入与比较范围

- 仅 `beta_1.0__R1`—`R5`，相对P0原H响应/50°C入口/80°C温限，期限系数1.3→1.0。
- 期限为 `release + beta * reference_CPU_H_chain_ms`，参考链长继承样本时长缩放，不是异构设备最短时长。R1—R5的A/B/C相对期限依次为95/121/110、76/145.2/110、114/96.8/110、95/96.8/132、95/145.2/88 ms。
- 逐输入只允许13处差异：id/condition_id/experiment_group、settings/deadline_beta、两场景各两请求的relative_deadline_ms/deadline_ms，以及既有清单派生的ablation_input标签由true变false。该标签只标原消融清单成员，不控制本批算法/物理模型或新增消融；保留生成器原值。模式表、释放、依赖、权重、完整三Stage链、全部资源、共享部署规则、OPP、400 ms窗口、5 ms合法启动集合、真实非整数结束、auto-L、局部温度漏电、四节点功热及误差门不变。
- 未来各方法独立重新加载并计费；不从P0/P1/P2读取候选、锚、温度缓存或预算外答案。P0的β=1.3只作冻结后报告中的既有条件参照，不重跑或充作免费初始化。本阶段不添加β=0.8/1.6/2.0或新的扫描。

## 方法及存档接口

科学派发与P2逐字一致，仅修改输入入口模块名；224份继承源码哈希保持。整体MILP、预消元4开2闭联动、HEFT和SA101—105保留原参数/能力，场景片60秒、反馈轮限10，MATLAB启动和全部阶段均在未来同一300秒根时钟内。没有新的初始化模板、回补、邻域或求解选项。

本阶段只增加两个结果审计门：

1. 已存完整SAFE候选须用本次实例再作精确资源/依赖/逐请求期限检查；不热复算、不改原记录、不补U。旧期限回执或只换问题ID不能绕过当前期限。非法最终候选不可保留为可排名U；非法已接纳中间候选阻断继续执行。
2. 联动真实结束标识 `NO_COMPLETE_SAFE_LINKED_SEED` 仅在本次三模板尝试完整有据、输入/源码身份正确、无原生请求及硬故障/数值异常、预算内完成时，登记为正常方法终止且无U。不等于配置/完整域不可行，不造最优或无解证书。热数值未分辨、缺失记录、异常身份和技术故障继续阻断；不得只看reason字符串放行。

正常时限无U、求解器报告无解、未找到安全种子、已知违规、热未分辨和技术故障分别保存。无U不填0能耗、不参与安全解能耗排名；正常无U不自动补跑或增加初始化。正式批量停止规则需在将来的实际启动协议中绑定本阶段审计能力；本阶段没有真实launcher。

## 待授权的调用提案

五题各整体/联动/HEFT一次、SA五种子各一次，共40槽。每槽300秒，拟方法预算12000秒、日历19200秒；尚未授权/预留/消费。顺序沿P0/P2五题方法块轮转，SA101→105固定。将来420/480秒停止监督和一次60秒post仅用于隔离/已有完整SAFE复核，不延长300秒证据窗口。无SAFE不补搜索或热积分来凑U。

准备声明 `authorised_to_execute=false`，ledger消费/预留0，无claims；CLI `run`始终拒绝。取得独立预算后再新增实际执行层、一次消费与日历监督并预检；不能只把false改为true。

结果拟报完整SAFE取得率、共同成功配对能耗、逐请求最小期限裕量、工作点/能耗组成、首SAFE/首次严格改善、MATLAB启动和两阶段实际耗时。独立L0、solver-reported界和最优状态分列。五种子单次和分布均保留，不用五次最佳值冒充单次300秒。β=1.0与既有1.3仅支持这一段期限收紧比较，不宣称多点单调规律或预设联动获胜/反馈触发。

## 完成与停止

输入逐字段对照、精确期限边界、40槽模拟派发、原结果合同回归、紧期限终态、当前期限SAFE门及漂移/非法授权预检全部通过后，生成独立输入/源码快照和冻结草案；旧失败检查目录不覆盖。同步研究状态及证据记录、提交普通推送，然后停止于准备完成、待实际执行预算确认。

复跑入口（每次用新目录）：

```text
F:/Anaconda3/python.exe -B research/chapter3_experiments/deadline_batch/prepare_deadline.py precheck --out research/chapter3_experiments/results/deadline_precheck_新编号
F:/Anaconda3/python.exe -B research/chapter3_experiments/deadline_batch/prepare_deadline.py prepare --checks 上步/checks.json --out research/chapter3_experiments/results/deadline_preparation_新编号
F:/Anaconda3/python.exe -B research/chapter3_experiments/deadline_batch/prepare_deadline.py inspect --out 上步目录
```
