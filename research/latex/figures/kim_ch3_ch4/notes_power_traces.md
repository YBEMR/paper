# 图3-2、图3-3的数据与图注

## 图3-2　三频域离散工作点的模型功率

建议放在3.6.1平台参数之后。图稿为 `fig02_power.pdf`、`fig02_power.png`，数据为 `data/fig02_power.csv`。

**图注。** 横轴为冻结合成平台的低、中、高三个工作点及其频率。实线圆点表示活动增量功率，CPU 的预处理、后处理按单个忙核分别绘制。GPU 活动增量按单个引擎计算，DLA 活动增量按一台 DLA 计算。橙色方点表示节点温度为 30 °C 时的频域静态功率，DLA 项涵盖两个设备。连线用于辨认同组离散点，各面板单独设置纵轴刻度。

活动增量按 `P_H × (f/f_H) × (V/V_H)²` 计算。按 CPU 预处理、CPU 后处理、GPU、单个 DLA 排列，最高档活动增量分别为 1.0、0.8、4.5、3.2 W。域静态功率取 25 °C 待机功率加上该档温度斜率乘以 5 K。CSV 另列待机功率与漏电增量，便于更改绘图口径。该图只展示合成模型分项，实机功耗和整板负载功率需要另外测量。

[模型平台参数](https://github.com/YBEMR/paper/blob/b8187776fdf2c995cbec410032b34a5a76fa774b/research/kim_synthetic_platform_v1/platform.json) · [阶段活动增量实现](https://github.com/YBEMR/paper/blob/b8187776fdf2c995cbec410032b34a5a76fa774b/research/kim_synthetic_platform_v1/profiles.py) · [参数口径](https://github.com/YBEMR/paper/blob/b8187776fdf2c995cbec410032b34a5a76fa774b/research/kim_synthetic_platform_v1/parameters.md)

## 图3-3　连续传温与场景独立重置下的四节点温度演化

建议放在3.6.2实验一。图稿为 `fig04_temperature.pdf`、`fig04_temperature.png`，数据为 `data/fig04_temperature.csv`、`data/fig04_peak_certificates.csv`。

**图注。** 环境温度 25 °C，正序原驻留，25 FPS。部署 C 在四个场景均取 HHH。蓝线继承上一场景出口温度，橙色虚线在实际切换时刻将四节点重置为 30 °C，以诊断忽略热历史的影响。两种方法沿用相同请求与排程，10 s 服务窗后保留 0.04 s 尾窗。细竖线分别对应 2.48、5.00、7.48 s，水平点划线为 80 °C 温限。场景边界两侧同刻的重置采样点均按归档顺序保留。

连续评价下，GPU 的认证峰温区间约为 80.7730 °C，超过温限。独立重置下，GPU 峰温上界为 77.5527 °C，其余节点峰温也低于 80 °C，因而误接纳了同一候选。图中使用现有事件端点采样，连续与重置分别为 204 和 209 行。整窗峰温与是否越限取自连续时间认证字段。

**表　同工况安全方案及两种温度评价的峰温上界**

| 方案与评价方式 | CPU / °C | GPU / °C | DLA0 / °C | DLA1 / °C | 能耗 / J | 期限满足数 | 温度判定 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| C，全程 HHH，连续传温 | 49.2543 | 80.7730 | 47.2162 | 43.6853 | 63.7183 | 500/500 | 超温 |
| C，全程 HHH，独立重置 | 47.0604 | 77.5527 | 45.3836 | 41.2405 | 62.2696 | 500/500 | 重置模型接纳 |
| D001，频序编码 448，连续传温 | 43.0772 | 71.0097 | 45.1951 | 38.7820 | 44.6793 | 500/500 | 安全 |

表中频序 448 对应 LLL／LLL／MHM／MHM，最小期限裕量为 0.30869 ms。该行引用此部署已归档的逐事件物理复核。峰温上界保留四位小数，完整上下界见 CSV。图中绘制了 C-HHH 的两条既有轨迹，D001 的四节点峰温单独列表。

[四节点轨迹](https://github.com/YBEMR/paper/blob/b8187776fdf2c995cbec410032b34a5a76fa774b/research/kim_synthetic_platform_v1/raw/traces.csv) · [C-HHH 能耗与认证字段](https://github.com/YBEMR/paper/blob/b8187776fdf2c995cbec410032b34a5a76fa774b/research/kim_synthetic_platform_v1/raw/candidates.csv) · [采样规则](https://github.com/YBEMR/paper/blob/b8187776fdf2c995cbec410032b34a5a76fa774b/research/kim_synthetic_platform_v1/run_experiment.py) · [D001 安全方案](https://github.com/YBEMR/paper/blob/b8187776fdf2c995cbec410032b34a5a76fa774b/research/kim_multidnn_expansion/raw/expanded/forward_flat_25C/deployment_D001.json)

在图包根目录运行 `python scripts/power_traces.py` 即可从包内 CSV 重绘。给出 `--source <仓库的 research 目录>` 可重新提取全部数据。脚本仅做归档筛选和参数代入。
