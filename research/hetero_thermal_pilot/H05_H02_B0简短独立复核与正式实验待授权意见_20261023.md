# H05：H02 B0技术封版简短独立复核与正式实验待授权意见

**审查日期：2026-10-23**  
**审查方式：GitHub只读核对源码与交付证据；未运行测试、HEFT、热评价、优化器或新科研调用。**

## 1. 冻结身份与范围

- 仓库：`YBEMR/paper`；B0分支：`codex/h02-b0`。
- B0实际实现源码提交：`7fd5db8991524dd469b29cf77f479c00c3932c1e`；最终交付HEAD：`f68787efaa3a2231eac21628d0c07a989d7e2978`。交付HEAD相对实现源码提交仅补充三份证据manifest/元数据，未改变Python与策略代码。
- 固定主线科学基准：`20fb232a81d69782b8ebd1fc1972a6bc96fff09e`；阶段A交付：`6f622b3db3c26bb4f8cb34882bff4723f307da5c`；上一轮独立审查H04：`ee4d15a7c09b605f58996e2c643f681837908d12`。
- [B0技术封版报告](https://github.com/YBEMR/paper/blob/f68787efaa3a2231eac21628d0c07a989d7e2978/research/chapter3_experiments/h02_pair_b0/evidence/B0_%E6%8A%80%E6%9C%AF%E5%B0%81%E7%89%88%E6%8A%A5%E5%91%8A.md)；[交付清单](https://github.com/YBEMR/paper/blob/f68787efaa3a2231eac21628d0c07a989d7e2978/research/chapter3_experiments/h02_pair_b0/evidence/delivery_manifest.json)；[228项回归证据](https://github.com/YBEMR/paper/blob/f68787efaa3a2231eac21628d0c07a989d7e2978/research/chapter3_experiments/h02_pair_b0/evidence/regression_tests.json)；[零调用账本](https://github.com/YBEMR/paper/blob/f68787efaa3a2231eac21628d0c07a989d7e2978/research/chapter3_experiments/h02_pair_b0/evidence/run_ledger.json)。

## 2. 限定三个检查点的独立判断

| 检查点 | 核对结果 | 结论 |
| --- | --- | --- |
| **原H与近似R规划数据隔离** | `controller.prepare_public_slot` 每槽从同一冻结H问题构造并通过阶段A白名单/静态合同检查；R公开packet的config/profile/mode及均值α被置为1，只改变响应及必要派生值；原H保存在控制端私有目录。planner worker只接受对应视图，源码bundle不携带原`config_v01.json`、H真值或历史结果，文件访问白名单与独立目录阻断普通应用层误读；后验不向planner回传。 | **通过，限定为受信固定Python源码的应用层隔离；非OS抗恶意沙箱。** |
| **真实后端调用与结果接纳** | `backends.resolve_real_bindings` 显式绑定原`heuristic_runner.execute_heuristic`、改造`heft_method.run_heft`、`thermal.evaluate_candidate`、`schedules.validate_schedule`；规划使用自身视图。`exports.verify_final_export`核对预算内`CandidateRecorder.best`、来源、方法、输入、SAFE、能量上界及candidate身份；真H后验独立重建原样候选，按严格SAFE回执验收。`classification`仅对六类可重算的资源/时间/DAG违规发`TRUE_H_INVALID`，其余畸形/策略/未知错误归接口异常；R真H可信违规触发单调性异常。 | **通过；实际真实HEFT/连续热运行性尚未测量，不构成B0阻断。** |
| **120秒规划、60秒真H后验预算及异常停止** | `controller` 在每槽输入展开/模式投影/进程启动前创建120秒parent `RootClock`；后验在封存H读取/解析前独立创建60秒根时钟；worker继承同一monotonic origin，`anchored_budget_class`不能重置预算。严格拒绝形成时刻`>=120/60`的SAFE；watchdog 50ms轮询，截止后5秒归档宽限不增加研究预算，超时终止/异常/身份错误锁STOP且不补跑。授权ID、槽位和worker claim一次性消费，gate当前明确关闭。 | **通过。720秒是方法+后验预算总和，不是OS总墙钟硬上限。** |

## 3. 证据与边界

已核对B0源码`controller.py`、`worker.py`、`backends.py`、`exports.py`、`classification.py`、`budget.py`、`boundary.py`、`bundle.py`、`io_contract.py`、`policy.json`、`execution_gate.json`，及原阶段A输入隔离源码；对照`regression_tests.json`与`run_ledger.json`。提交记录中的**228项静态/mock回归均PASS，protected计算body进入记录为空，正式研究调用0、新真实SAFE 0**。本会话不冒称独立执行过这些测试；真实后端虽已接线但并未真正运行。首次真实实验是否按时生成SAFE/数值是否收敛，必须以正式实验自身回执为准。

没有发现影响本次三个验收范围的**明确实质性阻断问题**，因此不提出新的模型、算法、测试或技术开发任务。现有威胁模型明确排除同账号恶意native代码/OS沙箱，不应在报告中拔高安全保证。

## 4. 复核签署

**B0可验收，建议停止技术开发并进入待授权的H02正式实验阶段。**

此处的“进入待授权阶段”仅指技术封版完成、可以向用户申请**独立明确的阶段B授权**，**不等于已经允许启动研究调用**。保持原H02的四槽`R1/H → R1/R → R2/R → R2/H`，每槽120秒、各最终规划SAFE候选最多一次60秒真H后验，最多4次规划与4次后验，共720方法/后验预算秒；不得换题、改模型、改算法、免费修复或追加调用。应继续保留`execution_gate.json`与`policy.json`中的禁止执行状态，直到用户单独明确批准并按冻结授权合同办理。

**审查结束；本会话未修改main、codex/h02-stage-a或codex/h02-b0分支，不运行正式科研调用。**
