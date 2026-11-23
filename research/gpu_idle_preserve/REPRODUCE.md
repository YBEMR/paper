# 复算与证据范围

结果提交在仓库根目录只读核验及重建表图：

```powershell
python -B -X utf8 research/gpu_idle_preserve/verify.py
python -B -X utf8 research/gpu_idle_preserve/analyze.py
```

两条命令均不进行新的物理回放或搜索。verify检查来源哈希、原始文件收据、计算阶段与原Kim逐行相等、500请求期限、切频不抢占、温度继承和能量分解。它是归档一致性核验，不冒充另一套独立物理求解器验证。analyze读取当前18条结果和上轮results.json，输出comparison.csv、summary.csv与PNG/SVG。

原始证据：`raw/<工况>/<档位>.json.gz` 包含完整阶段事件、切换、请求完成明细、热段入口/出口、连续峰温和能量分量；`<档位>_trace.npz`保存全部温度轨迹。基准证书位于上一轮 `research/gpu_idle_dvfs/raw/`，均纳入本轮冻结哈希。环境版本见environment.json。

仅有一个新增控制器：preserve.py将Kim原时间轴中需要H的后两个场景传给原predictive_calendar；前两个场景持续L。没有改旧调度器、热积分器或参数，没有计算中途变频。恢复H使用已知就绪时间；这是确定性离线时间轴假设，并未解决在线预测误差。

若审查者需要独立重执行，在执行冻结提交aba1c4c30f4f585e9bfe03a6cabd1892ef3c09b2的无raw目录检出中运行：

```powershell
python -B -X utf8 research/gpu_idle_preserve/run_preserve.py
```

会执行18次完整热回放，300秒整批硬上限，拒绝覆盖已有raw。稀疏检出需包括gpu_idle_preserve、gpu_idle_dvfs及原冻结依赖目录。本轮已完成一次正式批次，复算说明不自动触发追加实验。

本次开始前，切换分支使上一轮目录落在稀疏检出范围外；入口哈希检查在任何实验前阻止执行。恢复已提交文件后完成冻结，实际正式回放仅一次18条；未改变输入或算法。该环境问题不构成性能调参或实验重试。
