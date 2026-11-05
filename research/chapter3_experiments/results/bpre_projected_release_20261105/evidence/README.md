# B.pre 精简 MILP：最小公开证据包

本目录是 `bpre_projected_retry_20261105T071312Z` 的 **sanitized 脱敏提取副本**，不是原始日志的逐字节归档。原文件未改动；原字节 SHA-256 与本公开副本 SHA-256 分开记录在 `provenance.json`。只读检查通过，未运行求解器、模型构建、SAFE 或任何候选回放。

## 证据入口

| 要核查的事实 | 文件 |
|---|---|
| 实际完整回执提交时刻及三候选 | `receipts/committed_000001.json` 至 `committed_000003.json` |
| 在线 HEFT 的原始初解及完整 SAFE | `receipts/online_heft_initialisation.json` |
| 原 8,887 维到 8,341 维的代数映射 | `native/request_000001.projection_certificate.json`、`projection_equality_certificate.json` |
| 3 次 callback 的完整数值向量 | `native/event_000004.json`、`event_000006.json`、`event_000007.json` |
| 原 23 个非时间选项及实际报告 | `config/frozen_reference.json`、`native/request_000001.response.json` |
| 预算耗尽、迟到拒收、命令 UTC | `logs/delivery_extract.json`、`logs/observations.jsonl`、`logs/no_late_admission.json`、`logs/run_command.json` |
| 原完整进程身份树退出与最终无 MATLAB | `logs/closed.json`、`logs/host_final_check.json` |
| 3,185 项冻结源文件的相对路径及原 SHA | `code/frozen_source_sha256.json` |
| 本次 13 份适配器、启动/配置代码及测试源码 | `code/*.py`；原 SHA 见 `config/execution_manifest.json`，脱敏后 SHA 见 `provenance.json` |
| 输入、构建选项、根时钟和范围 | `config/` |
| 本次只读独立核查及完整性清单 | `audit_checks.json`、`scan_report.json`、`SHA256SUMS` |

三份 `committed_*` 来自原 `method/result.json` 的 `/diagnostic/evaluations`，包含落盘后追加的 `admission_committed_at_s`：**82.594、110.281、112.000 s**。单独存档的早期 receipt 文件还没有提交时刻，不能把其落盘视为采纳。对应完整 SAFE 形成时刻分别为 82.375、109.890、111.734 s；三者均恢复到 8,887 原坐标，检查全部原行、逻辑，再完成各场景 SAFE。数值行检查本身不等于热安全证明。

最终可采纳上界为 **0.861090900049153263666417840495489072146136748487968498035907 J**。本次在线 HEFT 上界为 **0.920195499983960944974381976769171389159940855612137674194178 J**，严格区间改善为 **6.423048%**。这是完整独立 SAFE 的可行上界，不是全局最优证明。回执中的 `formal_experiment_result: false` 原样保留；`legality.thermal_status: NOT_EVALUATED` 属于逻辑子检查，其后顶层 `evaluation.state: SAFE` 与每场景 `complete: true` 才是完整热评价结果。

截止后约 **602.531、602.640、602.875 s** 首次读取到末尾事件与响应：这里只记录观察时刻，不推断精确发布时刻，不接受迟到候选。原生 `status: SOLVED`、`exitflag: -1`、bound/gap/nodes/time 原样保留为 solver-reported；Python 接纳结果仍为 `BUDGET_EXHAUSTED`，总执行状态为 `NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST`。

清理为 `graceful_closed`，耗时 **10.922 s**，已捕获的 3 个原生进程身份均退出，最终主机检查无 MATLAB。原运行命令 UTC 为 **2026-11-05T07:14:39.463008+00:00 → 2026-11-05T07:25:02.727341+00:00**，耗时 **623.264969 s**、exit 0；600 s 科学预算以根单调时钟为准，启动、所有候选检查与必要归档共用该预算，退出清理不提供新证据配额。

基准 subject 为 `e0c4d2858e386e16348955f7c4f7f430a11fc2fd`。旧公开结果在 `bfcf3db10364da1b01391333dc132a8a3faa8eee`。最接近参照是相同在线 HEFT 初始化的原模型 600 s 运行；主机条件及证书/恢复/无缓存开销存在差异，单次结果不支持将全部收益归因于精简或声称普遍优越性。

## 复核范围与代码定位

运行 `python -B verify_public_evidence.py` 只验证本包文件 SHA、JSON/源码语法、时间和回执一致性，不运行本次算法。`code/` 是受限预算实验的源码快照，仍依赖基准仓库和外部 Python/MATLAB 环境，脱敏路径不是可执行部署配置，不应直接把原历史授权视为重跑授权。测试源码保留供审阅；本次没有再跑实验测试或 SAFE。

基准实现位于 `research/chapter3_experiments/`：包括 `formal_milp.py`、`milp.py`、`initial_point.py`、`matlab_bridge.py`、`thermal.py`、`control_policy.py` 和 `numeric_case_diagnostic/exact_equalities.py`，逐文件原 SHA 可由冻结索引检索。完整 3,185 文件在本地重新核 hash，结果见 `audit_checks.json`。本目录不重复发布这些既有源码，也不含 MATLAB 专有二进制、偏好、授权文件或运行矩阵 `.mat`。

投影证书、全部选定 callback 数值和完整 SAFE 回执保留，足以独立审阅映射、调度及证据绑定；数值矩阵未复制，若需重新构造须使用冻结输入、代码和独立计算环境，并另行明确实验范围。本包的只读检查不是第二次物理/热模型验证。

## 公开源码可得性与重建边界

哈希索引仅标识源码，不能替代源码交付。已有公开基准是 [`2b18f3cdf97939ec2dc5d58d3a863a8ddc55a0c5`](https://github.com/YBEMR/paper/tree/2b18f3cdf97939ec2dc5d58d3a863a8ddc55a0c5)。旧公开结果提交 `bfcf3db10364da1b01391333dc132a8a3faa8eee` 的以下材料可补齐其后差异：

- [四文件精确补丁](https://github.com/YBEMR/paper/blob/bfcf3db10364da1b01391333dc132a8a3faa8eee/research/chapter3_experiments/results/bpre_release_20261105/reproduction/scientific_fixes.patch)：本次只读比较确认其字节与基准到本地 subject 的四个科学/测试文件 `git diff --binary` 完全一致。
- [入口与测试源码参考](https://github.com/YBEMR/paper/tree/bfcf3db10364da1b01391333dc132a8a3faa8eee/research/chapter3_experiments/results/bpre_release_20261105/reproduction/entry_references)：`bpre_formal_entry.py.txt` 和 `test_bpre_formal_entry.py.txt` 是完整脱敏参考；本机路径需重新适配。
- [四份精确输入](https://github.com/YBEMR/paper/tree/bfcf3db10364da1b01391333dc132a8a3faa8eee/research/chapter3_experiments/results/bpre_release_20261105/inputs)及[旧重建说明](https://github.com/YBEMR/paper/blob/bfcf3db10364da1b01391333dc132a8a3faa8eee/research/chapter3_experiments/results/bpre_release_20261105/REPRODUCTION.md)。四份输入本次再次与本地 subject 的 Git blob 逐字节比对一致。

基准到 subject 共 12 个差异文件，冻结索引的 3,185 路径中 3,179 已存在于公开基准，剩余六个为上述两份入口/测试和四份输入。详情见 `source_availability_audit.json`。**不声称可逐字节重建 e0c4d285 的 Git tree/commit，也不声称本包可全自动复现实验**：入口与 plan 已脱敏，旧授权模板未发布；原生探针、资源与清理准入依赖新计算机重新取得的证据，历史授权/令牌不可复用。此次仅核查文件和 Git 差异，未应用补丁或进行任何实验。
