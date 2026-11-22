# 实验复算

本目录对应 `codex/ch3-algorithm-selection`。共同祖先为 `f6df387`，历史实现分别来自 `9324f7e`、`a7e789a`，三负载与执行器在 `1021412` 冻结。实验未修改两项既有搜索和原四节点回放源文件。第四章无需变更。

## 直接核验提交的结果

从仓库根目录运行下列命令。已发布的归档按工况拆成六个 tar，各成员保留原压缩字节。读取归档即可验收逐运行证书及曲线，无需重做搜索。

```text
python -B -X utf8 research/ch3_algorithm_selection/audit_cuts.py
python -B -X utf8 research/ch3_algorithm_selection/summarize.py --ablation --from-archives
python -B -X utf8 research/ch3_algorithm_selection/figures.py
```

`records.py` 检查每份运行收据和源码摘要，用原有独立证书检查器重算 500 条完成记录的释放、期限和最小裕量，对四个场景逐段核对频率、热入口继承、四节点温度界与总能耗。它从逐场景代理记录重建 Kim 各代累计排名，核对逐代最高未查映射、尾部次序、种群、Lexicase、交叉和变异。原负载另与同种子历史 Kim 的共同完整代逐代比对。仅 SAFE 父状态的验证检查每次父方案选择。输入摘要按文件字节校验，仓库属性保留原始换行。

## 重做正式搜索

环境为 Windows 11、i7-10750H（6 物理核、12 逻辑核）、约 15.8 GiB RAM，Python 3.12.4、NumPy 1.26.4、Numba 0.61.2、psutil。绘图使用 Matplotlib 及中文字体。六条队列分别绑定逻辑核 0/2/4/6/8/10，Numba/BLAS 各一线程，使用已有机器码缓存；每个运行在全新进程构造候选域和独立的物理、代理与搜索缓存。本轮使用上轮相同的冻结物理源码检出和机器码缓存目录；历史 Kim 的时间来自另一批运行。跨机复算时依赖安装、机器码编译开销及主机负载会影响墙钟。

在没有本轮解包结果的独立检出中运行。三个流已经提交；如要重新生成，可先运行 `loads.py` 并核对 `streams/sha256.json`。原始流同时通过旧断言和新声明检查；A/B 分别逐帧验证，保留每场景边界与尾窗检查。将 `CACHE_DIR` 换成实际机器码缓存目录。

```text
python -B -X utf8 research/ch3_algorithm_selection/run.py --cache CACHE_DIR
python -B -X utf8 research/ch3_algorithm_selection/summarize.py
python -B -X utf8 research/ch3_algorithm_selection/run.py --ablation --cache CACHE_DIR
python -B -X utf8 research/ch3_algorithm_selection/archive.py
python -B -X utf8 research/ch3_algorithm_selection/summarize.py --ablation --from-archives
python -B -X utf8 research/ch3_algorithm_selection/figures.py
```

`--source PATH` 允许引用同字节冻结物理源码和原 81 域参照工况的独立检出。主方法比较和消融分别排队，主比较三法随机交错。每个时盒从创建进程前计时，120 s 硬上限，116 s 停止接纳搜索结果并留出证书写出时间。某次物理调用可能略越过 116 s，超时返回的候选不进入 SAFE 曲线。Kim 的 95 s 生成窗口同时承担逐代认证开销；完成 64 代或用完窗口后检查剩余有效池，允许提前结束。所有方法使用原事件调度、温度相关漏电与完整 10.04 s 计能，超期前缀没有全窗焦耳。搜索终点与进程结束时间分别见 runs.csv。

## 表与复用接口

- `runs.csv` 每行一个种子，含完整切点和频率、SAFE、首证、最佳解初现、共同目标命中、搜索结束、进程用时、峰温及期限证书。空白命中时间表示在本运行内未达标。
- `improvements.csv` 为严格改善事件，`checkpoints.csv` 为各固定时点的最后一张有效 SAFE 证书，提前结束后沿用最后持有的证书。`case_summary.csv` 与 `checkpoint_summary.csv` 的焦耳均限同负载同温度。时间中位数以命中者计算，与命中数一起解释。
- `paired.csv` 给出同种子同工况的能耗胜平负（平局容差 10⁻⁷ J）。`historical_kim_original.csv` 仅列原负载两个温度的旧对照。
- `m2_incumbents.jsonl` 每工况一条可行上界，记录请求流、平台及部署域摘要、全窗部署、各网阶段和 DLA 绑定、四场景频率、四节点峰温上界、期限裕量、能耗、原始证书路径与摘要。第四章读取前需核对输入哈希、部署域与频率编码，并用同一评价器确认可行性。扩展域全局最优性和 M2 加速需由第四章分别验证。

## JEDI 源图复核

[作者发布的 jedi_legacy](https://github.com/cap-lab/jedi/releases/tag/jedi_legacy) 中取 yolo2_relu.cfg、yolo2tiny_relu.cfg、yolo3tiny_relu.cfg、yolo3_relu.cfg，四份 cfg 的 SHA-256 已列入 release_graphs.csv。将 GitHub release API 的 assets 数组（字段含 name、browser_download_url、size、digest）保存为同目录 assets.json，执行 `python research/ch3_algorithm_selection/compare_release.py 目录`。这是图字段的离线核对，无需下载权重 ZIP 或安装 TensorRT。
