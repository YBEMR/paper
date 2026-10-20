# GitHub研究执行—外部独立审查协议 v1

本机制先验收，真实执行关闭。用户随后已授权验收后有界科研：最多2轮、累计2次×300秒、总墙钟2小时、北京时间2026-10-21 07:00截止，无改善或技术故障即停，不补跑；此预算不替代任何准入门。执行端只报告、提案、校验和消费批准；用户原有另一段ChatGPT对话负责审查。子代理的代码审计不是该审查方。用户已确认该对话启用了每小时一次的“GitHub 独立实验审查”；尚未观察其GitHub写回和身份验签。GitHub每15分钟的任务只检测，不生成批准、不求解、不唤醒聊天。

## 1. 身份和权限

双方GitHub账号均为`YBEMR`。已核连接账号与仓库push/admin权限；GitHub不能用同账号PR自审建立角色隔离。分支保护接口读取被集成权限拒绝，实际保护状态未知。仅靠作者名、committer、`approved=true`或两个会话自称独立均不够。

本地闸门采用**独立审查私钥签名＋执行端事先固定公钥／配置hash**。`review_source`默认未配置；真实审批失败关闭。私钥必须由用户／独立审查环境保管，执行端不可接触；本轮没有生成或配置真实私钥。受信配置SHA通过仓库外环境`AGENT_LOOP_TRUSTED_CONFIG_SHA256`固定；改变配置必须人工重新授权，不从仓库自动接受新hash。公钥只能验证谁持有密钥，不能证明其科学判断正确。

同一管理员仍能改仓库、服务器规则或本地程序；这是软件协议及密钥保管约束，**不是对管理员不可绕过的隔离**。现有旧科研CLI尚未统一接入本闸门，本轮没有真实受控runner；不能宣称已阻止所有直接手工运行、复制permit或研究进程超时。真实执行适配／硬时限监督必须另验收后才能启用。

执行端不得创建、修改、删除`research/agent_loop/reviews/`中的任何文件。目录由外部审查方首次提交时创建，执行端不放`.gitkeep`、示例或测试。测试签名在隔离临时Git库中，决不作为真实审批。

## 2. 固定提交与文件契约

| 文件 | 写入方 | 作用 |
|---|---|---|
| `config.json` | 执行端，经用户确认冻结 | 开关、来源、公钥、次数／时间／停止上限；本轮均未启用 |
| `requests.json` | 执行端 | 待审轮次与完整subject SHA路由；不是批准 |
| `rounds/<round>/manifest.json` | 执行端 | 提案、报告、源码、输入和证据SHA256；唯一动作与上限 |
| `rounds/<round>/experiment_report.md` | 执行端 | 实际证据、计时、SAFE、失败与局限 |
| `rounds/<round>/next_proposal.md` | 执行端 | 仅一项任务、范围、预算与验收 |
| `reviews/<round>/<full-subject-sha>.md/.json` | **仅外部审查方** | 人类报告与机器结论，身份签名绑定 |
| `refs/heads/codex/agent-loop-ledger` | 机械闸门 | 独立追加账本，CAS争用、消费、预留与停止 |

报告／提案／manifest在一个提交中冻结，随后另一提交仅更新`requests.json`的完整SHA，避免SHA自指。批准绑定**原subject**，不绑定漂移的main HEAD。外部审查新增提交本身不失效；当前工作树被绑定文件与原subject不一致、原证据／输入／关键源码变化，才拒绝旧批准。审查文件不能被追加入被审查的源码hash清单。动态路由、验证日志也不能反过来改写已冻结证据。

优先外部独立分支／PR写回：只提交自身两份review，目标为main，先核原subject和hash。合入main后执行端读取，不因review新提交误判失效。同账号的PR形式仅方便diff，不提供GitHub强隔离。若外部连接只能直接写main，仍需绑定签名且不得改报告／证据；写入能力未实测前保持关闭。

JSON字段以[gate API](gate_api.md)为准。至少包括`schema_version/mode/repository/config_sha256/approval_id/round_id/subject_commit_sha/manifest_path/manifest_sha256/proposal_sha256/report_md_sha256/review_report_path/review_report_sha256/evidence_class/decision/approved_action/action_kind/allowed_scope/max_calls/per_call_budget_seconds/total_budget_seconds/wall_clock_limit_seconds/expiration/review_identity/signature`。缺项、重复JSON键、NaN、坏路径／hash／签名均拒绝。review Markdown的hash独立于研究report hash。

`decision`只允许`APPROVE_ONE_STEP/REVISE/STOP`。动作、路径范围及预算必须与提案完全匹配；`ANALYSIS_ONLY`研究调用预算全为0。没有签名密钥时外部可以写真实审查意见，但它只能是待核报告，**不会转成机器批准**。不要自行给它补签。

签名算法Ed25519；payload为除`signature`外JSON的UTF-8规范序列（key排序，无空白，非ASCII不转义，不允许非有限数），前置`agent-loop:REAL:v1\0`。TEST_ONLY前缀为`agent-loop:TEST_ONLY:v1\0`；模式、公钥来源、账本和临时远端隔离。不能只改一个布尔值把测试批准升级为真批准。

## 3. 状态、一次性消费与预算

`RESULT_COMMITTED → WAITING_REVIEW → APPROVED → READY → RUNNING → RESULT_COMMITTED`；`REVISE/STOP`阻断。APPROVED是有效意见，READY还要求身份、hash、未消费、预算、截止和环境门全部通过。检测器不产生READY。

1. 读取最新配置、待审项和Git证据；不根据旧K编号自动继续。
2. 校验真实来源签名、原subject、当前内容及动作／预算，检查所有上限非null且授权。审查尚未响应时停在WAITING_REVIEW。
3. 在独立Git账本生成唯一子提交，普通fast-forward push作为CAS。两个执行端从同parent争用，最多一方成功；失败／网络结果不明不给许可。不得force或自动重试成新批准。
4. claim一次性消费approval并预留整项预算；发每次permit先增加计数／扣预算，再次检查状态、有效期、剩余时间。崩溃残留RUNNING不自动释放／退款／重跑；费用按预留保守保留。
5. stop锁存到同一账本；无许可的读、校验和报告可以继续，新的研究调用禁止。当前实现把签名REVISE也锁存，且没有reset/resume接口；只能在明确范围内非实验修订，之后须人工重新验收／配置恢复，不能凭新批准自动复活旧账本。机器闸门不把普通建议解释成新任务。
6. 未分类I/O、权限、数值、载荷、清理、完整性故障先停；不能因时间到期豁免真异常。用户现已授权连续无改善／失败阈值1；未来受控adapter须以可核查结果调用结算，门禁自身只计数，不判断科学收益。

用户最初选择先验收、后预算；随后明确授权上述2轮/2次300秒新阶段，config已登记新上限、600秒累计研究预算、7200秒总墙钟、UTC `2026-10-20T23:00:00Z`截止和失败／无改善阈值1。开关仍false，公钥、真实来源与执行链未验收。旧K127的6小时/8次不能继承。总墙钟从首次获批claim开始，不能通过新进程重置；截止以先到为准。即使已有审查意见，未完成其它前提仍不得运行。

未来预算包括加载、初始化、MATLAB启动、构模、全部原生请求、回调／缓存、完整连续热复核和聚合。检查点／封存／清理另列，不补新SAFE或能量。保留预算内完整SAFE和末候选未决，不追加60/300秒、不重跑已消费调用。当前permit只是预留凭据，真实执行监督尚未实现；到期后不能凭permit自称已可靠硬杀进程。

## 4. 每轮研究交付最低内容

报告列任务、授权、源码输入与重要hash、完整AB/AC三Stage安排、具体设备／OPP／起点／精确结束、完整400 ms及尾段热回执和四节点峰包络、完整加权能耗与组成、初始化／首SAFE／首严格改善／最终SAFE、MATLAB启动／构模／复核／聚合／清理成本、原生候选／接纳／异常／热反馈／末候选未决、失败和未取得结果。

提案仅一项，给出必要性、现有依据、改变与不变项、调用和预算／墙钟、成功／失败／无改善／技术异常、成本及失败后的停止规则。`5开1闭`当前仅分析建议；初始交接提案也仅只读审查，未获实现或求解授权。

保持完整AB/AC、共享A具体单元、400 ms、5 ms起点与精确结束、auto-L、原功耗／温度漏电／四节点RC、原DVFS／资源／依赖／释放／期限／数值门。热约束筛选、初始化、局部搜索、外层热反馈分别归因。内部gap、局部最优不写成全域证书；不同批次不拼同期排名。

## 5. 检测、唤醒与本机边界

工作流`agent-loop-watch.yml`每15分钟、手动或PR事件检测。只checkout默认分支受信脚本（固定action SHA），contents:read，输出状态artifact；不执行PR代码，不调用ChatGPT、不写review、不启动runner或研究。GitHub调度可能延迟／遗漏，不能当精确计时器。[GitHub说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

用户已报告外部审查任务每小时启用；其是否能读全文、写文件、保管签名密钥、事件触发，须通过一次真实写回证明。执行端无权冒充该聊天。Work的GitHub事件型任务适用于符合条件的web/mobile，官方文档不支持从桌面端配置该触发；本轮未证明本聊天会被GitHub事件唤醒。[Work任务](https://learn.chatgpt.com/docs/automations)

本机有Windows、Python和MATLAB可执行文件；本轮不启动MATLAB、不测许可。未观察到runner服务／Runner.Listener，不能假定云Work能访问本机文件／进程／许可。桌面本地定时任务依赖机器开机且App运行；云端任务不因此获得Windows连接。若以后选self-hosted Windows runner，需用户配置专用机器／服务、最小权限、受信工作流、许可和进程截止；本公共仓库不能运行不受信PR代码。[自托管配置](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners)、[安全说明](https://docs.github.com/en/actions/reference/security/secure-use)

## 6. 验收与真实启用顺序

先在专用`.runtime/agent_loop_tests`隔离Git库完成TEST_ONLY提交、签名、消费、重复／并发、过期／漂移、RUNNING残留、STOP测试，不触碰真实reviews。然后真实仓库只测试**检测器**。机器／网络失败原样记录，不编造“自动化已启用”。

真实启用还需：外部审查实际写回；独立密钥或其他经重新设计验收的角色认证；仓库外可信配置锚；受控执行adapter及截止／故障结算；实际Work唤醒或受控本地运行链通过。预算使用本次已授权剩余配额，不再重复索取，也不延后截止。未满足时检测照常运行，执行继续关闭。审查任务已启用不替代其中任一项。

入口：[外部审查交接说明](reviewer_handoff.md)、[验收报告](ACCEPTANCE.md)、[检测器API](watch_api.md)。本轮只交付基础设施，不产生新研究结论。
