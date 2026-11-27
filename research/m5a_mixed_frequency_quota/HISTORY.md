# 共同初解与历史成本
以完整 SAFE 物理计划为单位。从 M1-i、M1-j 的所有重复与所有方法终点，U2 的各路线与因果复评，M3-a 的全部已认证候选，以及 U1 和 E3-a 的适用流中选择。M1 系列重复表使用同次运行各个统计截面的最低已认证值；U1 含 180 秒终点。逐方法来源及证据对象 ID 见 [历史索引](history_index.json)。本文件时间是既有工作产生选中排程的记录，全部新方法实际接入成本另计。
| 流 | 选择来源 | 初解 J | 原运行产生这份解的时间 |
|---|---|---:|---|
| A02 | M3-a，固定配额中的任务分布调整 | 27.865490217370 | 已有 NT 初解上追加优化；历史第 1 次热引导阶段在 0.25 秒截面已有此解，0.302 秒自然结束。上游 NT 是独立批次。 |
| A06 | U1，延长至 180 秒的 NT | 46.428494665782 | 160.776 秒取得。M1-i 的 ZQ-Beam 最好为 46.469099752267 J。 |
| C10 | U2，自适应成组降频 | 58.879444630400 | 第 1 次在计入共同初解成本后的 5.177 秒认证，5.376 秒结束。三次均为相同物理排程。 |
| C11 | M1-j，NT 的综合排名保留对照 NT-S | 74.319726749657 | 第 1 次 36.020 秒，另两次 35.939 和 35.812 秒。 |
C10 同时核对 M1-i 的 ZQ-Beam 58.920391726204 J、E3-a 的最低 58.915204017 J、M3-a 的最低 59.324561746979 J。U2 比 E3-a 低约 0.03576 J。只读取历史归档，原搜索的计时保留在原批次。
初解的原始三阶段时刻、设备与档位、显式空闲、切换及连续认证见 [四个历史排程](history)。U1 和 M1-j 从冻结物理归档以计划哈希提取。M3-a 从冻结 audit.json.gz 提取，U2 从 C10 物理卷提取。认证器的事件双实现校验和各初解物理身份的再次核对见最终物理预检。
[U1 改善时刻](https://github.com/YBEMR/paper/blob/44e99658159ded9042fd47a5c448b5be5868bcdb/research/u1_unified_diagnostic/results/improvements.csv) · [M3-a 各时刻](https://github.com/YBEMR/paper/blob/1bdb3e0671b6f2ad56aefe9d5b3652ff25b314b0/research/m3a_quota_distribution/tables/wallclock.csv) · [U2 各运行](https://github.com/YBEMR/paper/blob/c9aa84bc33e4554f0e18d31e15815c1063300b8d/research/u2_adaptive_groups/tables/runs.csv) · [M1-j 各重复](https://github.com/YBEMR/paper/blob/b95570f9ae5b0cdb26abcdf78701e12f1c644f40/research/m1j_retention/data/repetitions.csv) · [E3-a 报告](https://github.com/YBEMR/paper/blob/c05c0bb13935b4d220a27e5c5a010c08914f35e1/research/e3a_energy_interval_reconstruction/REPORT.md)
