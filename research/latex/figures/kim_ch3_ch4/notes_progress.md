# 图4-4　四个开发工况下的搜索覆盖进度

对应蓝图第 4.6.2 节实验四，文件为 `fig09_progress.pdf` 和 `fig09_progress.png`。PDF 保留矢量线条，PNG 为 2280 × 1515 像素、300 dpi。

**图注**　环境温度为 25 °C。四个开发工况各含 81 个候选部署，M0、M1、M2 在每个工况各冷启动一次，预算均为 120 s。阶梯在主搜索完整处理一个部署并写入完成事件时上升。M0 统计约束搜索，M1 和 M2 统计连续能耗搜索。菱形标记 M2 取得全库证书的时刻。达到截止的运行将最终已完成数持平至预算边界，取得证书的曲线止于认证时刻。

| 开发工况 | M0 完成数 | M1 完成数 | M2 完成数 | M2 全库认证时刻（s） |
| --- | ---: | ---: | ---: | ---: |
| 正序原驻留 | 4 | 41 | 81 | 56.49 |
| 正序交替驻留 | 3 | 46 | 81 | 53.15 |
| 逆序原驻留 | 34 | 42 | 81 | 54.79 |
| 逆序交替驻留 | 38 | 49 | 81 | 49.41 |

**读图口径**　时间原点取监督器启动冷进程前的单调时钟，含启动、导入、核验和冷 JIT。部分部署的构建、搜索前缀以及独立的 SAFE 重放事件不增加覆盖数。M2 达到 81 的时间取最后一个部署完成事件，认证时刻取随后的全库证书事件。每条线记录同一次运行的累计进度。工况之间的差异可解释本次预算内的覆盖，不能据以估计多次运行的方差、独立规模扫描的结果或截尾方法的全库加速比。H1、H2 和 H2 第 2 次的 M1 补跑属于留出组，见预算覆盖图。

**数据与复绘**　`data/fig09_progress_events.csv` 保存 12 次开发运行的 581 个主搜索部署完成事件和 4 个全库证书事件，保留原始累计秒数。运行 `python scripts/plot_progress.py` 可从 CSV 重绘。若有冻结版仓库或研究档案中的 `source` 目录，可用 `python scripts/plot_progress.py --source <含research的目录>` 从压缩日志重新提取、核对并绘图。

**核查**　按索引顺序合并两段日志归档，逐段核对 SHA-256，整包 SHA-256 为 `6087fe14cbada605d1aa1ccc171d53fdb0438c55efff8ef5a2ef26ecb50a65c4`。对所有开发运行检查 120 s 截止、事件单调性、81 部署的冻结顺序、累计数连续性、监督器结算与认证范围。每条曲线的终点数和全部四个认证时刻均与原汇总表相符。[协议](https://github.com/YBEMR/paper/blob/b8187776fdf2c995cbec410032b34a5a76fa774b/research/kim_multidnn_search_trial/PROTOCOL.md) · [日志及分块索引](https://github.com/YBEMR/paper/blob/b8187776fdf2c995cbec410032b34a5a76fa774b/research/kim_multidnn_search_trial/results/logs_index.json) · [逐次指标表](https://github.com/YBEMR/paper/blob/b8187776fdf2c995cbec410032b34a5a76fa774b/research/kim_multidnn_search_trial/results/run_metrics.csv)
