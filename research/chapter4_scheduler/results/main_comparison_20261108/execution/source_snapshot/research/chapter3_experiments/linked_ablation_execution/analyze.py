"""K173 terminal archive analysis only; no solve/decode/thermal/post functions."""
import argparse
import csv
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]

def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def optional(p):return read(p) if Path(p).is_file() else {}
def show(v,digits=9):return '—' if v is None else f'{float(F(str(v))):.{digits}f}'
def save_csv(path,rows,fields):
    with path.open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def main(declaration_path,output):
    declaration_path=Path(declaration_path).resolve();root=declaration_path.parent;output=Path(output)
    if output.exists():raise FileExistsError('Analysis output is append-only')
    d=read(declaration_path);ledger=read(root/'ledger.json')
    terminal=optional(root/'process_terminal.json') or optional(root/'terminal.json')
    if not terminal and ledger.get('state') in ('DECLARED','RUNNING'):raise ValueError('Batch not terminal')
    rows=[];updates=[];details=[];sources={str(declaration_path):sha(declaration_path),str(root/'ledger.json'):sha(root/'ledger.json')}
    for slot in d['slots']:
        folder=root/'calls'/slot['slot_id'];a=optional(folder/'audit.json');r=optional(folder/'result.json')
        post=optional(folder/'post_audit.json') or optional(folder/'post_audit_result.json')
        pr=optional(folder/'post_return.json');wi=optional(folder/'worker_identity.json');wr=optional(folder/'worker_return.json')
        consumed=any(c.get('slot_id')==slot['slot_id'] for c in ledger.get('calls',[]))
        eligible=(a.get('eligible_for_post') is True and post.get('passed') is True and pr.get('passed') is True)
        # Persisted post_audit is authoritative; no new audit or post is run here.
        u=a.get('usable_U_J') if eligible else None
        interval=r.get('weighted_energy_J') if u is not None else None
        seed=a.get('initial_seed') or {};seedI=seed.get('energy_J');phase_rows=[]
        for p in r.get('phases') or ([{'phase_index':1,'name':'N1','scenes':r.get('scenes',{})}] if r else []):
            index=p['phase_index'];up=[x for x in r.get('global_updates',[]) if x.get('phase_index',1)<=index]
            last=up[-1] if up else None
            counts=[]
            for sid,s in p.get('scenes',{}).items():
                summary=s.get('model_summary') or {};pre=s.get('preprocessing') or {}
                counts.append({'scene_id':sid,'options':summary.get('options'),'variables':summary.get('variables'),
                    'binary_variables':summary.get('binary_variables'),'rows':summary.get('rows'),
                    'model_completed_at_s':s.get('model_completed_at_s'),'search_started_at_s':s.get('search_started_at_s'),
                    'search_returned_at_s':s.get('search_returned_at_s'),'scene_slice_s':s.get('scene_slice_s'),
                    'anchor_preelimination':pre.get('closed_anchor_preelimination') or (summary.get('preprocessing') or {}).get('closed_anchor_preelimination'),
                    'reason':s.get('reason')})
            phase_rows.append({'phase_index':index,'name':p.get('name'),'started_at_s':p.get('started_at_s'),
                'completed_at_s':p.get('completed_at_s'),'complete_U_after_J':None if last is None else last.get('safe_upper_bound_J'),
                'complete_interval_after_J':None if last is None else last.get('weighted_energy_J'),
                'closed_anchor_candidate_sha256':p.get('condition',{}).get('warm_candidate_sha256'),'scene_records':counts})
        strict=[]
        for index,x in enumerate(r.get('global_updates',[])):
            stamp=x.get('committed_at_s');ival=x.get('weighted_energy_J')
            updates.append({'slot_id':slot['slot_id'],'update_index':index,'phase_index':x.get('phase_index',1),
                'formed_at_s':stamp,'transferred_at_s':x.get('transferred_at_s'),'U_J':x.get('safe_upper_bound_J'),
                'low_J':ival[0] if ival else None,'high_J':ival[1] if ival else None})
            if seedI and ival and F(ival[1])<F(seedI[0]):strict.append(stamp)
        timing=r.get('timing') or {};startup=(timing.get('phases_exclusive_s') or {}).get('solver_startup')
        row={'slot_id':slot['slot_id'],'case_id':slot['case_id'],'variant':slot['variant'],'consumed':consumed,
            'classification':a.get('classification','UNSTARTED' if not consumed else 'MISSING_AUDIT'),
            'reported_U_J':r.get('safe_upper_bound_J'),'verified_method_U_J':a.get('usable_U_J'),
            'post_status':'PASS' if eligible else 'NOT_APPLICABLE' if a.get('can_continue') and not a.get('eligible_for_post') else 'NOT_COMPARISON_ELIGIBLE',
            'comparison_U_J':u,'comparison_low_J':interval[0] if interval else None,
            'method_elapsed_s':timing.get('method_elapsed_s'),'MATLAB_startup_s':startup,
            'common_import_s':wi.get('common_support_import_elapsed_s'),'worker_dispatch_s':wr.get('method_elapsed_s'),
            'first_SAFE_s':r.get('first_safe_at_s'),'first_strict_improvement_s':min(strict) if strict else None,
            'seed_label_hash':seed.get('candidate_sha256'),'seed_U_J':seed.get('U_J'),
            'phase1_U_J':next((p['complete_U_after_J'] for p in phase_rows if p['phase_index']==1),None),
            'phase2_U_J':next((p['complete_U_after_J'] for p in phase_rows if p['phase_index']==2),None),
            'phase2_anchor_hash':next((p['closed_anchor_candidate_sha256'] for p in phase_rows if p['phase_index']==2),None),
            'minimum_deadline_slack_ms':a.get('current_schedule_audit',{}).get('minimum_deadline_slack_ms'),
            'post_elapsed_s':pr.get('evaluation_elapsed_s')}
        rows.append(row);details.append({'slot':slot,'method_audit':a,'post_audit':post,'phases':phase_rows})
        for name in ('result.json','audit.json','post_audit.json','post_audit_result.json','post_return.json','worker_return.json','worker_identity.json'):
            if (folder/name).is_file():sources[str(folder/name)]=sha(folder/name)
    paired=[]
    for case in ('base__R1','base__R3'):
        selected={r['variant']:r for r in rows if r['case_id']==case};b,c=selected['B'],selected['C']
        same_anchor=bool(b['phase2_anchor_hash'] and b['phase2_anchor_hash']==c['phase2_anchor_hash'])
        same_seed=len({r['seed_label_hash'] for r in selected.values()})==1 and all(r['seed_label_hash'] for r in selected.values())
        strict_comparisons=[]
        for left,right in (('A','B'),('B','C'),('A','C')):
            x,y=selected[left],selected[right]
            if x['comparison_U_J'] is None or y['comparison_U_J'] is None:state='MISSING_COMPARISON_ELIGIBLE_PAIR'
            elif F(y['comparison_U_J'])<F(x['comparison_low_J']):state=right+'_STRICTLY_LOWER'
            elif F(x['comparison_U_J'])<F(y['comparison_low_J']):state=left+'_STRICTLY_LOWER'
            else:state='OVERLAPPING_INTERVALS'
            strict_comparisons.append({'left':left,'right':right,'state':state})
        paired.append({'case_id':case,'same_fresh_seed_labels':same_seed,'B_C_same_phase1_anchor':same_anchor,
            'comparison':strict_comparisons,'causal_scope':'same-anchor formulation comparison' if same_anchor else 'end-to-end runs only; do not attribute all energy difference to elimination'})
    history=[]
    for case,camp in (('base__R1','p0_execution01'),('base__R3','p0_resume01')):
        p=REPO/'research/chapter3_experiments/results'/camp/'calls'/case/'heft/result.json'
        if p.is_file():
            old=read(p);history.append({'case_id':case,'method':'HEFT historical P0 context only','U_J':old.get('safe_upper_bound_J'),
                'source_path':str(p),'source_sha256':sha(p),'not_this_round_or_initialization':True})
    output.mkdir(parents=True)
    save_csv(output/'results6.csv',rows,list(rows[0]))
    save_csv(output/'safe_updates.csv',updates,['slot_id','update_index','phase_index','formed_at_s','transferred_at_s','U_J','low_J','high_J'])
    evidence={'protocol':'K173-readonly-six-slot-analysis-v1','ledger_state':ledger.get('state'),
        'consumed':ledger.get('consumed'),'planned':6,'post_consumed':ledger.get('post_consumed'),
        'comparison_eligible_count':sum(r['comparison_U_J'] is not None for r in rows),
        'rows':rows,'details':details,'paired':paired,'historical_HEFT_context_only':history,
        'source_sha256':sources,'new_models':0,'solver_calls':0,'thermal_or_post_calls':0,'new_candidate_or_U':0}
    (output/'facts.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n','utf-8')
    lines=['# K173六槽消融：终态只读分析','',f"已消费{ledger.get('consumed')}/6，post合格可比较{evidence['comparison_eligible_count']}/6；账本状态{ledger.get('state')}。未启动／无U不填0。",'',
        '|题目|方法|终态|可比较U/J|方法/s|首SAFE/s|首严格改善/s|','|---|---|---|---:|---:|---:|---:|']
    lines.extend('|'+ '|'.join([r['case_id'],r['variant'],r['classification'],show(r['comparison_U_J']),show(r['method_elapsed_s'],3),show(r['first_SAFE_s'],3),show(r['first_strict_improvement_s'],3)])+'|' for r in rows)
    lines+=['','A/B比较完整组织（含分时、额外构模及原第二阶段传输），B/C只在同锚时讨论同子问题预消元。每题各一次，不作总体或稳定性排名。','']
    for p in paired:lines.append(f"- {p['case_id']}：同fresh seed标签={p['same_fresh_seed_labels']}；B/C同闭锚={p['B_C_same_phase1_anchor']}；{p['causal_scope']}。")
    lines+=['','R3的固定部署、第一阶段闭合A选择、第二阶段冻结B/C main/post仍按原条件；即使安全U改善，也未开放全域部署，局部完成不等于全域最优。','',
        '历史HEFT仅作旧P0背景，不进入这六次配对、预算、初始化或本轮性能排名。原方法U、post可比较U及缺失状态分列，post不替换预算内U。','',
        '本工具只读已有文件与精确能量区间，不调用求解器、解码、构模、热积分、post或修复。阶段／anchor／过滤与完整时序见facts.json；safe_updates.csv保留原时钟更新。']
    (output/'summary.md').write_text('\n'.join(lines)+'\n','utf-8')
    print(json.dumps({'analysis':str(output),'consumed':ledger.get('consumed'),'eligible':evidence['comparison_eligible_count'],'new_scientific_calls':0},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--declaration',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();main(a.declaration,a.out)
