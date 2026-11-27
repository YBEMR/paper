# 证据读取

先查看逐流结果，选中某次首解或终值的排程身份，再读取相应连续证书和实际候选日志。历史安全参考只在离线核验中出现。

| 项 | 读取方式 |
|---|---|
| 输入与环境 | sources.json 保存输入与冻结版本指纹。foundation.py 定位原 U4-b、U4-a、U3-b 及其物化依赖；可用 U4C_LAB、U4B_SRC、U4A_SRC、U3B_SRC、U3A_INPUTS 显式指定。U4C_RUNS 为独立原始流水目录。实际 Windows、Python、固定核和单线程数值库设置沿用上轮。 |
| 在线原件 | results/流/runs/臂.json 含硬截止收据、阶段耗时、截止前完整认证和实际交付。journal 列表引用 journals/ 下的 gzip JSONL，解压内容哈希是文件名。parent 与 q4_action 给出真实父配置、频档、配额、偏移和时序；过时或未返回的调用不算交付。selection 含全部保留项或末层送检顺序。 |
| 保留与期限 | diagnostics/臂-retention.json 按层列实际候选数、完整入位配置、父身份、真实参考排名及余量。current 是该窗释放请求的最小余量，pending 是窗口分界仍未完成请求的最小余量（可包含前窗积压），all 是前缀全部请求的历史最小余量。单位为 tick，每 tick 为 0.1 ms。设备可用时刻、频档、最后后处理完成点和未完数量同时保留。末层 observed_choices 给出完整顺查列表。 |
| 配额生成 | diagnostics/臂-blocks.jsonl.gz 写入实际主阶段补充触发时的首个具体超期请求（按期限与请求序号破平），以及补充候选合法后该请求的设备、就绪、开始、主阶段结束、后处理开始、最终完成和余量。legal_supplement 的最后一项为实际发生设备更换的 A/B 请求数。用同一父身份、窗口、频档关联 blocked 行；新增非平衡动作和空层额外尝试均可从原始 journal 还原。 |
| 热证书 | results/流/physical 与冻结 U4-a 无损分块格式一致；plans.jsonl.gz 含排程、显式低频选择、证书、矩阵形状、块索引。用 frozen.trace_reader 依次拼块得到小端 float64 N×31，核对块及整轨迹 SHA256。proofs 内另存可严格排除的历史端点与连续物理前缀。verified.json 记录重建结果与每臂核对量。fragments 仅保存硬截止瞬间的未完成文件，单独标识。 |
| 离线原件 | offline/流/evidence/具体流名/计划哈希 内的 plan.json、certificate.json、trace.npz 可直接读取。window_*.json 保存固定后缀的原频档、平衡配额、实际首个冲突、逐圈整数枚举和每个并列最小修复的完整认证，以及延迟见证一窗/两窗/有限回退的工作量。索引 i 从 0 起，报告窗口从 1 起。 |
| 测量与归因 | tables/routes.csv、paired_live.csv、cohorts.csv 分别是逐臂逐流、同期配对、分组汇总。timing.csv 是共同单调时钟上的单核运行区间。最后一次更低能耗的 SAFE 是终值，首次 SAFE 的阶段单列。seed_lineage.json、tables/lineage.csv 和 seed_survival.csv 能区分直接使用新增动作、竞争分支变化和独立回退交付。 |
| 可复核步骤 | 执行顺序为 budget.py witness、run_c.py、control_c.py、pack_c.py，满足联合门槛时才另开联合路线。随后 budget.py verify、budget.py lineage、analysis_tables.py、audit_delivery.py。budget.py 的所有任务共享 600 核秒累计限额。已保存的结果可直接用 validate.py 从本归档核对，无需重跑实验。 |
