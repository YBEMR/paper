# 《面向端侧推理的热感知高能效任务调度研究》第三、四章图稿

打开 `thesis_figures.pdf` 可按论文图号浏览十幅图，每页含图题、工况和图注。正文插图请使用下表的单图 PDF，Word 也可插入下载包中的同名 300 dpi PNG。图号沿用《第三四章写作蓝图 v2》现阶段编号。

| 论文图号 | 图稿文件名（不含扩展名） | 插入位置与内容 |
|---|---|---|
| 3-1 | `fig01_joint` | 3.3，热状态如何随场景传递，部署与频率如何共同决定能耗 |
| 3-2 | `fig02_power` | 3.6.1，CPU、GPU、DLA 的离散频档及模型功耗分项 |
| 3-3 | `fig04_temperature` | 3.6.2（1），同一 C-HHH 方案在连续与重置评价下的四节点轨迹 |
| 3-4 | `fig03_baselines` | 3.6.2（1）（2），两组常规能效对照与误接纳计数 |
| 3-5 | `fig05a_pressure_classes` | 3.6.2（3），三个压力工况、四个部署的期限合法序列分类 |
| 3-6 | `fig05b_pressure_margins` | 3.6.2（3），六个安全代表的能耗、热裕量与期限裕量 |
| 4-1 | `fig06_search` | 4.5，M0/M1/M2 的认证、回退及场景核复用 |
| 4-2 | `fig08_budget` | 4.6.2（2）（3），开发与留出运行的 120 s 预算结果 |
| 4-3 | `fig07_fixed` | 4.6.2（4），固定四部署的构建次数与互斥耗时 |
| 4-4 | `fig09_progress` | 4.6.2（4），按部署真实完成事件绘制的开发工况阶梯图 |

清单第 5 项提供合并稿 `fig05_pressure`，适于汇报时同页比较。论文正文按图 3-5、3-6 分开插入。清单次序与论文章内图号的对应关系见上表。

## 图注与数据

| 文件 | 内容 |
|---|---|
| `notes_mechanisms.md` | 两张方法框图的符号、判定条件及源码依据 |
| `notes_power_traces.md` | 功耗口径、温度轨迹和安全方案四节点峰温表 |
| `notes_energy_pressure.md` | 常规与压力对照的候选域、计数母集、能耗和裕量 |
| `notes_timings.md` | 固定工作量计时边界与留出补跑依据 |
| `notes_progress.md` | 完成事件、预算边界和证书时刻 |
| `data/` | 十一个 CSV，保留原始精度，用于重绘与引用数值 |

数据以结果提交 `b8187776fdf2c995cbec410032b34a5a76fa774b` 为准。本阶段使用已归档的候选分类、连续能耗、峰温证书、温度采样和时间戳，新增模型评价为 0 次。[冻结仓库](https://github.com/YBEMR/paper/tree/b8187776fdf2c995cbec410032b34a5a76fa774b/research)

图 3-4(a) 的完整 81 部署范围适用于 25 °C、逆序原驻留。四个 25 °C 开发工况按正序原驻留、正序交替驻留、逆序原驻留、逆序交替驻留排列，完整分类记录分别覆盖 15、33、81、67 个部署。跨工况的常规基线对照另附共同四部署数据。完整动态域 Min-Peak-Temp 缺逐候选峰温，A/C 正序原驻留静态域的最低峰温者与同域 Static-DVFS 重合。图 3-3 的 D001 安全参照采用已认证峰温，数值表见图册对应页和 `data/fig04_peak_certificates.csv`。

图 4-2 留出工况每例有两次有效观测。H2 第二次 M1 采用单槽补跑；有效覆盖为 40/81。图 4-4 使用开发集同一批运行的逐事件记录。分图中保留首解、全库认证与总墙钟各自的计时含义。

## 重绘

在本目录运行下列命令。第一条读取包内 CSV 并导出全部单图和组合稿，需要 Python、Matplotlib、NumPy 及中文字体。第二条将单图编排成带书签的图册，需要 ReportLab、pypdf 和可嵌入的中文 TrueType 字体。

```bash
python scripts/plot_all.py
python scripts/build_atlas.py
```

如需从冻结仓库重新提数，各脚本接受的源码位置如下。末条的参数为包含 `research/` 的仓库根目录。四条命令仅读取现有原始归档。

```bash
python scripts/energy_pressure_data.py "<repo>/research"
python scripts/power_traces.py --source "<repo>/research"
python scripts/make_timings.py --trial "<repo>/research/kim_multidnn_search_trial"
python scripts/plot_progress.py --source "<repo>"
```
