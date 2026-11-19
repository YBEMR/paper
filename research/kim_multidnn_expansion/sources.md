# 多DNN部署扩展：来源与执行合法性边界

核查日期：2026-11-19。基线结果提交：`02f3f621cc9ce7f1cd991577388343fa906bbf56`。

本轮可建立小规模、规则可追溯的合成候选库，不能声称恢复了Kim全部实测Pareto库。新增候选均未在TensorRT上构建或运行，未验证真实模型精度、引擎容量及实际设备回退。图、MAC、全局服务率和热参数全部沿用`../kim_synthetic_platform_v1/`；合法性检查不得转化为部署专属性能调参。

## 1. 原论文事实

Kim & Ha，2023，*Energy-Aware Scenario-Based Mapping of Deep Learning Applications Onto Heterogeneous Processors Under Real-Time Constraints*，IEEE Transactions on Computers 72(6):1666–1680，DOI：[10.1109/TC.2022.3218991](https://doi.org/10.1109/TC.2022.3218991)。本轮读取了本地论文全文和p.1677表9的PDF图像。

| 项目 | 原文定位 | 已核事实 |
|---|---|---|
| 五种流水线结构 | §5.1、表3，p.1672 | A=DLA→GPU；B=GPU→DLA→GPU；C=DLA0→DLA1→GPU；D=GPU→DLA0→DLA1→GPU；E=GPU；DLA0/DLA1可交换 |
| 切点 | §5.1，p.1672 | 切点是前一段最后一层；排除卷积与紧接激活之间，以及连续不支持DLA层之间；尾部不支持DLA，因此最后一段GPU |
| 候选规模 | 表4，p.1674 | v2/v3/v2tiny/v3tiny分别选22/78/10/10个切点，得到112/158/19/14个Pareto映射；未列出完整切点及映射清单 |
| 常驻占用 | §3，p.1670；§5.2 Algorithm 1，p.1672 | 两DLA合计最多4个已加载阶段，按所有应用统计 |
| 静态映射 | §4.2，p.1671；§5.2，p.1672 | 映射跨场景不变；不允许通过场景切换迁移部署 |
| 物理DLA分配 | §5.2.1、Algorithm 2，p.1673 | 结构确定后，原文按DLA最长阶段及应用场景邻接关系轮转分配两DLA |
| 参数来源 | §5.1，p.1672；§6.1，p.1675 | 每个映射在实机测量；实验采用JEDI ReLU网络、256×256、FP16、batch 1；不能按层数拆分其时延 |

表9(a)的β案例：YOLOv2为`D[0–29],D[30–40],G[41–53]`；YOLOv2tiny为`D[0–16],G[17–23]`；YOLOv3tiny为`D[0–16],G[17–34]`；YOLOv3为`G[0–178]`。表9α案例的YOLOv2实际为`D[0–29],G[30–53]`。正文举例`D[0–40],G[41–53]`用于解释记法，不能误称表9α的部署。历史A/C以冻结输入逐项比较为准，不能静默改切点。

原文§5.1解释TensorRT层融合、额外交接核使逐层时间难以直接迁移到切分引擎；§6.3.1 p.1677亦报告逐层估计的期限判断在实测重评后改变。因此以下合成图检查是研究抽象的边界，不是实机性能或期限保证。

## 2. JEDI源码及快照

作者仓库：[cap-lab/jedi](https://github.com/cap-lab/jedi)，检索时master提交`50fda15ce3b82b38f46adddc04c47b58042cef71`。

本地快照[sources/jedi_yolov3.cfg](sources/jedi_yolov3.cfg)对应[固定提交的yolov3.cfg](https://github.com/cap-lab/jedi/blob/50fda15ce3b82b38f46adddc04c47b58042cef71/yolov3.cfg)，共820字节，Git blob SHA-1为`c76c10aeba1ea09e69bb9127a7af430af837601f`，SHA-256为`3b72d6d82cb50189684a258f68a19a03a94e05208264bd61e70daab1fc9eddd8`。已用`SHA1("blob "+长度+NUL+原字节)`校验与GitHub返回值一致。

该配置明确使用`cut_points="36,78,178"`、`devices="DLA,DLA,GPU"`，前两段分配DLA0/DLA1；同时它的`data_type`是`INT8`。本轮仅继承结构来源，在原合成FP16模型中重算全部阶段，不使用该配置的精度或性能。此文件不是FP16、256×256引擎成功运行的证明。

[固定提交README](https://github.com/cap-lab/jedi/blob/50fda15ce3b82b38f46adddc04c47b58042cef71/README.md)给出四个ReLU网络及FP16 GPU+DLA结果，但图像尺寸是416×416，结果未与上述具体切点逐项绑定。其吞吐率不用于本轮标定。原合成输入的结构代理另绑定`urmydata/tkDNN@b094c8e50076f944e60f1dc28ce06673788fb6ed`及各图blob；保持原绑定，不重新下载权重或修改网络。

## 3. 官方DLA约束及未验证项

核对[NVIDIA TensorRT 8.6.1 Developer Guide](https://archive.docs.nvidia.com/tensorrt/tensorrt-861/developer-guide/index.html)，§12.1.2.1、§12.2.1–12.2.2、§12.3–12.4。8.0.3历史PDF搜索索引亦保留了§10.2中卷积、ReLU及4个loadable约束；其旧直接链接当前会重定向，因此不把搜索摘录冒称全文复核。

官方资料确认FP16二维卷积、ReLU、池化及ElementWise Sum有DLA路径。二维卷积核尺寸须为1–32、步长1–8，并受通道、padding和CBUF限制；支持算子名称不保证整个引擎可构建。静态尺寸须一致；不支持节点或容量问题可能触发GPU fallback，额外格式转换也可能改变实际资源使用。真正实机验收仍需指定SDK构建日志、无隐式回退的设备归属及输出检查。本轮没有这些证据。

版本边界：Kim使用较早SDK，本轮维持其“两DLA合计4个常驻阶段”的冻结限制；不采用8.6.1文档较新的并发loadable数量放宽搜索空间。原`parameters.md`已把图中的激活位置按ReLU解释；本轮不新增激活替换，不主张代理图与Kim权重相同。GPU保留全部检测头、route、reorg/upsample等后缀；不把不支持DLA的层伪装为DLA执行，也不通过隐式fallback获得额外未计入GPU工作。

## 4. YOLOv3切点与跨段依赖

以下由冻结`platform.json`和`profiles.graph_features()`静态展开得到，未进行能耗、热或期限实验。编号为tkDNN式展开后编号，不是Darknet原始block编号。

| 区间/边界 | 静态检查 |
|---|---|
| 0–36 | 16个卷积、16个激活、5个shortcut；无route、upsample或检测头 |
| 37–78 | 17个卷积、17个激活、8个shortcut；无route、upsample或检测头 |
| cut36 | op35卷积→op36激活，随后op37 shortcut；不拆卷积/激活对 |
| cut78 | op77卷积→op78激活，随后op79 shortcut；不拆卷积/激活对 |
| shortcut | 输入尺寸在原`graph_features()`中逐项相等检查；保留两输入的ElementWise Sum语义 |
| 完整性 | 179个展开操作、3个检测头140/159/178全部执行；计算图和MAC总数不变 |

| 切点 | 切后仍需要的切前输出 | 形状H×W×C | FP16逻辑交接量 |
|---|---|---|---:|
| 36 | op32、op36，均供shortcut37 | 每个32×32×256 | 1,048,576 B |
| 78 | op74、op78供shortcut79；op62供route164 | op74/78各16×16×512，op62为32×32×256 | 1,048,576 B |

不能仅交接切点最后输出。原`profiles.live_bytes()`枚举切后全部消费者，已捕获上述残差和远距离route依赖；阶段交接应继续调用它。以上是逻辑张量量，不是已测TensorRT格式填充、拷贝或融合后的流量。默认256×256、batch1、FP16且这些DLA前缀的卷积核仅1/3、步长仅1/2，类别和可观察尺寸满足所用规则；CBUF、引擎编译、格式约束和内核融合仍未验收。

## 5. 小候选库的证据分类

| 网络与候选 | 来源级别 | 本轮状态 |
|---|---|---|
| YOLOv2历史A、C | 冻结输入；C对应表9β，A按冻结切点原样保留 | 历史基线；其性能仍是合成生成 |
| YOLOv2 E | 表3 E及原文BS全GPU方法 | 可加入；完整网络GPU |
| 两个tiny A16 | 表9β实际部署 | 原样保留 |
| 两个tiny E | 表3 E及原文BS全GPU方法 | 可加入；释放常驻DLA槽，但增加GPU计算 |
| YOLOv3 E | 表9β实际部署 | 原样保留 |
| YOLOv3 C36/78 | JEDI具体配置+冻结图和算子规则检查 | 合成候选，未在当前FP16设置下实机验证 |
| YOLOv3 A36 | 保留JEDI第一DLA段，余下完整后缀放GPU；符合表3 A | 规则构建的合成候选，非Kim原文实际部署；建议纳入 |
| YOLOv3 A78 | 合并JEDI两个DLA段 | 本轮不纳入；合并引擎容量未确认，避免额外扩展 |
| 其他任意B/D切点、DLA检测头、漏传残差方案 | 仅有结构名称或无依据 | 不纳入，不因增加候选数而推定合法 |

每个具体部署继续枚举并固定物理DLA归属；C的两个DLA段须使用不同核心，DLA频率共享。组合常驻占用为所有四网络DLA阶段数之和，即使网络当前场景未激活也不能释放其常驻槽。将YOLOv3从E改C需要两个槽，必须与其他网络释放DLA槽的决定共同检查；不能只在SC2中临时搬迁。

此次核查支持在既定合成模型内扩大合法决策空间；并未证明新增部署满足期限、热约束或节能，也未证明某种筛选或搜索算法存在局限。正式结果必须与本节的结构/来源判断分开。

## 6. 检索记录

日期2026-11-19。主要检索词：`JEDI TensorRT Jeong Kim Ha GitHub DLA YOLO pipelining`、`Energy-Aware Scenario-Based Mapping github`、`site:docs.nvidia.com tensorrt archives DLA ElementWise Convolution`。范围限Kim本地全文、作者JEDI/tkDNN代码、NVIDIA官方历史文档。没有据此开展新颖性综述，也不作“首次”判断。
