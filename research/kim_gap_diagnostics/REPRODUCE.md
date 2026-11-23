# 复算与归档说明

本轮已执行完毕。以下默认只读取归档，不调用搜索、事件调度或连续热积分。不要为复算报告重新运行实验。

## 1. 检查与重建报告

在结果提交的仓库根目录，使用 `environment.json` 对应Python环境：

```powershell
python -B -X utf8 research/kim_gap_diagnostics/archive.py
python -B -X utf8 research/kim_gap_diagnostics/analyze_gap.py
python -B -X utf8 research/kim_gap_diagnostics/frequency_attribution.py
python -B -X utf8 research/kim_gap_diagnostics/verify_gap.py
python -B -X utf8 research/kim_gap_diagnostics/build_outputs.py
```

第一条校验整个交付目录。后四条重建CSV、归因、核验和图表；后处理时间及绘图环境可能使派生文件字节改变，因此应在独立工作目录复算，保留原始清单。原始数据和历史归档不应改写。核验不重做热积分，其作用是检查冻结来源、已有证书内部一致性、500请求明细、完整频率数组及结果提取；它不取代另一套独立物理模型验证。

已用Python 3.12.4、NumPy 1.26.4、SciPy 1.13.1、Numba 0.61.2、llvmlite 0.44.0、psutil 5.9.0完成运行。报告绘图另需Matplotlib；Windows使用Microsoft YaHei，其他平台可安装对应中文字体或替换绘图字体，不影响数据。

## 2. 原始文件含义

`raw/<case>/<phase>/` 有12个工况—阶段目录：

- `reservation.json`：执行冻结提交、输入/源码清单哈希、CPU核。
- `receipt.json`：子进程退出状态、总墙钟、文件哈希。压缩归档在子进程结束后进行，不执行搜索。
- `events.jsonl.gz`：带实际墙钟时间的初始化、旧结果回归、候选开始、场景构造、SetFreq、SAFE见证和候选完成记录。
- `physical.jsonl.gz`：每个唯一策略的完整原评价器记录，含场景入口/出口温度、峰温上下界、真实能耗和期限信息。
- `safe_NNN.json.gz`：已完整评价SAFE策略的部署阶段、四场景频率、物理结果及500条请求完成明细。索引见 `safe_witnesses.csv`。
- `Xxxxxxxx.npz`：长度27⁴的联合频率能耗数组；无期限可行解的码为非有限值。触发热回退时另有同长度 `thermal_status`，0=期限不可行、1=SAFE、2=超温、3=未决。频率码为 `sum(i[j]*27**(3-j))`，单场景索引使用原 `search.OPPS`。
- `result.json`：已完成候选、进行中候选、未完成列表、已认证最好方案、计时和调用数。正在处理候选已有SAFE证书照常保存，但不获得固定部署最优性结论。
- `worker_end.json` 与 `console.txt`：子进程收尾时间和错误输出。本批12次均正常退出，控制台文件为空。

若无温限最低连续能耗候选经完整回放为SAFE，整个频率域的能耗下界闭合，不必把所有频率策略逐条物理积分。若其超温，原M2连续热分类检查所有期限可行码；任何UNRESOLVED阻止最优性结论。证明范围始终是该固定部署，不能升级为431万部署域证书。

`frequency_attribution.py` 用归档场景能耗及入口温度恢复同一策略的独立初始化代理能耗，不生成或评价新策略。其SetFreq复算校验和每对频率归因保存在 `frequency_attribution.json/csv`。

`phase_costs.csv` 的 `time_replay_inclusive_s` 包含内部调度、完整连续热评价及SAFE明细归档；`time_ledger_inclusive_s` 也可能嵌套其中。不可把所有列直接相加。图中仅将不重叠的调度与构核单列，其余取完整墙钟余额。

## 3. 需要重执行时

本轮只获准并完成一次批次，不自动重执行。审查方若自行重执行，可在**无raw目录**的执行冻结提交 `1b03f122e9f7b80cbdf2b06a6aa8f4e35854ae71` 独立检出目录中运行：

```powershell
python -B -X utf8 research/kim_gap_diagnostics/execute_gap.py
```

不需要重新生成请求、候选或冻结哈希。执行器会拒绝覆盖已有 `raw/`，并校验70个已冻结文件。不同机器可能在120秒内完成不同数量的部署，应分别保留实际覆盖，不延时凑齐48个候选。

输入来源为原 `research/ch3_algorithm_selection` 的3类负载流和18个Kim历史运行。代码沿用原扩展部署合法域、原事件调度、原M2频率能耗联合函数和连续热核；原函数通过AST提取仅用于避免执行旧模块的固定全局模型绑定。未改函数体、物理参数或频率集合。

六个固定部署阶段和六个探查阶段各用独立120秒预算、116秒停止接纳，六核并行，同工况两阶段串行。第一次SAFE是已知Kim方案回放，不能将其作为从零搜索速度。历史Kim的耗时只提供来源记录，不做跨批次速度结论。
