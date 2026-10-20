"""K131 saved-record audit; no model build, schedule decode, heat or solve."""
from pathlib import Path
from fractions import Fraction as F
import csv, hashlib, importlib.util, json, sys

REPO=next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file() and (p/'RESEARCH_BRIEF.md').is_file())
ROOT=REPO/'research/chapter3_experiments/results/fixed_unit_pair02'
PREVIOUS=REPO/'research/chapter3_experiments/results/night_k127_run02/analysis01/analysis_script.py'
spec=importlib.util.spec_from_file_location('saved_k127_audit',PREVIOUS)
a=importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
read=a.read
def save(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False,default=str)+'\n',encoding='utf-8')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def components(r,instance):
    receipt=r['aggregation']; result={}
    for s in instance['scenarios']:
        for name,v in receipt['scenes'][s['id']]['result']['energy_components_J'].items():
            iv=a.interval(v); row=result.setdefault(name,[F(0),F(0)])
            for k in range(2): row[k]+=F(s['weight'])*iv[k]
    return {name:[str(v) for v in values] for name,values in result.items()}
def check_units_and_changes(r):
    seed=r['condition']['seed_candidate']; final=r['safe_candidate']; rows=[]
    for sid,values in final['scenes'].items():
        old={x['stage_id']:x for x in seed['scenes'][sid]}
        for x in values:
            y=old[x['stage_id']]
            assert x['unit']==y['unit'],'unit escaped declared subdomain'
            rows.append({'scene':sid,'stage_id':x['stage_id'],'unit':x['unit'],
                'seed_opp':y['opp'],'final_opp':x['opp'],'seed_start_ms':y['start_ms'],
                'final_start_ms':x['start_ms'],'changed':x!=y})
    return rows
def main():
    ledger=read(ROOT/'ledger.json'); declaration=read(ROOT/'declaration.json')
    assert read(ROOT/'phase_context.json')['execution_context']=='approved_host'
    assert ledger['state']=='BLOCKED' and ledger['consumed']==2
    assert len(ledger['calls'])==2
    assert [x['state'] for x in ledger['calls']]==['COMPLETED','TECHNICAL_BLOCK']
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'analysis01')
    out=parser.parse_args().out.resolve(); out.mkdir(exist_ok=False)
    source={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*')
            if p.is_file() and 'source_snapshot' not in p.parts and not any(x.startswith('analysis') for x in p.parts)
            and p.suffix in ('.json','.jsonl','.txt','.log')}
    jobs=[]; raw={}; allchanges=[]
    for row in ledger['calls']:
        jid=row['id']; result=read(ROOT/jid/'result.json'); raw[jid]=result
        job={'id':jid,'method':'n1','condition':'base'}
        adapted={'input_identities':{'base':{'instance_sha256':declaration['input_sha256']}}}
        report=a.analyze_job(ROOT,job,row,adapted)
        assert report['final_SAFE_receipt_verified'] and not report['stored_receipt_errors'],report['stored_receipt_errors']
        report['job']={'id':jid,'method':row['method'],'condition':'base'}
        report['condition_sha256']=report.pop('N1_condition_sha256')
        report['scope_note']='Seed-fixed devices; old opens local suffix, new opens every Stage OPP/start. Scene solver bounds not global.'
        report['method_completed_without_technical_block']=row['state']=='COMPLETED'
        for b in report['solver_reported_bounds']:
            b['scope']=result['scenes'][b['scene']]['solver_bound_scope'] if 'solver_bound_scope' in result['scenes'][b['scene']] else ('old_N1_single_scene_conditional' if jid=='old_n1' else 'fixed_units_all_stage_OPP_start_single_scene_conditional')
        instance=read(ROOT/jid/'input_instance.json')
        report['components_J']=components(result,instance)
        report['seed_candidate_sha256']=a.digest(result['condition']['seed_candidate'])
        report['scope_protocol']=result['condition']['protocol']
        report['scene_model_summaries']={sid:{k:v for k,v in scene.items() if k in ('model_summary','model','build_summary','state','reason','solver_bound_scope')} for sid,scene in result['scenes'].items()}
        report['distinct_saved_full_SAFE_candidates']=len({a.digest(c) for c,r,_ in a.full_evaluations(result,'n1') if r.get('state')=='SAFE'})
        report['scene_search_metrics']={sid:{
            'search_started_at_s':scene.get('search_started_at_s'),
            'search_returned_at_s':scene.get('search_returned_at_s'),
            'model_view_evaluation_records':len(scene.get('model_view_evaluations',[])),
            'original_input_evaluation_records':len(scene.get('original_scene_evaluations',[])),
            'original_receipt_cache_hits':scene.get('original_receipt_cache_hits'),
            'native_outputs':[{'status':q.get('status'),'exitflag':q.get('exitflag'),
                'budget_valid':q.get('budget_valid'),'numnodes':q.get('output',{}).get('numnodes'),
                'numfeaspoints':q.get('output',{}).get('numfeaspoints')}
                for q in (scene.get('solver_result') or {}).get('rounds',[])]}
            for sid,scene in result['scenes'].items()}
        jobs.append(report)
        allchanges.extend(dict(job=jid,**x) for x in check_units_and_changes(result))
    old,new=jobs
    elo,ehi=a.interval(old['final_energy_J']); nlo,nhi=a.interval(new['final_energy_J'])
    sames=old['seed_candidate_sha256']==new['seed_candidate_sha256'] and old['initial_energy_J']==new['initial_energy_J']
    # Static posthoc scope membership only; never inject the old witness into
    # the independently completed new method invocation or recompute its heat.
    old_in_new=False
    if sames:
        old_in_new=all(row['stage_id'] in raw['all_opp_start']['condition']['opened_by_scene'][sid]
            and row['unit']==next(x['unit'] for x in raw['all_opp_start']['condition']['seed_candidate']['scenes'][sid]
                if x['stage_id']==row['stage_id'])
            for sid,rows in raw['old_n1']['safe_candidate']['scenes'].items() for row in rows)
    historical=ROOT.parent/'night_k127_run02/base_heft/result.json'; hr=read(historical)
    hi=read(historical.parent/'input_instance.json')
    hv=a.full_safe(hr['evaluation'],hr['safe_candidate'],hi,hr['timing']['limit_s'],'heft',hr)
    assert a.digest(hi)==declaration['input_sha256']
    assert raw['all_opp_start']['reason']=='SOLVER_NUMERICAL_CONSISTENCY_UNRESOLVED'
    assert raw['all_opp_start']['safe_candidate']==raw['all_opp_start']['condition']['seed_candidate']
    assert not new['strict_improvement_over_this_call_seed']
    comparison={'identical_fresh_seed_candidate_and_energy':sames,
        'quality_pair_completed':False,'performance_ranking_valid':False,
        'strict_new_improvement_over_old_observed':nhi<elo,
        'technical_stop_not_normal_no_improvement':True,
        'new_result_is_verified_seed_only':True,
        'old_interval_J':old['final_energy_J'],'new_interval_J':new['final_energy_J'],
        'HEFT_historical_only':{'result_sha256':sha(historical),'energy_J':[str(v) for v in hv],
            'old_signed_relative_gap':str((ehi-hv[1])/hv[1]),'new_signed_relative_gap':str((nhi-hv[1])/hv[1])},
        'same_input_and_physics':True,'no_independent_global_optimality':True,
        'stage':'K131','old_safe_candidate_within_new_fixed_unit_scope_static':old_in_new,
        'new_research_calls':2,'method_elapsed_s':sum(j['timing']['method_elapsed_s'] for j in jobs),
        'wrapper_elapsed_s':sum(j['ledger']['wrapper_wall_s'] for j in jobs),
        'cleanup_elapsed_s':sum(j['ledger']['cleanup']['cleanup_wall_seconds'] for j in jobs),
        'posthoc_physical_work_or_search':False}
    frozen_ok=all(sha(ROOT/'source_snapshot'/name)==h and sha(REPO/name)==h
                  for name,h in declaration['source_sha256'].items())
    assert frozen_ok
    facts={'protocol':declaration['protocol'],'verification_scope':'stored-receipt consistency; no posthoc thermal replay/search',
        'reused_audit_source':{'path':PREVIOUS.relative_to(REPO).as_posix(),'sha256':sha(PREVIOUS)},
        'calls':jobs,'comparison':comparison,'changes':allchanges,'raw_hashes_before':source,
        'frozen_current_and_snapshot_135_sources_match':frozen_ok,
        'numerical_consistency':raw['all_opp_start']['scenes']['AB_offset_0ms']['solver_result']['numerical_consistency']}
    for rel,h in source.items(): assert sha(ROOT/rel)==h,'raw changed: '+rel
    facts['raw_unchanged']=True
    save(out/'facts.json',facts)
    with (out/'comparison.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=['job','ledger_state','U_J','first_SAFE_s','method_s','feedback','strict_vs_seed']); w.writeheader()
        for j in jobs: w.writerow(dict(job=j['job']['id'],U_J=j['final_U_J'],first_SAFE_s=j['first_SAFE_s'],
            ledger_state=j['ledger']['state'],method_s=j['timing']['method_elapsed_s'],feedback=j['feedback_records'],strict_vs_seed=j['strict_improvement_over_this_call_seed']))
    with (out/'stage_changes.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(allchanges[0])); w.writeheader(); w.writerows(allchanges)
    with (out/'phase_costs.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=['job','phase','exclusive_s']);w.writeheader()
        for j in jobs:
            for phase,value in j['timing'].get('phases_exclusive_s',{}).items():
                w.writerow({'job':j['job']['id'],'phase':phase,'exclusive_s':value})
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(8,4.5))
    colors=['#2864a0','#d87b20']
    for color,j in zip(colors,jobs):
        points=j['updates']; xs=[p['at_s'] for p in points]; ys=[float(F(p['energy_J'][1])) for p in points]
        if points: ax.step(xs+[j['timing']['method_elapsed_s']],ys+[ys[-1]],where='post',label=j['job']['id']+(' SAFE seed; technical stop' if j['technical_state']=='FAILED' else ' SAFE U'),color=color)
        l=j['L0_gap'];
        if l: ax.hlines(float(F(l['L0_J'])),0,j['timing']['method_elapsed_s'],color=color,linestyle=':',alpha=.5)
    ax.axhline(float(hv[1]),color='gray',linestyle='--',label='K127 HEFT historical U (quality only)')
    ax.set(xlabel='Billed method elapsed time (s)',ylabel='Weighted system energy (J)')
    ax.grid(alpha=.2); ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(out/'energy_bounds.png',dpi=180); plt.close(fig)
    lines=['# K131：旧N1完成，新版因数值接纳与原生无解退出冲突停止','',
        '材料类型：已终止配对调用的只读存档审计。范围：原base__R1、两次独立调用、每次300秒上限；不重算热、不补求解。','',
        '| 方法 | 技术状态 | 完整安全U/J | 首SAFE/s | 方法耗时/s | 对自身种子严格改善 |',
        '|---|---|---:|---:|---:|---|']
    for j in jobs: lines.append(f"| {j['job']['id']} | {j['ledger']['state']} | {float(F(j['final_U_J'])):.12f} | {j['first_SAFE_s']:.3f} | {j['timing']['method_elapsed_s']:.3f} | {j['strict_improvement_over_this_call_seed']} |")
    lines += ['',f"**质量配对未正常完成，不能据此给新版作性能排名。** 新版只保留完整SAFE种子，未观察到比旧N1更低的安全输出；不把技术停止写成正常搜索无改善。两次新种子候选与能量区间逐字相同：{sames}。",'',
        '新版AB显式8525维x0已通过Python数值接纳，最大不等式残差约2.13e-14；worker确认收到。原生求解却以exitflag=-2返回空x／fval，未给内部界。接纳与退出状态冲突，不能当真实无解、内部界越过U或已证求解器缺陷。AC模型完成但未进入搜索；没有重启或改参。',
        f"K127 HEFT历史安全U={float(hv[1]):.12f} J，仍只作质量背景，不作本轮同期或完整配对排名。",'',
        '全部安全输出经预算内原输入完整窗口／连续热复核；存档能量分项、权重、守恒、峰温上端、范围、候选／回执身份及时间核对通过。全部unit保持本次种子；OPP／起点实际变化见stage_changes.csv。',
        '两调用的全域L0仍未闭合。单场景局部内部界／收敛不提升为全域证明；无独立最优或无解结论。没有新增热条件或补跑。',
        '',f"两次已消费，方法总耗时{comparison['method_elapsed_s']:.3f}秒；包装{comparison['wrapper_elapsed_s']:.3f}秒，清理合{comparison['cleanup_elapsed_s']:.3f}秒。两轮均graceful_closed，全部已观察身份退出；上次I/O／清理故障未再现。135项当前源与快照一致。",
        '', '补充[数值尺度只读审查](../numerical_scope_audit/summary.md)：新版AB最大同行系数比约4.80×10⁹，旧AB约1.20×10⁹；尚未证明它导致此次退出，具体行族待定位，未据此改系数或容差。',
        '', '图：[安全U与独立L0](energy_bounds.png)。详细事实、原档案SHA、分项与内部界见facts.json；比较表见comparison.csv。']
    (out/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'analysis_script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(comparison,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
