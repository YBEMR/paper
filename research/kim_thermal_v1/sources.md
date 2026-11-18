# V1 参数来源与文献适用边界

核对日期为 2026-11-18。下表的“直接观测”均指论文作者在其设备上的观测。本轮在仿真中采用旧配置的数值及预先规定的实验输入。本文引用的实测百分数仅用于核对建模方向，未进入输入生成器。

| 文献及正文定位 | 可继承的事实或方法 | V1 的取舍 |
|---|---|---|
| Kim & Ha，2023，*Energy-Aware Scenario-Based Mapping of Deep Learning Applications Onto Heterogeneous Processors Under Real-Time Constraints*，§5.2.2 算法 3（PDF 第 8 页）、§5.2.3–4（第 9 页）、表 7（第 11 页） | 固定部署后按场景和期限搜索离散频率。其空载静态功率对应固定 P-state，静态能量按周期计；动态功率由运行总功率扣除估计静态功率得到。原可调度性判定采用结合抖动的响应时间分析。 | A 保留两遍逐域搜索和全局最低适应度记录，用 V1 的已知释放轨迹和统一派发规则检查每个请求，以预规定标称入口温度评价场景能量。真实运行沿用当前热状态。这样评价的期限保证只覆盖给定输入轨迹。原台架、映射遗传算法、WCET 分析和原表 7 频档均未在 V1 复现。[原文](https://doi.org/10.1109/TC.2022.3218991) |
| Ahmadi 等，2023，*EdgeEngine: A Thermal-Aware Optimization Framework for Edge Inference*，§2.1–2.3，图 1、2（作者版 PDF 第 3 页），图 4（第 5 页） | TX2 在恒温箱 25/70°C、风扇开启且避免硬件节流时，高频组多个 CNN 的运行功率中位数平均增加 18.4%，运行时长中位数平均增加 2.5%。考察的控制量是 CPU、GPU 和内存频率。 | 支持同一推理配置的能量随温度改变。环境温度与节点结温是不同量。V1 以局部温度影响功耗，固定频档下的时长保持确定；这种简化省略了实测中较小但可见的时长变化。此文无法标定 V1 的 NPU 响应或节点漏电斜率。[论文](https://doi.org/10.1145/3583740.3626616) · [作者代码与数据](https://github.com/DependableSystemsLab/EdgeEngine) |
| Maity 等，2022，*Future aware Dynamic Thermal Management in CPU-GPU Embedded Platforms*，§IV-A.2（PDF 第 5–6 页，式 2–5）、图 1、算法 1–3 | 以热耦合表示同片 CPU/GPU，预测从当前温度出发，利用未来有限内核序列选择控制。其主要热优化指标为平台峰温。 | 借用跨时刻状态传播和节点耦合的建模思想。V1 的四节点热容/导热矩阵及场景尺度自设。D 使用整条已知轨迹作为离线参照。[论文](https://doi.org/10.1109/RTSS55097.2022.00041) |
| Choi 等，2024，*Mediator: Characterizing and Optimizing Multi-DNN Inference for Energy Efficient Edge Intelligence*，图 4（PDF 第 4 页）、§V（第 7 页）、图 9、10（第 10 页） | 手机多 DNN 推理实测表明共享处理单元、热耦合和温控会影响各设备表现。作者用外接 Monsoon 仪器评价手机整机能量。 | 借鉴完整系统能耗的评价边界和持续推理场景。V1 用分项功率积分评价模拟系统；其中公共功率固定。实际手机的传感器读数、节流策略、能量和温限均不作为本轮标定值。[论文](https://doi.org/10.1109/IISWC63097.2024.00014) |

### Kim 基线的对照依据

算法 3 第 2–4 行全域设最高档、最小适应度设为无穷；第 5–7 行进行两遍 GPU、CPU、DLA 域搜索，每到一域重新从该域最高档开始。第 9–14 行检查期限，仅对通过的配置计算能量适应度，严格更低才更新已保存的最佳配置。第 15–22 行遇不可调度时，当前域若已降档则退回前一档，转下一域；否则逐档降低至最低。切换到下一域时保留的是搜索路径上最近的可调度频率组合。最终评分的获胜配置由第 13 行单独保存。§5.2.3 对多场景作平均的理由是缺乏驻留时间信息；本轮各段持续时间已给定。

### 实际输入中的数据归属

| 量及单位 | 本轮实际来源 | 对结论的影响 |
|---|---|---|
| L/H 频档 GHz、工作电压 V | 旧包 `platform.domains` 的端点。CPU 0.8/1.6，GPU 0.4/0.8，NPU 0.5/1.0；各域两档电压亦取同一旧包。均为项目自设。 | 只有这些有限工作点参与搜索，D 的最优性限于列入的支持域。 |
| 阶段时长 ms、活动功率 W | 由旧包任务参数生成，采用 R1 和 H 响应变体。用文献支持频率影响执行时间及活动功率，具体参考时长、可缩放比例、参考功率和电压均由项目自设。 | 实例不能对应为某个商用模型或实测推理服务。 |
| 空载与温度相关功率 W，热容 J/K，导热率 W/K | 旧包 `platform` 的工作点基线、节点温度斜率、四节点热容/导热矩阵及 0.30 W 外部公共功率。CPU 两核共用一份域基线，局部温度项按节点计算。 | 散热时间尺度、降档的闲置收益和下一入口温度均依赖这些仿真参数。 |
| 场景、部署、请求和时间窗 | 新包 `inputs.json` 固定 A/B/C 三条前处理—推理—后处理链，组合 AB/AC/BC/ABC、种子 101/202/303、两种负载、两种排列、240 ms 段和 100 ms 尾窗。部署和释放策略为研究自设。 | 固定精度与工作量；轨迹之间的比较覆盖本批组合。 |
| 环境/初温/温限 °C | 旧包环境 25；V1 选择入口 50 或 78；A 标称入口 50，统一温限 80。均为抽象系统的实验条件。 | 热安全或热约束宽松是本输入上的计算结论，无法外推手机或开发板的保护阈值。 |

[旧数值配置](../chapter3_experiments/config_v01.json) · [冻结输入](inputs.json)

### 核查材料版本

稿内页码均为从 1 计的本地 PDF 页。检索范围为项目原文及对应 DOI/作者仓库；检索词包括各篇正式题名、Kim Algorithm 3、EdgeEngine ambient temperature、Mediator system-wide energy、F-DTM thermal coupling。前三篇可在基线仓库核对；Mediator 原文来自用户工作区的同名 PDF，未随本分支打包。[仓库论文](../../papers)

| 本地 PDF | SHA-256 |
|---|---|
| 2023_Kim_Energy_Aware_Mapping.pdf | `0e73cbf8f19e7530871bd38e584b3e19d639814efc75ea008c7b67807697c89d` |
| 2023_Ahmadi_EdgeEngine_author.pdf | `29ff251df6f647799057a0a8ad20936ed4a553801ab2dd968d9442fe81be632e` |
| 2022_F-DTM_RTSS_Future_aware_Dynamic_Thermal_Management_in_CPU-GPU_Embedded_Platforms.pdf | `a633da75bd8eff5bc1f0798f949767447718f542ab9321fa20395bbe0a312237` |
| 2024_Mediator_Characterizing_and_Optimizing_Multi-DNN_Inference_for_Energy_Efficient_Edge_Intelligence.pdf | `04b1d2410e3b35921f6f1b23d83ebe0cf5b7f10d456b1f9a7ec8cbc99d2ead5f` |
