# K147：交接基础设施验收

**当前结论：可交接、可检测、可做隔离审批测试；尚不能真实无人值守科研。** 真实开关保持关闭。用户已确认外部小时审查任务启用，随后授权最多2轮、2次×300秒、累计600研究秒、总墙钟2小时、北京时间2026-10-21 07:00截止；这些新配额已登记，不等于审查／身份／执行链验收。

| 能力 | 状态与证据 |
|---|---|
| 原研究状态交接 | `K146-handoff-001`保存已有差异分析与唯一只读提案；没有新实验 |
| 固定提交／hash | manifest绑定输入、关键研究源码、原档案、报告与提案；requests另提交完整subject SHA |
| 只读检测 | [monitor测试](validation/monitor_unittest.json)25/25通过，另修工作流上下文后[新增静态2/2](validation/workflow_static_unittest.log)通过；review提交本身不使旧subject失效 |
| 签名／一次消费／分布式争用 | 见[gate测试](validation/gate_unittest.json)和[TEST_ONLY端到端](validation/test_only_e2e.json)；仅隔离Git／本地bare，无真实批准 |
| 代码审计 | [基础设施静态审查](validation/infrastructure_review.md)，非用户外部ChatGPT研究审查 |
| GitHub连接 | 已核执行账号YBEMR及仓库push/admin；Actions运行列表GET 200；保护规则读取403，不推定无保护 |
| GitHub检测器真实运行 | [实际运行39451499057](https://github.com/YBEMR/paper/actions/runs/39451499057)手动触发成功，输出WAITING_REVIEW、real_experiments_started=false；[回执](validation/github_success_receipt.json)。定时／PR触发尚未观测，也不是本聊天唤醒证明 |
| 外部审查写回／验签 | **未观察、未配置真实公钥**；同YBEMR不能提供GitHub角色隔离 |
| Windows/MATLAB无人值守 | 只有本机文件／进程／服务只读探测；未启动MATLAB、未测许可，未安装受控runner |
| 本聊天自动续接 | 先前格式失败后，采用正确RRULE前缀的**每小时、最多6次**heartbeat创建成功、ACTIVE；[配置回执](validation/heartbeat_receipt.json)。这是已配置，尚未实测唤醒，依赖本机／App运行；不是每15分钟本机实验循环 |
| 真实执行 | **关闭，0研究调用、0 MATLAB/LP/MILP/热计算**；许可机制未接入旧科研CLI，不能宣称硬进程截止已实现 |

## 明早看什么

1. 待审入口：[requests](requests.json)、[已有研究交接](rounds/K146-handoff-001/experiment_report.md)、[下一项只读提案](rounds/K146-handoff-001/next_proposal.md)。`5开1闭`没有获得实施／求解许可。
2. 外部对话应依据[交接说明](reviewer_handoff.md)在真实`reviews/<round>/<subject>.md/.json`写回。执行端没有创建该目录或其中任何文件，测试approve只在临时库。
3. 需要用户／独立审查环境配置真实角色认证：独立私钥保管、固定公钥／source ID、仓库外可信配置SHA。不能让执行者自己生成审查私钥再“批准自己”。若外部ChatGPT无法完成签名，这是一项实际接口缺口；应先讨论可验证的替代，不将未签意见强行接纳。
4. 还需受控执行adapter和实际本机续接链验收。GitHub hosted Linux检测器不能直接调用这台Windows的MATLAB；没有部署self-hosted runner。公共仓库若部署本机runner，须限制受信代码、账号／文件权限、进程清理和许可，不运行不受信PR。

## 本轮失败记录

- 默认沙箱的本机系统查询／MSYS本地Git transport受限；只读环境探测及**隔离TEST_ONLY测试**分别经自动审批允许的提升权限完成。不是研究方法失败。
- 初版监测测试mock断言错误、测试临时目录权限问题保留于[失败记录](validation/failure_history.json)；修复后只重跑相关基础设施测试。
- 静态审查发现空远端账本误重置、CAS期间到期／字节漂移、配置字段／签名域不一致等，按审计记录修正；不能用初版通过代替最终凭据。
- 本地续接：前两种有界格式返回无未来运行，DTSTART直接创建被参数规则拒绝；永久版本自动审批拒绝，理由为超出截止范围。随后以正确RRULE前缀创建最多6次的安全替代，并核配置原样含COUNT=6；永久版本没有创建，不声称已实测唤醒或后台科研。
- 首次GitHub工作流上下文无效、手动HTTP422，以及ignored MAT误列Git对象依赖已留档；修为step级输出、10份本地MAT哈希单列、304份已发布证据绑定。新冻结subject为`d103c9b28a2c1e0e66bb5b13f38546af6f5abb2f`；不能沿用旧subject `091a963…`批准。

本轮不修改物理输入、算法或旧实验结果；不因为没有真实自动科研结果而补跑。真实批准、执行器和唤醒没有全链验证前，只能等待并报告阻塞。
