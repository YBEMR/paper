> E2正式状态（2026-10-26）：用户单独批准后已完成4规划＋4后验，均SAFE/POST_SAFE；见[正式结果](E2_RESOURCE_EXPERIMENT_RESULTS.md)。以下准备/待批表述保留为历史，原关闭模板不改。

# E2同平台设备可用范围：实施与零科研调用预检

日期：2026-10-26。分支：`codex/e1-e4-preparation`。源码封版：`7f544b59c009f3c0a76027a4f62b5d1788d6d54d`。

**结论：四组输入、执行接线与180项静态/mock检查已完成，可交回确认正式预算；本轮真实规划、真实热评价、MILP、MATLAB和新真实SAFE均为0。** E1已结束，其授权不能用于E2。

## 1．本次要回答什么

在同一物理平台上，仅改变任务能使用哪些设备，观察完整安全调度能耗及映射/工作点/时序怎样变化。使用原R1、AB/AC完整三Stage链、真实H响应、auto-L、400 ms窗口、5 ms启动域、50°C入口、80°C温限；期限、共享部署、精度和全部物理参数不变。四组均使用同一个FULL评分的确定性改造HEFT及已有一遍局部搜索，不加入邻域或调参。

| 固定顺序 | 输入 | 任务可用设备 | 合法模式目录数 | 未来规划/最终后验上限 |
|---|---|---|---:|---:|
| 1 | `resources_CPU__R1` | CPU1、CPU2 | 54 | 300 s / 至多一次60 s |
| 2 | `resources_CPU_GPU__R1` | CPU1、CPU2、GPU0 | 60 | 300 s / 至多一次60 s |
| 3 | `resources_CPU_NPU__R1` | CPU1、CPU2、NPU0 | 60 | 300 s / 至多一次60 s |
| 4 | `base__R1` | CPU1、CPU2、GPU0、NPU0 | 66 | 300 s / 至多一次60 s |

这里的“CPU-only”指Stage只允许映射CPU。GPU/NPU仍在芯片上，空闲功耗、温度漏电及导热仍计入，不是假设移除或关断设备。即使全设备基线与E1同输入，也必须独立重新运行，不能免费复用E1安全解或热缓存。

## 2．输入差异与物理记账

[输入核对](evidence/e2_resource_precheck01/input_contract.json)以原生成器逐字段重建四组：只允许输入ID、条件/实验组标签、`ablation_input`原标签、可用设备列表及其精确筛选后的Stage模式变化。原标签在resources三项为false、base为true，只作元数据，不改变算法、约束或误差标准。响应α、时长、功率、全部合法OPP、期限/释放、场景权重、入口状态和热参数均逐字节/规范化hash核对。

四节点CPU1/CPU2/GPU0/NPU0和三个频率域全部保留。空活动片段仍计CPU/GPU/NPU低档基准0.60/0.40/0.25 W；400 ms参考温度下基准0.5 J，另有公共项0.12 J。温度修正系数完整保留，未捏造其积分值。该片段只是功率代数，**不是一套完成工作负载的安排，也不是热安全证明**。

四组均保留全部CPU模式。CPU集合分别包含于CPU+GPU和CPU+NPU，二者又分别包含于全设备；CPU+GPU与CPU+NPU互不包含。扩大合法域使精确最优值不升，但本实验是有限HEFT结果，不要求输出单调。没有安全输出时记未决/覆盖不完整，不能称已证不可行。

## 3．实现与检查

仅新增`e2_resources`输入合同、固定四槽与预检；复用原控制器时只将固定E1槽读取改为按已知协议选择。未知协议、E1/E2槽混用或旧授权scope不符都会拒绝；槽位每次返回新副本。新协议的四个真实输入身份均已静态检查；一个实际mock规划/同候选mock后验及重复消费拒绝已留档。

[源码变更核对](evidence/e2_resource_precheck01/source_change_audit.json)：原15份物理/配置依赖保持；E1搜索、评分、runner、worker、合法性和连续热核均不改。只有控制器与执行身份文件接入固定协议，运行白名单新增两个纯协议文件。E1历史结果仍绑定其原源码b509a61，未重写旧结果或伪称新代码就是当时执行版本。

[最终保护性预检](evidence/e2_resource_precheck01/precheck_result.json)：**180项全部通过**＝原120＋输入49＋协议11；耗时39.953秒。实际启动20个测试用进程，父端禁止科学函数，mock worker禁止科学模块；无真实后端进入。保留[完整测试记录](evidence/e2_resource_precheck01/mock_tests.txt)及[两个mock阶段](evidence/e2_resource_precheck01/retained_mock_summary.json)。模拟SAFE不进入论文结果。

开发期输入测试曾把原`ablation_input`标签方向写反，核原生成器后修正期望，未改输入生成器；最终49项重验通过，记录见[开发说明](evidence/e2_resource_precheck01/development_record.json)。[内部只读审查](evidence/e2_resource_precheck01/internal_review.md)通过准备范围，不替代外部审查或用户正式授权。

## 4．已冻结的正式执行提案，尚未批准

[真实清单](evidence/e2_resource_precheck01/frozen_real_manifest.json)规范化SHA256：`aa67066cbb2c216da609d14a88b67e0ec18f9c47c3c9a38e175c644ca022868d`，绑定四份输入、源码、目标和顺序；[关闭模板](evidence/e2_resource_precheck01/authorization_template_CLOSED.json)保持false。[机器提案](evidence/e2_resource_precheck01/execution_proposal.json)含准确命令与预定路径。

正式提案仍是**4次独立规划，各最多300秒；合格最终候选各最多一次60秒后验**，最多1440证据预算秒、整批1800秒日历；单槽监督420秒，根截止后最多5秒仅用于停止/归档，不增加证据时间。根从输入展开、源码校验/复制和启动之前开始；子进程导入、搜索、连续复核、评分与选择均计费。后验另起60秒根，只复核固定最终方案，不搜索或修复。

普通无改善、正常截止或NO_SAFE照实保留，可继续预定剩余槽；技术故障、身份漂移、后验矛盾停止本批。不补跑、不延长、不调整参数、温限或方法以获取优势。每次独立初始化，不共享候选/历史答案/热缓存。正式授权前不创建真实消费记录。

正式交付按四槽列全部状态、真实能耗区间及四分项、完整设备/OPP/时间表、请求完成、连续峰温、首次安全/严格改善与分段耗时。缺失不填0；单次时间不作统计稳定性结论；资源范围对照不冒称方法竞争力实验或全局最优证明。

## 5．当前位置与下一步

E1目标评分消融已收口；**E2准备完成、尚未正式运行**，本步无收益结论。main最新观察`d4afe2a`，仅主线LP诊断/正文推进，当前15份依赖未漂移；未合并、未动其输入或额度。E3/E4也未启动。

下一步只需单独批准上述E2四槽预算，再核对源码/资源冲突后执行。本阶段不再附加开发门槛；若用户不批准，则保留准备成果并停止，不复用E1授权。

复跑本次纯预检（输出必须为全新目录）：

```text
工作目录：F:/by/paper-e1-e4/research/chapter3_experiments
F:/Anaconda3/python.exe -B -m e2_resources.precheck --out <全新预检绝对目录>
```
