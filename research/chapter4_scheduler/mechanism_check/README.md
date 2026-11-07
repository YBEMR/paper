# 第四章 R1/R3 阻塞边开关验证

本入口只服务当前有界开发检查，不接旧执行槽或旧预算。真实结果保存在
[`../results/cloud_mechanism_20261107/`](../results/cloud_mechanism_20261107/)。

`blocking.method` 的 `allow_blocking_edges` 默认开启；关闭时只跳过额外阻塞边反转。
两组共用原 HEFT、节能模式目标、主资源骨架、排序键、去重及完整电热接纳。
每次独立现场初始化，所有方法工作共用一个 300 秒根；不读历史候选或共享缓存。
修复候选加入后会占用相同评价预算；两组不要求评价次数相同。

本次顺序预先固定为 R1/OFF、R1/ON、R3/ON、R3/OFF，共四次方法调用；
每份正常完整 SAFE 最多一次 60 秒独立复核，总方法上限 1200 秒、复核上限 240 秒、
日历上限 1800 秒。每槽独占 claim，禁止重试。技术故障、结果不确定或复核失败停止后续槽。
MATLAB 不在此路径中：实际调用原 Python HEFT 和原连续区间电热评价器。

实际运行命令（均以仓库为工作目录；已消费目录不能重跑）：

```text
python -B -m research.chapter4_scheduler.blocking.run_precheck --out research/chapter4_scheduler/results/cloud_mechanism_20261107/precheck_launcher
python -B -m research.chapter4_scheduler.mechanism_check.run prepare --out research/chapter4_scheduler/results/cloud_mechanism_20261107/execution --checks research/chapter4_scheduler/results/cloud_mechanism_20261107/precheck_launcher/checks.json
python -B -m research.chapter4_scheduler.mechanism_check.run run --out research/chapter4_scheduler/results/cloud_mechanism_20261107/execution
python -B -m research.chapter4_scheduler.mechanism_check.run analyze --out research/chapter4_scheduler/results/cloud_mechanism_20261107/execution
```

`plan.json` 冻结源码、输入身份、环境、顺序和预算；每槽保留命令、开始／结束时间、
stdout/stderr、完整初解、完整评价候选及回执、结构失败诊断和独立复核。
`summary.json` 先核初始化是否完成、初解语义哈希和能量区间是否相同，再报告消融结果。
所有科学源和受保护历史档案运行前后核哈希；不覆盖旧档，不自动提交、推送或合并。

此处两题各一次，仅用于机制说明及无机会时的成本检查，不证明泛化、统计稳定性、
全局最优或方法新颖性。HEFT 原本就具有迁移、调频及重排能力。
