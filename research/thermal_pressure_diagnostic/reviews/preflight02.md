# K.31执行前定向复审02

## Material Passport

2026-10-08；主线（6）；被审提交`7a81d40bb18fc959c1c5ffd5b40bf4c06cfcd5ef`，本地main引用与委托一致。仅复核preflight01的R1、6项新增合成检查及入口门槛更新。只读源码、保存结果和哈希；未运行预检、热评价或正式诊断，未操作Git，未修改其他文件。

## 结论

**R1已闭合，执行前审查通过，无新增必要修订。允许主线在原授权范围内，将本审查及当前源码哈希绑定到ready记录、确认正式次数仍为0后，按原TP-1协议执行一次四组合诊断。** 此处是技术准入结论，不扩展参数、案例、精度、预算或重跑权限。

## 定向复核

| 要求 | 修订及证据 | 判断 |
|---|---|---|
| 超时保留已知冲突 | late_guard在full分支保留原evidence_conflict；存在已提交安全证书及反例时也设为冲突 | 闭合 |
| 保留证书背景及身份 | 保存内部joint已接收的safety_receipt或组装后sustained_safety，receipt含原binding；外层source_binding仍保留。旧joint只有接收预算检查通过后才保存安全receipt，不会将尚未接收的晚到证书提升为保证 | 闭合 |
| 后续探针识别冲突 | classify可从保留的证书状态与后续合法探针反例识别矛盾；不因完整能量超时把矛盾降为可靠排除 | 闭合 |
| 迟到能量仍不可接纳 | late_guard仍去掉有效U、score及完整能量负载，保留的证书仅供证据管理；没有恢复预算外安全能量 | 闭合 |
| 汇总不得产生错误最优 | 新增两条完整链检查分别覆盖已知冲突超时、已接收证书超时后出现探针反例；均进入evidence_conflict及unresolved_candidates，four_point_optimality保持unresolved | 闭合 |
| 新门槛及旧记录 | 正式入口已读取precheck03；26/26保存检查通过，全部依赖哈希与当前一致。旧precheck02仍保留。state为awaiting_review、formal_run_count=0、revision_count=1 | 闭合 |

新增6项为late_conflict_kept、late_conflict_classified、late_receipt_identity_kept、late_receipt_probe_conflict、conflict_summary_unresolved、later_probe_summary_unresolved，保存结果全部通过。审查核对了测试代码的合成输入与判据，没有重新执行它们。

原晚到安全值拒绝、真实无冲突反例排除、普通未决、一次性claim和哈希门槛保持。PROTOCOL.md及postcheck.py哈希与上次审查一致，28次独立20秒和事后策略回放口径未变。

## 审查绑定

- run.py：`784ee01dbed3f7474ce5bbcc6e97cc49ab6b8408e322f29f60870c7eb9b80877`
- precheck.py：`55bed86c30374a8981e8830bc2a7544a872c07a6b9158d970542d3852699070e`
- PROTOCOL.md：`d24531d4ef32215c7ae1f3a18ecabac996a4474a64ed51730455da2c9b1b75bd`
- postcheck.py：`2d65d2933309e01337c35e4d482e75986ec3f0a07c4d6af9a642a54edbbba0eb`

当前尚未正式运行。完成准入绑定后，一次诊断出现超时、未决或无收益均按协议保留，不追加运行寻找优势。下一次独立审查只审已保存结果。
