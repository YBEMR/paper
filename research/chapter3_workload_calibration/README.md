# 第三章随机任务与期限校准 V1

依据提交`6fcb6ef3`；用户于2026-10-29确认候选参数及24根／160条件／480份H/M/L时间表的有界执行。这里只生成时间参考和期限诊断，不运行MILP、HEFT、SA或热积分。正式能耗窗口未确定，输出不能直接作为正式求解输入。

## 固定口径

- 既有`config_v01.json` SHA-256为`615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe`。读取原型和完整四节点物理平台；旧配置hold字段不照搬，时间执行合同显式采用auto-L。不修改该文件或旧参考器。
- 四类画像各1/4，CPU六种pre/post等概率；一般异构池的友好类以0.4概率去掉CPU（总体期望各约10%，不强凑实际比例）。固定身份命名子流采用SHA-256，工作量以Decimal60位对数均匀抽样并0.001半上入；所有设备同倍率缩放参考时长，α、q_ref不变。
- 场景A/B严格使用协议八组合。L在0释放，S按大应用基础最快H关键路径计算的相对偏移释放。S2画像和分支模板前缀保持；同根不同规模并非独立样本。
- 分支基准为首4节点菱形后接尾链；S3等分为2/4连续子段。两者是公开实现规则。随机DAG按ceil√n平衡分层，全部末层节点为必需输出；边数为half-up(1.5(n−1))与层／度容量较小者。容量用纯整数网络流计数，不调用优化器。每次生成最多64次确定性构图尝试，全部失败则停止；n=2显式链例外。n≥4拒绝可达全序和基准菱形模板。
- BASE/S2全八场景各映射一次；S1仅投影。S3/S4/S5/S7沿用基础映射并继承期限，派生H表不得重定期限。参考映射、时间表不进入正式算法固定约束或免费初解。
- β=1/1.3/1.6/2仅算术诊断，优先查看1.3；ηL≥0.1为已确认的候选描述预警。不会自动选β或删除失败样本。

## 文件与接口

| 文件 | 内容 |
|---|---|
| `profiles.py` | 既有原型读取、稳定画像子流、时长及功率来源元数据 |
| `topology.py` | 三种拓扑、层/度容量、完整构造与失败trace、独立图检查 |
| `generator.py` | 八场景、真实规模增长、S1/S3/S4/S5/S6/S7/E2变换及不变量检查 |
| `evaluation.py` | 复用未修改的期限参考器，H/M/L构造、期限继承、S1投影、时间下界 |
| `configuration.py` | 已确认候选、公开种子20261029、160条计划；不生成任务 |
| `runtime.py` | 源码冻结、一次性claim、串行子进程、60/3600秒硬停止及证据hash |
| `run_checks.py`、`test_*.py` | 人工夹具、模拟启动及旧47项回归；不生成校准根 |

包装中的`time_contract`是旧参考器严格输入；功率、电压、RC原值另存`physical_platform/physical_profiles`。`evaluation_window_ms=null`、`formal_mapping_constraint=null`、`formal_initial_solution=null`不能被解释为已实现正式算法导出。S6/E2本次只在人工测试验证，不额外加入160条件。

## 执行和证据

已授权上限：24独立根；72基础+48拓扑+12压力+12双请求+16细分；480族时间表覆盖3840份场景排程；另360次S1投影不增加排程构造。每条件60秒、整批3600秒，首个生成／检查／身份错误或超时停止；禁止重采样、补跑和自动β调整。

入口均从仓库根运行，输出须新目录。`freeze`仅接受当前源码通过的人工回执；`execute`仅能消费同一冻结一次。校准已执行后不可将示例命令当作追加预算。

```text
python -B -m research.chapter3_workload_calibration.run_checks --output <new manual result directory>
python -B -m research.chapter3_workload_calibration.runtime freeze --output <new freeze directory> --checks <checks.json>
python -B -m research.chapter3_workload_calibration.runtime execute --freeze <freeze directory> --output <new execution directory>
```

每条件保存生成输入、完整时间表及独立检查、四种β期限/余量、原期限阈值、时间下界、子流与拓扑trace、结果hash和时钟。大文件为标准gzip压缩JSON；失败不覆盖，完整回执和两份证据hash均通过才能接纳。

`manual_precheck01`因系统临时目录权限出现3项ERROR；未产生校准任务。相同源在本机02为96/96；执行证据和预算保护补强后03为97/97。测试输出中的模拟C01名称只是计划ID，fake进程不生成任务。
