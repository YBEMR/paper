# 第四章冻结源码与科学模型核查（只读）

核查时间：2026-11-12；仓库 `YBEMR/paper`，分支 `chapter4/r2-r5-validation-20261107`，HEAD `143629e86cfa5a3951ab23da218ca9c8f260a277`。

结论：可以基于当前 HEAD 继续用户授权的两个新根 × 6/12 Stage × HEFT/ON、每次 300 秒预实验。第四章核心算法、原 HEFT、合法性检查器与连续电热评价器相对于 `0a01ae35320507618df58dcb19f111548eafc971` 完全未变。新输入仍须合法并使用同一模型与精度；这不构成新输入可行性或算法质量的事前保证。

## 版本证据

最新分支比旧摘要基线前进 17 个提交。以 Git tree/blob 身份直接比较两个提交：

| 路径 | 两提交共同 Git 对象 |
|---|---|
| `research/chapter4_scheduler/blocking/` | tree `5089088a813dacc0ba9c7c0a90850f161329d392` |
| `research/chapter4_scheduler/comparison/` | tree `910be42e9287538c054b26922dc7d78bbe0f692d` |
| `research/chapter4_scheduler/c01/` | tree `8652503e279d06f5dd9ed0870dc7afa39e13c11d` |
| `research/chapter4_scheduler/method.py` | blob `7c6358c65caf3e8487a4cd649d1ecf7f1d8adf97` |
| `research/chapter4_scheduler/graph_core.py` | blob `1b39202a7a7e2dd3e13719496cbc621f5076f699` |
| `research/chapter4_scheduler/validation/lifecycle.py` | blob `fe3e14684c4679c975438bca100473df23274d5e` |
| `research/chapter3_experiments/heft_method.py` | blob `2f998294e91007b77c6f25e5ad695825b920a120` |
| `research/chapter3_experiments/schedules.py` | blob `b953dfed453658a5b2ac01c975be73f1dbba8f52` |
| `research/chapter3_experiments/thermal.py` | blob `5fd55c712e9159077c5445d1a200f934638489da` |
| `research/chapter3_experiments/control_policy.py` | blob `47d215dd74ebacf4ac3260dacbf3892666ba8b84` |
| `research/chapter3_experiments/config_v01.json` | blob `99ee0e39aec29c50cdf1dab27f75e11773ed0798` |
| `research/v1_evaluator/interval.py` | blob `db9fed1af9eee5b3efddafe07002e71887b398cf` |

最新第三章 `milp.py` 有变化并新增 `option_support.py`、`joint_state_support.py`，属于第三章求解表达/剪枝工作，不在上述第四章运行依赖内；本次不运行或审计其求解收益。最新摘要的“ON 原生预算不足”指第三章 MILP 诊断 ON，不能混为第四章阻塞边 ON。

## 科学模型对应

- 第四章 `method.py:38` 的源码身份集合直接包含第三章 HEFT、`schedules.py`、`control_policy.py`、`thermal.py`、精度/预算与原区间热核。`method.py:127` 对每个候选调用原合法性检查；改进期 `method.py:138` 再检查共享部署不变；`method.py:148` 调用原完整连续评价。
- `schedules.py:95` 保持非抢占、执行中不迁移/不换频、频率域空闲时才切换、零附加切换/传输开销。`schedules.py:158` 检查既有起点网格；`:166` 请求截止；`:169` 跨场景共享具体设备；`:184` DAG；`:190` 设备互斥；`:193` 共享频域重叠频档一致。
- `schedules.py:197` 按任务事件重建功耗；`:215` 保持原 auto-L 空闲策略；`:238` 验证域基线只计一次。外部公共功率计能耗但不向局部热节点注热。
- `thermal.py:122` 检查正热容、对称接地被动导热矩阵和声明温区；`:182` 实现 `C dT/dt=-G(T-Ta)+baseline+activity+k(T-Tref)`；`:187` 强制覆盖完整窗口含空闲尾段；`:314` 检查热平衡能量区间相交。
- `thermal.py:320` 用全部节点连续峰值上包络判定安全；`:349` 只在全部场景合法、完整且安全后生成加权能量。权重非负且和为一，零权场景仍必须安全；场景热历史独立，从各自入口温度出发。
- `method.py:95` 初始化沿用 HEFT 最佳能量上界语义；`:103` 改进仅接受 `new.upper < incumbent.lower`；`:187` 拒绝预算后形成的 SAFE。声明邻域不完整，不能解释为全局最优/全局不可行。
- 原 `blocking/method.py` 声明规则仍为固定设备、正加权活动能量节省目标、有限模板、最多一条额外阻塞资源边；本次不应改动。

这里核查的是第四章实际运行沿用第三章科学评价定义，以及其冻结身份没有变化；不是独立数值实现验证，也不是对第三章最新 MILP 每条线性化约束的重新证明。参数仍为抽象自设仿真。

## 应纠正的旧交接背景

1. `research/chapter4_scheduler/results/thermal_pair_20261108/summary.md` 已完成 C01 50/78°C 配对；两组原 ON 都完整安全并通过同核 post。50°C 最终能量上界 0.839132424261 J；78°C 为 0.908129637265 J，ON 无新增改善，峰温上界 78.461184°C。热组 HEFT 初始化有四个实际超温点见证，故“热条件尚未做”已过时；仍无新根/规模泛化证据。
2. `results/evaluation_workpackages_20261110/SUMMARY.md` 为七个既有终解整理及固定周期温度后验，不是新调度搜索。周期热证据不能替代本次独立单窗口的新根规模比较。
3. 本次所查新增第四章内容未发现已经完成两个新根的 6/12 Stage 方法比较；历史 `C01` 与 R1/R2/R3/R5 不宜重新命名为未见任务根。

本审计未运行 HEFT、ON、SA、MILP或热评价；未改任何仓库文件。
