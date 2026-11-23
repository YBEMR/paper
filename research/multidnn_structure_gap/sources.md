# 来源、可验证内容与缺口

核查日期2026-11-23。新增图采用本机 TorchVision 0.21.0+cpu 声明提交 `7af698794eded568735f9519593603c1ec889eba`，逐文件SHA保存在 sources/audit.json，源码快照及BSD许可证归档。对应官方实现：[ResNet](https://github.com/pytorch/vision/blob/7af698794eded568735f9519593603c1ec889eba/torchvision/models/resnet.py)、[MobileNetV2](https://github.com/pytorch/vision/blob/7af698794eded568735f9519593603c1ec889eba/torchvision/models/mobilenetv2.py)。

ResNet-18含[2,2,2,2]残差块；MobileNetV2含标准倒残差配置，分组卷积及ReLU6未删除。官方224输入和分类参数量分别为11,689,512与3,504,872，新图计数相等。[ResNet-18文档](https://docs.pytorch.org/vision/0.21/models/generated/torchvision.models.resnet18.html)、[MobileNetV2文档](https://docs.pytorch.org/vision/0.21/models/generated/torchvision.models.mobilenet_v2.html)。本文没有验证这些公开权重在本切分FP16环境中的精度，不能把公开ImageNet准确率当作本实验测量。

新图以静态构造器重建，依赖/张量形状/MAC/参数量可独立复算。已安装Torch导入因torch_python.dll依赖缺失失败；没有声称运行了Torch FX、ONNX导出或整网数值对照。权重有官方URL，但本轮未下载、未核验完整权重哈希。Graph节点中BN采用推理折叠；小代数检查不等同于完整网络输出验证。

[DLA静态约束参考](https://docs.nvidia.com/deeplearning/tensorrt/11.4.1/inference-library/dla-layer-restrictions.html)：Jetson DLA支持所需卷积、ReLU/Clipped ReLU、逐元素求和和池化，但受数据格式、通道/分组及CBUF等限制。ReLU6按clip=6保留；深度卷积需要合适CHW布局，不能套用HWC4的窄分组范围。代码只实现显式抽象必要条件；未确定真实目标JetPack组合、未验证CBUF/张量填充/engine pool，不能宣称真实分区合法。四个常驻段仍是旧研究的调度约束，未替换成新版文档的硬件loadable上限。

本机GPU为GTX1650Ti，不是DLA目标；trtexec未找到。没有DLA引擎构建、真实放置、无隐式fallback及精度证据。旧YOLO仍使用冻结tkDNN结构，原源码与数据不改。

时延/功率来源为旧 synthetic_platform_v1/platform.json：相同算术吞吐、字节带宽、阶段setup、活动/空闲功率、漏电和RC。所有数值逐字节哈希保护。对新网络采用相同“算术量/服务率＋流量/带宽＋setup”规则，是明确的**合成外推假设**，不是新网络的性能测量；尤其深度卷积利用率与算子融合开销无板端标定。请求周期和期限是事前声明的研究输入，不冒称某实际应用的实测请求。

因此：本轮可以证明或否定**所声明合成小域**内的节能空间；无法仅凭本轮回答真实Jetson平台的3%–5%节能可能性。后续若转向硬件主张，最少缺口是目标版本、权重/输出一致性、分区构建和各算子/引擎的实际时延功率，不能用更多合成实例代替这些证据。
