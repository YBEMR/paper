# 证据读取与复核

各方法交付的排程可以从压缩档恢复到原始事件和整数时刻。配置字节、功率系数、切频耗时、因果空闲选择和全系统能耗定义均沿用冻结归档。检查新排程时从相同任务流和初态开始。

| 项目 | 路径、格式与运行约定 |
|---|---|
| 工作区 | shared.py 中 U4B_LAB 默认取父级项目工作区；U4A_SRC 指向冻结 U4-a 研究目录，U3B_SRC 指向冻结 U3-b 研究目录，U3A_INPUTS 指向原冻结源码物化树（nt、four、p1、u2 等），U4B_RUNS 为本轮独立流水目录。指定 NUMBA_CACHE_DIR 可复用编译缓存。版本与输入指纹见 sources.json。Python 3.12.4，NumPy 1.26.4，Numba 0.61.2；外部硬截止控制复用冻结 Windows 实现。 |
| 预登记与执行 | PROTOCOL.md 是主实验前登记，gate.json 绑定具体遗漏与物理端点，residual_scope.md 为主对照结束后单列的残余核查。budget.py 管理离线全局额度和恢复：offline、detail、proof_check、out_of_model、residual 分别对应原始审计、扩展、在线证据核验、域内违规回查和残余候选。online.py 仅在证据门槛成立且旧收据缺失时启动对应新路线。源文件保留复核入口；已归档数据直接读取即可。 |
| 原始日志与层 | offline/每流/audit.json 的 original_journal 以 U4-a results/该流 为相对根，原始每次频档/配额/时序尝试和父节点均可按哈希定位。legal_pools.jsonl.gz 每行是层、真实名次、完整配置十六进制、原时序向量。audit.json 另存原始保留序列、各层后裔数、首次后裔消失的时机、末层所有不同祖先计数及参考路径各窗归因。Ordinary/Previous/Source_repair.json.gz 含实际执行的修复尝试、展开父节点与已记录的完整池排序；硬截止处只保留已经写入的动作。 |
| 安全参考路径 | safe_reference.json 绑定 NT60 最后已交付的完整 SAFE 身份和连续轨迹哈希，逐窗沿实际父状态对齐所有等价频档对。conditional 计数只说明在给定父状态下生成动作。未生成、时序不通过、实池合法排名落后、父节点此前已丢失在 path 中分开记录。 |
| 违规证据 | terminal_evidence.json 记录全部真实末层候选逐一匹配到的物理前缀；无匹配者的最终状态见 residual.json。domain_prefixes.json 单列即使完整轨迹后来出域，早期仍在域内的严格超温端点。certificates.json 依运行和阶段存旧完整认证与可匹配前序证书，gross_call_s 是实际历史调用时间，gross_kernel_s 只是认证内核。 |
| 连续证书 | results/每流/physical/plans.jsonl.gz 包含完整排程、显式低频选择、证书、轨迹形状和块索引。manifest.json、block-index.json.gz 和 events-*.bin 可由冻结 verify_archive.trace_reader 拼回小端 float64 的 N×31 矩阵；前 14 列为事件，随后为初末温度、连续上界、能量和累计温度误差。复核每块及拼回后的 SHA256。offline/每流/physical 为离线新增证书的同格式存储。 |
| 在线证据 | runs/方法.json 给出收据、截止前所有认证与交付及 journal 列表。journals/*.jsonl.gz 还原实际生成、保留、淘汰、开放检查、引用和回退。选择事件的层索引以 0 起算，表中窗口以 1 起算。proofs/*.f64.gz 为开放或终端严格违规前缀的 N×31 原始小端矩阵，行数、哈希及来源见 verified.json 和各运行的 strict_proof。截止未返回的开放检查无可用证书。 |
| 归档步骤 | archive_results.py 用原分块工具打包新收据和证书。proof_check.py 校验每次开放热检查、证书与交付、跳过的完整计划及其物理证据。decision_tables.py 由已冻结日志生成决策归因。routes.csv 的 checked_parents 为已完成的开放检查调用总数，包含 H 的候选热排序检查。原认证数与严格排除数分别保留。 |
