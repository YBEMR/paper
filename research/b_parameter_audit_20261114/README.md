# B 同平台参数与可测效应审计

**结论：可以继续条件化仿真；现有公开证据不能把上轮 B 合成机制标定成真实 AGX Xavier 节能效果。** 用户无硬件，本阶段不以获取设备为后续前提。

- [审计报告](REPORT.md)：事实、参数可用性、效应识别边界与下一步。
- [数值汇总](results/audit_summary.json)、[参数表](parameter_status.csv)、[仿真输入约束](simulation_parameter_contract.json)。未知值保留 null，不能静默补值。
- [分析前规则](AUDIT_PROTOCOL.md)：看到代码与样例后冻结，完整数值汇总前形成；不是盲态预注册。
- [来源清单](source_manifest.json)、[补充来源](auxiliary_manifest.json)：固定提交、Git blob 与 SHA-256。
- [验证与统计边界](REVIEW.md)。本轮为同一助手自审，无独立审查背书。

复算（Python 3.12；审计计算只需标准库）：

```text
python get_sources.py
python audit.py
python audit_auxiliary.py
python validate.py
```

`get_sources.py` 只下载固定哈希的公开文本和一个结果 ZIP；不会运行第三方代码。源码缓存和 ZIP 不纳入 GitHub。复算已有下载可离线完成；从 GitHub 新下载本目录时须先联网取源。生成 HTML 阅读版额外使用 Markdown 3.x：`python build_report.py`。

上轮冻结实验位于相邻 `direction_screening_20261114/`，本轮未修改；本目录仅审计既有证据，没有新硬件、调度搜索或大规模模拟。审计修正不等于否定作者论文整体有效性，也不构成新算法贡献。

Material Passport: Origin Skill = experiment-agent; Origin Mode = validate; Origin Date = 2026-11-14; Verification Status = ANALYZED; Version Label = B-AUDIT-v1. ANALYZED 表示公开材料已复算，不能理解为物理模型已经验证。
