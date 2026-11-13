# D285：Git 入口修复冻结

基于 5bc1ade。固定直接 Git 主程序及身份，保存原始子进程错误，保持 D283 参数、600/550 秒及所有 Job 限额。

- [报告](REPORT.md)
- [冻结计划](executor/plan.json)
- [102 项纯控制结果](controls_final/results.json)
- [参数、预算与科学源码不变核对](unchanged_contract.json)
- [执行入口与授权规则](RUNBOOK.md)

科学构模、求解、热评价为 0。源码提交后将补充实际项目提交的 --entry-only 入口回执；其成功也不构成科研求解授权或效果证明。

临时 Git 测试仓库不发布；测试脚本每次独立创建。原始 Git 输出/错误、夹具提交身份和组回执保留，可按脚本重复验证流程。
