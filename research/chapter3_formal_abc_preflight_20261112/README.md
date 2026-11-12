# 完整 R1 正式 A/B/C：执行器与预验收

**已具备申请有限独立运行授权的条件；本轮未运行 A/B/C，未启动 MATLAB 或原生 MILP/LP。**

- 三组互补门控精确投影通过，A 组完整转换已补齐；B/C 数值及约简证据复核通过。
- 33 项控制/接口测试通过；正式流程各组独立构模、初始化、认证与计时。
- 每组方法证据窗 600 秒、响应截止 550 秒；原生配额在序列化后统一计算，最少 30 秒、最多 540 秒，每组最多一次请求。
- 既有 ON 返回原初解 SAFE，没有严格节能或加速结论。预验收不新增此类结论。

[研究报告与完整协议](REPORT.txt) · [冻结计划](executor/plan.json) · [冻结身份](executor/plan.identity.json) · [审批模板（false）](executor/approval.template.json)

[三组完整精确复核](checks/final_preflight_audit.json) · [控制测试](checks/control_tests.log) · [成本核算](checks/cost_accounting.json) · [证据和来源归档](R1_ABC_preflight_evidence.zip) · [成员身份](artifact_manifest.json)

归档保留 A/B/C 原矩阵、完整互补证书和所有预验收失败；矩阵中的零初始向量仅供坐标认证，不是可行见证。B 的首次字节比对失败来自 int32/int64 索引宽度，精确数值一致；C 空删除集回放分支修正后通过。正式流程不加载这些预验收计算结果。

复核：将归档中列明的 `work/` 科学来源恢复到同一研究工作区，执行器放于 `work/formal_abc_v1/`，以 `guard.verify_plan` 核对所有来源与执行器身份。纯控制测试入口为 `python -B -m unittest discover -s work/formal_abc_v1 -p "test_*.py" -v`，不产生科研求解。`preflight.py` 会重新构模，`audit_preflight.py` 是保存矩阵审计；它们不是日后每次运行之前必须重复的额外任务。

正式入口为 `run_abc.py`，必须另获绑定本计划 SHA 的新批准。它创建固定一次性目录 `work/formal_abc_execution_v1`；创建失败、错误或无调用均不可自动重试。当前没有实际批准或该执行目录。历史 ON 授权不能通过新审批校验。

600 秒是方法证据预算，清理和控制器成本另计入实际总墙钟；不能将其宣传为严格 600 秒进程硬上限。普通超时不阻断独立组；正确性、身份和清理错误按报告规定的影响范围停止。
