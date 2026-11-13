"""Generate a report exclusively from immutable execution receipts."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
s = json.loads((OUT/'summary.json').read_text(encoding='utf-8'))
arms = s['arms']

def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
                     ['| '+' | '.join(map(str,r))+' |' for r in rows])

results = table(['组','完整能耗 J（显示近似值）','相对共同初解节能','最终原生下界','原生 gap','处理节点','严格成功'], [
    [a, f"{float(v['final_energy_interval_J'][0]):.12f}", f"{v['approximate_saving_percent']:.6f}%",
     f"{v['native_response']['finite_native_lower_bound']:.12f}",f"{100*v['native_response']['finite_native_gap']:.6f}%",
     v['native_response']['nodes']['value'],'是'] for a,v in arms.items()])
models = table(['组','原变量 / 互补变量','输入整数变量','不等式 / 等式（互补）','不等式 nnz / 等式 nnz'],[
    [a,f"{v['counts']['original']['variables']} / {v['counts']['complement']['variables']}",
     v['counts']['complement']['integer_variables'],
     f"{v['counts']['complement']['inequalities']} / {v['counts']['complement']['equalities']}",
     f"{v['counts']['complement']['A_nnz']} / {v['counts']['complement']['Aeq_nnz']}"] for a,v in arms.items()])
timing = table(['项目（秒）','A','B','C'],[
    ['调用前累计计费']+[f"{v['allocation']['allocation_elapsed_s']:.3f}" for v in arms.values()],
    ['实际动态原生额度']+[v['allocation']['native_seconds'] for v in arms.values()],
    ['根 LP 原生日志时间']+[f"{v['root_LP_seconds']:.2f}" for v in arms.values()],
    ['全部根节点处理']+[f"{v['root_node_seconds']:.2f}" for v in arms.values()],
    ['随后 branch-and-cut']+[f"{v['branch_and_cut_seconds']:.2f}" for v in arms.values()],
    ['父进程完整收到向量及回执']+[f"{v['response_ack']['received_elapsed_s']:.3f}" for v in arms.values()],
    ['最终完整评价阶段']+[f"{v['timing']['phase_durations']['fresh_final_complete_AB_AC']:.3f}" for v in arms.values()],
    ['最终评价归档时刻']+[f"{v['timing']['full_evaluation_archived_s']:.3f}" for v in arms.values()],
    ['科学快照封存时刻']+[f"{v['timing']['seal_s']:.3f}" for v in arms.values()],
    ['真实单组墙钟（含外层清理）']+[f"{v['timing']['actual_arm_wall_s']:.3f}" for v in arms.values()],
    ['方法累计计费（含最终调度回执归档）']+[f"{v['timing']['method_including_final_dispatch_archive_s']:.3f}" for v in arms.values()]])
prep = table(['准备阶段（秒；嵌套阶段不可重复相加）','A','B','C'],[
    [title]+[f"{v['timing']['nested_science_durations'][key]:.3f}" for v in arms.values()]
    for title,key in [('完整构模','fresh_full_model'),('约简证书独立复核','fresh_reduction_certificate_replay'),
        ('独立初始化（含初解完整评价及连续辅助量）','independent_initialization'),
        ('互补转换与精确投影认证','complement_transform_exact_projection'),
        ('原矩阵与互补矩阵存档','full_original_and_complement_archive')]])
resources = table(['组','工作进程 Job 峰值 MiB','外层 Job 峰值 MiB','工作进程 CPU 用户/内核秒','完整组内证据 MiB'],[
    [a,f"{v['resources']['worker_job']['peak_job_memory']/2**20:.3f}",
     f"{v['resources']['outer_job']['peak_job_memory']/2**20:.3f}",
     f"{v['resources']['worker_accounting']['user_cpu_s']:.3f} / {v['resources']['worker_accounting']['kernel_cpu_s']:.3f}",
     f"{v['evidence_bytes']/2**20:.3f}"] for a,v in arms.items()])
residual = table(['组','原矩阵最大绝对残差','互补矩阵最大绝对残差','等式/边界/整数'],[
    [a, f"{v['audit']['independent_residual_details']['original']['A']['absolute']:.4e}",
     f"{v['audit']['independent_residual_details']['complement']['A']['absolute']:.4e}",'全部通过冻结准入']
    for a,v in arms.items()])
intervals = '\n\n'.join(f"**{a}**\n\n- 完整能耗下界：`{v['final_energy_interval_J'][0]}` J。\n- 完整能耗上界：`{v['final_energy_interval_J'][1]}` J。\n- 原生最终调度身份：`{v['final_schedule_identity']}`。" for a,v in arms.items())
report = f'''# D285：完整 R1 CPLEX A/B/C 单次正式执行结果

三组均真实完成根 LP，接受完整共同初解，并返回不同于初解的原生调度。三个最终向量通过原矩阵与互补矩阵数值准入、独立调度合法性、原 AB/AC 连续电热完整 SAFE 评价及严格能耗区间比较。冻结只读审计全部通过；不以窗口外分析新增科学信用。

## 1. 授权、身份与实际调用

- 唯一授权对象：`366169c4c6cec9e15dc9c2076b1fae0794ac63e6`；计划 SHA-256：`{s['plan_sha256']}`。原冻结文件未修改。
- 用户授权的一轮 A→B→C 已消费；独立进程、每组完整构模 1 次、求解 1 次、完整评价 2 次（新建初解与最终原生候选各一次），总计构模 3、solve 3、完整评价 6。初始化均第一次即 SAFE；无重试、无参数扫描、无补跑。
- 实际运行 UTC：{s['host']['started_at_utc']} 至 {s['host']['ended_at_utc']}；北京时间 2026-11-13 21:22:15 至 21:49:31。主机完整墙钟 {s['host']['host_wall_s']:.3f} 秒，批次内部墙钟 {s['batch']['actual_batch_wall_s']:.3f} 秒。
- CPLEX Python/引擎 22.2.0.0；DLL SHA-256 `{arms['C']['runtime']['dll_sha256']}`；固定单线程、种子 0、D283 全套原生参数。所有实际参数读回仅 `parameters.timelimit` 按冻结函数不同；没有切换算法、表达或初解。
- 每组 600 秒方法窗、550 秒完整原生响应截止、590 秒科学封存截止；动态额度 `floor(min(540,max(0,600-t-10-50)))`，最低 30 秒。工作进程 3 GiB 硬限、外层 Job 3.5 GiB；原进程数和软内存保护保持不变。
- 真正的 Job 内 Git 主程序读取计划和 21 个源码身份成功。各组 runtime、输入、矩阵、源文件与封存哈希通过执行器及只读审计；三个工作进程、外层 Job 最终活动进程数均为 0，无清理异常。

## 2. 共同科学任务与模型

保留完整 auto-L R1、12 次 Stage、66 种原合法模式、5 ms 网格、400 ms 完整窗口、原物理参数、目标和评价精度。A 为期限过滤；B 增加 Stage 选项支持传播；C 再增加联合频率状态剪枝。各组重新构模、独立初始化、独立约简认证和互补精确投影认证，无跨组科学缓存或矩阵复用。

{models}

三组互补表达均为 `split_constant_v1`，全部精确代数检查通过；CPLEX 原生装载与逐项读回通过。B/C 输入整数变量同为 1125：第二级删除联合辅助状态及其相关行，不继续删除已保留的 Stage 选项整数列。C 证书复核 9798 个状态、删除 2938 个；保留全部未知状态。互补转换保留本组原模型的连续投影；不同约简组之间不声称 LP 松弛完全相同。

CPLEX 内部预处理会发现额外二元结构；日志中最终预处理二元列 A=3148、B/C=2643，不是输入整数域被接口改写。每组原生预处理日志和实际参数完整保留。

共同初解由三组分别独立构造，调度身份完全相同：`{arms['A']['initial_schedule_identity']}`，能耗区间也逐字相同：

`[{arms['A']['initial_energy_interval_J'][0]}, {arms['A']['initial_energy_interval_J'][1]}] J`。

原生日志均明确记录 `1 of 1 MIP starts provided solutions`，并将 `common_complete_x0` 作为初始解。完整初解存入/读回和真正接纳分开存证，未回退至仅整数初解，未修复调度。

## 3. 分层科学结果

{results}

三组 12 次 Stage 均发生变化，最终均使用 L 档；共享部署、时序、资源、DVFS 耦合及截止约束通过独立合法性检查。逐 Stage 的初解/终解变化见 `analysis/schedule_changes.json`，完整原生向量在证据归档内。

三组在以下层次分别 PASS：完整输入/模型身份，根 LP 进入与完成，有限原生下界，原生最终候选，两种矩阵准入，独立调度合法性，双场景完整 SAFE，不同调度，严格降低完整能耗。独立全局最优性均为 UNKNOWN。

三组最终均为 CPLEX 状态 **107 / time limit exceeded**，有原生可行向量；这是普通时限退出，不是数学不可行。A 时限内尚停留在根节点处理，仍产生两次更低的原生 incumbent，不能将节点 0 解释为没有优化。B/C 实际进入 branch-and-cut。普通超时没有阻断后组。

完整 SAFE 证据包含 AB、AC 两个场景，各覆盖 2/5 秒，均 `complete=true`、`energy_accuracy_met=true`。本轮各节点完整温度峰值区间均为 [50,50] °C（包含初始时刻）。这说明本实例的优化候选热安全；不能据此宣称在更紧热约束下同样有效，也不能省略电热模型。

{residual}

以上由冻结审计器逐行 `math.fsum` 独立复算；绝对和归一化准入 1e-9、整数准入 1e-6 均未修改。A 的非零残差约 9e-11，B/C 约 1e-14；这是数值准入，不是原生向量的精确有理数可行性证书。互补表达的精确等价认证与原生点的数值准入必须区分。

原生 objective 也不替代完整物理能耗：A 为 {arms['A']['native_response']['finite_native_upper_bound']:.16f}，B 为 {arms['B']['native_response']['finite_native_upper_bound']:.16f}，C 为 {arms['C']['native_response']['finite_native_upper_bound']:.16f}；特别是 A 与完整评价值差约 4.50e-11 J。严格改善只比较完整 SAFE 能耗区间，所有组的新上界都严格小于共同初解下界。

{intervals}

能耗区间之间有严格次序 **C < B < A < 共同初解**。B 相对 A 少 {s['comparisons']['A_minus_B']['approximate_J']*1e6:.6f} 微焦耳；C 相对 B 仅少 {s['comparisons']['B_minus_C']['approximate_J']*1e6:.6f} 微焦耳，约占 B 能耗 0.000533%。上述差异经 Fraction 精确比较，非打印舍入导致；实际工程意义和跨实例稳定性仍未知。

## 4. 完整成本与求解过程

{timing}

调用前累计计费包含各组进程/身份检查、构模、初解完整评价、认证、传输装载、逐项读回和参数检查。共同启动 1.343 秒保守地分别计入三组，未免费排除；实际批次成本没有用三组重复计费代替主机墙钟。最后一行进一步包含调度回执归档，略高于控制器收尾读数。剩余预算是预留验证/收尾未用部分，不用于追加求解。

{prep}

互补转换与精确投影认证成本显著，不能从端到端对照中扣除。C 构模及约简复核增加成本，最终调用前累计比 B 多 20.625 秒，原生额度少 21 秒。C 根 LP 比 B 快 2.97 秒，但全部根节点处理多 32.17 秒；分支阶段少 53.15 秒，却处理 154 对 133 个节点。这些是本轮观测，不代表节点子问题相同或稳定吞吐优势。

各阶段起止与未命名间隔均在 `scientific_snapshot.json`、控制器和外层回执中；阶段表有嵌套，不能相加后再次加方法总窗。全过程没有免费的 MATLAB 启动成本：本执行器使用 Python/CPLEX，没有启动 MATLAB。

{resources}

内外 Job 都未触及内存限额，资源与原生错误回执无异常；无来源漂移、迟到响应或候选拒绝。C 完整组内封存证据约 125.79 MiB，接近 128 MiB 证据保护上限（余量约 2.21 MiB），是后续推广时需要预先冻结评估的风险，本轮未扩大限额。原生日志末尾的 `Advanced basis not built.` 原样保留；接口没有把它报告为求解异常，三个正常时限退出和最终候选证据不受影响；不据此推断内部根因。

## 5. 异常、未知项与结论边界

- 本轮未出现身份、许可、内存、数值退出或清理异常。每组都正常达到原生时限；日志、回调、最终回执独立保留。
- 回调中间向量没有逐个进行完整热评价。不能把首次 incumbent 的日志时刻称为首次完整 SAFE/严格节能时刻；只有最终候选完成了本轮冻结科学验收。
- 原生有限下界和 gap 是 CPLEX 数值报告，没有独立精确对偶证书或全局最优性证明；不能把 13% 左右 gap 写成已最优。
- 这是固定顺序 A→B→C、固定 seed 0、单线程、单个 R1、单次批次。主机资源/顺序效应、重复性、其他工作负载、期限与热条件的推广仍未知。
- 本轮证实完整任务上的 MILP 优化确实获得了不同、合法、完整 SAFE 且严格节能的调度；三个组都做到，约 20.67% 相对初解收益不能全部归因于两级约简。
- 第一级与第二级的增量证据必须分别报告：B 在本轮比 A 准备和根 LP 更短、进入分支且能耗略低；C 比 B 的模型和内存更小、最终能耗略低，但准备和全部根节点处理更久，方法总成本没有优势。因此不能宣称已证明第二级稳定加速。

下一步优先把本轮有效结果、全成本和微小增量收益纳入第三章；若继续科研调用，应单独冻结有限重复性/推广检验，保留失败与无增益结果，不能在本授权下继续补跑。当前不需要为获得更好数字临时换参数或改模型。历史 intlinprog A/B 或保存 C 诊断不进入本轮剪枝加速比较。

## 6. 审计、归档与复核入口

`analysis/A_audit.json`、`B_audit.json`、`C_audit.json` 均为冻结 `audit_result.py` 的只读结果：文件身份、输入身份、响应/封存/最终归档窗口、两矩阵独立残差、严格能耗声明、调用上限和内外清理均通过。只读审计调用成本另列 `analysis/audit_execution.json`；它不构模、不求解、不热评价，也不能给迟到结果补科学信用。`analysis/summarize.py` 只读取保存矩阵维数/已有回执并用精确分数比较已封存能耗。

完整 A/B/C 组内原始证据分别无损压缩为 `raw_A.zip`、`raw_B.zip`、`raw_C.zip`，含全部原/互补矩阵、所有候选向量、模型与认证证据、日志、资源采样、完整评价及原始 Git 输出；逐文件大小/SHA-256 和解压回读核验见 `ARCHIVE_MANIFEST.json`。仅为本轮这三个确定证据归档添加 Git 忽略例外，不提交许可文件或凭据。`execution/` 保留根目录批次回执及每组可直接浏览的关键 JSON/日志（与归档内同名文件字节一致）；`launch/` 保存本轮用户授权消费与主机启动/结束记录。

发布压缩、只读复算、写报告和 Git 操作发生在方法窗口之后，是行政复核/出版成本；没有对候选作新的评价，不用于提升科学状态。单组600秒成本已包含科学封存、完整评价、原始证据读取归档和清理，发布只是现有证据的无损复制。

原冻结计划与执行器：[D285 冻结目录](../chapter3_cplex_ABC_entry_fix_20261113/executor/)。原始矩阵与程序版本可结合 manifest 和冻结哈希逐项复核；在原冻结工作区可用 `audit_result.py --workspace <原工作区> --plan <冻结plan.json> --run <解压后的组目录>` 重做只读审计。审计依赖冻结工作区输入；不得用新构模或新热评价补齐缺失文件。本轮授权已完成、不可复用。
'''
(OUT/'REPORT.md').write_text(report, encoding='utf-8')
print('Report written:', len(report), 'characters')
