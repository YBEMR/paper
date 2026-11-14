# 热感知高能效调度：第一轮方向筛选（2026-11-14）

本目录补交已完成的独立研究结果，原实验参数和结果没有重跑或修改。

## 结论

- A：合成争用使串行更省能，但冷热状态未改变最佳并发关系；需要补证。
- B：冷态最优批结构为2＋1＋1，温态为2＋2；相对两态共同最佳固定方案，能量改善仅0.0594996%。仅支持继续同平台参数与可测效应审计，不支持硬件收益或新算法贡献。
- C：缺合法分区与完整调用/搬运成本，未构造虚假分区实验，暂缓。

三个方向均未确立为论文主线。唯一建议是B的参数审计，详见[NEXT_PROTOCOL.txt](NEXT_PROTOCOL.txt)；硬件和大规模实验尚未启动。

## 材料入口

- [完整自包含HTML报告](report.html)（下载后用浏览器打开）
- [文献矩阵](literature_matrix.csv)：13项来源，11项原文关键章节定向核查，2项摘要/工件级
- [冻结实验协议](PROTOCOL.txt) / [参数](parameters.json) / [C方向补证协议](PROTOCOL_C.txt)
- [全部1224条候选结果](results/all_candidates.csv) / [包含末温等完整字段的JSONL](results/all_candidates.jsonl)
- [全部并列最优与消融回放](results/summary.json) / [完整能耗分项](results/energy_accounting.csv)
- [数值检查](results/checks.json) / [交付一致性检查](results/delivery_qa.json)
- [源码](screen.py) / [分析](analyze.py) / [原仓库与工件快照](repository_provenance.json)
- [发布清单与字节哈希](publication_manifest.json) / [发布说明](PUBLISHING.txt)

全部时延、功率、RC和休眠参数属于SYNTHETIC_UNCALIBRATED。1224是确定性候选评价行，不是独立重复实验数。B仅验证单GPU合批机制，尚未证明异构调度收益。

## 复现

在本目录使用Python 3.12.4，依赖见[requirements.txt](requirements.txt)。先复制目录或保存现有结果，再按需运行：

```text
python screen.py
python analyze.py
python tail_audit.py
python energy_accounting.py
python report_builder.py
python validate_delivery.py
```

主实验本机91.18秒，预设120秒软上限；较慢环境可能停在上限，不自动追加预算。复现不需要MATLAB或商业求解器。

冻结协议提交为7b498d6d10c83a775d4b755b38a57d769006f75b，执行提交为284cfda6cb070f3307df2c759cce5d4131c86df0，原本地归档提交为a92c91856d64365234fac6e906478a2c41aa9413。这三项属于独立本地仓库历史，不冒称本远程仓库中的祖先提交。

## 归档范围

远程版基于YBEMR/paper的main 92cd9f1702d96d4606bdacc921ff5d1fe4769c67，只新增本目录并更新根目录RESEARCH_BRIEF.md。旧源码、冻结参数、失败结果及章节材料不改。

本地独立Git bundle、压缩包和已在原仓库固定提交可追溯的重复文献笔记/回顾快照没有再次上传。原始本地复现包仍保留这些材料。README.txt、report.html中“未远程写入”的说明记录的是首轮交付时点；本次补提交状态以PUBLISHING.txt为准。
