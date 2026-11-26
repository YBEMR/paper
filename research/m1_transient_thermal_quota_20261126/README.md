# M1 瞬态热容量联合配额诊断

固定 1 秒决策窗，比较普通多配额搜索与热容量引导搜索。L640、L800、L320、L480 共完成 20 次搜索、80 次终端认证。实验结论及适用范围见[中文报告](实验报告.md)。

- [诊断任务书](诊断任务书.md)及[改进轮设计](改进轮任务书.md)
- [逐工况结果](data/audit/summary.csv)、[80 份认证明细](data/audit/terminal_certificates.csv)及[L480 同池对照](data/audit/L480_common_pool.csv)
- [首轮原始数据](data/e1/)、[改进轮原始数据](data/e1b/)及[冻结模型](frozen/)

校验数据与代码可在本目录运行 `sha256sum -c SHA256SUMS`。从头复现时，将原始 `ch4_original_experiments.zip` 和 `ch4_thermal_evidence.zip` 放在本目录的上一级，然后按报告运行 `reproduce.py`。两包的预期 SHA-256 见[输入准备脚本](prepare.py)。
