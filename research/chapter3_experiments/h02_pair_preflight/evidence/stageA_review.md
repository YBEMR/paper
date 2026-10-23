# H02阶段A实施与审查回执

**结论：阶段A静态与mock预检通过，可回交独立协议审查。正式研究调用0，新真实SAFE 0；没有启动阶段B。**

## 1．版本与实际范围

- 主线固定起点：`20fb232a81d69782b8ebd1fc1972a6bc96fff09e`；独立实现分支：`codex/h02-stage-a`。
- 三份协议均取探索分支`f63cc4f8c5ceb7161a15ce55c6cf610081482f30`。H02/H02R/H03 blob及sha256见[source_manifest.json](source_manifest.json)，原文快照位于`../protocols/`。
- 开始核对时远端main为指定起点；交付前main推进至`e93c32aa5aeaec1a743a36d967713b7fcf3df0f8`。逐一核查12份指定源码、AGENTS和直接依赖，均未变化；新增的是另一条linked-ablation/release研究材料。继续保留20fb基准，未合并／变基／覆盖主线。后续源码提交SHA在同目录manifest及本次Git交付记录中绑定。
- 仅新增本目录。原配置、主线数学核、旧档案、A03/A04及`agent_loop/reviews`均未改写；没有读取历史最优方案或热缓存作为输入。

## 2．A6交付核对

| 交付 | 实际结果 |
| --- | --- |
| [source_manifest.json](source_manifest.json) | 12份主线文件sha256、三个协议blob和字节hash、Git基准／非影响性漂移 |
| [paired_inputs_audit.json](paired_inputs_audit.json) | R1/R2各66模式；逐字段diff、R α全1、精确时长／活动能量公式、模式支持和场景／物理／策略／精度身份 |
| [static_monotonicity_contract.json](static_monotonicity_contract.json) | 每题9组静态核对通过；有限参数前提与数学推论分列，不签发SAFE |
| [mock_isolation_tests.json](mock_isolation_tests.json) | 121项unittest通过，含一个具有17项访问／反馈断言的R-only子进程测试；本次无真实计算守卫违规 |
| [adapter_source_manifest.json](adapter_source_manifest.json) | 薄接口及测试文件sha256、调用图、源码清单；原核不变 |
| 本报告 | 已实现范围、失败修正、内部审查和阶段B待办 |
| [run_ledger.json](run_ledger.json) | `real_heft_calls=0`、`real_h_thermal_audits=0`、`research_calls=0`、`new_safe=0`、`formal_budget_authorized=false` |

原始candidate hash沿用主线canonical JSON对象口径：键排序、保留行列表顺序及原值类型；不是原始JSON文件空白的hash。semantic hash另按scene/Stage排序、将起点精确有理数规范化。两者不可互相替代；语义相等不授权改写候选。候选只含四字段Stage、设备、OPP、绝对起点，不能携带预测结束或能量。

## 3．数学合同：核对结果与推论分开

本次**实际计算**仅是有限参数的精确有理数比较：H α∈[0,1]、f≤f_ref、q非负且H/R逐值相同；C>0、被动接地G、Metzler非对角；基准分配非负、CPU域只计一次；各档基准／局部漏电斜率非负且非递减；auto-L立即降档且零开销；入口50°C、环境=漏电参考25°C、20—100°C模型域、80°C温限、400ms、5ms起点域、0.30W外部只计电能及原精度。

P1的条件推导为：

`d_R-d_H = d_ref (1-alpha)(f_ref/f-1) >= 0`。

对**同一个完整R合法候选**保持设备、OPP、绝对起点不变，H执行区间逐项包含于R区间，故依赖、期限、互斥和同域兼容不变差。该推论不能比较两个不同搜索结果。

P2中H有活动时域工作点与R相同、空闲时回L，故逐节点非温度热源u_H≤u_R、漏电系数D_H≤D_R。令theta=T−Ta，正系统使theta_H≥0；差值z=theta_R−theta_H满足：

`C z' = (-G+D_R)z + (D_R-D_H)theta_H + (u_R-u_H)`。

同入口z(0)=0与比较原理得到theta_H≤theta_R；完整R-SAFE轨迹因而在此模型内蕴含同候选H安全及E_H≤E_R。模型下界由theta≥0保证T≥25>20，上界仍以R完整SAFE为条件。**静态PASS不代表实际运行过热核，不保证搜索成功或后验预算内数值可判，也不代表H规划必胜R规划。**

## 4．实现及失败修正

- R config、模式α与均值均遮蔽为1，时长和活动能量重算；列表外差异、重复／缺失／错序模式、错误功率、网格、期限、RC均拒绝。原全条件R构造的`Duplicate effective condition`作为负例保留，未改主线构造器。
- 控制端绑定固定源码真H、公开packet、实际静态合同、物理及精度身份；R loader仅捕获公开字节，不捕获truth、Registry或后验回执。H/R目录、输入副本及Recorder缓存独立。
- 导出`CandidateRecorder.best`，不是最后SAFE或search私有候选；并列保留最先接纳者。严格拒绝等于截止时刻的SAFE，保留截止前已形成但晚返回的完整证据。
- 后验根预算先于输入hash／候选解析，唯一token在任何预算检查前消费；失败、提前耗尽均不允许重试。无candidate不调用评价；未决不当违规；R模拟明确H违规触发单调性异常并停止。
- 内部独立代码核查发现：真实核可能将内层数值／资源故障归成顶层普通未决或POINT_WITNESS。已增加递归技术状态检查，两接口共用；既有见证保留、故障单列、STOP锁定。增加相应mock回归。
- 首次114项预检有UTF-8子进程解码及类定义误拦两项测试故障；第二次因守卫逐调用构造路径开销过大人工停止，只停止核实命令的本次mock进程。均保留在`precheck_attempts/`。修复后118项通过，补齐根预算及回执边界后121项最终通过；不抹除旧失败。

## 5．审查性质、风险与后续边界

本报告是执行端自查，加一个子代理的只读代码核查；**不是用户原独立对话的协议批准**，没有写入`agent_loop/reviews`。内部意见中嵌套技术故障问题已采纳；末次只读复核未发现修补引入新错误。

已实现／已预检：三薄接口、纯输入与数学合同、mock完整回执、截止／一次消费、R公开视图与应用层拒读、异常停止。

未运行／未证明：真实HEFT规划、真实H后验、热轨迹、实际120/60秒执行、科研SAFE／节能率／排名／最优性。字面测试候选未获真实合法性证明；身份核查不等于资源／期限／热安全核查。

R-only worker的Python audit hook只证明应用层访问合同，不是OS权限隔离。真实backend尚未配置；阶段B仍需另行冻结工作进程读取边界、真实热核接入、计费内输入读取／模式展开及数据交接、120/60秒根预算和外部墙钟监督。不得把mock生命周期测试当成这些真实环节已验收。

**建议：值得申请阶段B协议复核，当前无须改物理模型或新增科研案例。先交由用户安排独立审查；即使本次全部PASS，仍不得启动四次120秒规划及最多四次60秒真实H后验。**
