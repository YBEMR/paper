# Kim 跨场景热继承 V1

研究结论见 [研究判断](report.md)，逐轨迹结果见 [全样本表](comparison.csv)。A 是 Kim 算法 3 在固定部署上的两遍逐域搜索适配，B 是当前段全部工作点组合的精确枚举，D 是知道未来序列的离线全局参照。模型、来源、历史复用和数值边界分别见 [输入](input_protocol.md)、[来源](sources.md)、[复用](reuse.md)、[连续热安全](physics_model.md)、[求解与小例核验](求解与核验.md)。

## 重放

检出包含本目录的项目分支，进入 research/kim_thermal_v1。程序会从同一次项目检出读取 ../chapter3_experiments 及 ../v1_evaluator 下的既有模块。已验证环境为 Python 3.12.4、NumPy 1.26.4、SciPy 1.13.1。采用纯 Python 和 NumPy 仿真，无需 MATLAB、MILP 商业求解器或硬件。

新运行请指定新的输出目录，保留归档结果。在 PowerShell 中运行：

```powershell
New-Item -ItemType Directory replay01
python verify.py replay01/checks.json
python run_v1.py replay01/raw
```

verify.py 独立检查事务调度、连续传播、区间核、独立枚举及断开热继承的退化，再生成冻结源码指纹。run_v1.py 要求输出目录先前不存在、同级 checks.json 核验通过且源码哈希匹配。若变更源码、模型或病例，它就不属于归档的 V1；检查源代码与历史版本后再另行定义新研究。

## 阅读输出

- checks.json 保留实际运行前完成的独立核验，包括 64 个短序列的穷举、末端温度、热峰越限反例和重置测试。
- raw/ 中每个 JSON 对应一条预定轨迹，包括原始请求、每个方法的完成及失败状态、频率和资源时间线、逐请求完成时刻、各段首末温度、段内连续峰包络、逐段能量、每个热功率区间以及已访问入口的8个候选。末段 trace 中超过240 ms的部分是统一100 ms低档尾窗；温度单位°C，时间单位ms，功率单位W，能量单位J。
- 无解的 B/D 不提供可用于比较的整窗能耗。D 若证明无解则 path 为空，D.diagnostic 的首个入口列出首段的热/期限排除；A 的完整超温重放保留以便核查。
- comparison.csv 包含全部24条，pairs.csv 按同一场景的出现次数对齐顺序与入口温度，decision_diagnostics.csv 区分期限排除、温限排除、Kim 搜索覆盖和温度引起的候选排序变化。statistics.json 汇总。
- 在保存这些结果的项目副本中，运行 `python analyze.py` 可从本目录 raw 重建上述四张结果表；脚本会写入该副本。计时与机器和运行环境有关，数值主张以逐轨迹频率、可行性、能耗和峰温为准。

## 版本

原工作区 HEAD、冻结基底与 22 个旧文件的版本记录见 legacy_sources.json。V1 运行前本地冻结提交为 e07351cc70d75d1d2a7c4197fa3dff2b13e77a18，文件树 b1d3958c16e400a0e64d00e9dcaa59cc43be75f5；远程冻结提交 7399c87c36e49a973c7e004fcdb7bdcab5372f56 具有相同文件树。分支 research/kim-thermal-inheritance-v1 从 92cd9f1702d96d4606bdacc921ff5d1fe4769c67 分出。全部结果为指定模拟设备和参数的数值结果。

