"""Independent saved-output checks. Does not search or regenerate joint evidence."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import csv
import json
import sys
import diagnostic as d
from precheck import rk4,midpoint


def postcheck(folder,out):
    folder=Path(folder); out=Path(out); out.mkdir(parents=True,exist_ok=False)
    checks=[]; numerics={}
    def check(name,ok): checks.append(dict(name=name,pass_=bool(ok)))
    x=d.load(); sources=d.read(folder/'sources.json'); locals_=d.read(folder/'locals.json')
    summary=d.read(folder/'summary.json')
    check('研究输入及原依赖哈希保持',sources==d.identities()==locals_['sources'])
    energies={}
    for label in ['a0b0','a0b1','a1b0','a1b1']:
        saved=d.read(folder/(label+'.json')); b=d.candidate(x,label[:2],label[2:]); r=saved['result']
        # JSON serialization identity; saved rational fields are intentionally strings.
        encoded=json.loads(json.dumps(b,default=d.v1.encode,ensure_ascii=False),parse_float=d.D)
        check(label+'方案与原冻结选择一致',encoded==saved['bundle'])
        check(label+'持续安全绑定和完整能量可用',r['status']=='certified_candidate' and r['certified_candidate_energy']['status']=='available')
        check(label+'证据预算内形成',r['budget_status']=='within_limit' and float(r['diagnostic']['elapsed_s'])<=20)
        check(label+'持续证书覆盖8片段',r['sustained_safety']['status']=='sustained_safe' and r['sustained_safety']['thermal_certificate']['coverage_complete'])
        J=d.I(0)
        for path in b['evaluation']['paths']:
            tid=path['trace']['id']; trace=r['finite_path_energy']['traces'][tid]; thermal=trace['thermal']
            check(label+tid+'完整合法窗口和连续温度安全',trace['rankable_energy'] and trace['execution_status']=='valid' and thermal['complete'] and thermal['status']=='safe' and F(thermal['covered_until_us'])==80000)
            rows=trace['schedule']; requests=trace['requests']
            check(label+tid+'轮期限与全部Stage覆盖',len(rows)==(15 if tid=='F1' else 12) and all(F(q['finish_us'])<=F(q['deadline_us']) for q in requests))
            by_id={}
            for row in rows: by_id.setdefault(row['request_id'],{})[row['stage']]=row
            valid=True
            for group in by_id.values():
                mode=next(iter(group.values()))['mode']
                for st in x['problem']['modes'][mode]['stages']:
                    row=group[st['id']]
                    valid &= any(o['unit']==row['unit'] and o['opp']==row['opp'] and F(o['duration_us'])==F(row['end_us'])-F(row['start_us']) and F(o['activity_increment_W'])==F(row['activity_increment_W']) for o in st['options'])
                    valid &= all(F(group[p]['end_us'])<=F(row['start_us']) for p in st['predecessors'])
                vals=list(group.values())
                valid &= all(a['unit']!=c['unit'] or max(F(a['start_us']),F(c['start_us']))>=min(F(a['end_us']),F(c['end_us'])) for i,a in enumerate(vals) for c in vals[i+1:])
            check(label+tid+'独立有理数核模式、依赖、互斥',valid)
            E=d.box(thermal['energy_J']); J=J+E/2
            double=sum((d.box(v) for v in thermal['base_by_node_J']+thermal['activity_by_node_J']),d.I(0))+d.box(thermal['external_J'])+d.box(thermal['leakage_J'])
            check(label+tid+'分项能量双算及公共功率一次计入',d.overlap(double,E) and d.box(thermal['external_J']).lo==F(1,25))
            # Reconstruct power segments from exact source/table, not serialized float fields.
            xx,tr,pre,state,rr,segments=d.path_parts(b,path)
            ode=rk4(xx['platform'],segments,[30,30])
            errors=[abs(v-midpoint(t)) for v,t in zip(ode[:2],thermal['end_temperature_C'])]+[abs(ode[-1]-midpoint(thermal['energy_J']))]
            numerics[label+tid]=dict(ODE_vs_interval_midpoint_absolute_errors=errors)
            check(label+tid+'全过程独立ODE终温／能量核对',max(errors[:2])<1e-8 and errors[2]<1e-10)
            check(label+tid+'归因重建与直接完整能量相容',d.overlap(d.box(summary['rows'][label]['paths'][tid]['rebuilt_J']),E))
        check(label+'独立权重汇总与保存J相容',d.overlap(J,d.box(summary['rows'][label]['J_J'])))
        energies[label]=d.box(summary['rows'][label]['J_J'])
    baseline=[a+b for a in d.retained({k:d.box(v) for k,v in locals_['S_A_J'].items()}) for b in d.retained({k:d.box(v) for k,v in locals_['S_B_J'].items()})]
    check('逐模式保留集合独立复算',baseline==summary['local_cartesian'])
    check('共同保留集合独立复算',d.retained(energies)==summary['joint_retained'])
    for a in ['a0','a1']:
        for tid in ['F1','F2']:
            state=locals_['A'][a][tid]['boundary']
            check(a+tid+'转换共同非温度状态',not state['unfinished'] and state['held_opps']=={'C0':'L','N0':'H'})
    delta=energies['a1b1']-energies['a1b0']-energies['a0b1']+energies['a0b0']
    check('四点交互量独立复算',d.overlap(delta,d.box(summary['delta_J'])))
    report=dict(material_passport={'id':'HT1-postcheck','type':'saved output validation','status':'VERIFIED' if all(c['pass_'] for c in checks) else 'FAILED'},
                all_pass=all(c['pass_'] for c in checks),checks=checks,numerics=numerics,
                sources=sources,postcheck_source_sha256=d.cp.sha(Path(__file__)),
                no_search_or_repair=True)
    d.write(out/'postcheck.json',report)
    with (out/'energy_summary.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['combination','J_lower_mJ','J_upper_mJ','R_lower_mJ','R_upper_mJ','sustained_safe'])
        for label,row in summary['rows'].items(): w.writerow([label]+[str(d.D(v)*1000) for field in ['J_J','R_J'] for v in row[field]]+['yes'])
    print(json.dumps(dict(all_pass=report['all_pass'],checks=len(checks)),ensure_ascii=False))
    return report


if __name__=='__main__':
    if len(sys.argv)!=3: raise SystemExit('usage: postcheck.py RESULT_FOLDER NEW_OUTPUT_FOLDER')
    sys.exit(0 if postcheck(sys.argv[1],sys.argv[2])['all_pass'] else 1)
