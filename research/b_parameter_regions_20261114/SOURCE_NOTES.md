# 本轮物理依据补充

检索日期：2026-11-14。已有LoudVA/BatchDVFS审计优先复用；补充查询AGX Xavier thermal RC/model/capacitance、batch energy dataset、power/rail gating latency，聚焦原厂文档、作者原文和已确认工件。未把搜索返回的训练/其他模型或其他Jetson设备数值拼成一个AGX配置。

新增有效依据是NVIDIA原厂《Jetson AGX Xavier Thermal Design Guide》TDG-08981-001_v1.0（2018-10），由载板厂商Diamond Systems托管。§3.1.1、图3-1与表3-1分别定义SoC→TTP→环境路径及典型热阻：θjp在均衡/集中负载下为0.35/0.65 K/W；θjb=5.5 K/W供模块两热阻CFD表示使用。二者不是CPU/GPU节点热导矩阵，更没有给出本轮所需动态热容。数值登记于证据表，未填入仿真矩阵。

NVIDIA R35.6.0官方说明Active状态下GPU可被power-gated；SC7则为系统挂起。它支持功率状态机制的存在，不确定本轮请求模型的有效空闲门槛或唤醒成本。SOC_THERM的0.5°C描述不等于完整测量链的误差界；±2°C作为敏感性情景明确自设。

sBEET（Wang等，RTSS2021）作者稿§II-A、IV-A、V-A补充同型号GPU功率建模依据：其处理GPU轨功率、动态/闲置资源项，实测设置固定670MHz，以10分钟均值取得功率参数，并在当时测试温变很小的前提下未纳入温度影响。它不是本轮同模型同精度batch1/2的标定数据，也不支持把GPU-only节能比例写成完整系统收益。

本轮未找到可直接用于目标B动作模型的同配置batch1/2、温度漏电、动态RC及唤醒联合辨识数据；表中未知量保留null。这是有限检索的结果，不断言这些数据在所有公开资料中都不存在。

原文定位和链接见physical_evidence.json。PDF为网页定向读取，未声称本地结构预检PASS或逐页精读完成。来源事实、物理解释、合成情景三者分开；不以模型能产生翻转反推参数真实。
