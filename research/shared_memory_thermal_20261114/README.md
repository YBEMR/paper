# 共享内存—热频率限制联合价值（SMT20261114）

**数据准入未通过；未启动联合数值实验，不开发新算法。** 机制有公开依据，但同平台有效频率、带宽/仲裁、功率与热反馈参数未闭合，不能声称≥1%完整能耗空间。

入口：[结论报告](REPORT.md) · [单文件HTML报告](report.html) · [文献与工件审计](SOURCE_AUDIT.md) · [符号模型/判据](SYMBOLIC_MODEL.md) · [参数表](parameter_identifiability.csv) · [质量边界](REVIEW.md)

复算（不执行调度仿真）：

```text
python admission.py
python symbolic_checks.py
```

可选原始资料复核：`python download_sources.py --all`后`python audit_artifacts.py`。固定哈希发生漂移时停止，不自动接受新内容。源论文及作者工件不随本轮重新分发。

四消融与五强对照的结果均为NOT_RUN/null，详见results/。14项符号关系和65行公开摘要仅为复核，不是正收益或零收益实例。Python3.12；依赖见requirements.txt。`build_registry.py`重建输入登记，`build_report.py`重建HTML；不会启动研究求解。
