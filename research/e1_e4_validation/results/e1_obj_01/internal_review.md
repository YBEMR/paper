# E1四槽内部独立核对

结论：通过。本审查只读真实档案，核对源码、输入、一次消费、预算、候选身份及能量算术；未调用搜索或热积分，未产生新SAFE。不是外部协议批准。

封版源码：`b509a61afc272ebb07d630d9ebae377723db770d`；清单SHA256：`bb820ef5a7ecd741d65112b0d47280e22d9212b2753fcedd8693403048ee734b`。

已执行4次规划＋4次固定候选后验，无补跑。规划外层累计332.923s，后验累计9.282s，整批345.531s；全部自然结束且回收，均在各自300/60s及整槽/整批期限内。

已逐项核对208份源码副本hash。各候选的完整场景、400ms窗口、连续峰温与期限回执有效，后验与该臂最终候选完全一致。

| 输入 | FULL真能耗/J | OMIT_TEMP真能耗/J | 严格差值/μJ | 改善/% |
|---|---:|---:|---:|---:|
|base__R1|0.8810879972810|0.8811043409076|16.34362665|0.00185490|
|base__R3|0.8622513257761|0.8622687681872|17.44241119|0.00202285|

两个输入的最终设备和OPP均相同，基准、活动及公共能量相同。FULL主要通过5~10ms级延后改变温度修正积分；差异可被数值区间分辨，但幅度极小。不能表述为显著节能、普遍优越，或热约束/热反馈有效性的证明。当前是评分消融，不能与K178响应H/R消融混合归因。

## base__R1时序变化

- `AB_offset_0ms::A_r1::A.pre`：OMIT_TEMP 0ms → FULL 5ms。
- `AB_offset_0ms::B_r1::B.post`：OMIT_TEMP 70ms → FULL 75ms。
- `AC_offset_0ms::A_r1::A.main`：OMIT_TEMP 15ms → FULL 20ms。
- `AC_offset_0ms::A_r1::A.post`：OMIT_TEMP 60ms → FULL 70ms。
- `AC_offset_0ms::A_r1::A.pre`：OMIT_TEMP 0ms → FULL 5ms。
- `AC_offset_0ms::C_r1::C.main`：OMIT_TEMP 20ms → FULL 25ms。
- `AC_offset_0ms::C_r1::C.post`：OMIT_TEMP 105ms → FULL 115ms。
- `AC_offset_0ms::C_r1::C.pre`：OMIT_TEMP 0ms → FULL 5ms。

## base__R3时序变化

- `AB_offset_0ms::A_r1::A.post`：OMIT_TEMP 75ms → FULL 80ms。
- `AB_offset_0ms::B_r1::B.pre`：OMIT_TEMP 0ms → FULL 5ms。
- `AC_offset_0ms::A_r1::A.main`：OMIT_TEMP 20ms → FULL 25ms。
- `AC_offset_0ms::A_r1::A.post`：OMIT_TEMP 75ms → FULL 85ms。
- `AC_offset_0ms::A_r1::A.pre`：OMIT_TEMP 0ms → FULL 5ms。
- `AC_offset_0ms::C_r1::C.main`：OMIT_TEMP 20ms → FULL 25ms。
- `AC_offset_0ms::C_r1::C.post`：OMIT_TEMP 105ms → FULL 115ms。
- `AC_offset_0ms::C_r1::C.pre`：OMIT_TEMP 0ms → FULL 5ms。

四槽最终后验的最大连续峰温上界分别约50.71088、50.71093、50.06135、50.00266°C，范围50.00266—50.71093°C，最大值50.71093°C，均低于80°C温限。此处没有热安全约束改变可行性的证据。结果只适用于这两个抽象输入、既定一遍启发式与评分规则，未证明最优，也不能从单次用时判断统计稳定性。

完整机器记录见 `internal_review.json`；审查只生成本报告及该JSON，未改原结果、源码或账本。
