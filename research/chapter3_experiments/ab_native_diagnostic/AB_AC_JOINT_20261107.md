# AB／AC 完整联合验收与历史强基线核查

**原 β=1.3、50 °C 入口、80 °C 温限的 12 次 Stage 输入下，已有 AB 加补全后的 AC 通过原联合合法性与连续电热验收，等权能耗为 0.970316622819 J。** 同输入的增强 HEFT 和五个 SA 种子均有更低的历史完整 SAFE 能耗。建议以此收束模型验证，当前无需新增正式对照。

## 联合验收

沿用 `base__R1` 的原输入和配置、原 5 ms 启动网格、400 ms 窗口和每景 1/2 权重。AB 与 AC 各复用六个 Stage 的原设备、频档及启动时刻。原全输入 `thermal.evaluate_candidate` 先检查联合合法性，再独立重算两景完整电热轨迹。A.pre、A.main、A.post 的部署在两景分别一致为 CPU1、NPU0、CPU1。两景无违规，重算能耗区间与各自归档完全一致。 [AB 来源](fullpath_evidence/optimization/continuous_receipts.json) · [AC 来源及补全](AC_RELIFT_20261107.md) · [完整联合回执](ab_ac_joint_evidence/joint_receipt.json)

| 场景 | 权重 | 完整验收 | 能耗上界 / J | 峰温上界 / °C |
|---|---:|---|---:|---:|
| AB | 1/2 | SAFE | 1.046120846870406 | 53.126722（NPU0） |
| AC | 1/2 | SAFE | 0.894512398766814 | 50.185785（CPU1） |
| 合并 | 1 | SAFE | **0.970316622818610** | 53.126722 |

联合检查一次，共 1.063 秒，MILP 和调度搜索均为 0 次。验收证明该完整调度在原输入下合法且电热 SAFE。本轮未构建全域联合 MILP 变量向量，两个场景既有的固定部署数值见证各自保留。 [联合调度](ab_ac_joint_evidence/candidate.json) · [联合摘要](ab_ac_joint_evidence/summary.json)

## 已有同输入强基线

对照 `base__R1` 原档逐次核对。增强 HEFT 与 SA101–105 的实例、配置与本轮输入逐字节相同，原设备、频档和启动选择域保持开放，均由独立后验判为两个场景完整 SAFE。HEFT 版本为 `shared-scenario-heft-energy-pass-v1`。P0 的 HEFT 曾有包装写档故障，原结果独立后验通过，K145 的完整归档也得到相同能耗。 [P0 逐调用汇总](https://github.com/YBEMR/paper/blob/ba64b1dc5cb520571e26261f9f8a92083dd27110/research/chapter3_experiments/results/p0_resume01/analysis01/results40.csv) · [K145](https://github.com/YBEMR/paper/blob/c3f80f302798809f4f340e6631e044963cc0fff6/research/chapter3_experiments/results/heft_sa_followup01/k145_summary.md) · [逐档核查](ab_ac_joint_evidence/baseline_audit.json)

| 历史方法 | 完整 SAFE 加权能耗上界 / J | 方法时间 / 秒 |
|---|---:|---:|
| 增强 HEFT | **0.881087997281** | 43.438 |
| SA101 | 0.907346431253 | 300.000 |
| SA102 | 0.909985098762 | 300.015 |
| SA103 | 0.904843625505 | 300.000 |
| SA104 | 0.888993180224 | 300.000 |
| SA105 | 0.904429919981 | 300.000 |
| SA 中位数 | **0.904843625505** | — |

合并见证比增强 HEFT 高 0.089228626 J，约 10.13%。按两景等权分解，约 92% 的差额来自 AB。增强 HEFT 最终 A.pre 选 CPU2，其搜索部署域比这份见证开放。历史 SA102、SA105 的最终 A 部署与本轮一致，两者能耗仍更低。同输入、同 A 部署的历史联动方案还达到 0.860663343334 J，因此固定 A 部署无法单独解释本轮质量差距。 [历史 HEFT 后验](https://github.com/YBEMR/paper/blob/ba64b1dc5cb520571e26261f9f8a92083dd27110/research/chapter3_experiments/results/p0_execution01/calls/base__R1/heft/postcheck.json) · [历史联动后验](https://github.com/YBEMR/paper/blob/ba64b1dc5cb520571e26261f9f8a92083dd27110/research/chapter3_experiments/results/p0_execution01/calls/base__R1/anchor_linked4/postcheck.json)

## 是否追加正式对照

建议保留此次结果作为第三章的完整调度见证及历史质量定位，沿用已有强基线结果。0.970317 J 来自跨轮固定部署拼接和联合复核，各方法的搜索范围、预算与耗时口径不同，现有数据仅支持同输入的解质量比较。若论文后续需要对修复后的 MILP 给出算法性能结论，再单独冻结共同部署域、端到端预算和独立初始化。本轮到此停止。

复现入口为 `python -B verify_ab_ac_joint.py <原Windows冻结目录> <新输出目录>`。脚本只读取两份既有安排，在新目录保存合并候选和原评价回执。 [入口](verify_ab_ac_joint.py) · [证据清单](ab_ac_joint_evidence/manifest.json)
