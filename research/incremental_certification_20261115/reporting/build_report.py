"""Read-only reporting of the finished frozen replay; no evaluator imports."""
import json,statistics,sys
from pathlib import Path

def main(root):
    d=json.loads((root/'formal_v2/analysis.json').read_text(encoding='utf-8'))
    pilot=json.loads((root/'pilot/analysis.json').read_text(encoding='utf-8'))
    totals=d['totals'];runs=d['runs'];a=totals['A']['common_charged_s'];b=totals['B']['common_charged_s'];c=totals['C']['common_charged_s']
    costkeys=['identity_s','query_s','restore_s','save_s','prefix_query_s','prefix_save_s','prefix_restore_s']
    maintenance={arm:sum(totals[arm]['cache_common'].get(k,0) for k in costkeys) for arm in 'ABC'}
    extra=1-c/b;scene_saved=a-b;prefix_saved=b-c
    events=[json.loads(s) for s in (root/'formal_v2/events.jsonl').read_text().splitlines()]
    process={arm:sum(e['process_wall_s'] for e in events if e['event']=='RETURN' and e['arm']==arm) for arm in 'ABC'}
    # Engineering recommendation is an explicit reviewed decision, not a new
    # post-hoc statistical threshold hidden inside the report generator.
    stable='--recommend-controlled-search' in sys.argv
    if stable:assert not d['failures'] and d['saving_vs_A']['C']>0
    summary={'verification':'VERIFIED_ON_FROZEN_REPLAY_NOT_FORMAL_SOFTWARE_PROOF','common_candidates':d['common_SAFE_candidates'],
      'B_time_saving':d['saving_vs_A']['B'],'C_time_saving':d['saving_vs_A']['C'],'C_additional_vs_B':extra,
      'common_charged_s':{arm:totals[arm]['common_charged_s'] for arm in 'ABC'},'maintenance_s':maintenance,
      'full_process_wall_s':process,'recommend_controlled_search_protocol':stable,
      'formal_analysis':'../formal_v2/analysis.json','pilot_analysis':'../pilot/analysis.json','correction':'../CORRECTION.md','excluded_v1_completed_runs':21}
    (root/'results').mkdir(exist_ok=True);(root/'results/summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 连续电热认证增量复用原型验证', '',
      f"**本批共同完整候选上，B计费下降{100*d['saving_vs_A']['B']:.2f}%，C下降{100*d['saving_vs_A']['C']:.2f}%；C较B再下降{100*extra:.2f}%。** 所有配对完整证据按区间端点和全语义精确核对；结论限于本批冻结输入和单机回放，不是新调度节能率或任意输入的软件形式化证明。",'',
      f"诊断基线[b052cb0](https://github.com/YBEMR/paper/commit/b052cb004ae753e5d61b5b582561f9315739fde4)；评价器及历史候选基线[0de4d19](https://github.com/YBEMR/paper/commit/0de4d191966294dc673c21ed244616f1b5a6a85c)。准入8条A/B回放，共206个共同候选，B下降{100*pilot['saving_vs_A']['B']:.2f}%、4根3根改善；通过后才开发C。准入与正式数据分开。正式16条归档序列×A/B/C，全部保留原候选次序及每根300秒总预算，不运行搜索或MILP。",'',
      '## 1. 五个问题的回答','',
      '|问题|结论|','|---|---|',
      '|严格认证语义是否保留|v1存在根结束后继续发证缺口，已停止并修复。v2本批有限验证通过；原有向Decimal60/Taylor18、连续峰谷、精度、守恒及形成时刻均保留，证据精确相等。|',
      f"|实际计费降低多少|共同完整前缀合计A {a:.3f}秒，B {b:.3f}秒，C {c:.3f}秒；包含读入、合法性、缓存与回执维护、逐候选归档。|",
      f"|节省来自哪里|A→B净差{scene_saved:.3f}秒；B→C净差{prefix_saved:.3f}秒。它们是配对总差，不把所有墙钟波动归因于缓存；物理运算覆盖分别单列。|",
      f"|缓存及认证维护成本|共同前缀直接计时A/B/C为{maintenance['A']:.3f}/{maintenance['B']:.3f}/{maintenance['C']:.3f}秒；另列回执检查＋提交（与缓存保存部分重叠）及进程峰值内存。|",
      '|是否进入搜索实验|'+('值得提出受控协议；本轮未实施。' if stable else '当前不建议扩大搜索实验；保留未通过收益条件。')+'|','',
      '## 2. 同工作量与实际总消耗','',
      f"正式共同完整SAFE前缀合计{d['common_SAFE_candidates']}/855个候选。只有这些候选用于耗时百分比；任何未决和未开始记录均在原始日志及下表保留。边界取下一候选start（含其复制准备，不含其数值工作），若无下一条则取方法停止时刻。",'',
      '|方法|共同计费s|新增面板尝试|极值调用|新增细化|实际全根计费s|完整进程墙钟s|SAFE/未决/未开始|峰值工作集最大MiB|',
      '|---|---:|---:|---:|---:|---:|---:|---|---:|']
    for arm in 'ABC':
        t=totals[arm];s=t['full_states']
        lines.append(f"|{arm}|{t['common_charged_s']:.3f}|{t['new_panels_common']}|{t['new_extremum_calls_common']}|{t['new_refinements_common']}|{t['full_method_charged_s']:.3f}|{process[arm]:.3f}|{s['SAFE']}/{s['UNRESOLVED']}/{t['not_started_count']}|{t['peak_rss_max_bytes']/2**20:.2f}|")
    lines+=['','全进程/全根总耗时包含各臂实际完成的不同工作量，不能直接代替共同前缀节省。内存为被测子进程生命周期峰值，含其输入/记录/缓存，不含公共监督进程或整机合计；不是缓存独占。检查点累计逻辑字节也不是常驻内存。原面板计数是尝试次数，中断可能留下未提交尝试；共同SAFE前缀均完整提交。','',
      '|归档序列|共同/计划|A计费s|B计费s|C计费s|B较A|C较A|',
      '|---|---:|---:|---:|---:|---:|---:|']
    for r in runs:
        v=r['arms'];lines.append(f"|{r['call']}|{r['common_SAFE_prefix']}/{r['planned']}|{v['A']['common_charged_s']:.3f}|{v['B']['common_charged_s']:.3f}|{v['C']['common_charged_s']:.3f}|{100*r['saving_vs_A']['B']:.2f}%|{100*r['saving_vs_A']['C']:.2f}%|")
    lines+=['','## 3. 运算与维护成本','',
      '|方法|整场景命中/覆盖面板|前缀命中/覆盖面板|身份核对s|场景查询/保存/恢复s|前缀查询/保存/恢复s|回执检查＋提交s|',
      '|---|---|---|---:|---|---|---:|']
    for arm in 'ABC':
        t=totals[arm];m=t['cache_common'];fmt=lambda keys:'/'.join(f"{m.get(k,0):.3f}" for k in keys)
        lines.append(f"|{arm}|{m['scene_hits']}/{m['avoided_scene_panels']}|{m['prefix_hits']}/{m['avoided_prefix_panels']}|{m['identity_s']:.3f}|{fmt(['query_s','save_s','restore_s'])}|{fmt(['prefix_query_s','prefix_save_s','prefix_restore_s'])}|{t['validation_commit_common_s']:.3f}|")
    lines+=['','每个配对均核对“新增面板＋复用覆盖＝A面板”，四节点对应8次连续峰谷调用。回执检查＋提交含历史证据精确回归核对，也含部分缓存保存，不能与缓存成本再相加。所有核对均对三臂采用同一口径。源码未对子核Taylor/峰谷/积分分别计时，因此不再把总耗时归因于某个子核。','',
      '## 4. 正确性、负结果及边界','',
      '修正版43项前置检查通过（15场景、15前缀、13根停止）。v1在非墙钟上限未决后可能借缓存形成新回执，数值包络仍正确但根停止语义不合格；先暂停结论，在第7组三臂后停止，保留21条旧回放及一次输入读取前控制阻断。独立测试复现后修复，原48条在统一v2上完整重启一次，旧数据不混入性能结论。额外21条诊断消耗及全部反例见CORRECTION.md。首次场景测试的panel_limit层级断言错误也保留，未修改冻结评价器。','',
      '正式回放逐候选核对完整合法性、历史SAFE全部数值字段和严格能量接纳顺序；分析再核对跨臂语义、来源先后、新SAFE形成时刻及覆盖计数。原JSON档整体读入用于固定顺序和事后回归，数值后端每步仅收到当前候选；前缀基准只由此前完整接受结果产生，引用来源序号严格小于当前序号，不利用未来候选或回执作数值决策。v2未决后根关闭，旧完整SAFE仍可只读审计，违规见证仍保留。','',
      '原10个历史预算未决全部保留标签。纯回放省去了原搜索构造，旧未决可在本轮完成，不能回填历史成功率。相同功率但事件切分不同不复用前缀；零命中序列、任何计时负收益和超时均保留。单次轮换不产生统计显著性；4根同族、16序列互相关联，855候选不是855个独立样本。准入与正式首条A计时不同，也说明背景运行波动存在。','',
      '检查点仅保存已完整提交的内部区间状态，原函数五处受检查插入形成独立封装；完整物理输入验证、窗口精度与守恒仍重做。原接口没有独立保存谷温时刻见证，保留其原连续谷温包络，不伪造不存在的见证。单线程进程内缓存；不支持跨根持久复用或并发共享模块。SHA用于身份与意外损坏检测，不声称抵御能同时篡改数据/摘要的恶意进程。','',
      '## 5. 复现与完整记录','',
      '[冻结协议](PROTOCOL.md)、[准入与实现](ADMISSION.md)、[修正与重启](CORRECTION.md)、[语义论证](SEMANTICS.md)、[复现命令](README.md)、[来源清单](source_manifest.json)、[正式逐序列汇总](formal_v2/analysis.json)、[机器可读结论](results/summary.json)。原始receipts.jsonl保留计时、来源、完整能量及热峰谷包络，trace/合法性正文以精确摘要压缩；不可用于从输出轨迹续算。全部冻结来源可按清单独立重算。','',
      'Material Passport：ICR20261115；执行与只读验证；来源=两个固定提交；方法=确定性同路径回放；Verification Status=VERIFIED（限定本批）；无新调度搜索、MILP、参数扫描或硬件平台标定。']
    (root/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main(Path(sys.argv[1]))
