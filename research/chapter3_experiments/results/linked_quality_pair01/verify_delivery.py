"""Read-only K140 delivery identity/ledger audit. No production imports or solve."""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json

OUT=Path(__file__).resolve().parent
ROOT=next(p for p in OUT.parents if (p/'AGENTS.md').is_file())
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
checks={}
def check(name,condition):
    checks[name]=bool(condition)
    if not condition: raise AssertionError(name)

def main():
    d=read(OUT/'declaration.json'); f=read(OUT/'analysis01/facts.json')
    l=read(OUT/'ledger.json'); admission=read(OUT/'admission_verification.json')
    review=read(OUT/'verification.json'); context=read(OUT/'phase_context.json')
    check('one_terminal_pair',l['state']=='COMPLETED' and l['consumed']==2
          and [c['id'] for c in l['calls']]==['old_n1','linked_n1']
          and all(c['state']=='COMPLETED' and not c['error'] and not c['technical_issues'] for c in l['calls']))
    check('frozen_300s_and_no_retry',d['per_method_budget_s']==300 and d['method_call_limit']==2
          and d['scene_slice_s']==60 and d['retry_allowed'] is False and d['extend_budget_allowed'] is False)
    check('frozen_context',all(context[k+'_sha256']==sha(OUT/name) for k,name in
          [('protocol','protocol.md'),('launcher','launcher.py'),('declaration','declaration.json')]))
    check('source157_unchanged',len(d['source_sha256'])==157 and all(sha(ROOT/p)==v
          and sha(OUT/'source_snapshot'/p)==v for p,v in d['source_sha256'].items()))
    base=read(OUT/'method_checks.json')
    check('K139_155_inherited',base['count']==66 and base['passed'] is True and len(base['source_sha256'])==155
          and all(d['source_sha256'].get(p)==v for p,v in base['source_sha256'].items()))
    check('wrapper28_pass_and_no_physics',read(OUT/'wrapper_checks.json')['passed'] is True
          and read(OUT/'wrapper_checks.json')['tests_run']==28
          and not any(read(OUT/'wrapper_checks.json')['blocked_calls'].values()))
    check('history1087_unchanged',len(d['historical_artifact_sha256'])==1087
          and all(sha(ROOT/p)==v for p,v in d['historical_artifact_sha256'].items()))
    check('input_unchanged',all(sha(OUT/p)==v for p,v in d['input_file_sha256'].items()))
    check('independent_admission_and_review',admission['passed'] is True and review['passed'] is True
          and review['check_count']==41)
    check('stored_analysis_raw_identity',f['raw_unchanged'] is True and f['raw_hashes_before']==f['raw_hashes_after']
          and all(sha(OUT/p)==v for p,v in f['raw_hashes_before'].items()))
    check('fresh_same_seed',f['comparison']['identical_fresh_seed_candidate_and_energy'] is True)
    check('strict_complete_energy_improvement',F(f['comparison']['new_interval_J'][1])<F(f['comparison']['old_interval_J'][0]))
    p2=next(p for p in f['phase_attribution'] if p['job']=='linked_n1' and p['phase_index']==2)
    check('phase2_has_own_improvement',p2['strict_energy_improvement_vs_own_before_interval'] is True
          and p2['committed_U_decrease_count']==3 and F(p2['U_decrease_J'])>0)
    check('phase2_setup_counted',abs(p2['inclusive_phase_elapsed_s']
          -p2['recorded_interval_elapsed_s']-p2['pre_record_setup_s'])<1e-9)
    jobs={j['id']:j for j in f['calls']}
    check('complete_SAFE_and_deadlines',all(j['final_SAFE_receipt_verified'] is True
          and j['timing']['limit_s']==300 and j['timing']['method_elapsed_s']<300
          and all(u['at_s']<300 for u in j['updates']) for j in jobs.values()))
    check('no_thermal_feedback_claim',all(j['feedback_records']==0 and j['feedback_rows']==0 for j in jobs.values()))
    check('no_global_proof',all(j['independently_proven_optimal'] is False
          and j['independently_proven_infeasible'] is False for j in jobs.values()))
    check('six_budget_valid_native_requests',len(f['native_call_times'])==6
          and all(r['budget_valid'] is True for r in f['native_call_times']))
    check('normal_launcher_exit',read(OUT/'launcher_timing.json')['returncode']==0
          and not read(OUT/'launcher_timing.json')['error'])
    check('all_unique_claims_present',(OUT/'launcher_claim.json').is_file()
          and (ROOT/'research/chapter3_experiments/results/linked_pair_claim01.json').is_file()
          and all((OUT/'claims'/(j+'.json')).is_file() for j in jobs))
    check('figure_and_reports_present',all((OUT/p).is_file() for p in
          ['summary.md','protocol.md','independent_review.md','admission_review.md','analysis01/summary.md',
           'analysis01/energy_bounds.png','analysis01/comparison.csv','analysis01/phase_attribution.csv']))
    report={'stage':'K140','scope':'pure saved identity and arithmetic delivery audit; no model, heat or solve',
        'passed':all(checks.values()),'count':len(checks),'checks':checks,
        'new_research_native_model_thermal_calls':0,'plot_visually_checked_by_parent':True}
    (OUT/'delivery_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'count':report['count']}))

if __name__=='__main__': main()
