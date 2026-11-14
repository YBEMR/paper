端侧异构热感知能耗调度：第一轮机制筛选（2026-11-14）

先读 report.html。所有数值实验都是 SYNTHETIC_UNCALIBRATED，不预测实际设备收益。
结论：A未见冷热最优并发关系翻转；B有批结构翻转但相对共同最佳固定方案仅0.0594996%；C缺合法分区成本，未运行。唯一下一步见NEXT_PROTOCOL.txt，尚未启动。

主要文件
parameters.json / PROTOCOL.txt：运行前冻结参数和方案。
PROTOCOL_C.txt：C的补证协议，未运行。
screen.py：事件驱动有限穷举+两节点电热积分，无优化求解器。
analyze.py：从已保存原始结果计算跨温度固定基线、阈值与摘要。
tail_audit.py：8条关键10s续接结果用Radau交叉核查。
energy_accounting.py：306条full记录的互斥设备阶段能耗分项。
results/all_candidates.csv / .jsonl：全部1224条候选结果，含不可行行；CSV适合筛选，JSONL含各设备末温/峰温等。
results/summary.json：24个方向/入口/模型组合的所有并列最优与回到full的能耗范围。
results/actions.json：可复原动作参数。
results/energy_accounting.csv：计算、清醒空闲、休眠、唤醒及外部常量能耗，单位J。
results/checks.json / tight_validation.json / tail_validation.json / energy_accounting_check.json：数值核查。
results/run_environment.json：实际运行环境、耗时、源码/参数SHA256与执行时Git提交。
literature_matrix.json / .csv：原文核查与待验证假设。
provenance/：已读源文件的下载哈希、PDF结构预检状态、原仓库回顾与笔记快照（不含论文PDF全文）。
repository_provenance.json：原仓库分支/SHA、原文位置、工件审计范围。
source_audit.json / REVIEW.txt / EXECUTION_NOTES.txt：检索边界、同助手自审、执行差异。
delivery_manifest.json：交付提交及文件哈希。
study_history.bundle：独立本地Git历史；没有向YBEMR/paper推送。

复现（推荐在复制出的目录执行，避免覆盖交付原数据）
环境：Python 3.12.4、numpy 1.26.4、scipy 1.13.1；报告作图另需matplotlib。
若从bundle恢复：git clone study_history.bundle recovered-study
然后在对应目录执行：
python screen.py
python analyze.py
python tail_audit.py
python energy_accounting.py
python report_builder.py
主运行本机91.18秒；120秒软上限可能在较慢机器触发，保留中间JSONL并停止，不自动扩预算。报告生成器只读取现有结果，不重新实验。
如果不使用bundle且未初始化Git，screen.py末尾获取git SHA会失败；应先用bundle恢复。只有依赖安装需要联网，本实验不联网。

口径
cool=40/40°C；warm=60/60°C；cpu_warm=60/40°C。A mapping 0=CPU,1=GPU；first 0=X,1=Y；id尾数是偏移目录索引。B如B-211-100表示批2/1/1、额外等待20/0/0ms。
所有“最优”只在本轮有限目录内成立。102为动作参数化数，A去重后40条事件表；1224不是独立重复实验。
固定基线先在cool/warm的总能量上共同选一个动作，再与逐状态知道最佳动作的离线上界比较；两态等权仅为本轮诊断权重。
并列容差1e-7J是数值规则，不是物理测量精度。
报告中的1%进入门槛是未来投入判断建议，不是文献规定；未开始采集。
