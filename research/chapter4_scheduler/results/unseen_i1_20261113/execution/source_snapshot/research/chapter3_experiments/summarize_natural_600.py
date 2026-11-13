"""Summarize saved 600 s evidence; zero new solve or thermal evaluation."""
import hashlib
import json
from pathlib import Path
from fractions import Fraction as Q
import sys
from completion_metrics import build_completion_metrics

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def summarize(folder):
    folder=Path(folder)
    slot=folder/'slots/whole_milp__method'
    rawpath=slot/'worker/raw_result.json';raw=read(rawpath)
    batch=read(folder/'batch.json');meta=read(slot/'slot_result.json')
    metrics=build_completion_metrics(raw,uses_matlab=True,seconds=600)
    postslot=folder/'slots/whole_milp__post'
    post=read(postslot/'worker/post_result.json') if (postslot/'worker/post_result.json').exists() else {}
    postmeta=read(postslot/'slot_result.json') if (postslot/'slot_result.json').exists() else {}
    if post:
        assert post['method_receipt_sha256']==sha(rawpath)
        assert post['same_candidate']==raw['safe_candidate']
    ev=raw.get('evaluation') or {};u=raw.get('safe_upper_bound_J')
    safes=metrics['complete_SAFE_receipts']
    best=[r['completed_at_s'] for r in safes if u is not None and Q(r['safe_upper_bound_J'])==Q(u)]
    previous=read(folder.parent/'natural_full_repaired_execution01/summary.json')
    comparison=[{k:r.get(k) for k in ('id','final_energy_J','total_method_wall_s','post_wall_s','execution_status')} for r in previous['methods']]
    for r in comparison:
        r['method_budget_s']=300
        r['new_MILP_relative_energy_percent']=float(100*(Q(u)-Q(r['final_energy_J']))/Q(r['final_energy_J'])) if u else None
    scenes=ev.get('scenes',{})
    result=dict(schema='one-natural-full-domain-600-summary-v1',scope='One fresh 600 s MILP, archived 300 s comparators; unequal budgets. Saved evidence only.',
        batch_state=batch['state'],batch_error=batch.get('error'),batch_wall_s=batch['total_wall_s'],
        original_execution_status=meta['status'],method_state=raw.get('state'),reason=raw.get('reason'),
        initial_energy_J=metrics['initial_complete_SAFE_energy_interval_J'],final_energy_J=u,
        first_safe_s=metrics['first_complete_SAFE_at_s'],best_safe_s=min(best) if best else None,
        method_root_s=raw['timing']['method_elapsed_s'],method_wall_s=meta['total_wall_s'],
        post_state=post.get('state'),post_wall_s=postmeta.get('total_wall_s'),
        post_execution_status=postmeta.get('status'),raw_sha256=sha(rawpath),
        independently_proven_optimal=raw.get('independently_proven_optimal',False),
        completion_metrics=metrics,timing=raw['timing'],comparison=comparison,
        candidate=raw.get('safe_candidate'),schedule=(ev.get('legality') or {}).get('scenes'),
        weighted_energy_interval_J=ev.get('weighted_energy_J'),
        peak_upper_degC=max((float(v[1]) for s in scenes.values() for v in s['peaks_degC'].values()),default=None),
        weighted_components_J={k:[str(sum(Q(s['energy_components_J'][k][i]) for s in scenes.values())/2) for i in (0,1)] for k in next(iter(scenes.values()),{}).get('energy_components_J',{})})
    result['native']=[dict(path=p.relative_to(folder).as_posix(),**{k:read(p).get(k) for k in ('status','exitflag','fval','output','phase_seconds')}) for p in sorted((slot/'worker/method/matlab').glob('*.response.json'))]
    return result

if __name__=='__main__':
    result=summarize(sys.argv[1])
    with Path(sys.argv[2]).open('x',encoding='utf-8',newline='\n') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:result[k] for k in ('method_state','final_energy_J','first_safe_s','best_safe_s','post_state')},ensure_ascii=False))
