# 多 DNN 部署候选的来源与准入

本轮冻结 8 个逐网络候选，每个网络 2 个。全部组合先生成 16 套，再依据全部常驻 DLA 阶段至多 4 个的条件保留 12 套。该集合包含历史 A、C。候选选取依据为原文具体部署、全 GPU 模板与公开 FP16 配置，形成规则早于本轮新增结果。其他未纳入配置属于未采样候选；没有以本轮结果宣称其 Pareto 被支配。

核查日期为 2026-11-19。论文依据为本仓库原始 PDF，已阅读 §5.1—5.2、表 3—4、表 9(a) 和 §6.1，表 9(a) 另外进行了页面图像核查。PDF SHA-256 为 `0e73cbf8f19e7530871bd38e584b3e19d639814efc75ea008c7b67807697c89d`。JEDI 依据为本轮从作者仓库逐文件读取的不可变提交。数据来源核查不等同于实机推理核验。[Kim 2023 原文](../../papers/2023_Kim_Energy_Aware_Mapping.pdf) · [DOI](https://doi.org/10.1109/TC.2022.3218991)

## 五种结构和切点规则

| Kim 表 3 模板 | 推理阶段组成 | DLA 常驻阶段数 |
|---|---|---:|
| A | DLA0 → GPU | 1 |
| B | GPU → DLA0 → GPU | 1 |
| C | DLA0 → DLA1 → GPU | 2 |
| D | GPU → DLA0 → DLA1 → GPU | 2 |
| E | GPU | 0 |

表 3 的 DLA0、DLA1 允许互换。§5.1 规定切点指上一阶段的末层，层号从 0 开始，端点包含在内。卷积与其后激活层之间不作为切点，连续不可映射 DLA 的层之间也不保留切点。四网络的尾部含 DLA 不支持层，因此五种模板均以 GPU 结束。本文只恢复有具体出处的 A、C、E，B、D 作为原方法规则记录，尚未为它们生成具体新切点。

表 4 给出 YOLOv2 / YOLOv3 / YOLOv2tiny / YOLOv3tiny 的层数分别为 54 / 179 / 24 / 35，筛后切点数 22 / 78 / 10 / 10，总候选数 2025 / 82161 / 221 / 221，Pareto 解数 112 / 158 / 19 / 14。原表没有发布这些集合的完整切点清单或阶段响应数据库，不能将本轮小库称为该 Pareto 集复现。§5.1 的个体适应度来自最高频率下的实测时延和处理器功率，§5.2 则组合逐网络候选、检查 DLA 常驻数量、确定物理 DLA、逐场景选频与计算平均能耗。[原文，期刊页 1671—1674](../../papers/2023_Kim_Energy_Aware_Mapping.pdf)

## 逐候选来源

| 应用 | 候选 | 完整推理分段，含首尾 | 来源类别与具体依据 |
|---|---|---|---|
| YOLOv2 | A29 | DLA0[0–29]，GPU[30–53] | Kim 表 9(a) case α 的 YOLOv2 实际部署，作为历史 A 移入 case β |
| YOLOv2 | C29_40 | DLA0[0–29]，DLA1[30–40]，GPU[41–53] | Kim 表 9(a) case β app0，历史 C |
| YOLOv2tiny | A16 | DLA0[0–16]，GPU[17–23] | Kim 表 9(a) case β app1 |
| YOLOv2tiny | E | GPU[0–23] | Kim 表 3 E 与 §6.3 BS；JEDI 2021-04-06 FP16 配置进一步确认全 GPU 形式 |
| YOLOv3tiny | A16 | DLA1[0–16]，GPU[17–34] | Kim 表 9(a) case β app2 |
| YOLOv3tiny | E | GPU[0–34] | Kim 表 3 E 与 §6.3 BS；JEDI 2021-04-06 FP16 配置进一步确认全 GPU 形式 |
| YOLOv3 | E | GPU[0–178] | Kim 表 9(a) case β app3，历史固定部署 |
| YOLOv3 | C27_46 | DLA0[0–27]，DLA1[28–46]，GPU[47–178] | JEDI 2021-01-12 配置直接给出 FP16、batch=1、DLA/DLA/GPU、27/46/178、DLA 核 0/1 |

其中 YOLOv3 C27_46 在本轮属于**公开配置约束的合成候选**。没有把它标成 Kim 表 9 使用过的部署。两个 tiny 的全 GPU 是有公开支持的原方法 E 结构，其跨网络常驻组合以及同一仿真器下的 256×256 时序是本轮构建。两 tiny 的 DLA 物理绑定继承冻结基线，未重新执行 Kim Algorithm 2 的绑定启发式。[候选机器可读清单](candidates.json)

[JEDI YOLOv3 FP16 三段配置](https://github.com/cap-lab/jedi/blob/c0d98171494251942ecefa4fb67f046279544ecc/yolov3.cfg) · [YOLOv2tiny FP16 全 GPU](https://github.com/cap-lab/jedi/blob/bc263fcce612ccca15f9b2b11c919d1b15dcc5e7/yolov2tiny.cfg) · [YOLOv3tiny FP16 全 GPU](https://github.com/cap-lab/jedi/blob/bc263fcce612ccca15f9b2b11c919d1b15dcc5e7/yolov3tiny.cfg)

## 算子与跨段依赖

新增 YOLOv3 前 47 层按冻结图展开，仅含卷积、ReLU 和 shortcut 求和。所用卷积核为 1×1 或 3×3，步幅 1 或 2；shortcut 是相同形状张量的逐元素求和。切点 27 为 shortcut 输出，切点 46 为卷积后的 ReLU 输出，均未切开卷积—激活对。GPU 从 47 开始，保留随后所有残差、route、upsample 和检测头。第 47 层仍需要第 42 与 46 层输出，阶段交接须传递两个活跃张量。统一生成器的 live_bytes 按后继依赖取集合，保留这个跨段依赖和流量。

对应旧代官方文档 TensorRT 5.1.2 RC 的 §6.1—6.2 已列出 FP16 DLA、ReLU、elementwise Sum 和上述卷积范围。这为算子语义提供旁证。此次尝试读取 TensorRT 6.0 的官方归档页面失败，没有将新版本算子支持倒推为 TensorRT 6 已验证。JEDI FP16 完整阶段配置是此次具体分段的直接工件依据；缺少引擎构建、实际层落点及 GPU fallback 日志，所以单阶段纯 DLA 执行仍是透明的合成执行假设。[NVIDIA 旧代 DLA 支持，文档页 48、51—52](https://developer.download.nvidia.com/compute/machine-learning/tensorrt/docs/5.1/rc/TensorRT-Developer-Guide.pdf)

GPU 支持沿用公开四个网络的全 GPU 基准及冻结图。YOLO 检测头、reorg、upsample 等没有在此次小库中分配到 DLA。已知不满足尾部支持规则的全 DLA 网络不准入；任意新增 B/D 切点、随机延长 DLA 前缀尚无逐候选依据，不加入；JEDI 当前主分支的 YOLOv3 C36_78 配置是 INT8，因此不作为 FP16 实测证据。历史 FP16 配置的存在避免了为适配本轮条件而改变精度。[当前 JEDI YOLOv3 INT8 配置](https://github.com/cap-lab/jedi/blob/50fda15ce3b82b38f46adddc04c47b58042cef71/yolov3.cfg)

## 数值与平台边界

Kim 的实验目标为 AGX Xavier、JetPack 4.3、TensorRT 6、256×256、FP16、batch=1，使用 ReLU 网络。JEDI README 的公开吞吐表使用 AGX Xavier、JetPack 4.3、416×416、MAXN 与 jetson_clocks。此次未取这些 FPS 的倒数或比例作为新阶段的执行时间。所有候选共享冻结平台的图、MAC、数据量、全局计算吞吐与带宽参数、频率—时间—功率关系、CPU 前后处理、交接参数及四节点 RC。图变化只改变由同一公式导出的阶段响应和资源事件。[冻结统一平台](../kim_synthetic_platform_v1/platform.json) · [生成器](../kim_synthetic_platform_v1/profiles.py) · [JEDI README 固定版本](https://github.com/cap-lab/jedi/blob/50fda15ce3b82b38f46adddc04c47b58042cef71/README.md)

常驻占用按全部四应用计算，场景不活跃也保留相应 DLA 阶段。12 个通过容量条件的组合均使用独立 DLA0、DLA1 执行资源和共同 DLA 频域，跨场景保持映射。所有请求执行完整固定图，阶段顺序和依赖由分段重建。具体事件时序还需通过互斥、交接、全任务完成和期限检查。当前结论可用于合成调度建模，真实 TensorRT 引擎的无回退构建、固定精度输出一致性和实机热标定仍待核验。
