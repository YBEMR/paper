# B参数区域与稳健性复算包

本包回答三个问题：参数有没有同平台物理依据；哪些关系导致批次排序翻转；共同最佳固定与单阈值之后还剩多少收益。它是条件化合成分析，不是AGX硬件校准。

先读 [REPORT.md](REPORT.md)。范围与输入冻结见 [PROTOCOL.md](PROTOCOL.md)、[design_freeze.json](design_freeze.json)；参数实证空缺见 [physical_evidence.json](physical_evidence.json)。原始合成参数逐字节继承前一阶段，SHA256 `b9fce0477a836826dae4046ecb6d2ea9a13a9825e83fe95dc4d2f23fd9ffbefe`。

## 运行

Python 3.12.4、NumPy 1.26.4、SciPy 1.13.1验证通过；绘图使用Matplotlib 3.10.0，报告使用Markdown。主扫描预算600秒、数值验证预算300秒。主扫描约58秒；不同机器时间会变化。缺少依赖时自行安装至隔离环境。

在本目录运行以下步骤。参数与证据输入已随包冻结，无需网络或硬件：

```text
python preflight.py
python evidence.py
python run_analysis.py
python validate_numeric.py
python interpret.py
python plot_results.py
python verify_artifacts.py
python build_report.py
```

`design.py`保留了首次准备配置的过程，其原始输入路径指向上一阶段工作目录；**复算使用现成冻结配置，不需要运行design.py**。不要为了复算更新冻结日期或哈希。`previous_selected_references.json`保存旧结果相关记录及来源哈希；`input_evidence_contract.json`逐字节保存上轮参数契约，消除跨目录依赖。独立数值核验使用标量方程和另一积分器，仍共享排程事件表，不宣称完全独立软件实现。

## 输出与字段

| 文件 | 内容 |
|---|---|
| parameter_identifiability.csv / physical_evidence.json | 23项证据记录、16项未知null；典型值、描述性范围、假设严格区分 |
| results/scenario_summary.csv | 67情景×2窗口，固定/阈值/目录最优、无收益、可行性与开销预算 |
| results/temperature_results.csv | 67×2×21行，策略能量、S/Q差值、立即执行双DPM基线 |
| results/all_action_aggregates.csv | 67×2×92行，所有候选的均值/范围/可行温度数 |
| results/all_candidate_arrays.npz | energy与feasible、peak形状(67,2,92,21)；components末维4为基础（含外部）、动态、漏电、唤醒 |
| results/cpu_fixed40_arrays.npz | 同目录在名义参数、CPU固定40°C下的1932个状态 |
| results/catalogue.json / policies.json | 动作定义、每情景两窗口政策、网格分割；on/off指主窗DPM |
| results/frozen_policy_transfer.csv | 冻结名义政策后的参数/观测偏移检查；空能量字段表示不可行 |
| results/analytic_regions.csv | 固定温度近似连续关系；未误写成动态ODE证书 |
| results/analytic_uncertainty_envelope.csv | 解析模型独立原始参数盒精确角点界 |
| results/dynamic_corner_sign_envelope.csv | 动态模型的已采样角点包络，无连续盒认证 |
| results/interpretation.json | 机器可读结论摘要 |
| results/numerical_validation.json | 数值验证及逐轨迹差异 |
| manifest.json | 全部交付文件SHA256与GitHub/本地分发标记 |

窗口索引0=0.4秒主窗，1=10.4秒共同延长窗。温度单位°C、功率W、能量J。capture分母为固定与逐温度目录最优的平均能量差；差为0时JSON用null、CSV留空。百分比与百分点分别标记。浮点末位和运行时间可能随软件/硬件略变，不要求压缩NPZ字节跨版本一致。

GitHub保留文本文件和SVG图；PNG、HTML与两个NPZ随本地ZIP交付，也可由脚本重建。PNG不是原始实验数据；完整候选能量数组不得与真实测量混称。冻结设计有此前发现性结果背景，不称盲态预注册。原研究筛选、同平台审计各自保留独立目录与旧提交。

## 结论边界

本轮1%是研究投入参考；零开销理想收益未达门槛。阈值在同网格优化是强结构参照，不能作为部署精度；任意权重证书只覆盖已算21温度点。16角点范围是敏感性假设，无经验概率含义。
