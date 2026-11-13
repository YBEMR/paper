# D284：统一 CPLEX 完整 R1 A/B/C 冻结准备

基于 c4aa629。**准备通过，等待一次新的独立执行授权；本轮科学调用为 0。**

- [研究报告与协议](REPORT.md)
- [冻结计划](executor/plan.json)
- [执行入口说明](RUNBOOK.md)
- [执行后只读审计](AUDIT.md)
- [最终 84 项控制结果](controls_final/results.json)
- [拒绝未批准执行的真实入口测试](gate_denied/receipt.json)

最终计划 SHA-256：`bd5c73303c83e862ccd484df7db9dcbe1a2cf73ec63f3dc989784b019a2005d6`。
每组 600 秒、响应截止 550 秒，沿用 D283 CPLEX 参数、完整互补表达及原共同初解规则；独立构模/初始化/认证/评价，普通超时继续其他组。
首版未执行草案仅作历史记录，已废止。模拟回执不构成科研求解结果。历史授权不适用于此计划。
