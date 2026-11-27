# 复核入口与数据格式

## 不运行搜索的复核

先准备登记版本的 U3-b 源码与 U3-a 的冻结输入树。环境变量 `U3B_SRC` 指向含 worker.py 的 U3-b 目录，`U3A_INPUTS` 指向含 nt、four、u2、p1 的冻结输入目录。复核机若没有逻辑核 8，可用 `U4_ARCHIVE_CPU` 指定可用核心。运行 `python -B verify_archive.py` 逐案重建全部计划时刻、原始事件和候选身份。`python -B summarize.py` 与 `python -B mechanism_check.py` 只从归档生成汇总。源树的 199 份依赖按 U3-b 已提交清单重新核验。预检终值另有独立热积分结果，见 `registration/gate_verified.json`。

## 原始证据

| 文件 | 内容 |
|---|---|
| results/工况/runs/方法.json | 每次开始与自然返回／硬截断凭据、预算、CPU、通用预热、分段时间、开始／完成的认证、首次 SAFE 及每次更新在位解的确切时刻、证书身份、原始候选日志分片名 |
| results/工况/journals/*.jsonl.gz | 按 runs 文件的 journal 顺序连接；文件名是解压后字节 SHA256。每行是一条带类型的原始事件。目标计算中即时记录，截止之后只做无损转存。 |
| results/工况/physical/plans.jsonl.gz | 每个不同物理身份包含三阶段排程、显式空闲、连续证书、完整轨迹形状和按顺序的事件块 SHA256。重复调用的内核耗时另在路线证书表保留。 |
| results/工况/physical/block-index.json.gz | 哈希映射到 [分卷序号、字节偏移、长度]。从对应 events-*.bin 取这一段，zlib 解压并按计划顺序拼接，得到小端 float64 的完整 31 列事件数组。manifest.json 含各分卷字节数及 SHA256。 |
| results/工况/verified.json | 冻结 FIFO、双事件重建、全时域温度连续性与能量核验，以及从父配置和原整数配额重建的候选身份计数。 |
| registration/nt60_previous.json | U2 原分卷 SHA256、开发流首个和最佳限时 SAFE、源证书成员位置。独立流的长预算参照是本批真实独立运行。 |

## 日志列

| 类型 | 行内字段与还原方式 |
|---|---|
| parent | 本次调用的父编号、父配置十六进制。每个字节 0–9 为 GPU 档、10–12 为 NPU 档。 |
| native_action | 父编号、从零计的窗、两设备档位、两类 NPU 配额、实际扩展字节、原代价／尾项／最小期限余量，非法为 null。 |
| q4_action | 父编号、从零计的窗、档位对、实际配额、配额偏移、完整前缀重放状态。状态依序为两设备结束时刻、两档位、精确整数代价、尾项、期限余量、积压、后处理结束、最坏违约 tick。使用冻结 extension 在指定窗按任务种类复原字节。 |
| store / choice | 存放真实各层保留者、末层名单、定位依据、局部池完整排序；choice 给出阶段、认证名次和实际配置。 |
| nt_actions / nt_groups / nt_beam / nt_terminals | 宽度及冻结 NT 的原始动作／校准组／保留前缀／有序终端。动作依次含从一计的窗、父哈希、两档位、两配额、候选哈希、试点与原生成器标记、可行状态、参考能耗、峰温估计、风险、排空时间及期限余量。完整配置从根空串和逐窗扩展还原。 |
| group_proposed / group_pool / group_rounds | 父配置、冻结规则每个起点产生的有效候选及扫描／入选数；实际重放通过的完整候选配置和对应请求号、设备、档位；每轮选择与接受身份。被内部条件直接滤去的扫描长度记入计数。 |
| begin / end / cert_start / cert / delivered / return | 单调墙钟分段，按原次序开始和返回认证，完整证据已交付的最优安全计划更新与自然结束。被硬截断的未闭合阶段按剩余时间封账；没有完整交付的证书不参与能耗排名。 |

## 实验入口

在独立工作目录中设置 `U4_RUNS`，运行 `batch_control.py gate`、`gate_check.py`、`batch_control.py batch`。控制器只接受有记录的已完成单元，残留的未交付目录须先查明原因。完整路线共用一只 10 秒硬时钟。预检的 60 秒保护只用于确保交接和分组完整结束。成组单独对照的 10 秒不会加入任何完整路线。分卷由 `pack_results.py` 生成，计算阶段不共享候选证书或在位解。
