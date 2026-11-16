# Jetson GPU/DLA负载相关能效决策：证据准入核查

2026-11-16。**结论：CONDITIONAL；本支线在证据准入阶段停止，不进入仿真、模型扩展或算法设计。**

公开论文支持“DLA开关的功率排序随输入路数变化”，尚不支持“相同有效服务量下的系统能耗排序变化”。未找到与4路／30路功率配对的有效输出计数、期限达标记录及温度。HaX-CoNN提供执行与争用资料，但不能填补这些缺口；也未证实简单负载规则或已有联合规划处理不了的剩余困难。

## 1．测量证据与最小复算

Herrera论文表10的原图位于印刷页61／PDF第73页。以下功率是**作者报告的模块整体功率值**；正文p.47称覆盖模块各系统，但未给仪表、电源轨、采样和平均算法，不能升级为已独立核验的整机输入功率。大学下载链接返回403，实际逐页核图使用[作者公开副本][thesis]；已与[大学存档][university]的题名、作者和相关正文核对，未声称两份PDF字节相同。

| 同一设备 | 输入路数 | DLA关／W | DLA开／W | 开／关功率比 | 表列功率变化 | 同服务量能耗优势所需的有效吞吐比* |
|---|---:|---:|---:|---:|---:|---:|
| AGX Xavier | 4 | 14.71 | 15.80 | 1.07410 | +7.410% | >1.07410 |
| AGX Xavier | 30 | 18.05 | 12.70 | 0.70360 | −29.640% | >0.70360 |
| AGX Orin | 4 | 14.32 | 15.58 | 1.08799 | +8.799% | >1.08799 |
| AGX Orin | 30 | 38.75 | 16.67 | 0.43019 | −56.981% | >0.43019 |
| Xavier NX（补充原表） | 4 | 16.00 | 16.36 | 1.02250 | +2.250% | >1.02250 |
| Xavier NX（补充原表） | 30 | 27.98 | 14.04 | 0.50179 | −49.821% | >0.50179 |

原始表值与复算值分列保存在[evidence.json](evidence.json)；[recompute.py](recompute.py)只用有理数重算六个功率比，未调用设备、求解器或物理模型。

*阈值的含义是条件式：同一有效工作量N、完整且一致的计能边界下，若P̄确为各次完整窗口平均功率，令R=N/T，则

\[
\frac{E_{开}}{E_{关}}=\frac{\bar P_{开}/\bar P_{关}}{R_{开}/R_{关}},\qquad
E_{开}<E_{关}\iff\frac{R_{开}}{R_{关}}>\frac{\bar P_{开}}{\bar P_{关}}.
\]

将表值代入只得到**有条件的盈亏阈值**，不是已测能耗。表10未交代其值是否为图中60秒的完整窗口均值；因此也不计算“功率×60秒”。30路AGX Xavier需保留超过70.36%的有效吞吐，Orin需超过43.02%；实际是否达到均未知。每路还须完成约定帧及质量，聚合吞吐足够不证明没有饿死某一路，更不证明全部按时完成。

## 2．任务及数据完整性

| 核查项 | 已报告／可观察内容 | 缺口与判定 |
|---|---|---|
| 工作任务 | §4.c、§5.b采用剪枝DashCamNet；图25复制同一视频为4／30源，正文说明逐源推理 | 没有配套配置和模型／引擎哈希；表10未逐项确认跟踪、深度估计、显示及编码是否开启。不能将其等同最终完整驾驶感知工作流 |
| 精度和分辨率 | 表7／9区分720p、qHD；正文报告模型精度指标 | 表10未给所用分辨率、FP16／INT8配置及开关DLA后的输出一致性。模型总体准确率不证明两种引擎同精度 |
| 软件 | p.36：JetPack 5.1、L4T 35.2.1、TensorRT 8.5.2.2、DeepStream 6.2 | 属作者声明，无每次运行环境回执 |
| 功率模式 | pp.36、38声明后续采用MAXN；列出Xavier 30W、Orin 60W | MAXN与固定瓦数／固定频率不同；官方Xavier表把MAXN与30W模式分列。没有`nvpmodel -q`、配置及锁频回执，精确工作点不可还原 [N1] |
| 板型 | 表1列AGX Xavier／Orin均32 GB | Orin同时列12核、GPU 1.3 GHz、DLA 1.6 GHz，与官方r35.2.1的32 GB配置不一致，而接近其64 GB列；不自行改判实测板型 [N2] |
| 测量时长 | p.65说明图26—28运行观察60秒；图是GPU负载与GPU/DLA频率 | 表10功率窗口、采样间隔、预热、初始化及尾段计入方式未披露；无重复数、误差条或原始功率序列 |
| 有效服务量 | p.57称输入视频30 FPS；表7给单路检测／跟踪平均推理时间 | 无表10对应的有效完成帧数、逐路有效FPS、丢／跳／重复帧及积压。**不能填入30×路数×60** |
| 时延与期限 | p.47用相邻帧处理时间差描述指标；p.57讨论33.3／16.6 ms | 不是配对的逐帧到达—最终完成时间戳或硬期限验收；表7的倒数不等于30路有效吞吐，均值也不保证尾延迟 |
| 温度 | 图26—28没有温度曲线；全文相关核查未发现配对温度／风扇／降频原因记录 | 热因素未得到支持；频率变化可能涉及负载调频、电流限制或温控，不能仅凭降频归因为热 |

表7（p.57）与表9（p.59）的12组单路条件已逐项转录进证据文件，**没有与表10相乘或拼接**。图27／28可见GPU频率并不固定；图26—28纵轴写GHz但刻度达上千，本轮未把图像读数导出为精确频率数据。原文功率排序保留，物理解释、计量精度及服务等价性分别保留不确定。

执行语义还存在三项不能省略的核查：

- DeepStream 6.2的`nvstreammux`组批及超时会影响等待；`nvinfer.interval`可跳过连续批次。源路数、画面路数、检测执行数和有效输出数不是同一量。论文没有给这些配置，不能默认为“每路每帧均执行相同网络”。[N3][N4]
- DLA开启是推理放置选择，不等于DLA电源开关，更不保证GPU完全空闲。TensorRT支持不适合DLA的层回退GPU；HaX-CoNN构建器明确设置FP16、DLA核0及`GPU_FALLBACK`。需要引擎实际分区／占用证据，不能把整个混合引擎当独占DLA任务。[N5][H2]
- `tegrastats`能够报告频率、温度和各电源轨；但“工具能测”不代表论文公开了这些记录。Orin的GPU_SOC、CPU_CV、系统5V、DDR等轨边界不同，不能把单个加速器轨或部分求和直接当完整系统总能量。[N2][N6]

## 3．最强已有方法对照

| 方法／资料 | 已有能力 | 本轮不能据此宣称什么 |
|---|---|---|
| **HaX-CoNN／D-HaX-CoNN** | 原论文§3.3—3.5、式(1)—(11)共同考虑层分组映射、跨设备转换和按重叠片段变化的内存争用；目标为吞吐或最大时延，并含动态求解／复用 | 不是只选GPU/DLA的弱基线；未提供本文所需的完整能量目标、逐帧硬期限和温度证据。时延收益不能当能耗收益 [H1] |
| **HaX公开数据与实现** | 固定提交`87f5f25`有层／网络时间、转换时间、EMC和多网络对照；核验8份本地文件与远程blob一致 | 这些是GoogleNet等网络及不同软件环境，不能与DashCamNet表10拼接。示例`z3_solver_multi_dnn.py`的转换／内存数组注明dummy，不能当完整标定复现；未运行该脚本 [H2] |
| **现有正式第三章及跨场景联合调度** | 已有合法设备／频档、共享部署、起点、依赖、互斥、期限、完整窗口能量和连续热安全；bba552e核清实现边界 | GPU/DLA模式二选一及联合时序不是新变量类别。正式稿第81行明确固定模式时长／活动功率不随运行并发变化；若要表达内生争用，不能只把表10某个功率填入Stage表，更不能把“本仓库未迁入”当成领域空白 [R1][R2] |
| **99—104号既有讨论** | 99—100已有模式＋时序及完整评价；101—102已讨论合批、划分、驻留等；103—104已有忙闲／睡眠联合规划和任务响应定位 | DLA执行开关不能偷换为电源休眠；新批次选择或实际混合资源占用需要额外语义与数据，不是本轮已证的新困难 [R3] |
| **简单负载规则／查表** | 对已观测两点，规则“4路关、30路开”足以复述表列功率排序；固定配置下可直接按每场景合法模式比较 | 该规则尚非合格能耗策略，也没有期限保证；两点既不能确定中间阈值，也不能证明它会输给复杂调度。没有观察到需要更复杂方法的同服务量剩余差距 |

**参数与结构的区别：**若4／30路是给定场景、运行模式已固定且画像完整，已有场景／模式选择框架即可承载决策，首先缺的是真实参数。若调度本身改变重叠、组批或GPU回退占用，则需相应条件响应与资源关系；HaX已有争用表达，99号也已有固定多资源占用接口。现有材料不足以判断更细表示是否必要、能带来多少完整能耗价值，更不足以证明需要新算法。

## 4．继续／停止判定

**CONDITIONAL，停止本支线。** 有实测报告中的负载相关功率现象，但同服务量、完整计量和期限证据未闭合；热因素只能作为未来有数据时的条件性约束。未发现已被证实且简单规则／现有联合框架不能直接解决的困难。此结论不否定GPU/DLA调度研究，只限制这组公开证据能支持的主张。

本轮检索范围包括大学记录、作者论文及公开站点／所链接GitHub、HaX当前105项树及135项Zenodo归档、NVIDIA官方文档和仓库指定记录；**未找到可补齐表10服务量的配对公开日志**。不是断言作者没有测量或数据永远无法获得。HaX归档元数据为CC-BY-4.0，当前GitHub未识别许可证；Herrera论文保留版权，报告只摘录必要事实，不重新发布全文／整页图。

只有以后获得同一次运行的逐源有效输出、实际配置、对齐总功率窗口与期限记录，才有理由重新做证据审查；热主张另需配对温度／频率及降频原因。**本轮不提出仿真实验设计，不补造帧数、功率或温限，不启动算法。**仅进行了表格核对、已有文件检查和六组比例复算；论文、模型和旧记录未修改。

## 出处

[thesis]: https://juanpablopena.wordpress.com/wp-content/uploads/2024/04/msc-thesis.pdf
[university]: https://khazna.ku.ac.ae/en/studentTheses/an-objective-evaluation-of-edge-devices-optimized-with-hardware-p/

- **[N1]** [Jetson Xavier，r35.2.1：工作点和电源管理](https://docs.nvidia.com/jetson/archives/r35.2.1/DeveloperGuide/text/SD/PlatformPowerAndPerformance/JetsonXavierNxSeriesAndJetsonAgxXavierSeries.html)，Supported Modes and Power Efficiency。
- **[N2]** [Jetson Orin，r35.2.1：工作点、电源轨和热管理](https://docs.nvidia.com/jetson/archives/r35.2.1/DeveloperGuide/text/SD/PlatformPowerAndPerformance/JetsonOrinNxSeriesAndJetsonAgxOrinSeries.html)，AGX Orin 32GB／64GB表、Software-Based Power Consumption Modeling、Thermal Management。
- **[N3]** [DeepStream 6.2：Gst-nvstreammux](https://docs.nvidia.com/metropolis/deepstream-nvaie30/dev-guide/text/DS_plugin_gst-nvstreammux.html)，组批与`batched-push-timeout`。
- **[N4]** [DeepStream 6.2：Gst-nvinfer](https://docs.nvidia.com/metropolis/deepstream-nvaie31/dev-guide/text/DS_plugin_gst-nvinfer.html)，`batch-size`、`interval`。归档页直接访问重定向失败，本轮使用官方搜索索引中对应章节，不拿新版行为替代旧版参数。
- **[N5]** [TensorRT 8.2.5开发指南](https://docs.nvidia.com/deeplearning/tensorrt/archives/tensorrt-825/pdf/TensorRT-Developer-Guide.pdf)，§12.2—12.3；只核DLA精度限制／GPU fallback基本语义，不冒充论文8.5.2逐层支持清单。
- **[N6]** [Tegrastats，r35.2.1](https://docs.nvidia.com/jetson/archives/r35.2.1/DeveloperGuide/text/AT/JetsonLinuxDevelopmentTools/TegrastatsUtility.html)，Reported Statistics。
- **[H1]** Dagli、Belviranli，HaX-CoNN，PPoPP 2024，[DOI](https://doi.org/10.1145/3627535.3638502)，重读已有全文§3.3—3.5、§4—5；最优性范围依赖其性能模型，不是硬件时延保证。
- **[H2]** [HaX-CoNN固定版本](https://github.com/ismetdagli/HaX-CoNN/tree/87f5f25e6571ae04b577d1c38ddd241ffacab983)，`README.md`、`output_expected/`、[`build_engine.py`](https://github.com/ismetdagli/HaX-CoNN/blob/87f5f25e6571ae04b577d1c38ddd241ffacab983/src/build_engine.py#L20-L24)、[`z3_solver_multi_dnn.py`](https://github.com/ismetdagli/HaX-CoNN/blob/87f5f25e6571ae04b577d1c38ddd241ffacab983/src/z3_solver_multi_dnn.py#L21-L32)；[Zenodo归档](https://doi.org/10.5281/zenodo.10225025)。
- **[R1]** [正式第三章修订稿](https://github.com/YBEMR/paper/blob/bba552e5f045c805be9d6274eaafb83e64b2815f/research/latex/chapter03_revised_20261025/chapter03.tex#L67-L81)。
- **[R2]** [bba552e准入审查](https://github.com/YBEMR/paper/blob/bba552e5f045c805be9d6274eaafb83e64b2815f/research/正式四节点轻量求解准入审查_20261116.md)。
- **[R3]** [99号](https://github.com/YBEMR/paper/blob/bba552e5f045c805be9d6274eaafb83e64b2815f/research/99_端侧热约束节能联合模型骨架.md)、[100号](https://github.com/YBEMR/paper/blob/bba552e5f045c805be9d6274eaafb83e64b2815f/research/100_联合模型求解路线与适配边界.md)、[101号](https://github.com/YBEMR/paper/blob/bba552e5f045c805be9d6274eaafb83e64b2815f/research/101_研究问题重组的候选决策与原文依据.md)、[102号](https://github.com/YBEMR/paper/blob/bba552e5f045c805be9d6274eaafb83e64b2815f/research/102_研究要素组合与问题选择.md)、[103号](https://github.com/YBEMR/paper/blob/bba552e5f045c805be9d6274eaafb83e64b2815f/research/103_K3忙闲状态联合调度的文献基座与决策边界.md)、[104号](https://github.com/YBEMR/paper/blob/bba552e5f045c805be9d6274eaafb83e64b2815f/research/104_K3联合问题与任务相关响应作用定位.md)。历史候选与当前正式模型分别解读；未把99号的空闲保持政策套给现行auto-L实现。
