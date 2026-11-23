# 复核与复算

## 冻结身份

- 基准提交：40f8f095ff067cc388890c824908592c3bcf8659。
- 执行冻结：35fb9f073bec069059f7c9f3dadb57e71bc338bc；配置、控制器、事件接口、必要检查和145项来源清单在运行前提交。
- 实际执行SHA、Python和依赖版本见environment.json；输入逐项相等检查见input_checks.json。
- raw内36份新物理证书、36份控制器日志、36份全温度轨迹。receipt.json记录运行时间、返回状态和原始文件SHA256。
- Kim及Oracle各18条复用旧目录，不复制伪装为新运行；comparison.csv保留来源提交、证书路径及reused标志。

## 默认离线核验（不重新运行物理实验）

在仓库根目录，使用带numpy、scipy、numba、matplotlib的Python；实际版本见environment.json：

```powershell
python -B -X utf8 research/gpu_idle_baselines/archive.py
python -B -X utf8 research/gpu_idle_baselines/verify.py
python -B -X utf8 research/gpu_idle_baselines/analyze.py
```

archive.py先检查交付完整性；verify.py核对执行来源、原始收据、阶段工作量/顺序/频率、因果预测、期限、连续热块继承和能量分解。峰温证书由冻结完整评价器在正式运行时生成；离线脚本检查证书与轨迹一致性，不将离散温度采样重新当作连续峰温证明。analyze.py只重建CSV、decision.json与PNG/SVG，不调用事件或热模拟器。不同绘图环境可能改变图片字节，原始交付哈希应在重绘前核验。

原始证书中activity_J包含切换能量，汇总时compute_activity_J减去switch_energy_j。能量加总时切换只计算一次。timing_diagnostics.csv的direct_dvfs_wait_ms只统计GPU空闲、固定队首已实际就绪但频档不可用时的阻塞；gpu_ready_queue_wait_ms还包含普通GPU排队，不能混为直接切频延迟。

## 如另行独立复现实验

本轮不自动追加。需在全新独立checkout的执行冻结提交35fb9f0上运行，保持归档未覆盖：

```powershell
python -B -X utf8 research/gpu_idle_baselines/run_baselines.py
```

runner要求执行来源哈希相等、没有已跟踪改动且raw目录不存在；只运行36次完整认证，600秒整批硬停止，故障不自动重试。每个负载/开销/策略独立重置控制器，同一控制轨迹分别在25/30°C完整认证。运行结果与原归档分开保存，不能回写替换本轮数据。验证/绘图脚本在结果提交中，正式策略与配置仍取冻结提交。

## 文件索引

| 文件 | 内容 |
|---|---|
| results.json / console.txt | 36次新增评价与原始控制台输出 |
| raw/*/*.json.gz | 500请求完成记录、阶段、转换、时钟区间、热块、证书 |
| raw/*/*_control.json.gz | 逐预测观测来源、运行时事件、GPU开始时刻及阻塞 |
| raw/*/*_trace.npz | 完整四节点温度轨迹 |
| comparison.csv | 72条匹配记录，含36条复用记录、全部物理和控制指标 |
| summary.csv | 18组四策略匹配对照 |
| energy_attribution.csv | 空闲/计算/漏电/转换能量归因 |
| timing_diagnostics.csv | 等待、阶段偏移、首帧与后续帧期限裕量 |
| execution_manifest.json | 执行前冻结的来源、实现、输入和旧证书哈希 |
| archive_manifest.json | 结果交付文件清单及哈希（清单自身除外） |
