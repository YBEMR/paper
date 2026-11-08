"""Build the report exclusively from saved metrics and audit records."""
from datetime import datetime, timezone
from fractions import Fraction as F
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
m=read(OUT/'metrics.json');a=read(OUT/'audit.json');p=read(OUT/'execution/plan.json')
b=m['batch'];stats=m['statistics'];start=read(OUT/'execution/batch_started.json')['utc']
rounded=lambda v:f'{float(F(v)):.12f}'
sec=lambda v:'未达' if v is None else f'{v:.3f}'
name=lambda r:r['arm']+(str(r['seed']) if r['seed'] else '')
lines=['# C01 七次正式方法比较','',
    f'记录生成：{datetime.now(timezone.utc).isoformat()}。本轮读取真实七次调用及七次复评结果，不加入新搜索或热积分。','',
    f"固定 C01 C1/C2 上，ON 最终能耗为 {rounded(pv:=next(r['energy_upper_J'] for r in m['rows'] if r['arm']=='ON'))} J，较本轮增强 HEFT 降低 {stats['ON_energy_reduction_vs_HEFT_percent']:.6f}%；相对原 SA 五种子中位降低 {stats['ON_energy_reduction_vs_SA_median_percent']:.6f}%。七次均保有完整 SAFE 解并通过同评价器新进程复评，未重试或替换种子。仅为已见 C01 的固定预算观察。",'',
    '## 每次结果','',
    '|方法/种子|最终能耗上界 J|方法根秒|进程秒|post 根秒|实际评价/完整 SAFE/缓存|停止|',
    '|---|---:|---:|---:|---:|---|---|']
for r in m['rows']:
    lines.append(f"|{name(r)}|{rounded(r['energy_upper_J'])}|{sec(r['method_root_s'])}|{sec(r['method_process_s'])}|{sec(r['post_root_s'])}|{r['evaluation_attempts']}/{r['validated_SAFE_receipts']}/{r['cache_hits']}|{r['terminal']}|")
sa=stats['SA'];lo,hi=sa['energy_upper_J_range_among_successes']
lines+=['',f"SA 成功安全解条件中位数 {rounded(sa['energy_upper_J_median_among_successes'])} J，范围 {rounded(lo)}–{rounded(hi)} J，完整安全解及复评成功率 {sa['SAFE_post_successes']}/5。五次合计预算1500秒，只报告逐种子及中位/范围，不以最好种子冒充一次300秒表现。",'',
    '精确能量上下界、停止与原生搜索计数见 `metrics.json`、`metrics.csv`、各 `method/result.json` 和 `method_return.json`；表内上界仅为便于阅读的四舍五入。安全成功率不代表优化胜率或最优性。','',
    '## 达到质量的时间','',
    '|方法/种子|首份完整 SAFE 秒|首次严格优于首解秒|首次自身最终质量秒|达到本轮 HEFT 上界秒|达到本轮 ON 上界秒|',
    '|---|---:|---:|---:|---:|---:|']
for r in m['rows']:
    lines.append('|'+name(r)+'|'+'|'.join(sec(r[k]) for k in ('first_SAFE_s','first_strict_improvement_over_first_SAFE_s','own_final_quality_s','HEFT_quality_s','ON_quality_s'))+'|')
lines+=['',f"SA 达到 ON 阈值的种子：{stats['SA_seeds_reached_ON_quality']}；达到 HEFT 阈值的种子：{stats['SA_seeds_reached_HEFT_quality']}；比 HEFT 自身更早达到 HEFT 最终质量的 SA 种子：{stats['SA_seeds_reached_HEFT_quality_before_HEFT_itself']}。阈值在结果后统一从本轮 HEFT/ON 上界抽取，仅用于只读分析，不作为搜索停止或参数选择条件。",'',
    '## 计时、评价与比较边界','',
    '每次真实方法根均为300秒，从worker入口单调时钟开始，包含选定科学模块导入、冻结身份验证、候选无关输入读取、原生初始化、全部内部结构操作和完整连续电热评价；根不重置。解释器与标准启动导入以及最终序列化另记进程墙钟，因此进程时间可略大于300秒。采用原有协作式截止，末尾未决凭证保留；只能接受300秒前形成的完整SAFE。自然完成的方法保留实际耗时，不补齐预算、不共享余量。','',
    'post 每次独立最多60秒，含自己的身份核验、结果读取和完整评价；不进入方法排名时间。评价器与方法内相同，属于复评，不能称独立实现验证。物理尝试/返回/完整SAFE/热违例/未决/缓存分列；SA原生含缓存评估数不混作实际热积分次数。','',
    'HEFT 与 ON 各自现场完成相同增强HEFT初始化，核对初解哈希与初始化候选序列一致；未共享对象、缓存或已有答案。原SA使用自己的原生构造/初始化、映射与频档/顺序邻域及上坡接纳。三方法共同输入、合法域、评价、总cap一致，原生初始化与停止策略允许不同；这不是统一初始搜索状态或只改变单个邻域的消融。','',
    f"方法内实际评价合计 {stats['counts_total']['evaluation_attempts']}，返回 {stats['counts_total']['returned_receipts']}，完整SAFE {stats['counts_total']['validated_SAFE_receipts']}，返回未决 {stats['counts_total']['returned_unresolved_receipts']}，缓存 {stats['counts_total']['cache_hits']}；另七次完整SAFE复评。完整统计见 `audit.json`。",'',
    '## 输入、实现与冻结证据','',
    f"仓库基线 `{p['subject_commit']}`，分支 `{p['branch']}`。本轮新增 `c01/formal.py` 及两个针对性测试入口，直接调用原300秒主对照分派，不使用短根HEFT包装层。原算法、物理模型、评价器和历史输入不改。冻结计划 `{m['plan_sha256']}`，形成于 {p['created_utc']}，早于批次。",'',
    f"输入来自 `{p['source_sha256'] and 'research/chapter3_method_entry_preparation/results/frozen_entry02/common_input.json'}`，原文件SHA `{p['input_file_sha256']}`，实例 `{p['input_id']}`，canonical实例/config哈希 `{p['input_sha256']}` / `{p['config_sha256']}`。保留C1/C2、实际230ms窗口、显式DAG、8共享Stage/12次执行、72合法模式、5ms开始格点与精确持续时间、原期限、50°C入口/80°C温限、原四节点平台及auto-L。config默认400ms保留但不覆盖实际230ms。未读取历史参考调度用于初始化。",'',
    f"`execution/source_snapshot/` 保存所有非results冻结源副本，另保存 `frozen_common_input.json`、`frozen_config.json`、`frozen_instance.json`；{len(p['source_sha256'])}项源码/配置/检查身份和{len(p['protected_sha256'])}项旧文件保护在批次前后匹配。",'',
    '## 实际运行与可追溯文件','',
    f"任务首条时间记录为 `session_start.json` 的2026-11-08 08:12:04 UTC；正式批次 {start} 至 {b['ended_utc']}，实际 {b['wall_s']:.6f} 秒。方法及post各自实际起止/命令见 `execution/calls/<slot>/worker_command_*.json`、`post_command_*.json`，日志见同目录 `*_stdout.log`、`*_stderr.log`、`*_evaluation_journal.jsonl`。无漏跑、无补跑，按HEFT、SA101、ON、SA102–105预定顺序串行。",'',
    f"环境：{p['environment']['platform']}，Python {p['environment']['python']}，numpy {p['environment']['packages']['numpy']} / scipy {p['environment']['packages']['scipy']}，{p['environment']['cpu_count']} CPU；OMP/OpenBLAS/MKL/NUMEXPR固定单线程。资源预检通过。无MATLAB/Octave，未安装软件、调用MILP或改变环境。",'',
    '主要命令（cwd `/workspace/paper`，完整精确argv/起止/耗时见 `command_01`–`command_12` 的started/return JSON）：','',
    '```text',
    'python -B -m research.chapter4_scheduler.c01.formal_precheck --out <R>/unit_run02',
    'python -B -m research.chapter4_scheduler.c01.lifecycle_precheck --out <R>/lifecycle_regression',
    'python -B -m research.chapter4_scheduler.c01.precheck --out <R>/c01_regression',
    'python -B -m research.chapter4_scheduler.blocking.run_precheck --out <R>/graph_regression',
    'python -B -m research.chapter4_scheduler.comparison.precheck --out <R>/comparison_regression',
    'python -B -m research.chapter4_scheduler.validation.sa_precheck --out <R>/SA_regression',
    'python -B -m research.chapter4_scheduler.c01.formal prepare --out <R>/execution --checks <R>/unit_run02/checks.json',
    'python -B -m research.chapter4_scheduler.c01.formal batch --out <R>/execution',
    'python -B -m research.chapter4_scheduler.c01.formal summarize --out <R>/execution',
    'python -B <R>/analyze.py',
    'python -B <R>/extract_metrics.py',
    '```','',
    '`R=research/chapter4_scheduler/results/c01_formal_20261108`；均经 `command_runner.py command_NN ...` 记录，非新运行指令。首轮10项及快照补全后的最终10项检查均保存，不把重复运行加算成20项覆盖。最终新增10＋回归15/17/109/20/21，共192项人工/模拟检查通过，性质不等同真实算法性能。','',
    f"结束后 {a['assertion_count']} 条只读断言通过：重算调度合法性、核对SAFE闸门/两场景230ms覆盖、候选/输入身份、预算内凭证、SA五种子参数与最佳安全档案、初解独立一致、post能量相交、统一评价计数与完整冻结副本；强制禁止新优化/积分调用，实际为0。核查复用原SAFE检查逻辑，不是独立数值实现。",'',
    '## 结论限制与下一步','',
    f"C01此前已用于接线与短冒烟，因此不称盲测、独立新任务族或普遍性验证。本轮没有OFF组，ON相对HEFT的收益不能单独归于阻塞边；也没有全局最优证明或真实芯片测量。七组最终各场景峰温上界最高 {stats['maximum_final_peak_upper_degC']:.6f}°C，原温限80°C；这不展示紧热边界收益或热约束主导收益。各场景能量分项与峰温区间保存在 `metrics.json`。",'',
    '本轮七次范围完成即停止，不扩例、调参或自动追加消融，不提交/推送/合并。下一步建议把R2/R5与本C01证据合并整理为第四章算法与有界对照叙述，保留不同任务结构、原生初始化、预算和因果归属限制。','']
with (OUT/'summary.md').open('x') as stream:stream.write('\n'.join(lines))
print(str(OUT/'summary.md'))
