# 文献和原始工件：准入审计

截止2026-11-14，有界定向核查；不是穷尽性综述。“未取得”不等于不存在。论文、官方机制、公开工件与联合数值标定分别评级，不把目标不同解释为方法不可适配。

## 最近邻及适用边界

|来源|已核到的内容|本轮可用性和边界|
|---|---|---|
|[HaX-CoNN，PPoPP 2024](https://doi.org/10.1145/3627535.3638502)，全文§3.1–3.4、§5与工件说明|用层组时长、转移和共享内存竞争预测选择并发DNN的异构分配，目标为时延/吞吐。对黑盒DLA通过EMC相关性推断访存特征|支持“竞争会影响分配/重叠”的实测依据；没有给本轮所需的联合热频率限制与固定服务全窗能量闭环。其分组/竞争方法可以适配，不因目标不同排除|
|[OPTiC，TCAD 2019](https://www.comp.nus.edu.sg/~tulika/OPTiC.pdf)，2018作者稿§IV-B/C/D、§V-D|已联合预测CPU/GPU热降频及内存竞争；消融包括去掉竞争、同时去掉竞争与热反馈。选择划分点和频率优化共同执行时间|是直接方法近邻，不能声称“首次联合两机制”。Odroid XU3观察到GPU访问优先，模型主要惩罚CPU；该平台EMC频率不能调。回归系数和完整原始档位/功率/热序列未取得，不能移植为Orin仲裁或EMC热cap模型。能耗目标及服务期限仍可另行适配|
|[RT-TAS，TECS/EMSOFT 2019](https://doi.org/10.1145/3358235)，[正式版全文](https://rtcl.eecs.umich.edu/rtclweb/assets/publications/2019/youngmoon-TECS-19.pdf)§5–7|Tegra X1上的CPU/GPU热耦合、任务功率差异及避免热任务同时执行；目标为满足期限下抑制峰温。Table 1给稳态耦合系数，Table 2给任务CPU/GPU段时长、功率和周期|CPU段和GPU段不是同一任务的两个可选替代实现。实验关风扇并设65°C门槛，不能当Orin出厂热门槛。无共享带宽—频率竞争标定和完整内存能量；稳态耦合矩阵也不能单独识别动态热容|
|[Orin官方电源与性能文档，L4T r35.3.1](https://docs.nvidia.com/jetson/archives/r35.3.1/DeveloperGuide/text/SD/PlatformPowerAndPerformance/JetsonOrinNanoSeriesJetsonOrinNxSeriesAndJetsonAgxOrinSeries.html#emc-frequency-scaling-policy)|EMC/DRAM支持DVFS；运行策略受板级DVFS表、带宽使用、驱动请求和热限制影响；MAXN仍可能受功率限制|**官方确认机制存在，不给出当前任务实例的EMC热cap轨迹、有效带宽曲线或系统能量。** 不把功率/电气节流都归因温度，也不把模式最高频率当实测运行频率|

RT-TAS原先检到的11页作者稿有模板页眉，随后取得25页正式版并以正式版核对表格/实验设置。OPTiC沿用已验证作者PDF；其页眉为2018稿，正式卷期为2019，DOI为10.1109/TCAD.2018.2873210。阅读覆盖与获取状态另存source_registry.json、provenance/；四份PDF结构预检均因缺pypdf为UNAVAILABLE，Poppler提取可用，RT-TAS第18页和OPTiC第7页已目视核对；不声称结构预检通过。

## HaX-CoNN工件逐项核查

固定[作者提交87f5f25e6571ae04b577d1c38ddd241ffacab983](https://github.com/ismetdagli/HaX-CoNN/tree/87f5f25e6571ae04b577d1c38ddd241ffacab983)：完整树105条目，选54个代码/文档/结果文本，逐文件Git blob与SHA256核对。另核查[Zenodo归档10.5281/zenodo.10225025](https://doi.org/10.5281/zenodo.10225025)，7,321,491字节，MD5匹配，135个成员。归档工作树84个普通文件，其`.csv/.json/.log/.profile`数据只有EMC摘要；未穷挖其打包Git历史。作者硬件采集、TensorRT构建和Z3程序均未执行。

|工件|静态复算结果|禁止的误读|
|---|---|---|
|[layer_results.json](https://github.com/ismetdagli/HaX-CoNN/blob/87f5f25e6571ae04b577d1c38ddd241ffacab983/output_expected/layer_results.json)|10组GPU时长摘要|不能当同一Orin、多个频点与热状态的标定表|
|[dla_compute_times.json](https://github.com/ismetdagli/HaX-CoNN/blob/87f5f25e6571ae04b577d1c38ddd241ffacab983/output_expected/dla_compute_times.json)|10项中3个`layer_diff`负值，约−.406556、−1.145858、−1.881030ms|这是预处理差分异常，不是负的物理执行时间；保留原值、不截零、不擅自推断根因|
|[emc_results.json](https://github.com/ismetdagli/HaX-CoNN/blob/87f5f25e6571ae04b577d1c38ddd241ffacab983/output_expected/emc_results.json)|25个峰值百分比，24%–89%|不是GB/s，也不是完整时间序列|
|[采集脚本](https://github.com/ismetdagli/HaX-CoNN/blob/87f5f25e6571ae04b577d1c38ddd241ffacab983/scripts/emc_analysis/emc_single_run.sh)、[汇总脚本](https://github.com/ismetdagli/HaX-CoNN/blob/87f5f25e6571ae04b577d1c38ddd241ffacab983/scripts/emc_analysis/emc_util_all.py)|从tegrastats只截取EMC百分比，汇总取max；频率、温度、功率和时间关联未保留|不能反推出有效EMC频点、服务期间积分功率或热cap因果轨迹|
|[transition_results.json](https://github.com/ismetdagli/HaX-CoNN/blob/87f5f25e6571ae04b577d1c38ddd241ffacab983/output_expected/transition_results.json)|20项转移相关时长摘要，含参考项|缺转移能量及频点/热状态轴，不补成零成本|
|[Orin构建脚本](https://github.com/ismetdagli/HaX-CoNN/blob/87f5f25e6571ae04b577d1c38ddd241ffacab983/build_engine_orin.py)、[README](https://github.com/ismetdagli/HaX-CoNN/blob/87f5f25e6571ae04b577d1c38ddd241ffacab983/README.md#reusability-on-orin-agx)|Orin使用INT8并允许GPU回退；Xavier示例用FP16；README说明prob不能在DLA执行|不能把“DLA engine”当全程纯DLA，也不能拼接两芯片/两精度数据|

README总述的TensorRT 8.4.0/CUDA11.2与后文Orin 8.5/8.5.2有不一致。[官方JetPack 5.1.1](https://developer.nvidia.com/embedded/jetpack-sdk-511)为L4T35.3.1、TensorRT8.5.2、CUDA11.4；因此官方文档选择同代r35.3.1，但这不自动修复所有结果文件的软件来源标签。[tegrastats官方定义](https://docs.nvidia.com/jetson/archives/r35.3.1/DeveloperGuide/text/AT/JetsonLinuxDevelopmentTools/TegrastatsUtility.html)中EMC百分比相对于当前运行频率，正说明丢掉MHz后无法得到绝对带宽。

检查归档没有找到额外联合功率/温度数据可填缺口；代码中的已有时长/慢化数组也没有本轮要求的逐任务、精度、有效频点和功率热元数据。不能以“有数值”替代“数值可辨识”。静态提取65行摘要及检查记录在results/，不是新实验结果。

## 同平台准入决定

|平台组|有资料的部分|仍缺关键部分|决定|
|---|---|---|---|
|HaX-CoNN Xavier/Orin，各自独立|合法层组方法、时长/转移/竞争经验与代码；Orin有官方EMC机制|同一精度/同一板卡的有效OPP全表、仲裁与带宽曲线、温度到cap映射/延迟、同步完整功率及动态热模型|不准入联合数值|
|OPTiC Odroid XU3|联合热降频与争用的性能建模、功率建模方法和论文实验|本轮两链任务的完整输入/拟合参数、全系统内存能耗与公共窗口；其不可调EMC不能替代Orin|不准入联合数值|
|RT-TAS Tegra X1|CPU/GPU分段工作、功率、稳态热耦合和期限机制|共享带宽竞争与EMC频率轴、动态参数及一致的全系统能量|不准入联合数值|

检索界限包括上述论文全文/作者页、作者仓库固定工作树、公开归档及官方文档；未发作者邮件，未取得私有日志。没有证明不存在其他数据。本轮也不扩展到其他芯片寻找可拼接参数。
