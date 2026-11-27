# 复核与重放

完整请求、原始排程、历史证书和身份摘要位于 `inputs/{D1,D2,C10}/`。每阶段起点均可直接按逐阶段的设备编号、频档、起始 tick 和最低档空闲标志读取。1 tick 为 0.1 ms。C10 的 NT 来源与第三章在 JSON 字段顺序上使用不同的内容摘要，原始文件 SHA 和原排程 SHA 均保存在 identity.json。

## 数据核对

开发版端点与逐模式统计见 `results/`。每个工况的证据包同时包含所有单元的 candidates.jsonl、原始窗口分数、区域、探针池、计时回执以及按排程 SHA 去重的证书和轨迹。归档利用同一工况初解轨迹作按位异或压缩。恢复程序按 SHA-256 核验每个排程、证书和完整 31 列双精度事件数组。若从 Git 取得分卷，放在同一 archive 目录即可自动合并。

在本目录执行下列命令，均为离线读取。

```sh
python evidence.py verify C10
python evidence.py restore C10 --output restored/C10
```

恢复出的 `<排程 SHA>/plan.json` 给出完整原生 rows、low，`certificate.json` 给出能耗分项和峰温界，`events.npz` 的 events 数组为每个事件段的实际数据。前 14 列依次为起止 tick、四节点参考功率、温度系数与驻留基值。后 17 列依次为四节点段首温度、段末温度、段内温度上界、节点能量和累计温度误差界。节点顺序按 P1 的两个 CPU 核、GPU、NPU。资源占用和切换细节由排程和完整证书的 switches 对照。日志中的 TIMING_INVALID 给出冻结验证器遇到的首个冲突，此类尝试没有合法物理轨迹。

## 复现实验入口

以第三章冻结提交为源码根，加入本目录，另将 M1-i 冻结提交检出为独立目录。环境版本及源码摘要见 inputs/source_manifest.json。设置 `E3_THREE`、`E3_NT` 为两个源码根的绝对路径，`E3_RUN` 指向新的输出目录；若 Python 包装在独立目录，将其同时设为 `PYTHONPATH` 与 `G1_ORTOOLS`。单线程环境设置为 OPENBLAS_NUM_THREADS、OMP_NUM_THREADS、MKL_NUM_THREADS、NUMBA_NUM_THREADS、NUMEXPR_NUM_THREADS 全部等于 1。使用相同 Linux CPU 环境可减少限时 CP-SAT 的路径变动。

实际数值执行使用 preflight.py、run.py 和一次性分组运行器 batch.py。preflight.py 在单核运行，计算三份强初解的双入口核对。batch.py diagnostic 按工况执行第一阶段，gate.py 从第一阶段终点检查启动条件，batch.py comparison 仅在条件成立时发起 A–D 对照。复核已发布证据只需使用上方读取命令。history.py 用于从完整历史仓库归档重建 inputs；已发布的 inputs 可直接重放。

第三章 G2 的原始关键区间反馈用于 A 的选区。B 采用普通 VNS 机制适配，随机锚点、近邻及 2/3/4 请求规模循环；Zhang 等的公开摘要区分 makespan 与能耗邻域，本实验沿用任务书给出的 P1 合法范围。Chen 等讨论睡眠切换的收支平衡时间（式 7）及分段计能（式 9–11）。Huang 等第 5 节从单频区间计算给定排程能耗。本实验的热修正、连续安全判定和能量单位均由仓库内的 P1 定义。[Zhang 等](https://doi.org/10.1002/cpe.6456) · [Chen 等](https://doi.org/10.1145/2567935) · [Huang 等](https://www.sciencedirect.com/science/article/abs/pii/S2210537913000395)
