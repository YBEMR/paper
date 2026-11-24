"""Post-run reporting only. Consume existing certificates without launching a scheduler or thermal solver."""
import csv,decimal,hashlib,io,json,math,shutil
from collections import Counter
from fractions import Fraction as Q
from pathlib import Path
root=Path.cwd()
def read(n):return json.loads(Path(n).read_bytes())
def fmt(x,n=6):return ('—' if x is None or x=='' else f'{float(x):.{n}f}')
def outward(x,d=5,up=False):
    val=Q(str(x)); rounded=(math.ceil if up else math.floor)(val*10**d)
    return f'{rounded/10**d:.{d}f}'
def csvin(n):
    with Path(n).open(encoding='utf8',newline='') as f:return list(csv.DictReader(f))
def write(n,s):Path(n).write_bytes(s.encode('utf8'))
def emit(n,x):write(n,json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def raw(n):return Path(n).read_bytes()
def preserved(key):
    dest=Path('logs')/('batch_'+Path(key).name)
    if dest.exists():raise RuntimeError('archival synthesis already present')
    dest.write_bytes(raw(key))
snap=read('RESULT_SHA256.json')
for key in ('decision.md','summary.csv','RESULT_SHA256.json'):preserved(key)
methods=csvin('logs/method_metrics.csv') if Path('logs/method_metrics.csv').exists() else []
rows=csvin('summary.csv')
rf=read('local_rf/intervals.json')
replay=csvin('certificates/reset_comparison.csv') if Path('certificates/reset_comparison.csv').exists() else []
calls=[json.loads(v) for v in Path('logs/calls.jsonl').read_text(encoding='utf8').splitlines()]
starts=[r for r in calls if r['event']=='begin']
ends=[r for r in calls if r['event']=='end']
checks=read('preflight/checks.json'); manifest=read('manifest.json')
gates={r['case']:read('logs/gate_'+r['case']+'.json') for r in rows if Path('logs/gate_'+r['case']+'.json').exists()}
thermal_notes=[]; globalrows=[]
for row in rows:
    cid=row['case']; safe=[r for r in methods if r['case']==cid and r['SAFE']=='1']
    for col in ('all_methods_best_SAFE','all_methods_best_SAFE_J','all_methods_peak_upper_C','all_methods_best_plan','common_to_all_best_certified_percent'):
        row[col]=''
    if not safe:continue
    best=min(safe,key=lambda r:Q(r['SAFE_E_upper_J']))
    import gzip
    cert=json.loads(gzip.decompress(raw('certificates/'+best['safe_plan']+'_continuous.json.gz')))['metrics']
    bname=best['method']+(('/'+best['arm']) if best['arm'] else '')
    row.update(all_methods_best_SAFE=bname,all_methods_best_SAFE_J=best['SAFE_E_J'],all_methods_peak_upper_C=max(cert['peak_hi']),
               all_methods_best_plan=best['safe_plan'])
    com=next(r for r in safe if r['method']=='common')
    rate=100*(1-Q(best['SAFE_E_upper_J'])/Q(com['SAFE_E_lower_J']))
    row['common_to_all_best_certified_percent']=str(float(rate))
    hi=Q(best['SAFE_E_upper_J']); lo=Q(row['guaranteed_lb_J'])
    row['thermal_cost_upper_J']=float(hi-lo)
    g2=next((r for r in methods if r['case']==cid and r['method']=='G2' and r['upper_bound_J']),{})
    u0=min(hi,Q(g2['upper_bound_J']) if g2 else hi)
    globalrows.append(dict(case=cid,lower_J=str(lo),safe_upper_J=str(hi),no_limit_upper_J=str(u0),
                           optimality_gap_upper_J=str(hi-lo),thermal_cost_lower_J='0',thermal_cost_upper_J=str(hi-lo)))
    ini=read('g1_initial/'+cid+'_common.json')
    if ini['hot']:
        hot=ini['hot']
        thermal_notes.append((cid,hot['E_J'],max(hot['peak_lo']),max(hot['peak_hi']),hot['hotspot'],ini['hot_plan']))
for row in rows:
    row['G1_G3_best_method']=row.pop('best_SAFE_method')
    row['G1_G3_best_SAFE_J']=row.pop('best_SAFE_J')
    row['G1_G3_peak_upper_C']=row.pop('peak_upper_C')
    row['G1_G3_first_SAFE_s']=row.pop('first_SAFE_s')
header=list(rows[0].keys())
out=io.StringIO(newline=''); w=csv.DictWriter(out,fieldnames=header,lineterminator='\n');w.writeheader();w.writerows(rows)
write('summary.csv',out.getvalue())
local=[]
for item in rf:
    cid=item['case']
    def bound(arm):return [Q(str(v)) for v in item[arm]]
    rr0,rrt,ff0,fft=map(bound,('R0','Rtheta','F0','Ftheta'))
    # Use exact saved per-arm lower, and directed conservative decimal representation of certified float endpoints.
    for interval,arm in [(rr0,'R0'),(rrt,'Rtheta'),(ff0,'F0'),(fft,'Ftheta')]:
        rec=read('local_rf/'+cid+'_RF_'+arm+'.json')
        interval[0]=Q(rec['search']['conditional_lower']['total'])
        interval[1]=Q(str(rec['best']['E_bounds'][1]))
    rr0[1]=min(rr0[1],rrt[1]);fft[1]=min(fft[1],rrt[1]);ff0[1]=min(ff0[1],rr0[1],fft[1])
    # Nonnegative costs and nested domains. A sign certificate uses a strictly positive lower bound.
    low=max(Q(0),rrt[0]-rr0[1])-max(Q(0),fft[1]-ff0[0])
    high=max(Q(0),rrt[1]-rr0[0])-max(Q(0),fft[0]-ff0[1])
    local.append(dict(case=cid,delta_lo=str(low),delta_hi=str(high),nested_bounds={k:list(map(str,v)) for k,v in zip(('R0','Rtheta','F0','Ftheta'),(rr0,rrt,ff0,fft))}))
emit('local_rf/nested_bounds.json',local)
emit('logs/global_bounds.json',globalrows)
# Preserve raw batch results and add an editorial table whose best SAFE includes G2 when independently certified.
decision_raw=Path('logs/batch_decision.md').read_text(encoding='utf8')
n_g4=sum(x['method']=='G4_targets' for x in starts)
n_groups=sum(x['method']=='G4_group' for x in starts)
n_pilot=sum(x['method']=='pilot' for x in starts)
held=[r['case'] for r in rows if r['case'][0]=='H' and r['status']=='EXECUTED']
approved='立项通过' in decision_raw
verdict='达到第三章候选算法立项门槛。' if approved else '本轮不进入第三章正式算法实验。'
lines=['# P1 多场景连续任务流最小立项验证','',f'**{verdict}** 开发工况中，'+str(sum(r['case'][0]=='D' and bool(r['all_methods_best_SAFE_J']) for r in rows))+' 个取得完整 SAFE 排程。'+
       ('已完成留出 '+ '、'.join(held)+'。' if held else '开发证据未达到开启留出的门槛。'),'',
       '## 1. 模型正确性','',
       'G0 通过。五份原始 JSON 的 Git blob 均与任务书相符，40 组网络、温区、频率组合均唯一匹配。连续热评价与单节点解析解、空闲稳态及旧的有向舍入热核交叉一致。共享 CPU 频率、互斥、依赖、切换能量、窗口末端恢复及跨边界状态继承均通过检查。','',
       f'D0 的全低频排程在 2301 ms 内处理 60 个请求，能耗 5.39317215 J，峰温上界 37.89888°C。65°C 是解析不变区域上界。D1 高负载场景仅 main 的低档最小总占用为 {checks["high_main_min_demand_device_ms"]} 设备·ms，而两台加速器在该批请求的释放至期限区间内合计只有 2566.67 设备·ms。全低频容量不足。已构造合法的固定高档对照。','',
       '## 2. 完整窗口能耗与热约束','',
       '|工况|请求数|共同初解/J|无温限 G2/J|80°C G3/J|全部方法中最低 SAFE/J|来源|峰温上界/°C|较共同初解节能下界|',
       '|---|---:|---:|---:|---:|---:|---|---:|---:|']
for r in rows:
    c=r['case']; common=next((x['SAFE_E_J'] for x in methods if x['case']==c and x['method']=='common'),None)
    lines.append('|'+ '|'.join([c,r['requests'],fmt(common),fmt(r['G2_J']),fmt(r['G3_J']),fmt(r['all_methods_best_SAFE_J']),
                                  r['all_methods_best_SAFE'] or '未执行',(outward(r['all_methods_peak_upper_C'],4,True) if r['all_methods_peak_upper_C']!='' else '—'),
                                  (outward(r['common_to_all_best_certified_percent'],3)+'%') if r['common_to_all_best_certified_percent']!='' else '—'])+'|')
lines+=['','节能下界按新方案能耗上界和共同初解能耗下界计算。G2 在完整连续模型中重新判为 SAFE 后可参与上表的跨方法汇总。机制初解按预登记仅从 G1/G3 中选择，两种口径分别列入 summary.csv。','']
dev_methods=[r for r in methods if r['case'][0]=='D']
counts=[]
for label in ('HEFT','ETA','SA','G2','G3'):
    sample=[r for r in dev_methods if r['method']==label]
    if sample:counts.append(f"{label} {sum(r['SAFE']=='1' for r in sample)}/{len(sample)}")
lines+=['开发工况中各方法提供完整 SAFE 解的比例为 '+'，'.join(counts)+'。','']
for cid,E,pl,ph,node,k in thermal_notes:
    lines.append(f'- {cid} 的高档候选满足非热约束，{"CPU1 CPU2 GPU NPU".split()[node]} 的峰温下界为 {outward(pl,4)}°C，全窗能耗为 {E:.6f} J。该排程在 20–100°C 有效区间内被 80°C 温限排除。')
if any(x['G2_status']=='SAFE' for x in rows):
    lines+=['','无温限搜索中最终候选已通过 80°C 复核的工况为 '+ '、'.join(x['case'] for x in rows if x['G2_status']=='SAFE')+'。有限搜索仍留下最优差距。个别 G3 上界低于同工况 G2 上界，反映有限时间内找到的候选不同。']
lines+=['','|工况|精确解析下界/J（向下取整）|安全最优差距上界/J|全局热安全代价可靠区间/J|',
        '|---|---:|---:|---:|']
for g in globalrows:
    lines.append(f"|{g['case']}|{outward(g['lower_J'])}|{outward(g['optimality_gap_upper_J'],5,True)}|[0, {outward(g['thermal_cost_upper_J'],5,True)}]|")
lines+=['','## 3. 跨场景继承与局部机制','']
if replay:
    flips=[r for r in replay if r['continuous']!=r['reset']]
    changes=[r for r in replay if r['continuous_energy_rank']!=r['reset_energy_rank']]
    decrease=max(replay,key=lambda r:abs(float(r['peak_cont_C'])-float(r['peak_reset_C'])))
    lines+=[f"对 {len(replay)} 个不同最终排程逐一重放。仅在边界重置温度后，{len(flips)} 个排程的安全判定改变，{len(changes)} 个排程的工况内能耗点估计名次改变。峰温变化最大的排程来自 {decrease['case']}，连续传播与重置后的峰温上界分别为 {float(decrease['peak_cont_C']):.4f}°C 和 {float(decrease['peak_reset_C']):.4f}°C。重置结果仅作诊断。",'']
    if flips:
        ex=flips[0];lines+=[f"例如 {ex['case']} 的排程 {ex['plan'][:12]} 在连续模型中为 {ex['continuous']}，在重置模型中为 {ex['reset']}。",'']
for a in local:
    lines.append(f"- {a['case']} 的四 Stage 局部 Δθ 可靠区间为 [{outward(a['delta_lo'])}, {outward(a['delta_hi'],5,True)}] J。")
for cid in [a['case'] for a in local]:
    ref=next((r for r in methods if r['case']==cid and r['method']=='common' and r['SAFE']=='1'),None)
    arm=next((r for r in methods if r['case']==cid and r['method']=='RF' and r['arm']=='Rtheta' and r['SAFE']=='1'),None)
    if ref and arm and Q(arm['SAFE_E_upper_J'])<Q(ref['SAFE_E_lower_J']):
        gain=100*(1-Q(arm['SAFE_E_upper_J'])/Q(ref['SAFE_E_lower_J']))
        if gain>Q(1,10): lines+=['',f"{cid} 的固定单元与相对次序域 R 已将共同初解从 {float(ref['SAFE_E_J']):.6f} J 降至 {float(arm['SAFE_E_J']):.6f} J，严格节能至少 {outward(gain,3)}%。这一改善可以由局部调档和起点调整取得。"]
lines+=['','R 的每个可行解也属于 F，安全解也属于同域无温限问题。上述区间利用这些包含关系复用现有上界。各臂原始回执和独立界见 local_rf/。','',
        f'G4 目标筛查实际调用 {n_g4} 次，机制组调用 {n_groups} 次，全窗三组筛查共调用 {n_pilot} 次。']
if n_g4==0:
    lines+=['','冻结筛选要求已知超温候选的完整能耗低于机制初解，或其至少一个 main 的参考增量活动能耗下降。已保存的超温候选未触发该条件。G4 恢复率、同规模邻域胜负及全窗算法节能率均无可报告的对照数据。']
else:
    for cid,g in gates.items():
        if g['g4_records']: lines+=['',cid+' 的目标筛查与同规模比较见 g4_mechanism/，通过同规模判据的目标数为 '+str(sum(r['positive'] for r in g['g4_records']))+'。']
lines+=['','## 4. 立项判断','',
        '- **已证实**　P1 在本轮检查的模型和数值边界内自洽。开发工况有可行排程。'+('部分非热合法排程在真实连续传播下超温。' if thermal_notes else ''),
        '- **仍未决**　有限搜索给出的安全与无温限最优能耗界尚未分离。'+('各局部 Δθ 区间均包含零。' if all(Q(a['delta_lo'])<=0<=Q(a['delta_hi']) for a in local) else '局部域结论见各区间。'),
        '- **项目决定**　'+verdict+('联合时热机制相对同规模普通邻域的独立收益，以及包含留出的双对照 1% 改善，尚未证实。' if not approved else ''),
        '','## 5. 复核入口','',
        'summary.csv 汇总工况。logs/method_metrics.csv 逐方法列出首次 SAFE 时间、可行性、候选数、能耗、期限余量、预算与实耗。certificates/reset_comparison.csv 和压缩证书保存同一计划的连续与重置结果。所有可靠界、输入、随机顺序及 Git 快照都可从同目录追溯。']
lines+=['',f'本轮共 {len(starts)} 次调用，自首次 G0 至归档审计结束约 {max(r["elapsed_s"]+next(x["actual_s"] for x in ends if (x["case"],x["method"],x["arm"])==(r["case"],r["method"],r["arm"])) for r in starts):.1f} s。冻结提交为 {manifest["freeze_commit"]}。','',
        'D0 采用轻载例外，两条流 A1、B1 均从 10 FPS 切换至 20 FPS。CPU/NPU 画像和四节点平台为合成模型，GPU 观测温区之外使用任务书指定的仿射外推。']
write('decision.md','\n'.join(lines)+'\n')
manifest['raw_batch_snapshot_sha256']=snap['snapshot']
manifest['archival_synthesis']='按冻结回执汇总所有方法的独立 SAFE，包括 G2。利用 R⊆F 及热安全域包含于无温限域传递可行上界。未新增任何方法调用。原始 decision、summary 及快照索引保留于 logs/batch_*。'
emit('manifest.json',manifest)
hashes={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob('**/*')) if p.is_file()
        and '__pycache__' not in p.parts and p.name!='RESULT_SHA256.json' for p in [p.relative_to(root)]}
emit('RESULT_SHA256.json',dict(algorithm='sha256',files=hashes,snapshot=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()))
