# 共享映射实验问题交接（2026-11-06）

> 发布传输说明：6个文本文件统一为LF换行，原始JSON数据、源码字符及科学结果未改变。发布字节哈希以MANIFEST为准；报告中的原输入/worker哈希指本机原件。详见[换行转换记录](TRANSPORT_NORMALIZATION.json)。本机执行环境在发布前断开，因此本交接不宣称这些文件与原件字节相同。


**状态：诊断已停止，无新实验授权。** 同一 MATLAB worker 的12个玩具请求成功；原完整任务链单映射 AB/AC 的10秒、30秒诊断均空返回。停止机制A/B控制和唯一AB初解探针仍未取得可返回候选，保留的SAFE来自现场初解。

请先读 [中文交接报告](HANDOFF_ZH.md)，再按其中路径核查原始响应、停止决策和清理。这里没有全局最优、不可行、算法性能或“初解已被求解器采纳”的证明。

- [文件清单与校验](MANIFEST.json)
- [原文件来源、原哈希与脱敏哈希](source_index.json)
- [脱敏与排除范围](SANITIZATION.md)
- [未上传二进制的哈希索引](binary_evidence_index.json)
- [原完整输入](inputs/input_instance.json)、[原配置](inputs/input_config.json)
- [停止控制汇总](evidence/CONTROL_RESULT.json)、[唯一AB探针审计](evidence/ab_probe/RESULT_AUDIT.json)
- [R2023b官方资料索引](OFFICIAL_SOURCES.json)

六组证据位于 `evidence/toy12`、`soft10`、`soft30`、`control_A`、`control_B`、`ab_probe`。原始JSON按明示规则脱敏，部分结果仅提取必要字段；完整最终场景/聚合SAFE回执未改动，重复进度与尝试不复制。来源哈希与发布哈希分列，不能混用。

`sources/*.py.txt` 与 `sources/*.m.txt` 是审查快照。路径占位符不能直接运行；快照也不构成重新启动MATLAB、修改参数或重复实验的授权。MathWorks安装源码、许可证、动态偏好目录和原生MAT文件没有包含在本包。

本材料新增至独立分支 `results/shared-mapping-handoff-20261106`，计划父提交为 `2174d038899241fa864f7a7309cbfce02f5d1d95`（此前已发布结果链）；实验科学基线另由各冻结清单标识。没有合并或覆盖main。下列结果是已有记录：本次仅整理、脱敏和提交。
