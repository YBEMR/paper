"""Reproducible basic V2 prechecks; each run creates an immutable result folder."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
from unittest.mock import patch

from verify import verify, replay, witness_trace, Budget, classify_point_interval, v1, Exhausted

ROOT=Path(__file__).resolve().parent
PACKAGE=ROOT.parent/'v2_precheck_draft'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, x):
    with p.open('x',encoding='utf-8') as f:
        json.dump(x,f,ensure_ascii=False,indent=2,default=v1.encode); f.write('\n')


def stop_at(name, exception=Exhausted):
    def hook(at):
        if at==name:
            raise exception('injected_'+name)
    return hook


def main(output):
    output.mkdir(parents=True,exist_ok=False)
    sources={'verify.py':ROOT/'verify.py','run_v2.py':Path(__file__),
             'v1_evaluate.py':ROOT.parent/'v1_evaluator/evaluate.py','v1_interval.py':ROOT.parent/'v1_evaluator/interval.py'}
    before={n:sha(p) for n,p in sources.items()}
    original={str(p.relative_to(ROOT.parent)):sha(p) for p in (ROOT.parent/'v1_precheck_draft').iterdir() if p.is_file()}
    (output/'source').mkdir()
    for n,p in sources.items():
        (output/'source'/n).write_bytes(p.read_bytes())
    spec=importlib.util.spec_from_file_location('v2_static',PACKAGE/'check_static.py')
    static=importlib.util.module_from_spec(spec); spec.loader.exec_module(static)
    gate=static.run(PACKAGE); save(output/'static_gate.json',gate)
    if not gate['all_passed']:
        raise RuntimeError('input/static gate failed')
    x=v1.load(PACKAGE/'inputs.json'); sem=x['semantics']
    cases={c['id']:c for c in x['fixtures']}
    results={}
    for name,c in cases.items():
        results[name]=verify(c,sem)
        save(output/(name+'.json'),results[name])
        print(name+': '+results[name]['status'],flush=True)
    # Independent answers are opened only after the primary verifier calls finish.
    expected=v1.load(PACKAGE/'expected.json')['fixtures']
    checks=[]; extra={}
    def check(name, fn):
        try:
            passed=bool(fn()); reason='' if passed else 'assertion failed'
        except Exception as exc:
            passed,reason=False,f'{type(exc).__name__}: {exc}'
        checks.append(dict(name=name,passed=passed,reason=reason))
    def trial(name,c=None,budget=None,semantics=None):
        r=verify(c or cases['B1'],semantics or sem,budget)
        extra[name]=r; return r
    check('B1_sustained_certificate',lambda:results['B1']['status']=='sustained_safe' and results['B1']['coverage']=='all_declared_processes_certified')
    check('B1_exact_deadline_certificate',lambda:results['B1']['deadline']['spans_us']==expected['B1']['spans_us'] and all(e['slack_us']==0 for e in results['B1']['deadline']['edge_checks']))
    check('B1_all_eight_fragments',lambda:results['B1']['thermal_certificate']['checked_count']==8 and results['B1']['thermal_certificate']['coverage_complete'])
    check('B1_exact_face_values',lambda:results['B1']['thermal_certificate']['minimum_lower_net_W']==list(map(F,expected['B1']['minimum_lower_net_W'])) and results['B1']['thermal_certificate']['maximum_upper_net_W']==list(map(F,expected['B1']['maximum_upper_net_W'])))
    check('B2_real_deadline_not_just_failed_bound',lambda:results['B2']['status']=='violation' and results['B2']['witness']['real_violation'] and results['B2']['witness']['failure']['lateness_us']==1000)
    hist=v1.load(ROOT.parent/'v1_evaluator/results/run05/traces.json')['F3']
    check('B2_historical_F3_failure_unchanged',lambda:results['B2']['witness']['failure']==hist['failure'])
    check('B3_real_thermal_witness',lambda:results['B3']['status']=='violation' and results['B3']['deadline']['status']=='pass' and bool(results['B3']['witness']['thermal']['known_violations']))
    with localcontext() as context:
        context.prec=80
        eq=D(1100)/49
        exact=D(25)+eq+(D(5)-eq)*(-D('0.98')).exp()
    pair=results['B3']['witness']['thermal'].get('peak_C',[[]])[0]
    check('B3_80digit_analytic_peak_inside_enclosure',lambda:len(pair)==2 and D(pair[0])<=exact<=D(pair[1]))
    check('B3_peak_witness_at_200ms',lambda:results['B3']['witness']['thermal']['peak_lower_witness_s']==['1/5'])
    check('B3_rational_lower_bound_exceeded',lambda:F(pair[0])>F(expected['B3']['witness_temperature_strict_lower_C']))
    check('B4_certificate_failure_is_unresolved',lambda:results['B4']['status']=='unresolved' and results['B4']['thermal_certificate']['status']=='not_proved' and results['B4']['witness'] is None)
    check('B4_exact_failed_faces',lambda:results['B4']['thermal_certificate']['maximum_upper_net_W']==list(map(F,expected['B4']['maximum_upper_net_W'])))
    c=deepcopy(cases['B4']); c['certificate_box_C']=deepcopy(cases['B1']['certificate_box_C'])
    check('same_B4_plan_can_be_certified',lambda:trial('B4_alternate_box',c)['status']=='sustained_safe')
    c=deepcopy(cases['B1']); c['fragment_superset'].pop()
    check('missing_fragment_is_not_safety',lambda:trial('missing_fragment',c)['thermal_certificate'].get('reason')=='fragment_coverage_missing' and extra['missing_fragment']['status']=='unresolved')
    c=deepcopy(cases['B1']); c['certificate_box_C']=[[31,59],[25,59]]
    check('initial_coverage_required',lambda:trial('missing_initial_coverage',c)['status']=='unresolved')
    c=deepcopy(cases['B1']); del c['initial_states'][0]['phase_us']
    check('missing_entry_phase_invalid',lambda:trial('missing_phase',c)['status']=='input_invalid')
    c=deepcopy(cases['B1']); c['initial_states'][0]['phase_us']=1
    check('nonzero_initial_phase_not_silently_supported',lambda:trial('nonzero_initial_phase',c)['status']=='input_invalid')
    c=deepcopy(cases['B1']); c['initial_states'][0]['unfinished_work']=['old']
    check('pending_work_not_silently_dropped',lambda:trial('pending_work',c)['status']=='input_invalid')
    c=deepcopy(cases['B1']); c['platform']['units']['N0']['frequency_domain']='DC'
    check('incompatible_shared_domain_invalid',lambda:trial('domain_conflict',c)['status']=='input_invalid')
    c=deepcopy(cases['B1']); c['fixed_plans']['A']['stages'][1]['offset_us']=1
    check('dependency_failure_invalid',lambda:trial('dependency_failure',c)['status']=='input_invalid')
    c=deepcopy(cases['B1']); c['platform']['opps']['C0']['H']['base_W']=float('0.2')
    check('binary_float_not_treated_exact',lambda:trial('float_input',c)['status']=='input_invalid')
    altered=deepcopy(sem); altered['temperature_continuity']=False
    check('temperature_reset_semantics_rejected',lambda:trial('reset_temperature',semantics=altered)['status']=='input_invalid')
    check('numeric_boundary_overlap_unresolved',lambda:classify_point_interval(D('34.999999'),D('35.000001'),35)=='unresolved')
    check('point_safety_not_sustained_proof',lambda:classify_point_interval(30,31,35)=='safe_point_only')
    check('actual_wall_clock_expiration',lambda:trial('expired_clock',budget=Budget(seconds=-1))['status']=='unresolved')
    check('partial_fragment_limit_not_pass',lambda:trial('fragment_limit',budget=Budget(fragment_limit=1))['status']=='unresolved')
    for at in ['input_validated','deadline_ready','fragment','thermal_certificate_ready','before_final']:
        check('interrupt_'+at,lambda at=at:trial('interrupt_'+at,budget=Budget(hook=stop_at(at)))['status']=='unresolved')
    for error in [MemoryError,ArithmeticError]:
        check(error.__name__+'_not_pass',lambda error=error:trial(error.__name__,budget=Budget(hook=stop_at('fragment',error)))['status']=='unresolved')
    check('deadline_witness_survives_interruption',lambda:trial('deadline_witness_interrupted',cases['B2'],Budget(hook=stop_at('witness_committed')))['status']=='violation')
    check('thermal_witness_survives_interruption',lambda:trial('thermal_witness_interrupted',cases['B3'],Budget(hook=stop_at('witness_thermal_ready')))['status']=='violation')
    with patch.object(v1,'thermal',return_value={'status':'unresolved','known_violations':[],'complete':False,'reason':'injected_numerical_overlap'}):
        check('thermal_unresolved_not_violation',lambda:trial('thermal_unresolved',cases['B3'])['status']=='unresolved')
    def late_thermal(*args):
        args[-1].seconds=-1
        return {'status':'safe','known_violations':[],'complete':True}
    with patch.object(v1,'thermal',side_effect=late_thermal):
        check('replay_cross_budget_not_completed_proof',lambda:trial('replay_over_budget',cases['B3'])['status']=='unresolved' and extra['replay_over_budget']['budget_status']=='exhausted')
    for name,at in [('on_release',F(40000)),('fraction_after_release',F(80001,2)),('too_early',F(79999,2))]:
        c=deepcopy(cases['B2']); c['witness_requests'][0]['time_us']=at
        r=replay(c,sem,Budget()); extra[name]=r
    check('same_time_switch_suppresses_old_release',lambda:all(not(r['mode']=='A' and r['release_us']==40000) for r in extra['on_release']['releases']) and any(r['mode']=='B' and r['release_us']==40000 for r in extra['on_release']['releases']))
    check('real_fractional_switch_preserves_old_work',lambda:any(r['mode']=='A' and r['release_us']==40000 for r in extra['fraction_after_release']['releases']) and extra['fraction_after_release']['real_violation'])
    check('early_external_request_not_plan_violation',lambda:extra['too_early']['kind']=='invalid_witness' and not extra['too_early']['real_violation'])
    check('initial_new_release_retained',lambda:any(r['release_us']==0 for r in results['B2']['witness']['releases']))
    c=deepcopy(cases['B1']); c['witness_requests']=[{'time_us':40000,'to_mode':'B'},{'time_us':80000,'to_mode':'A'}]
    rr=replay(c,sem,Budget()); extra['A_B_A']=rr
    check('finite_repeated_transition_replay',lambda:not rr['real_violation'] and rr['thermal']['status']=='safe')
    c=deepcopy(cases['B1']); c['platform']['units']['N0']['frequency_domain']='DC'
    c['platform']['opps']['N0']['H'].update(f_Hz=2000000000,V=D('0.9'))
    c['initial_states']=[s for s in c['initial_states'] if s['held_opps']['C0']=='H']
    c['fixed_plans']['B']['stages'][0]['opp']='H'
    c['fixed_plans']['A']['stages'][1].update(offset_us=0,predecessors=[])
    # A broader supplied envelope can safely include additional activity choices.
    c['fragment_superset'].extend([{'held_opps':{'C0':'H','N0':'H'},'activity_W':{'C0':1,'N0':q}} for q in [0,3]])
    check('same_frequency_concurrency_not_removed',lambda:trial('same_frequency_concurrent',c)['status']=='sustained_safe')
    c=deepcopy(cases['B1']); c['fixed_plans']['A']['stages'][0]['duration_us']=F(3999,2)
    check('noninteger_duration_not_rounded',lambda:trial('fractional_duration',c)['status']=='sustained_safe')
    check('no_refined_claim',lambda:all(r['refined_layer']=='not_implemented' for r in results.values()))
    source_text=(ROOT/'verify.py').read_text(encoding='utf-8')
    check('core_does_not_read_expected_or_old_answers',lambda:'expected.json' not in source_text and 'results/run' not in source_text and 'check_static' not in source_text)
    check('source_and_old_inputs_unchanged',lambda:before=={n:sha(p) for n,p in sources.items()} and original=={str(p.relative_to(ROOT.parent)):sha(p) for p in (ROOT.parent/'v1_precheck_draft').iterdir() if p.is_file()})
    save(output/'derived_checks.json',extra)
    (output/'inputs.json').write_bytes((PACKAGE/'inputs.json').read_bytes())
    (output/'expected.json').write_bytes((PACKAGE/'expected.json').read_bytes())
    record=dict(created_utc=datetime.now(timezone.utc).isoformat(),scope='V2 basic sufficient verification and concrete witness replay; no optimization',
                checks=checks,passed=sum(c['passed'] for c in checks),total=len(checks),all_passed=all(c['passed'] for c in checks),
                source_hashes=before,input_sha256=sha(PACKAGE/'inputs.json'),expected_sha256=sha(PACKAGE/'expected.json'),
                environment=dict(python=sys.version,platform=platform.platform()),refined_layer='not_implemented')
    save(output/'precheck.json',record)
    print(f"Precheck: {record['passed']}/{record['total']} passed",flush=True)
    for c in checks:
        if not c['passed']:
            print(c['name']+': '+c['reason'],flush=True)
    return 0 if record['all_passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['precheck'])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; do not overwrite a previous run.')
    raise SystemExit(main(args.output))
