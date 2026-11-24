# 来源与未验证项目

核查日期：2026-11-23。文件内容由 [frozen_sources.json](frozen_sources.json)绑定至 Kim 研究线不可变提交；本轮不下载权重、不建设硬件平台、不新增性能标定。

## 现有数值与请求

| 对象 | 直接来源 | 本轮处理 |
|---|---|---|
| 四个 YOLO 图、尺寸、FP16、CPU/GPU/DLA 服务率 | `research/kim_synthetic_platform_v1/platform.json` 及 `profiles.py` | 原字节保留；公开结构代理与合成性能，不是实测引擎 |
| RC 容量/热导、漏电、板级功耗、活动/空闲功耗 | 同一 platform.json；`thermal.py`、`joint_thermal.py` 等冻结实现 | 不重标定、不缩精度；常温参考点25°C、温限80°C |
| 原始请求、事件优先级、频率与常驻规则 | `kim_case_b_freeze/input.json`、`workloads.py`、`events.py` | 原均衡正序请求摘要逐字节复现 |
| 81 具体部署与27频点 | `kim_multidnn_expansion/catalog.json`、`expanded_input.json` | 保存候选实体；新初态不重新应用旧对称约简 |
| 场景驻留 | `ch3_algorithm_selection/config.json` 中 original：62/63/62/63 | 正逆序均跟随具名场景，不根据结果换驻留 |
| 两类新负载 | 本次 protocol.json 的分析性设计 | 总数750/376事先计算；没有测量来源声明 |
| 预热入口 | `kim_multidnn_expansion/raw/expanded/forward_flat_25C/deployment_C.json` 的 independent.physical.final_c | 旧10.04s全窗完整回放；保留小数、坐标、证书及来源哈希 |
| 图/权重/硬件证据边界 | `kim_multidnn_expansion/sources.md`、`ch3_algorithm_selection/hardware.md` | 继承已有来源核查；不将其升级为硬件证明 |

既有图引用 tkDNN 固定提交 b094c8e50076f944e60f1dc28ce06673788fb6ed，并在平台文件记录各图 Git blob。原硬件审查未发现与获胜切点匹配的目标 DLA 引擎、构建日志和输出对照。本轮没有新增硬件检查，也不假定硬件状态发生变化。

## main.pdf 的可借鉴范围

读取仓库基线的 `main.pdf`：SHA-256 为 36993aaf872d292251b2f58d346e58649eb87e80d46a5f0e641011496ca7f4d6。pdfinfo 报86页，按 pdftotext 的分页符得到86个有内容页面；结构预检脚本因当前环境没有 pypdf 返回 UNAVAILABLE，未伪记 PASS。见 [PDF 阅读证据](reference_check.json)。

重点读取第三章问题定义及实验设置，物理 PDF 第37页和第47–48页（印刷页25、35–36，以章节标题为主定位）。文稿把开始/结束时刻纳入决策，并以随机 Stage-DAG、任务规模、场景数、资源配置和期限系数组织实验；其 Stage 执行时长及活动系数由随机规则产生。**只借鉴按预定负载维度组织实验和分离输入/算法的思路**，不移植自由 Stage 时序、随机阶段时长、场景加权平均能耗或论文图中的性能差距。本文继续研究连续真实时间窗口和 DNN 专用合法切点。

本轮没有对该 PDF 的文献新颖性、实验真实性或算法优越性做独立复核；它不提供新 DNN 板端性能的依据。

## 第二轮 DNN 候选的来源审查

仅列两个结构不同、具有官方实现的候选，**尚未加入候选库**：

| 候选 | 可核查结构/权重出处 | 相对现解析器缺口 | 性能/功耗来源状态 |
|---|---|---|---|
| ResNet-18 | TorchVision 0.20 的 resnet18、IMAGENET1K_V1；残差分类网络 | BN融合、投影残差、全局平均池化与分类头语义；不能把分类头当 YOLO region | 无本平台切分引擎时延/功率；禁止用官方 GFLOPs 当实测时延 |
| MobileNetV2 | TorchVision 0.20 的 mobilenet_v2；倒残差/线性瓶颈分类网络 | 分组/深度卷积、ReLU6、瓶颈与分类头；旧密集卷积服务率不能直接代表深度卷积 | 无本平台数据；不得删算子、改激活以便套旧模型 |

来源：[ResNet-18 官方模型页](https://docs.pytorch.org/vision/0.20/models/generated/torchvision.models.resnet18.html)、[MobileNetV2 官方模型页](https://docs.pytorch.org/vision/0.20/models/generated/torchvision.models.mobilenet_v2.html)。这些页面提供结构、可用权重和预处理，未提供本研究平台切分后的时延、功耗或 DLA 编译成功证据。若进入第二轮，应锁定代码提交、权重哈希、输入尺寸与输出精度规范；不能把不同原生尺寸的网络统一缩放后仍声称精度不变。

DLA 约束须绑定实际 JetPack/TensorRT 版本。官方资料区分受支持算子、构建 loadable、设备配置与 GPU fallback；算子名称受支持不足以证明某分区可构建。[NVIDIA DLA 官方入口](https://docs.nvidia.com/deeplearning/tensorrt/latest/inference-library/work-with-dla.html)。本轮旧8.6.1链接发生跳转且无法重新抓取，历史约束依据保留在旧 sources.md；不利用新版更宽资源限制改变原四名额模型。

第二轮最少需要：完整图与跨切点活跃张量；每个分区设备和精度语义；统一可信的执行时间/传输/功率来源；目标环境可用时的无隐式回退编译、放置与输出核对。当前条件仅支持来源评估，不能提供这些验收结果。若只能采用新的结构多样化合成模型，其全局参数规则必须在实验前冻结，模型名称和结论均明确带“合成”，且不与旧实测来源混同。
