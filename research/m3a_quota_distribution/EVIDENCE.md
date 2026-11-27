# 证据、字段与复现

每行工况可从 [cases.csv](tables/cases.csv) 的流名进入同名 [data 子目录](data)。每个子目录提供五个文件。各表中的 `cfg` 是每请求设备与频档字节的 SHA-256，证书内的 `plan_sha256` 是包含三个阶段实际开始时刻、设备、频档以及因果空闲决定的规范计划 SHA-256。每条流使用单独命名空间。

| 文件 | 包含的证据 |
|---|---|
| seed.json | 原 NT 计划身份、输入哈希、历史与本轮的逐事件数组哈希，每一项物理指标的最大绝对复现误差 |
| s1.json.gz、s2.json.gz | 每组每次的序位、亲和核、运行环境、起点、全候选动作、FIFO 结果、排序信息、连续认证调用顺序、原始指标、认证完成时间与最终选择 |
| audit.json.gz | 全部已产生配置的无损编码以及来自哪个阶段、组、父排程和动作。时序可行者有完整原生计划、因果空闲决定、切换明细、全证书、逐事件哈希与占用统计。失败者有所有请求的起止、完成时间、违反期限的请求编号和末状态 |
| traces.zip | 该工况原 NT 和各组两个阶段胜出排程的去重轨迹；每个配置目录含实际逐请求调度 CSV、四节点占用 CSV、原生逐事件数组的无损转置 NPY |

## 数据表

| 表 | 查阅内容 |
|---|---|
| [cases.csv](tables/cases.csv) | 12 条流的两阶段各组能耗、节能百分比、单阶段净收益以及第一阶段全候选回放覆盖 |
| [endpoints.csv](tables/endpoints.csv) | 每工况、每阶段、每组的胜出解和父配置、总能耗及界、E35 和温度项、分项、连续峰温界、最小期限余量、每节点忙/闲/切换段统计 |
| [trajectory_changes.csv](tables/trajectory_changes.csv) | 对原分布真正改变设备的请求数、主阶段和后处理开始时间有变的请求数 |
| [candidates.csv](tables/candidates.csv)、[actions.csv](tables/actions.csv) | 637 个工况内去重的配置和 1,071 条在线候选使用关系（跨组保留重复引用），用于还原物理与方法两个不同分母 |
| [families.csv](tables/families.csv)、[paired_lower.csv](tables/paired_lower.csv) | 每条流的相位与交换覆盖；同流、同降频窗、同设备在原分布和相应引导分布下的严格配对 |
| [wallclock.csv](tables/wallclock.csv)、[wallclock_summary.csv](tables/wallclock_summary.csv) | 全部重复和七个时刻的可用已认证能耗，以及逐工况取重复中位数后的等权平均 |
| [gate.json](data/gate.json)、[verification.json](data/verification.json) | 第二阶段触发者；逐工况源输入重放、所有配置的独立 FIFO 和归档轨迹检查 |

每 tick 为 0.1 ms，记录的时刻从本次任务流起点计算。原模型中的释放时刻和期限还保留有理数毫秒表示。失败配对中的余量用整数期限 tick，连续证书中的余量用原请求的毫秒期限。设备 0/1/2/3 分别为 CPU 前处理、CPU 后处理、GPU、NPU；这些编号与功率向量次序一致。内部 action 的窗下标从零起算；paired_lower 表另给从 1 起算的窗号。普通相位动作的类号 0/1 对应 A/B；交换动作给出两个原始请求 ID。配置字节 0–9 是 GPU 档，10–12 是 NPU 第 0–2 档。changed_requests 表示设备或频档字节发生变化；纯映射数见 trajectory_changes 表。

每个时序可行候选的证书包含所有节点的峰温上下界、峰值时刻、最低温下界、能耗上下界、积分面板数、裕量、节点能耗、基准功率能耗、活动增量、温度相关项、切换、外部项及切换时间表。参考能耗 E35 的分项是实际工作点下的基础功率项、活动增量、切换能耗和外部常耗。完整能耗还加上温度相关功率积分。逐节点 idle 时长已扣除切换；从释放到可执行再到完成的等待时间按请求计算。时间、能耗和峰温字段在 TIMING 失败时按其物理含义留空，禁止以被拒绝计划的能耗计算节能率。

## 读取精确轨迹

traces.zip 内的 requests.csv 给出所有请求的释放/期限 tick、前处理开始和完成、主阶段设备与 OPP、主阶段开始与完成、后处理开始与完成。intervals.csv 按节点记录整个时域的 busy、idle、switch 区间；切换区间频档为切换目标，切换源档和目标档也同时保存在原证书内。events_T.npy 因按列重复较多而转置压缩，读后再转置即得到 P1 原数组。

| 原数组列（从 0 开始，区间含两端） | 含义 |
|---|---|
| 0–1 | 事件段起止 tick |
| 2–5、6–9、10–13 | 四节点段内参考功率、温度斜率、该档空闲基础功率 |
| 14–17、18–21、22–25 | 段首温度、段末温度、段内连续峰温上界 |
| 26–29、30 | 该段四节点积分能耗、累计温度数值误差界 |

例如，从 [A04 的压缩包](data/A04_HLLLHHHL_T35/traces.zip) 读取半周期相位且已降频的排程。

```python
import io
import zipfile
import numpy as np
key = "aff8f75c9c832c28e88fa4d13c1637f6c4799c52f0a5cfca8ccb034c08ef6a36"
with zipfile.ZipFile("data/A04_HLLLHHHL_T35/traces.zip") as z:
    events = np.load(io.BytesIO(z.read(key + "/events_T.npy")), allow_pickle=False).T
```

## 复现

从本分支完整检出仓库，在本目录运行。原计时环境为 Linux、Python 3.12.14、NumPy 2.3.5、SciPy 1.17.0 和 Numba 0.63.1，另使用 psutil。计时批次在三个逻辑核 0、1、2 上交错，各工况的所有方法及重复固定同一核；四个数学线程变量均为 1。共同的通用 JIT 预热及已知 NT 起点再认证在计时前完成。实际时间取决于硬件及运行负载。

```bash
python replay.py A04_HLLLHHHL_T35 aff8f75c9c832c28e88fa4d13c1637f6c4799c52f0a5cfca8ccb034c08ef6a36 work/replay_example
python verify.py
```

完整重跑依次运行 `python batch.py`、`python audit.py`、`python summarize.py`、`python verify.py`。批运行与审计重新生成本目录的比较数据，适合在独立检出中进行。物理指标和事件数组可严格核对，认证耗时、原始计时文件和 ZIP 容器时间元数据会随重跑改变。使用 `sha256sum -c SHA256SUMS` 可核对本次提交的原始交付文件。
