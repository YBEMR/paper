# 第三章正式算法对比结果

## 论文插图与正文

[可插入第三章的 LaTeX 正文及四张结果表](thesis_results.tex) · [独立阅读版入口](thesis_preview.tex) · [A–G 可编辑 SVG 与 450 dpi PNG](figures)。绘图脚本同时生成矢量 PDF，图中保留原始种子点，图题及编号由论文模板排版。

| 实验 | 论文图 | 原始或派生数据 |
|---|---|---|
| 一　算法综合效果 | [A 安全能耗及差距](figures/figA.svg) · [B 最低安全能耗命中数](figures/figB.svg) | [逐次结果](tables/run_results.csv) · [A 逐点能耗](tables/figA.csv) · [B 命中数与种子](tables/figB_optimal_hits.csv) |
| 二　跨场景热继承 | [C GPU 温度轨迹](figures/figC.svg) · [D 误收与连续分类](figures/figD.svg) | [原轨迹](../derived/temperature_traces.csv) · [峰温证书](../derived/peak_certificates.csv) · [四节点安全轨迹](raw/figureC/samples.csv) · [误收](../derived/reset_confusion.csv) · [压力分类](../derived/pressure_classification.csv) |
| 三　部署与调频消融 | [E 四策略对照](figures/figE.svg) | [四策略能耗及可用裕量](../derived/ablation_results.csv) · [固定部署敏感性](../derived/figE_sensitivity.csv) |
| 四　匹配热压力 | [F 安全返回数](figures/figF.svg) · [G 安全能耗及热裕量](figures/figG.svg) | [F 计数](tables/figF.csv) · [G 逐点数据](tables/figG.csv) · [超温诊断](tables/non_safe_diagnostics.csv) |

图 B 按未舍入能耗判定 SAFE 且绝对差不超过 10⁻⁹ J 的运行。分母为各方法每工况的五个种子，确定性参照只提供最低值。原图 B 的 [SAFE 返回数 CSV](tables/figB.csv) 保留为历史数据。图 D 的三个高温配置来自已有四部署候选域分类，图 F/G 的算法比较仅覆盖逆序原驻留。

在本目录执行 `python -B plot_results.py` 即可从已接受的 CSV 与图 C 证书生成全部图。连续两次执行 `xelatex thesis_preview.tex` 可生成独立阅读版。论文模板中，将 `\ChThreeFigurePath` 定义为相对主文件的 `figures` 路径，再在第三章“仿真与结果分析”节使用 `\input{.../thesis_results}`。七幅图使用自动编号，图片格式优先 PDF，也支持 PNG。

## 正式实验结果

25°C、81 部署的四个工况中，Kim-Adapt、Kim-Adapt+SAFE、Thermal-GA 各有 20/20 次返回安全方案。本文连续热联合优化方法（CT-Joint）在每个工况均有同域最低安全能耗证书。Kim 在常温下已接近或达到该值。逆序原驻留升至 27.5°C 时，Kim 首选在五个种子中均超温，此时连续热检查和部署选择直接影响可用性。

## 25°C 主实验

每格给出全窗系统能耗（J）。随机方法取五个 SAFE 种子的均值，CT-Joint 取归档 M2 精确值。末列是 GA 高于同域精确值的平均百分比，分母为精确能耗。

| 场景配置 | CT-Joint | Kim-Adapt | Kim-Adapt+SAFE | Thermal-GA | GA 平均最优差距 |
|---|---:|---:|---:|---:|---:|
| 正序原驻留 | 43.110688 | 43.110883 | 43.110883 | 43.241507 | 0.303% |
| 正序交替驻留 | 43.207258 | 43.207440 | 43.207440 | 43.429815 | 0.515% |
| 逆序原驻留 | 43.250300 | 43.250300 | 43.250300 | 44.131804 | 2.038% |
| 逆序交替驻留 | 43.351353 | 43.351353 | 43.351353 | 44.739794 | 3.203% |

20 对 Kim 运行均在第一条候选找到 SAFE。两个正序工况的 Kim 平均最优差距分别为 0.000451% 和 0.000421%，两个逆序工况五次均达到精确能耗。Thermal-GA 在 20 个种子运行中有 3 次命中同域最优；最大单次差距 4.812%，出现在逆序交替驻留。若按每个种子的 GA 安全能耗作分母，CT-Joint 在四个工况平均节能依次为 0.301%、0.508%、1.973%、3.088%。

Kim 每次完成 64 代，搜索从全部 81 个部署中取样，每次实际访问 63–70 个部署。Thermal-GA 同时搜索部署和四段频率，120 s 预算内各次完成的代数和候选覆盖有差异。观测支持逆序工况下 GA 更难命中低能耗方案；搜索编码、搜索算子及预算各自的影响尚未单独量化。

## 共同四部署压力实验

固定逆序原驻留、同一 500 请求流和 A/C/D001/D015 四个部署，两侧温度各跑 15 次。随机方法给出 SAFE 次数和 SAFE 能耗均值。精确参照为相应温度下四部署域的确定性证书。

| 环温 | CT-Joint | Kim-Adapt | Kim-Adapt+SAFE | Thermal-GA |
|---|---|---|---|---|
| 25°C | 43.250327 J，C | 5/5，43.250327 J | 5/5，43.250327 J | 5/5，43.344397 J |
| 27.5°C | 45.100779 J，D001 | 0/5，五次超温 | 5/5，45.276228 J | 5/5，45.206048 J |

升温后，Kim 首选 C 的完整回放能耗为 43.547995 J，500 个请求均按期完成，认证峰温约 81.9217°C。这一能耗仅用于说明超温方案。增强版五次均沿同一排序检查 C、A、D015，经两次回退选中 D015。其峰温为 70.645°C，热裕量为 9.355°C。CT-Joint 选 D001，峰温为 76.320°C，热裕量为 3.680°C，最小期限裕量为 0.309 ms。相对增强版，CT-Joint 节省 0.175448 J（0.388%），D015 多出约 5.675°C 热裕量。

同一高温工况中，Thermal-GA 有 2/5 次找到 D001 的精确方案，3/5 次得到与增强版相同的 D015 方案。CT-Joint 相对 GA 的逐种子平均节能率为 0.233%。四部署最优能耗从 25°C 的 43.250327 J 升至 27.5°C 的 45.100779 J，并伴随从 C 到 D001 的部署切换。

## 图 C

25°C 正序原驻留、部署 C、频率序列 LLL/LLL/LHL/LHL（编码 168）的 CPU、GPU、DLA0、DLA1 轨迹包含 3,504 行原生事件采样，覆盖 0–10.04 s，保留场景交界和末尾 40 ms。场景端点和四节点峰值证书均已与归档方案核对。全窗能耗 43.110758 J，认证峰温上界 76.505632°C，最小期限裕量 2.721279 ms。[四节点轨迹](raw/figureC/samples.csv) · [物理证书与逐请求完成记录](raw/figureC/certificate.json)

## 实验口径与适用范围

- 算法和评价器基线为 `ba774cd2`，正式配置提交为 `f59a2ef1`。三个随机方法共 90 次独立冷启动，单次硬上限 120 s，实测 10.34–116.46 s。Kim 两版的 30 对有序候选池逐对相同。Kim 种群 24、最多 64 代，95 s 截止生成；增强版可依次检查整个已生成候选池。Thermal-GA 种群 32、最多 96 代，116 s 截止接纳结果。此前采用三条检查上限的 14 个已占用槽位均单列排除，其中 10 个完成、4 个中断。[冻结配置](formal_experiment_config.csv) · [逐运行参数、实际代数和回退](formal_experiment_config_actual.csv) · [旧配置账目](superseded/accounting.json)
- 每次使用同一组合内完整部署菜单、每场景 27 种频率组合、500 个请求、40 ms 期限、30°C 四节点初温、连续状态继承和 80°C 上限。SAFE 能耗覆盖整个 10.04 s 系统运行窗。冻结评价器对超期候选记录失败前缀，超期后的全窗能耗留空。最优差距以相应域的精确能耗作分母，节能率以同一运行中基线方法的 SAFE 能耗作分母。[逐运行结果](tables/run_results.csv) · [失败诊断](tables/non_safe_diagnostics.csv)
- M2 的四份 81 部署精确证书沿用归档，历史墙钟为 49.64–56.76 s；四部署参照由归档域证书重建，没有对应本轮单次求解计时。速度比较受执行环境限制。结果适用于冻结的合成平台；27.5°C 仅覆盖逆序原驻留四部署，随机方法每组五个种子。真实设备能耗、热轨迹及其他压力配置仍待验证。

## 数据与复现

| 用途 | 文件 |
|---|---|
| 汇总与配对 | [四法汇总](tables/comparison_summary.csv) · [Kim 种子配对](tables/kim_pairing.csv) · [逐候选检查](tables/kim_checks.csv) |
| 主实验 | [图 A](figures/figA.png) · [A 数据](tables/figA.csv) · [图 B](figures/figB.png) · [B 命中数据](tables/figB_optimal_hits.csv) |
| 热轨迹与压力实验 | [图 C](figures/figC.png) · [图 F](figures/figF.png) · [F 数据](tables/figF.csv) · [图 G](figures/figG.png) · [G 数据](tables/figG.csv) |
| 原始证据 | [30 个逐种子归档包](archives) · [图 C 原始记录](raw/figureC) · [实验设计](design.md) |
| 脚本 | [执行](run_formal.py) · [采样](sample_c.py) · [打包](pack_runs.py) · [从归档重建表格](summarize.py) · [逐运行参数](actual_config.py) · [绘图](plot_results.py) |

每个归档包保存同工况、同域、同种子的三种算法的运行收据、结果、候选事件、连续评价与请求完成记录，并附成员 SHA-256。使用冻结 Python 环境，在本目录运行以下命令即可从归档重建 CSV 和 PNG/PDF。首行参数指向检出本分支且含 `research/` 的仓库根目录。

```text
python -B summarize.py --source-root <仓库根目录>
python -B actual_config.py
python -B plot_results.py
```
