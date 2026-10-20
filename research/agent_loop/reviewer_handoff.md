# 给现有ChatGPT独立审查对话的交接

此文件是操作说明，不是审查结论。执行端不生成真实review，也不为外部意见补签。

1. 先读main最新`RESEARCH_BRIEF.md`、`research/agent_loop/PROTOCOL.md/config.json/requests.json`。用户报告每小时“GitHub 独立实验审查”已启用；尚不意味着写回／签名已验证。
2. 从requests取**完整subject SHA**，在该固定提交读取manifest、研究报告、提案和原始证据。不要把新review的提交SHA当subject，也不要仅按main HEAD审查。初始轮次`K146-handoff-001`承接K146只读差异分析。
3. 审查真实数据、完整SAFE、输入／源码漂移、预算与归因，决定`APPROVE_ONE_STEP/REVISE/STOP`之一。下一项只能针对该提案，不替执行端扩大域／算法／预算。
4. 在独立review分支／PR提交`research/agent_loop/reviews/<round>/<full-subject>.md`和`.json`，只写自己的文件。可以同账号YBEMR写回，但这不能独立认证；PR作者不能审批自身PR。[GitHub规定](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/reviewing-proposed-changes-in-a-pull-request)
5. 机器字段与签名参照`gate_api.md`。Markdown单独SHA256，JSON批准绑定它；真实私钥须用户在独立环境配置并保管，执行端不可取得。当前公钥／source_id/key_id为null，不要把“已读”“同意”“GitHub作者名”当成有效签名。
6. 若连接不支持文件写入、签名或PR，提交你实际能完成的审查／阻塞说明，回报用户；不要声称闸门已通过。缺预算时即使批准只读提案，也仍不得自动运行。

初始待审动作：`AUDIT_FIVE_OPEN_ONE_CLOSED_V1`，只读分析、0研究调用，拟分析墙钟1800秒，未获该项审查批准。用户随后已授权验收后科研总上限2轮/2次300秒/总墙钟2小时/北京时间2026-10-21 07:00截止，无改善或技术故障即停。该总配额不把本提案变成求解或实施许可；本项不能批准调用MILP、MATLAB或热计算，更不能实施5开1闭。下一项如确需实现／求解，另冻结提案逐项审查，且共享上述剩余配额。

外部只写真实结论。`TEST_ONLY`仅用于执行端隔离测试；不得将它混入真实reviews。真实review写回、签名和外部触发目前都需分别验收。
