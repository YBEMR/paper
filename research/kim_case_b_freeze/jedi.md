# JEDI 对 Kim case β 输入的可用范围

**判决。** JEDI 为四个 YOLO 网络提供了 ReLU 网络工件、部分历史切点和 Xavier 同平台的类别吞吐实测。此次核查未取得可绑定到 Kim 表 9(a) 四个具体部署的 256×256 阶段计时、功率或逐节点热轨迹。归档类别吞吐可作异口径背景，不能充当这些阶段的数值上下界。数据核查日期为 2026-11-18，全程只读。

## 核对的候选与版本

表中层端点均含首尾。Kim 的实测环境为 AGX Xavier、JetPack 4.3、TensorRT 6、COCO2017 val、ReLU、256×256、FP16、batch=1。JEDI README 的最新 FP16 吞吐表使用 AGX Xavier、JetPack 4.3、MAXN + jetson_clocks、416×416。README 给出整网与设备类别；没有把该表逐行绑定到历史切点、线程、频率或引擎哈希。该处只引用 FPS，不把数值精度 FP16 误写成模型准确率。公开材料尚未为这两种图像尺寸、各个切点给出同一权重和相同推理结果/mAP的可复核链条。[Kim §6.1、表6、9](https://doi.org/10.1109/TC.2022.3218991) · [JEDI 版本化运行条件与网络表](https://github.com/cap-lab/jedi/blob/50fda15ce3b82b38f46adddc04c47b58042cef71/README.md)

| case β 应用 | Kim 表9(a) 的 FSM-A 部署 | JEDI 公开 FP16 文件的实际内容 | 416×416 类别 FPS：基线 GPU / JEDI GPU / JEDI GPU+DLA |
|---|---|---|---|
| app0，YOLOv2 ReLU | D[0–29]、D[30–40]、G[41–53] | sample.cfg 指定 DLA0[0–20]、GPU[21–53]。此文件的两段与 Kim 的三段不同。 | 74 / 187 / 295 |
| app1，YOLOv2tiny ReLU | D[0–16]、G[17–23] | 2021-01-12 配置指定 DLA0[0–5]、GPU[6–23]；2021-04-06 配置指定 GPU[0–23]。两者 batch=1，CPU 前/后处理线程分别为 4/1 与 4/2。当前主分支的全 GPU 配置为 INT8。 | 91 / 625 / 701 |
| app2，YOLOv3tiny ReLU | D[0–16]、G[17–34] | 同两版历史文件分别为 DLA 前缀到第 5 层、GPU 至 34，以及单 GPU 全网到 34。当前主分支对应文件为 INT8。 | 102 / 614 / 729 |
| app3，YOLOv3 ReLU | G[0–178] | README 报告此网络的全 GPU 类别，固定 master 的 yolov3.cfg 却指定 DLA/DLA/GPU 且 INT8。历史 FP16 文件的端点为 27、46、178，属于三个阶段。缺少把 Kim 单 GPU 实例与 JEDI 某次同分辨率完整运行一一绑定的依据。 | 50 / 85 / 128 |

部署来源为[当前 sample.cfg](https://github.com/cap-lab/jedi/blob/50fda15ce3b82b38f46adddc04c47b58042cef71/sample.cfg)、[2021-01-12 YOLOv2tiny](https://github.com/cap-lab/jedi/blob/c0d98171494251942ecefa4fb67f046279544ecc/yolov2tiny.cfg)、[2021-04-06 YOLOv2tiny](https://github.com/cap-lab/jedi/blob/bc263fcce612ccca15f9b2b11c919d1b15dcc5e7/yolov2tiny.cfg)、[早期 YOLOv3tiny](https://github.com/cap-lab/jedi/blob/c0d98171494251942ecefa4fb67f046279544ecc/yolov3tiny.cfg)、[随后 YOLOv3tiny](https://github.com/cap-lab/jedi/blob/bc263fcce612ccca15f9b2b11c919d1b15dcc5e7/yolov3tiny.cfg)、[早期 YOLOv3](https://github.com/cap-lab/jedi/blob/c0d98171494251942ecefa4fb67f046279544ecc/yolov3.cfg)、[当前 YOLOv3](https://github.com/cap-lab/jedi/blob/50fda15ce3b82b38f46adddc04c47b58042cef71/yolov3.cfg)。两项 YOLOv2tiny 历史配置的 Git blob 分别为 f7a78cc8bc05d78860d19b8a4ec8a6d965c2f677 和 0dcc00f34b922d910c1181af397d79d17e42581f。引擎构建源程序从 0 开始，上一段切点加一作为下一段入口。[JEDI model.cc](https://github.com/cap-lab/jedi/blob/c0d98171494251942ecefa4fb67f046279544ecc/src/model.cc#L120-L147)

## 可以保留的证据边界

- **时长与期限。** Kim 图 2 展示 YOLOv2 的 13–18 层改放 DLA 后引入 I/O 重排 kernel；§3.1、§5.1 说明 DLA 以阶段测时，GPU 以 TensorRT IProfiler 测 kernel，估计 WCET 取样本最大值与均值加六倍标准差的较大者。单层处于不同融合或边界上下文时，对应执行对象即可能改变。公开 FPS 的倒数仅是平均出帧间隔，不能替代响应时间上界，也不能按层数或分辨率比例乘除重建另一切段的 ACET/WCET。[Kim §§3.1、5.1、5.2.4](https://doi.org/10.1109/TC.2022.3218991)
- **频率与整套配置。** Kim 表 7 按 CPU、GPU、DLA 类型列档，不支持从表中为 DLA0、DLA1 各自任取频率。表 9(b) 的 case β 仅覆盖表 9(a) 同一部署、FSM-A 的 SC3。在 25/30/32 FPS 下 CPU 为 1958.4/1651.2/1728.0 MHz、GPU 为 1032.75/1338.75/1377.0 MHz；正文称 DLA 保持最高档。1958.4 不在印刷表 7 的 CPU 列表内，原样记录、隔离该不一致。表 8 的最大 FPS 属于完整方法所得方案，表 10 的 FPS 是实验输入要求。它们共同约束对原实验的解释，无法生成其他部署的期限通过标签。MAXN 是功耗模式；JEDI 公布的吞吐没有逐域扫档记录，Linux 官方文档的模式上限也不是实测频率轨迹或功率。[Kim 表7–10](https://doi.org/10.1109/TC.2022.3218991) · [JetPack 4.3 / L4T 32.3.1](https://developer.nvidia.com/embedded/l4t-3231-archive)
- **功率、热与实际落点。** README 的 -p、-t 分别为可选 tegrastats 和推理总时间输出。在 master 的完整 62 项目录树中，log 只含占位文件；jedi_legacy 有网络配置和权重，可核对资产名称，未提供这四套 β 部署的分段测量数据库。Kim §5.2.3 指定 CPU/GPU 用选项 E、DLA 用选项 A 的可映射层，在其他频域保持最高、一次改变一个频域的实验中回归每个应用的动态功率。取得该回归的系数与适用范围后才可按其定义使用。Xavier 的通用轨名称也不足以分别识别 DLA0 和 DLA1 的有功功率或节点热容。JEDI 引用的 tkDNN 未锁提交；其公开版本中存在 GPU fallback。配置声明、引擎实际落点和物理采样需分别记录。[JEDI 发布资产](https://github.com/cap-lab/jedi/releases/tag/jedi_legacy) · [master 树](https://api.github.com/repos/cap-lab/jedi/git/trees/50fda15ce3b82b38f46adddc04c47b58042cef71?recursive=1) · [tkDNN GPU fallback](https://github.com/urmydata/tkDNN/blob/b094c8e50076f944e60f1dc28ce06673788fb6ed/src/NetworkRT.cpp#L313-L314) · [NVIDIA Xavier 供电轨说明，R32.7.6](https://docs.nvidia.com/jetson/archives/l4t-archived/l4t-3276/Tegra%20Linux%20Driver%20Package%20Development%20Guide/power_management_jetson_xavier.html)

核查覆盖 master 上四个模型名称对应的配置、sample.cfg、README、根目录运行/采集接口、各模型配置在 master 历史中的版本、发布资产列表与当前公开分支上的同名配置。另以论文题名、AGX Xavier、YOLOv2tiny/YOLOv3tiny、256、cut point、stage、layer profiling、power、supplement 检索逐阶段材料。在本次核查范围内可冻结的数字是已注明条件的吞吐、论文频档及完整部署的论文报告点；任何声明针对 case β 各阶段的毫秒、瓦特、热上限与频率响应仍需匹配的测量或明示的假设。无新增运行或参数拟合。
