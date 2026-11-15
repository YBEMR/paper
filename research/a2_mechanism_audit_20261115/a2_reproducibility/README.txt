A2 热感知选择性并发：公开数据审计与可复算结果
日期：2026-11-15。完整说明见同批交付 A2_机制核查报告.html。

本包不含硬件实验、模型仿真或算法收益。EdgeEngine 能耗为作者数据字段的推理能耗代理，非固定窗口整机积分。不得把结果改标成 A2 并发反转。

复现（Python 3.10+，分析只用标准库）：
1. python download_sources.py --out INPUT
   下载官方固定提交的100个EdgeEngine JSON与少量JLL样本；逐文件验证SHA-256。
   需要网络；不修改频率、不运行设备、不安装依赖。
2. python analyze_public.py --edge INPUT/EdgeEngine --jll INPUT/jll_samples --out reproduced
3. 比较 reproduced/edgeengine_results.json 与本包同名文件。

离线复算：已有两个仓库的对应提交时，直接指定本地路径。JLL样本仅下载manifest列出的文件。
EdgeEngine 原始资料未明确许可证，因此包内只交付自编脚本、来源清单、派生统计。
HaX-CoNN Zenodo 归档元数据标CC BY 4.0；JLL标Apache 2.0；模型有独立许可证。

主要文件：
ANALYSIS_PROTOCOL.txt：计算结果前写下的有界分析规则，非第三方注册。
edgeengine_results.json：数据完整性、采样、功率加和审计、7模型匹配变化与28组比较。
edgeengine_aggregates.json：每模型/温态/频率配置的聚合指标，单位显式写在键名。
edgeengine_source_manifest.json：100个文件、大小、记录数、SHA-256。
jll_sample_audit.json：原始样本轨迹统计；积分只覆盖日志时段。
provenance.json：版本与阅读范围；Mediator没有全文结论。
validation.json：独立汇总交叉检查与交付检查。

规则：无期限与既有期限均完整保留；主功率截取与全部样点敏感性均保留。
不把温度点/配置/采样点数量冒充独立实验重复数。温度分组是环境标签。
两态各50%权重是描述性分析设定，并非用户部署热状态概率。
数值上界仅指在这个已观测离散画像和动作集合内、不计额外决策开销的oracle上界，非真实设备可保证上界。
