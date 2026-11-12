"""Read-only compact observer; never touches execution files or starts science."""
from pathlib import Path
import json,time
root=Path(__file__).resolve().parent/'formal_abc_execution_v1'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
for arm in 'ABC':
    d=root/arm
    if not d.exists():continue
    claim=read(d/'claim.json');out=dict(arm=arm,elapsed_s=round(time.monotonic()-claim['parent_start_monotonic'],3))
    out['milestones']=[n for n in ['model_summary.json','initialization.json','representation_certificate.json',
        'initial_admission.json','matlab/ready.json','matlab/request_000001.request.json',
        'returned_vector_validation.json','returned_complete_evaluation.json','receipt.json','controller.json'] if (d/n).exists()]
    for name in ['publication_allocation.json','receipt.json','controller.json']:
        if (d/name).exists():
            r=read(d/name);out[name]={k:r[k] for k in ['terminal_state','native_seconds','measured_elapsed_s',
                'native_calls_observed','physical_evaluations_observed','error','fault_scope','completed','actual_total_wall_s',
                'returned_complete_SAFE','same_initial','strict_energy_improvement','evidence_integrity'] if k in r}
            if name=='controller.json':out['elapsed_s']=r['actual_total_wall_s']
    es=sorted((d/'matlab').glob('request_000001.event_*.json'))
    if es:
        try:
            r=read(es[-1]);out['latest_event']={k:r.get(k) for k in ['kind','state','event_number','values']}
        except (ValueError,PermissionError):out['latest_event']='INCOMPLETE_READ'
    for name in ['stderr.log']:
        if (d/name).exists() and (d/name).stat().st_size:out[name]=(d/name).read_text(errors='replace')[-1200:]
    print(json.dumps(out,ensure_ascii=False))
if (root/'batch.json').exists():
    r=read(root/'batch.json');print(json.dumps({k:r[k] for k in ['completed','not_started','actual_batch_wall_s','per_arm_wall_sum_s','retries']}))
