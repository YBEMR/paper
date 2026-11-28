# 低成本配额生成迁移验证

研究结论、数据口径和索引见[中文决策报告](REPORT_zh.md)。正式计时和诊断均已封账。

## 复核现有交付

在本目录运行 `python -B verify.py` 可校验全部交付、截止、预算、原始输入和证书轨迹，无需求解器。若要恢复单份排程，使用 `python -B verify.py --restore CASE PLAN_SHA NEW_DIRECTORY`，工况名和完整哈希取自 [certificates.csv](results/certificates.csv)。恢复轨迹需 NumPy，输出目录应为新目录。事件矩阵的时间、温度连续性及能耗区间在生成归档时逐份核验。相同排程跨运行共享静态证书，单次交付时间、证书内核耗时以当次日志为准。

从现有证据生成统计表可运行 `python -B decision.py`。能耗图由 `python -B figure.py` 生成，需 Matplotlib 和中文字体。三者均只读取已登记的输出。逐次表中的空能耗、空时间表示没有对应认证交付；零候选表示计数器没有观测到候选生成。

## 运行实现

| 文件 | 职责 |
|---|---|
| [setup.py](setup.py) | 从冻结检出复制研究驱动到 Linux 磁盘，构建原调频库，保存驱动文件指纹。 |
| [control.py](control.py) | 校验墙钟和整棵进程树 CPU 保护；正式四流固定核轮转，禁止重复发车。 |
| [transfer.py](transfer.py) | 调用冻结独立冷进程入口，替换配额选择并记录共用轻量计数。 |
| [fixed.py](fixed.py)、[probe.py](probe.py) | 真实父路径及固定工作量诊断，附加探针扰动核对。 |
| [archive.py](archive.py) | 截止裁决、连续证书与物理轨迹核验、去重归档，保留原始时钟和诊断记录。 |

冻结依赖和数值库位于第一轮的 Python 3.12 Linux 环境。实现通过 `FAST_SCRATCH` 查找已有的 `site`、`nt`、`four`，通过 `TRANSFER_ROOT` 定位本轮独立账本和 Linux 原始工区。预登记写明启动、程序缓存和停止条件。可单独复核当前档案，无需重建这个运行环境。
