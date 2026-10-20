"""Replay stored status/timing only; never imports a method or heat evaluator."""
from pathlib import Path
import hashlib
import json
import sys

HERE=Path(__file__).resolve().parent
REPO=next(p for p in HERE.parents if (p/'AGENTS.md').is_file())
CODE=REPO/'research/chapter3_experiments'
sys.path.insert(0,str(CODE))
from execution_status import classify_execution
from completion_metrics import build_completion_metrics

read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    old=CODE/'results/fair_comparison_preparation01'
    prior=read(CODE/'results/budget_end_review01/audit.json');facts=prior['facts']
    r=read(old/'linked_n1/result.json');gate=read(HERE/'checks.json')
    raw_before={n:sha(old/n) for n in prior['raw_artifact_sha256']}
    source_before={n:sha(REPO/n) for n in gate['source_sha256']}
    context={'input_identity_valid':facts['identities_valid'],'source_identity_valid':facts['identities_valid'],
        'current_request_identity_valid':facts['current_request_identity_valid'],'cutoff_s':facts['cutoff_s'],
        'hard_errors':facts['hard_errors'],'observed_numerical_rejection':facts['observed_numerical_rejection'],
        'worker_isolation':'VERIFIED' if facts['cleanup_verified'] else 'UNKNOWN',
        'prior_requests_complete':facts['prior_requests_complete'],'completion_verified':False,
        'root_deadline_confirmed':facts['root_deadline_confirmed'],'deadline_causal_trace':facts['deadline_causal_trace'],
        'last_request':{'state':'PENDING','pending_at_cutoff':facts['pending_response_at_cutoff'],
            'refuses_late_candidate':facts['budget_stub_refuses_candidate'],'deadline_causal_trace':facts['deadline_causal_trace'],
            'deadline_reasons':facts['deadline_reasons']},
        'safe_receipt':{'verified':facts['prior_safe_verified'],'identity_valid':facts['prior_safe_identity_valid'],
            'complete':True,'formed_at_s':facts['safe_formed_at_s'],'energy_upper_J':r['safe_upper_bound_J']},
        'numerical_checks':[v for q in r['augmented_transport']['requests'] for v in q['numerical_checks']]}
    status=classify_execution(r,context);metrics=build_completion_metrics(r,uses_matlab=True,seconds=300)
    checks={'same_normal_deadline_interpretation':status['execution_status']=='NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST',
        'previous_complete_U_preserved':status['usable_U_J']==r['safe_upper_bound_J'],
        'last_request_remains_unresolved':status['last_request']=='UNRESOLVED',
        'first_SAFE_from_complete_aggregate':metrics['first_complete_SAFE_at_s']==r['first_safe_at_s'],
        'first_strict160344':metrics['first_strict_improvement_at_s']==prior['first_strict_improvement_vs_initial_at_s'],
        'phase2_has_no_new_strict_improvement':metrics['phases'][1]['first_strict_improvement_at_s'] is None,
        'startup72_297_recorded':abs(metrics['matlab_startup']['wall_s']-72.297)<1e-8,
        'source165_unchanged':len(source_before)==165 and source_before==gate['source_sha256'] and source_before=={n:sha(REPO/n) for n in source_before},
        'original301_unchanged':raw_before==prior['raw_artifact_sha256'] and raw_before=={n:sha(old/n) for n in raw_before},
        'K142_ledger_not_rewritten':read(old/'ledger.json')['state']=='BLOCKED' and read(old/'ledger.json')['consumed']==2}
    report={'stage':'K144','passed':all(checks.values()),'checks':checks,'execution_status':status,
        'metrics':metrics,'research_calls':0,'native_calls':0,'thermal_evaluations':0,'candidate_decodes':0,
        'scope':'saved status/timing replay only; historical candidates never passed to a search entry'}
    (HERE/'saved_K142_replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'checks':checks},ensure_ascii=False))
    return report['passed']
if __name__=='__main__':raise SystemExit(0 if main() else 1)
