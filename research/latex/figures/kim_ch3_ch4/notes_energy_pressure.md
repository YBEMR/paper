# 图 3-4 至图 3-6 图注与数据口径

## 图 3-4　常规工况下的最低安全能耗与独立热评价误接纳

图稿为 `fig03_baselines`。（a）25 °C、逆序原驻留，完整 81 部署库。最高频固定为 HHH×4，静态调频在每部署的 27 种跨场景恒定频率三元组中择优，联合调度允许四个场景分别选档。各方法均在通过请求期限和连续热约束的候选中比较全窗能耗。三者的最低安全能耗分别为 63.3540、48.2799 和 43.2503 J，联合调度相对前两者分别节能 31.73% 和 10.42%。81 个最高频候选中有 58 个安全、23 个超温。静态调频的 2,187 个候选中有 272 个安全，全动态搜索的 43,046,721 个编码中有 932,796 个安全。

（b）25 °C、正序原驻留，历史部署 A、C。静态调频和联合调度的最低安全能耗为 47.9963 和 43.1108 J，降幅为 10.18%。在此工况，独立分场景选频与联合选择均得到 C 的 LLL/LLL/LHL/LHL。该序列的独立能耗估计为 42.535282 J，连续评价为 43.110758 J。10.18% 对应静态频率与场景调频的差异。A、C 的两个 HHH 候选均超温，最高频安全能耗留空。

（c）同（b）工况。A、C 的独立热评价各接纳 59,049 个期限合法频率序列。连续热复核分别确认 56,307 和 57,084 个安全，并检出 2,742 和 1,965 个超温误接纳。两部署合计误接纳 4,707/118,098（3.99%），连续评价单独接纳的序列为 0。该比值的分母是独立评价接纳的已枚举编码数。

限定的峰温对照可作表注。25 °C、正序原驻留的 A/C 静态域中，54 个候选有 15 个安全。四节点峰温认证上界最小的候选为 C-LHL，峰温上界 77.5265 °C，能耗 47.9963 J，与该域最低能耗静态方案重合。完整动态域的分类与能耗数组缺少逐候选峰温，完整 Min-Peak-Temp 留空。

## 图 3-5　27.5 °C 压力工况下期限合法频率序列的连续热分类

独立图稿为 `fig05a_pressure_classes`，对应组合图 `fig05_pressure` 的面板（a）。正序交替、逆序原驻留和逆序交替中分别比较 A、C、D001 和 D015。每个工况与部署组合共有 27⁴＝531,441 个频率编码，柱高只计其中满足全部请求期限的编码。三个工况中，A、C 各 59,049 个期限合法码全部超温，D001 的 18,225 个和 D015 的 6,561 个期限合法码全部安全，12 个单元的未决数均为零。

## 图 3-6　27.5 °C 压力工况中最低安全能耗方案的能耗及裕量

独立图稿为 `fig05b_pressure_margins`，对应组合图 `fig05_pressure` 的面板（b）至（d）。每个工况分别在 D001、D015 的安全频率序列中选取全窗能耗最低者，共六个代表。热裕量为 80 °C 减去该代表四节点全窗最高峰温的认证上界，期限裕量为该代表全部 500 个请求中最小的“绝对期限减完成时刻”，以 ms 计。三个工况中，D015 相比 D001 多耗 0.1754–0.2012 J，热裕量增加 5.5165–5.6747 °C。D001、D015 的最小期限裕量分别为 0.308690 和 1.248307 ms。A、C 在这些压力工况下均无安全代表。

## 数据与复绘

以下路径均相对于 [归档提交 b818777](https://github.com/YBEMR/paper/tree/b8187776fdf2c995cbec410032b34a5a76fa774b)。

|范围|归档依据|制图输入|
|---|---|---|
|逆序原驻留完整 81 域及 25 °C 四种工况的共同四部署| `research/kim_multidnn_expansion/raw/expanded/<case>/space_<deployment>.npz` 中的 `status` 与 `energy_j` | `data/fig03_energy_domains.csv` |
|25 °C 正序原驻留历史 A/C| `research/kim_scene_dvfs_admission/raw/space_25_{A,C}.npz`、`raw/comparison_sets.json` 及 `summary.csv` | `data/fig03_energy_domains.csv`、`data/fig03_false_admissions.csv` |
|A/C 静态最低峰温| `research/kim_synthetic_platform_v1/raw/candidates.csv` 中 `10s_25fps_25C_on_base`、连续传温、期限通过且热状态 SAFE 的候选 | `data/fig03_static_min_peak.csv` |
|压力三工况共同四部署| `research/kim_pressure_feasibility/manifest.json`、`raw_execution/00..11/{space.npz,result.json,requests.json}`、`audit_27p5/audit.json` | `data/fig05_classes.csv`、`data/fig05_margins.csv`、`data/fig03_energy_domains.csv` |

图 3-4 的节能率按各自域的（基线能耗−联合能耗）/基线能耗计算。`full81` 为完整 81 部署，`common4` 固定为 A/C/D001/D015，`original_AC` 为历史 A/C。已核验四个 25 °C 工况分类数组实际分别覆盖 15、33、81、67 个部署。CSV 附带三组 27.5 °C 工况的同域基线，供撰写实验三时查用。最高频、静态调频和动态策略的候选集合不同，均使用同一工况、部署库和连续评价标准。

在本目录执行 `python scripts/plot_energy_pressure.py` 即可从 CSV 出图。持有原归档时，可先运行 `python scripts/energy_pressure_data.py <research目录>` 重建这五张 CSV。脚本只索引、汇总既有数组和请求明细，新增科学评价次数为 0。
