"""Read existing receipts only: no construction, solve, decode or thermal evaluation."""
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / 'research/chapter3_experiments'
OLD = HERE.parent / 'base_long_diagnostic01'
PRE = HERE.parent / 'diagnostic_precheck04'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    result, old = read(HERE/'result.json'), read(OLD/'result.json')
    integrity = read(HERE/'source_integrity.json')
    claim = read(PRE/'original_run_claim.json')
    prereq = read(PRE/'original_prerequisites.json')
    diagnostic = result['diagnostic']
    raw = read(HERE/'matlab/request_000001.response.json')
    old_raw = read(OLD/'matlab/request_000001.response.json')
    closed = read(HERE/'matlab/closed.json')
    checks = []

    def check(name, value):
        checks.append({'name': name, 'passed': bool(value)})

    check('source_integrity', integrity['match'] and integrity['before']==integrity['after'])
    for name, value in integrity['after'].items():
        source = SOURCE/name if name!='interval.py' else SOURCE.parent/'v1_evaluator/interval.py'
        check('current_source/'+name, digest(source)==value)
        check('archived_source/'+name, digest(HERE/'source_snapshot'/name)==value)
    check('prerequisite_source_matches', prereq['source_hashes']==integrity['before']==claim['source_hashes'])
    check('prerequisites_passed', prereq['all_prerequisites_passed'])
    for name, record in prereq['records'].items():
        check('prerequisite_record/'+name, digest(ROOT/record['path'])==record['sha256'])
    check('protocol_unchanged', digest(SOURCE/'diagnostic_900_protocol.md')==prereq['protocol_sha256'])
    check('original_config_identical', read(HERE/'input_config.json')==read(OLD/'input_config.json'))
    check('original_instance_identical', read(HERE/'input_instance.json')==read(OLD/'input_instance.json'))
    check('only_one_claimed_invocation', claim['seconds']==900 and claim['retries']==0
          and Path(claim['out']).resolve()==HERE and result['solver_request_attempts']==1
          and len(list((HERE/'matlab').glob('*.request.json')))==1)
    check('total_budget_900', result['timing']['limit_s']==900 and result['budget_exhausted'])
    check('no_accepted_late_round', all(not r.get('budget_valid') and not r.get('accepted_for_evaluation')
          for r in result['rounds']))
    check('received_events_in_budget', all(e['method_elapsed_s']<900 for e in diagnostic['solver_progress']))
    check('no_candidate_or_safe_receipt', diagnostic['candidate_receipts']==0 and not diagnostic['evaluations']
          and result['safe_candidate'] is None and result['safe_upper_bound_J'] is None
          and diagnostic['first_candidate_received_s'] is None and diagnostic['first_safe_receipt_s'] is None)
    check('unresolved_not_infeasible', result['state']=='UNRESOLVED' and result['reason']=='wall_time_limit'
          and not result['independently_proven_optimal'] and not result['independently_proven_infeasible'])
    check('requested_formulation', result['model_summary']['formulation']=={
        'fix_late_options': True, 'aggregate_opp_locks': True, 'relax_auxiliary_integrality': False})
    for key in ['options','variables','binary_variables','coefficient_sets','events_per_scene']:
        check('preserved_model_structure/'+key, result['model_summary'][key]==old['model_summary'][key])
    check('exact_expected_row_and_bound_counts', result['model_summary']['rows']==613164
          and result['model_summary']['deadline_fixed_options']==4741)
    skip = {'MaxTime'}
    check('solver_options_unchanged_except_remaining_time',
          {k:v for k,v in raw['options'].items() if k not in skip}==
          {k:v for k,v in old_raw['options'].items() if k not in skip})
    check('worker_closed_without_new_evidence', closed['returncode']==0 and closed['cleanup_not_available_for_new_evidence'])
    check('no_formal_comparison', not result['formal_comparison'] and not claim['formal_comparison'])
    last = raw['callbacks'][-1]
    old_last = old_raw['callbacks'][-1]
    # Preserve the inconsistent native counter; never turn it into a candidate.
    mismatch = {'done_reported_numfeaspoints':last['values'].get('numfeaspoints'),
                'done_candidate_length':len(last.get('x',[])),
                'final_reported_numfeaspoints':raw['output'].get('numfeaspoints'),
                'final_candidate_length':len(raw.get('x',[])),
                'seen_in_previous_diagnostic':last['values'].get('numfeaspoints')==old_last['values'].get('numfeaspoints')
                    and old_raw['output'].get('numfeaspoints')==raw['output'].get('numfeaspoints'),
                'acceptance':'archival anomaly only; no candidate vector and outside method evidence cutoff'}
    def event_time(d, phase):
        return next(e['method_elapsed_s'] for e in d['diagnostic']['solver_progress']
                    if e.get('values',{}).get('phase')==phase)
    old_count=old['model_summary']['rows']; new_count=result['model_summary']['rows']
    comparison = {'old_rows':old_count,'new_rows':new_count,
                  'row_reduction_fraction':(old_count-new_count)/old_count,
                  'old_nonzeros':old['construction']['nonzeros_in_rows'],
                  'new_nonzeros':result['construction']['nonzeros_in_rows'],
                  'old_solver_entered_s':old['diagnostic']['solver_entered_received_s'],
                  'new_solver_entered_s':diagnostic['solver_entered_received_s'],
                  'old_rootlp_received_s':event_time(old,'rootlp'),'new_rootlp_received_s':event_time(result,'rootlp'),
                  'old_cutgen_received_s':event_time(old,'cutgen'),'new_cutgen_received_s':event_time(result,'cutgen'),
                  'scope':'single-run descriptive comparison; not a statistically stable speedup or formal comparison'}
    output={'all_passed':all(c['passed'] for c in checks),'passed':sum(c['passed'] for c in checks),
            'total':len(checks),'checks':checks,'comparison':comparison,'late_counter_mismatch':mismatch,
            'scope':'archive-only verification; no new scheduling or thermal evidence',
            'verification_script_sha256':digest(Path(__file__))}
    (HERE/'verification.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:output[k] for k in ['all_passed','passed','total','comparison','late_counter_mismatch']},indent=2))
    if not output['all_passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
