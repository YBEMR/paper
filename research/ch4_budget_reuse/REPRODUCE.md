# 从归档复算

执行冻结为 `89d02ca58bd59dfc5c11445b47f3ea3ed7b8abed`，父提交为第三章 `ed437fc13071409bf49b7c241d7336d580fdd92e`。从结果提交的完整检出运行：

```text
python -B -X utf8 research/ch4_budget_reuse/analyze.py
python -B -X utf8 research/ch4_budget_reuse/figures.py
```

分析逐份核验 tar 与成员 SHA-256、冻结版本、保留的原始文件摘要和运行上限。随后从 candidate 事件独立重建改善序列，调用原第三章检查器重验每个所选部署、频率、四节点温度继承及 500 条请求的身份、完成时间和期限。B/C 在计分进程中也把最终解交给原物理回放，逐字段核对。固定回放的两套结果与 A 流的对应条目完整比较。真实 A/B 搜索则检验每个匹配区组共同前缀的调用参数、代理结果、精确峰温和父状态所需信息。扩展域 4,319,803 个代表的最优性不在本轮证书范围内。

## 原始数据

每个运行一个 tar，含 reservation、receipt、进程输出、逐运行配置、结果、完整 flow、events 与最终解 selection；固定回放另含 comparison。flow 每行依次为序号、类型、参数、相对起始及返回时间（秒）、返回值。proxy 表示 SetFreq 所请求的独立场景标量，deadline 表示候选入口逐场景期限筛查，full 表示完整连续回放；full 内部四段的调度与热计算已包含在该顶层调用中。完整或截止时仍未被接纳的调用均保留，用于计分的时钟以通过截止检查后的 incumbent 为准。

- `tables/runs.csv`、`checkpoints.csv`、`improvements.csv`、`case_summary.csv` 分别列逐运行、固定墙钟、每次改善和工况汇总。空值表示尚未获得相应证书或未命中。
- `tables/fixed_agreement.csv` 列两条固定回放对 A 原调用的逐项核对。逐项数值可从对应 flow 的同一序号读取。
- `tables/exclusive_costs.csv` 的时间列互斥，计数前缀为 `n_`。whole 含初始化和最终证书处理；0–20、20–116、116 后、到目标及目标后分别列出，其中目标时点取该次 incumbent 的计数快照。每个 phase 内可加秒数，不能把重叠阶段相加。最终结果文件的写入、解释器退出和父进程回收位于 worker 最后快照之外；进程总墙钟见 runs.csv。峰值内存包括进程工作集和新 LRU 的代表性 NumPy 数组字节数，后者未计 Python 容器开销、可能包含与调度对象共享的数组，不能等同为新增 RSS。
- `tables/amortization.csv` 按相同顺序累加顶层调用本体的墙钟，分固定回放全前缀及 A 达标前缀，并列真实搜索的共同前缀。固定流只重放评价请求，不复现候选生成/排序对原执行链缓存的预热。持续摊销点使用自首个 full 后原累计耗时始终不低于 M2 的最早调用，空白表示至流末未达到；不外推到未观测调用。
- `tables/paired.csv`、`case_gates.csv`、`adoption.csv` 保留九对、各工况和整体门槛。相对于配对基线计算耗时比，未命中保留空白及计数；不跨负载平均焦耳。
- SVG 和 PDF 的三组图使用同一 CSV。PDF 存于仓库已有的论文插图目录 `research/latex/figures/ch4_budget_reuse/`。

## 重做计分运行

使用独立检出和空运行目录。确认历史物理评价依赖、Python/NumPy/Numba 等版本与冻结清单吻合。正式批次从冻结提交检出，不能将另一个软件版本混入同一主表。在根目录以 Python 3.12.4 运行：

```text
python -B -X utf8 research/ch4_budget_reuse/prepare.py SOURCE_ROOT
python -B -X utf8 research/ch4_budget_reuse/execute.py --source SOURCE_ROOT --cache NUMBA_CACHE_DIR
python -B -X utf8 research/ch4_budget_reuse/bundle.py
```

准备时将环境变量 NUMBA_CACHE_DIR 设为与 execute 的 --cache 相同的目录，并将 OPENBLAS_NUM_THREADS 设为 1。SOURCE_ROOT 可以是完整检出的根目录；本次使用第三章沿用的相同物理源码检出，使历史通用 JIT 缓存命中路径一致。只预编译通用筛查函数，一次性准备实测 3.388 s，候选热核数为零。每次工作进程独立，所有领域缓存重新初始化。同一台 i7-10750H、Windows 11、逻辑核 0、单进程，Numba/OpenBLAS/MKL/OMP 线程数均为 1。CPU、后台负载及机器码缓存差异会影响复测秒数。

真实搜索依种子分三轮，轮内依次是 original 30°C、A 25°C、B 30°C，各区组按 ABC、BCA、CAB 排列。这样在九个区组总体上平衡方法次序；同一工况内次序固定，不能从三个种子估计独立的顺序效应。固定流中的完整返回按原顺序逐项比对；C 若未更换名额，共同调用前缀还会对照 B 的完整回答。候选打分和邻域生成单独计时，原先 Python 最终排序、集合构造等记入搜索控制。
