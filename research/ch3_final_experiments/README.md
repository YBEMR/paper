# 第三章 P0–P1 归档核对与图 C/D/E

**P2 规范修订（2026-11-21）。** [Kim 主基线与 SetFreq 枚举的身份、SAFE 配对回退、Thermal-GA 试参数](protocols/kim_adaptation_spec.md) · [P2 成本验收与后续预算](protocols/P2-P4_minimum.md) · [图 E 全部 81 个固定部署的代表性分析](figE_representativeness.md)。图 C 的安全代表目前只有场景端点，完整安全轨迹标为**待补数据**，拟单独申请一次固定方案采样，上限 30 秒。

**归档重建复核。** 从固定 Git 对象向新目录提取 512 个输入和原 P0–P1 的 3 个脚本，使用现有 Python 环境以隔离模式（`-I -B`）重新提取、绘图和校验。生成的 17 张原 CSV 与 `af6670fb` 的 Git blob 逐字节一致，C/D/E 的 PNG、PDF、SVG 通过格式校验。此项复核使用本机已安装依赖；新增科学调用为 0。

基准为 [YBEMR/paper · b8187776](https://github.com/YBEMR/paper/commit/b8187776fdf2c995cbec410032b34a5a76fa774b)。本交付读取归档、筛选已有数组并绘图，新增科学仿真调用为 0。任务书为《第三章正式实验设计与Work执行任务书_v1》，文档 SHA-256 及逐输入 Git blob、SHA-256 见[证据清单](audit/sources.json)。

| 交付项 | 阅读入口 |
|---|---|
| 实例、模型参数、覆盖差距 | [范围判定](gap_matrix.md) · [12 个实例与请求摘要](derived/instances.csv) · [参数总表](derived/parameters.csv) · [108 行覆盖矩阵](derived/coverage_matrix.csv) |
| 图 C　同方案热继承与重置 | [PNG](figures/figC.png) · [SVG](figures/figC.svg) · [四节点温度数据](derived/temperature_traces.csv) · [认证峰温](derived/peak_certificates.csv) |
| 图 D　误收与压力分类 | [PNG](figures/figD.png) · [SVG](figures/figD.svg) · [重置接纳分母](derived/reset_confusion.csv) · [4,707 条误收原件索引与指标](derived/candidate_diagnostics.csv) · [压力分类](derived/pressure_classification.csv) |
| 图 E　部署和 DVFS 四格消融 | [PNG](figures/figE.png) · [SVG](figures/figE.svg) · [四格数据及裕量](derived/ablation_results.csv) · [每部署受限域最低值](derived/grid_minima.csv) |
| 其他图的数据接口 | [A/B 方法与最优参照](derived/figAB_method_comparison.csv) · [F/G 匹配四部署](derived/figFG_matched_pressure.csv) · [七图登记表](derived/figure_registry.csv) |
| 新方法与下一阶段 | [算法 1/3 映射、回退与 GA 规范](protocols/kim_adaptation_spec.md) · [P2–P4 最小批次与预算](protocols/P2-P4_minimum.md) |
| 输入与代码 | [来源路径及哈希 CSV](derived/evidence_inventory.csv) · [数据提取](derive.py) · [绘图](plot_figures.py) |

三幅 PDF 随本地完整 ZIP 提供。仓库按已有忽略规则保存 PNG 和可编辑 SVG，运行绘图脚本可同时导出 PDF。逐阶段冻结与归档的完整 SHA 见[版本表](derived/versions.csv)。

## 从图中能读出什么

**图 C。** 25°C 正序原驻留，部署 C 的四段频率均取 HHH。独立重置时全窗认证峰温上界为 77.553°C；相同动作连续运行时为 80.773°C，归档判为超温。上图绘 GPU 原始采样，CSV 保留四节点，场景切换时保留重置前后同一时刻的两个点。下图给同工况安全代表 C、LLL/LLL/LHL/LHL 的场景端点，归档认证峰温上界 76.506°C。端点间未绘制插值。源档两种请求摘要使用不同编码；提取程序从 HHH 调度账本重读 500 个请求的 ID、应用、释放与期限，以压力协议的规范格式重算并匹配实例摘要。连续峰温证书独立于绘图采样。

**图 D。** 在 25°C 正序原驻留，A/C 各有 59,049 个序列被重置评价接纳。其中 2,742 与 1,965 个在连续运行中超温，合计 4,707/118,098，即 3.99%。逐编码已与全长数组和误收记录对齐。在 27.5°C 的三个预选工况中，图右每格的分子和分母分别为连续热 SAFE 数、满足期限数。A、C 各为 0/59,049，D001 为 18,225/18,225，D015 为 6,561/6,561。右图随档给出超期、超温、未决完整计数；右图的比例与左图误收率使用不同分母。

**图 E。** 在筛选四格数值前，指定历史 A 为固定对照，理由是它为源目录的第一套传统部署，层段见参数表。此选择属于已观察数据上的事后消融设计。每个场景取一个 CPU/GPU/共享 DLA 三元组；“整窗同频”保持同一三元组贯穿四场景。选取逆序原驻留 25°C，在相同请求、完整 10.04 s 计能窗和 80°C 约束下，四格最低 SAFE 能耗依次为 49.029417、43.303623、48.279859、43.250300 J。相对固定 A＋整窗同频，节能 0%、11.678%、1.529%、11.787%。这些数值量化本实例放开部署和频率决策的作用。外部算法节能率待补。

**状态与数据血缘。** 全域分类时 0/1/2/3 分别为超期、SAFE、超温、未决。域内最低值从 SAFE 编码求严格最小，并在 10⁻⁹ J 并列容差内取代表编码。受限域内已证无解、未运行、限时未找到及只有 SAFE 见证分别记录。压力单元的超温诊断峰温不填入 SAFE 输出。图表使用合成 FP16 代理和四节点热模型；新增部署的真实引擎与输出验收仍待实机证据。

## 复核与重新绘图

在含原始提交的仓库中，令 `SOURCE` 为检出的基准仓库根，且包含 `research/` 与 `papers/`。需要 Python、NumPy、pandas、Matplotlib 和中文字体（微软雅黑或 Noto Sans CJK SC 等）。绘图只需本目录的 CSV。

```text
python derive.py SOURCE
python plot_figures.py
```

源文件与 Git 元数据分开保存时使用 `python derive.py SOURCE --git-dir ORIGINAL_GIT_DIR`。提取器核对输入 blob 与固定结果树，复核 212 份网格的有限能耗位置、关键分类／计数、12 个压力单元的冻结清单及图 E 的 81 部署最优值。每张图均从 CSV 读取观测。仅重新作图时无需下载历史原始数组。
