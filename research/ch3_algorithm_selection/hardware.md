# X4139374 的图边界与硬件证据

固定 FP16、batch 1、256×256 输入。用原始 `catalog.check_chain` 对每个连续前缀重验操作种类、卷积和激活的连接、前后层完整覆盖、跨分区仍需保留的全部张量和 MAC 守恒。以下编号均从 0 起，含端点。四网共占四个常驻 DLA 阶段。

| 网络 | DLA 前缀 | GPU 后缀 | 必须交接的层输出 | FP16 字节/请求 |
|---|---|---|---|---:|
| YOLOv2 | DLA0，0–42 | 43–53 | 29、42 | 393216 |
| YOLOv2tiny | DLA1，0–22 | 23 | 22 | 54400 |
| YOLOv3tiny | DLA1，0–24 | 25–34 | 13、21、24 | 196480 |
| YOLOv3 | DLA1，0–12 | 13–178 | 10、12 | 1572864 |

冻结图引用 tkDNN 的四份配置及解析器版本。切点对应的图 blob、前缀算子分布、边界张量形状及字节数见[逐网核查表](tables/cut_audit.csv)。三张网有多个活跃输出，单张量交接不足以复现本研究的输入。YOLOv2tiny 的 GPU 后缀仅余 region 输出层，YOLOv3 的边界包含残差支路。[冻结结构代理](../kim_synthetic_platform_v1/platform.json) · [图规则](../kim_multidnn_expansion/catalog.py)

进一步读取 JEDI 作者 jedi_legacy 发布的四份 ReLU 网络配置，并把算子类型、卷积通道/核/步幅/激活开关、池化、残差、路由依赖和缩放投影到冻结图的字段。四网分别对齐 32/32、16/16、24/24、107/107 个配置块；源图输入为 416×416，模拟输入为 256×256。该项核对覆盖合成图保留的结构字段。权重数值、BN 融合、填充的数值语义及推理输出需要单独验证。四个权重 ZIP 在发布元数据中存在，已记录地址和字节数，未将其加载为当前引擎。[逐图差异与来源哈希](tables/release_graphs.csv) · [作者发布](https://github.com/cap-lab/jedi/releases/tag/jedi_legacy)

项目归档的 YOLOv3 示例使用 INT8 和 36、78 两个内部切点。两项来源均无法逐项确认本次 256×256、FP16 的四个引擎。四组权重的论文对应版本和校验值尚未建立。[JEDI 作者发布与权重索引](https://github.com/cap-lab/jedi#supported-and-tested-networks) · [归档配置及出处](../kim_multidnn_expansion/sources/source_manifest.json)

本次检查了基准 Git 文件树及本机研究目录中的引擎、模型与权重文件。检出的相关运行配置为上述 YOLOv3 示例；未找到匹配四个前缀的引擎、构建日志或输出对照。实验主机可见 NVIDIA GeForce GTX 1650 Ti，驱动 556.12，未发现目标 Jetson DLA、trtexec、tegrastats 或当前 Python 环境的 TensorRT 模块。四网的无回退 FP16 构建、实际层放置、共享内存与重排、分段和整网输出一致性、任务精度及板端能耗、温度、期限均未实测。可支持的判断限于冻结图上的合法性以及该合成平台上的调度证书。
