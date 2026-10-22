# K163原始2/40停止前缀：只读结果核对

状态按原归档记录：STOPPED_PROCESS_OR_WORKER_FAILURE；仅R1整体MILP和联动被消费，38槽尚未启动。方法根时钟600.016秒，监督日历633.406秒，预留/消费600方法秒；没有补跑或追加研究调用。本报告不判断将来续接是否成功。

| 已调用方法 | 原归档执行状态 | 原完整SAFE回执U/J | 原回执形成/s | 当前期限审计 | 既定post | 原状态下可比较U/J |
|---|---|---:|---:|---|---|---:|
| 整体MILP | NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST | 1.084886371304 | 69.625 | 通过 | PASSED | 1.084886371304 |
| 联动MILP | TECHNICAL_FAILURE_CONFIRMED | 0.880088064994 | 255.156 | 通过 | 未执行 | — |

原始records.current_schedule_audit两份均passed=true；第二次不是请求期限检查失败。其context.hard_errors只有MISSING_MATCHING_ROOT_CANCEL_FILE；cutoff_audit.applied=true而cancel_file_verified=false。原数值检查和输入/源码身份已通过，原SAFE见证仍由回执保留，但执行接纳被阻断且未作post。因此原停止时只能列2份完整SAFE回执、1份post通过/可比较，不能写2份post通过或已完成公平配对。取消标记的严格解释和派生终态由独立接口审计另行处理，本报告不改原分类/记录。

整体和联动最终安排的最小逐请求期限裕量分别40 ms与0.4 ms，均由已存真实非整数结束作精确Fraction减算；没有热重算。两份SAFE曲线末值均与原U一致，认证L0均1152169123/1560600000 J、未闭合且没有L0高于U异常。存档反馈0、热违规评价0。HEFT与全部SA均未启动，不能填零能耗、不能把0/5当5次失败，不能作方法排名或推广安全率。

联动同次阶段记录保留：第一段179.250秒，安全能量从约1.080823451833降至0.962985514894 J；第二段119.797秒，继续降至0.880088064994 J。MATLAB启动分别整体57.047秒、联动48.719秒，首次SAFE分别69.625秒、0.844秒。阶段下降仅描述该次原回执，不是等预算机制消融；联动末U尚未通过此停止前缀的post/完整对照接纳。

[40槽保留表](results40.csv)、[分组表](cohorts.csv)、[精确请求裕量](request_deadline_margins.csv)、[阶段表](phases.csv)、[原始状态与硬错索引](facts.json)以及[复核过的图](plots_reviewed01/plot_review.json)保存。analysis01是初版提取，未覆盖；analysis02明确分开原回执U、可比较U、post、已调用/未启动及硬错。图中联动虚线是已存原SAFE回执的运行最小上界，标注未完成对照接纳；其余未启动面板没有伪造零能量。

20项手写纯夹具通过，新增阻断但保留U与未启动SA分母边界；validation02.json保存本次核对和脚本hash。本轮新求解/热积分/post/候选/能耗U均0。若将来通过独立取消审计和补原定一次post，再建立带原/派生状态与来源分列的分段视图；不能改写本停止前缀或预先宣告续接成功。
