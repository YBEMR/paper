"""Render the Chinese development report from audited tables and primary evidence."""
import csv,ast
from shared import HERE,RUN,DATA,read
from run import logs
R=HERE/'results'
def tab(f):return list(csv.DictReader((R/(f+'.csv')).open()))
def fmt(x,d=6):return f'{float(x):.{d}f}'
def draw():
    endpoints=tab('endpoints');modes=tab('stage_counts');rev=tab('reversals');bud=tab('budget')
    cases=['D1','D2','C10'];arms=['A','B','C','D'] if read(RUN/'gate.json')['open'] else []
    best={(r['case'],r['arm']):r for r in endpoints}
    lines=['# E3-a 高质量 SAFE 排程的执行区间联合重构诊断','',
           '**保留普通参考能耗驱动的局部联合重构，第三章的主动电热选区贡献仍缺少证据。** 只有 C10 上的 C 同时优于 A、B。C 将历史强初解降低 5.1877 mJ（0.008805%），较普通 VNS 再降低 2.8165 mJ。D 在 D1、D2 与 C 返回同一排程，在 C10 比 C 多耗 0.192 µJ。C10 的收益集中在约 5 s 处的短区间，当前证据支持将该操作作为局部后处理候选，其跨工况收益仍待验证。','', '## 开发结果','',
           '表中单位为 J。第二阶段各方法从同一历史初解开始，固定种子 101，列出预算内返回的最佳完整 SAFE 排程。','',
           '| 工况 | 历史强初解 | 第一阶段最佳 |' + ''.join(' '+a+' |' for a in arms),
           '|---|---:|---:|'+''.join('---:|' for a in arms)]
    for c in cases:
        q=best[c,'diagnostic'];lines.append('| '+' | '.join([c,fmt(q['baseline_J'],9),fmt(q['SAFE_J'],9)]+[fmt(best[c,a]['SAFE_J'],9) for a in arms])+' |')
    lines+=['','## 强初解及接口','',
            'D1、D2 各 160 个请求。两者在第三章正式归档的最低完整 SAFE 能耗分别为 9.179860893 J、9.215413581 J。第四章 Windows 26200 交叉验证归档保存了更低的 D 臂排程，分别来自种子 103、101。C10 为 HHHHLLHHLLLL、960 请求，选用 M1-i 的 ZQ-Beam 排程。M1-j 和 M3-a 的 C10 最低完整记录分别为 59.531471812 J、59.324561747 J。归档证书筛选覆盖面见 inputs/historical_certificates.csv.gz，早期结果表另见 inputs/prior_tables.json。','',
            '逐字节核对三个输入。两个版本的 model.py、heat.py、P1 四节点参数及 CPU/NPU、GPU 画像相同；profiles.py 的 NT 版本保留了请求生成入口，三个实际输入逐字节相同。两个入口重放原始 rows 与 low 后，31 列事件数组相同。与原 Windows 归档相比，D1、D2 的事件前 14 列完全相同，全数组逐元素最大绝对差均为 7.11×10⁻¹⁵；C10 与 M1-i 归档数组的 SHA-256 完全相同。','',
            'D1、D2 的 FIFO 重建均复现原排程。C10 的全部阶段起点可以复现，但默认 idle_plan 改变了空闲标志与切换轨迹，重建能耗为 58.918771463 J。三个工况都从历史原始排程开始。本轮联合求解使用第三章 E2-a 逐阶段接口，可在选区内开放 CPU 前后处理、设备映射、频率和起点。C10 第一阶段最佳排程比默认空闲控制重建结果也低 3.567 mJ。','',
            '## 第一阶段','',
            '固定启动时刻的单配置枚举覆盖每个选区锚点的全部阶段及其合法设备、频档，包括升频和降频。时序冲突记录冻结验证器的第一条拒绝原因。固定映射与联合重构从同一原解独立求解。以下每格依次给出实际尝试次数、去重且不同于原解的完整 SAFE 候选数、严格优于历史原解的去重候选数。','',
            '| 工况 | 单配置 | 固定映射，开放频率与时序 | 开放映射、频率与时序 | 最佳节能率 |','|---|---:|---:|---:|---:|']
    for c in cases:
        sr={r['mode']:r for r in modes if r['case']==c and r['arm']=='diagnostic'}
        def counts(k):
            r=sr[k];return '/'.join(r[x] for x in ('attempts','nonseed_SAFE_unique','strictly_better_unique'))
        lines.append('| '+' | '.join([c]+[counts(k) for k in ['single','fixed','joint']]+[fmt(best[c,'diagnostic']['saving_pct'],6)+'%'])+' |')
    lines+=['','窗口宽 100 ms，步长 50 ms。D1、D2 各选出六个窗口条目，C10 八个。D1、D2 在初解上没有非最低档的空闲驻留，因而这一类没有选区。其他指标均取自原始事件。每个区域的逐档驻留及紧期限请求的实际依赖、资源阻塞链见 results/seed_window_audit.json。不同指标允许选中相同窗口。','']
    mech=read(R/'mechanisms.json')
    for c in cases:
        if c+'_gain' not in mech:continue
        g=mech[c+'_gain'];w=g['winner'];reg=g['region'];d=g['energy_delta_J']
        lines += [f"**{c} 的第一阶段最佳案例**取自 {reg['start']/10:g}–{reg['end']/10:g} ms 的 {'非最低档空闲驻留' if reg['kind']=='high_idle' else reg['kind']}区域。完整能耗减少 {-1000*d['J']:.4f} mJ。活动、驻留、切换和温度修正的变化依次为 {1000*d['activity']:+.4f}、{1000*d['base']:+.4f}、{1000*d['switch']:+.4f}、{1000*d['temperature']:+.4f} mJ；公共能耗变化 {1000*d['external']:+.4f} mJ。{w['config_changes']} 个阶段改变设备或频档，{w['start_changes']} 个阶段改变起点，峰温上界 {80-w['margin_C']:.6f}°C，最小期限余量 {w['slack_ms']:.3f} ms。",'']
        for z in g['stage_changes']:
            if z['stage']=='main' and z['old'][:2]!=z['new'][:2]:
                desc=lambda v: ('CPU1','CPU2','GPU','NPU')[v[0]]+f" 档 {v[1]}"
                lines+= [f"- 请求 {z['request']} 的主阶段从 {desc(z['old'])} 改至 {desc(z['new'])}，开始时刻从 {z['old'][2]/10:g} 改至 {z['new'][2]/10:g} ms。"]
        lines+=['']
    lines+=['## 参考能耗排序反转','',
            '逐工况对同一初解产生的不同 SAFE 物理解两两比较。参考能耗使用精确有理数，真实能耗要求证书区间严格分离。相同参考能耗单列为平局。','',
            '| 工况 | 第一阶段不同 SAFE 解（含初解） | 全池反转对 | 同一第二阶段公共探针池反转对 |','|---|---:|---:|---:|']
    for c in cases:
        vals={r['pool']:r for r in rev if r['case']==c}
        x=vals['all_phase1'];lines.append(f"| {c} | {x['unique_SAFE']} | {x['reversals']} | {vals['common_probes']['reversals']} |")
    for c in cases:
        key=c+'_all_phase1_reversal'
        if key in mech:
            r=mech[key];a,b=r['reference_preferred'],r['thermal_preferred']
            lines+=['',f"{c} 全池差异最大的反转中，参考排序选出的解为 {a['plan'][:12]}，E35 为 {a['E35']:.9f} J，真实能耗为 {a['J']:.9f} J；另一解 {b['plan'][:12]} 分别为 {b['E35']:.9f} J 和 {b['J']:.9f} J。后者多用 {1e6*r['reference_difference_J']:.3f} µJ 参考能耗，却少用 {1e3*r['thermal_difference_J']:.6f} mJ 完整能耗。两解对应的探针、证书、参考项和温度修正见 results/mechanisms.json。"]
    if arms:
        lines+=['','## 同核对照与归因','',
                'A 用 G2 的原 targets 和关键区间反馈确定请求，投影到同规模 E2-a 区域。B 为普通 VNS 机制适配，按随机锚点与时间邻近选区。C、D 在预算内分别完整重放相同的已登记探针，分别按 E35 和完整 SAFE 能耗给区域排序。四组均可接纳探针改善，随后共用单线程 E2-a、2/3/4 请求规模循环、完整认证和接纳规则。A 的原实现还包含大范围 FIFO 搜索，这里的 A 指其选区机制在共同求解器下的表现。','',
                '| 工况 | A 节能率 | B 节能率 | C 节能率 | D 节能率 | C 相对 A / B 节能（mJ） | D 相对 C 节能（mJ） |','|---|---:|---:|---:|---:|---:|---:|']
        for c in cases:
            vals={a:float(best[c,a]['SAFE_J']) for a in arms}
            lines.append('| '+' | '.join([c]+[fmt(best[c,a]['saving_pct'],6)+'%' for a in arms]+[f"{1000*(vals['A']-vals['C']):+.4f} / {1000*(vals['B']-vals['C']):+.4f}",f"{1000*(vals['C']-vals['D']):+.4f}"])+' |')
        lines+=['','C、D 的区域优先序及实际调用次序见 results/probe_rankings.csv。三个工况的公共探针排序差异还需对照证书精度解释。D1 改变次序的两对和 C10 的三对具有相同的精确参考能耗，完整能耗中点之差分别至多 1.78×10⁻¹⁵ J 和 4.26×10⁻¹⁴ J，全部落在证书重叠范围内。D2 的一对同参考能耗探针可由完整能耗可靠区分，差为 11.72 µJ。详见 [探针优先序审计](results/probe_priority_audit.json)。模型内部可行解不另计为返回的候选。限时返回 FEASIBLE 只保证该候选可行，真实能耗以外部连续认证为准。']
    lines+=['','## 研究决策','',
            'D1 的 B 将请求 156 的前处理换到另一 CPU 核，并微调请求 156、158 的起点。参考能耗不变，完整能耗减少 14.906 nJ，证书给出的节能区间为 8.748–21.063 nJ。D2 四个方法返回同一历史排程。C10 的 C、D 终点具有相同的精确参考能耗，D 多出的 0.192 µJ 来自温度修正，两证书给出的差值区间为 0.155–0.228 µJ。逐对判定见 [对照差值及证书区间](results/contrasts.csv)。','',
            '第一阶段的 C10 全池出现 22 对严格反转，最终用于选区的公共探针池出现 0 对。参考排序反转证明完整电热计能会改变候选优劣，但在当前探针规则下，电热引导没有提高最佳排程质量。保留 P1 连续认证及统一局部求解器；普通方法已取得本轮全部主要节能收益，主动热感知的后续探索应优先考虑探针足以可靠区分、且差异能够改变终点能耗的区域。','',
            '## 预算与可复核材料','',
            f"按单元计时回执及预检预留核算，预检 {float(bud[0]['charged_s']):.2f} 核秒（含 60 秒历史盘点预留），第一阶段 {sum(float(r['charged_s']) for r in bud if r['arm']=='diagnostic'):.2f} 核秒，第二阶段 {sum(float(r['charged_s']) for r in bud if r['arm'] in arms):.2f} 核秒，合计 {sum(float(r['charged_s']) for r in bud):.2f} / 6000 核秒。最长单次局部建模与求解 {max(float(r.get('max_local_s') or 0) for r in bud):.3f} 秒。并发工况使用不同逻辑核；同一单元的局部建模、求解与认证串行执行。原始回执含进程 CPU 和墙钟。工作区准备、离线清点和证据压缩独立于搜索。",'',
            '输入与历史原件在 inputs，全部返回候选、逐事件轨迹和证书在 archive，读取方法见 [复核说明](REPLAY.md)。[端点](results/endpoints.csv) · [逐权限统计](results/stage_counts.csv) · [能耗分解](results/energy.csv) · [计时回执](results/budget.csv) · [真实反转](results/reversals.csv) · [机制案例](results/mechanisms.json)','',
            'C/D 共用的优先序探针是预登记的每区首个有效单配置替代（缺失时取固定映射替代）。这一小池的辨识能力与第一阶段全候选池不同。本轮只评价三个开发工况和种子 101。F1、F2、C11、C12 保持封存。']
    (HERE/'REPORT.md').write_text('\n'.join(lines).replace('；','。')+'\n')
if __name__=='__main__':draw()
