"""Fixture-specific static/rational checks. No V2 evaluator or thermal simulation."""
import argparse
from decimal import Decimal
from fractions import Fraction as F
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import itertools
import json


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text(encoding='utf-8'), parse_float=Decimal)


def span(plan):
    return max(F(s['offset_us']) + F(s['duration_us']) for s in plan['stages'])


def deadline_pass(c, transitions):
    plans = c['fixed_plans']
    return (all(0 < p['relative_deadline_us'] <= p['period_us'] <= p['minimum_switch_interval_us']
                and span(p) <= p['relative_deadline_us'] for p in plans.values())
            and all(span(plans[a]) + span(plans[b]) <= plans[b]['relative_deadline_us']
                    for a, b in transitions))


def fragment_keys(c):
    """Superset induced only by initial/plan OPPs and Stage activity choices."""
    units = list(c['platform']['units'])
    choices = []
    for u in units:
        opps = {s['held_opps'][u] for s in c['initial_states']}
        stages = [s for p in c['fixed_plans'].values() for s in p['stages'] if s['unit'] == u]
        opps.update(s['opp'] for s in stages)
        choices.append([(o, q) for o in sorted(opps)
                        for q in sorted({F(0)} | {F(s['activity_increment_W']) for s in stages if s['opp'] == o})])
    return units, set(itertools.product(*choices))


def supplied_keys(c):
    units = list(c['platform']['units'])
    return [tuple((f['held_opps'][u], F(f['activity_W'][u])) for u in units)
            for f in c['fragment_superset']]


def net(c, temperature, fragment):
    p = c['platform']
    t = list(map(F, temperature))
    answer = []
    for k, node in enumerate(p['nodes']):
        u = next(u for u, v in p['units'].items() if v['node'] == node)
        o = p['opps'][u][fragment['held_opps'][u]]
        power = F(o['base_W']) + F(fragment['activity_W'][u]) + F(o['leak_W_per_K']) * (t[k]-F(p['leak_reference_C']))
        answer.append(power - sum(F(g)*(tj-F(p['ambient_C'])) for g, tj in zip(p['G_W_per_K'][k], t)))
    return answer


def extrema(c):
    lo, hi = zip(*c['certificate_box_C'])
    lower = [net(c, lo, f) for f in c['fragment_superset']]
    upper = [net(c, hi, f) for f in c['fragment_superset']]
    return [min(v) for v in zip(*lower)], [max(v) for v in zip(*upper)]


def plans_legal(c):
    units, opps = c['platform']['units'], c['platform']['opps']
    for p in c['fixed_plans'].values():
        stages = {s['id']: s for s in p['stages']}
        if len(stages) != len(p['stages']):
            return False
        for s in stages.values():
            if s['unit'] not in units or s['opp'] not in opps[s['unit']]:
                return False
            if not (s['duration_us'] > 0 and s['offset_us'] >= 0 and s['activity_increment_W'] >= 0):
                return False
            for pred in s['predecessors']:
                if pred not in stages or span({'stages': [stages[pred]]}) > s['offset_us']:
                    return False
        for a, b in itertools.combinations(stages.values(), 2):
            if max(a['offset_us'], b['offset_us']) < min(span({'stages':[a]}), span({'stages':[b]})):
                if a['unit'] == b['unit']:
                    return False
                if units[a['unit']]['frequency_domain'] == units[b['unit']]['frequency_domain']:
                    oa, ob = opps[a['unit']][a['opp']], opps[b['unit']][b['opp']]
                    if (oa['f_Hz'], oa['V']) != (ob['f_Hz'], ob['V']):
                        return False
    return True


def run(root):
    x, y = read(root/'inputs.json'), read(root/'expected.json')
    cases = {c['id']: c for c in x['fixtures']}
    b1, b2, b3, b4 = (cases[k] for k in ['B1','B2','B3','B4'])
    e = y['fixtures']
    out = []

    def check(name, fn):
        try:
            ok = bool(fn())
            detail = '' if ok else 'Static/algebraic expectation not satisfied.'
        except Exception as exc:
            ok, detail = False, f'{type(exc).__name__}: {exc}'
        out.append(dict(name=name, passed=ok, detail=detail))

    source = root/x['source']['path']
    old = read(source)
    check('original_V1_hash', lambda: sha(source) == x['source']['sha256'] == 'c20fd2003cb77c2978bcae081355a96e905e53a39a2109b75fe9c6f8d66973e3')
    check('version_and_fixture_identity', lambda: x['version'] == y['version'] and set(cases) == set(e))
    check('execution_rules_unchanged', lambda: x['semantics'] == old['semantics'])
    check('B1_only_deadline_differs_from_V1_plan', lambda: all(
        dict(p, relative_deadline_us=12000) == old['fixed_plans'][m] and p['relative_deadline_us'] == 14000
        for m, p in b1['fixed_plans'].items()) and b1['platform'] == old['platform'])
    check('B2_original_plan_and_platform', lambda: b2['platform'] == old['platform'] and b2['fixed_plans'] == old['fixed_plans'])
    check('B4_same_problem_only_certificate_changed', lambda: all(b4[k] == b1[k] for k in ['platform','fixed_plans','initial_states','fragment_superset','witness_requests']))
    check('fixed_plan_legality', lambda: all(plans_legal(c) for c in cases.values()))
    required = {'actual_mode','pending_switch','temperature_box_C','held_opps','phase_us','next_release_us','mode_request_age_us','saturated_switch_age_us','unfinished_work','instant'}
    check('complete_entry_fields', lambda: all(required <= set(s) for c in cases.values() for s in c['initial_states']))
    check('entry_clock_and_pending_consistency', lambda: all(s['actual_mode'] in c['fixed_plans'] and s['pending_switch'] is None and s['unfinished_work'] == [] and all(s[k] == 0 for k in ['phase_us','next_release_us','mode_request_age_us','saturated_switch_age_us']) for c in cases.values() for s in c['initial_states']))
    check('B1_four_discrete_entry_blocks', lambda: {(s['actual_mode'],s['held_opps']['C0']) for s in b1['initial_states']} == set(itertools.product(['A','B'],['H','L'])) and len(b1['initial_states']) == 4)
    check('entry_OPPs_legal', lambda: all(set(s['held_opps']) == set(c['platform']['units']) and all(o in c['platform']['opps'][u] for u,o in s['held_opps'].items()) for c in cases.values() for s in c['initial_states']))
    check('entry_and_box_temperature_inclusions', lambda: all(len(s['temperature_box_C']) == len(c['platform']['nodes']) and all(c['platform']['valid_temperature_C'][0] <= l <= a <= b <= h <= limit <= c['platform']['valid_temperature_C'][1] for (a,b),(l,h),limit in zip(s['temperature_box_C'],c['certificate_box_C'],c['platform']['temperature_limit_C'])) for c in cases.values() for s in c['initial_states']))
    check('passive_RC_and_nonnegative_leak', lambda: all(all(F(cap)>0 for cap in c['platform']['C_J_per_K']) and all(F(g)==F(c['platform']['G_W_per_K'][j][i]) and (i==j or F(g)<=0) for i,row in enumerate(c['platform']['G_W_per_K']) for j,g in enumerate(row)) and all(sum(map(F,row))>0 for row in c['platform']['G_W_per_K']) and all(F(o['leak_W_per_K'])>=0 for opts in c['platform']['opps'].values() for o in opts.values()) for c in cases.values()))
    check('idle_power_nonnegative_in_valid_region', lambda: all(F(o['base_W'])+F(o['leak_W_per_K'])*(F(t)-F(c['platform']['leak_reference_C']))>=0 for c in cases.values() for opts in c['platform']['opps'].values() for o in opts.values() for t in c['platform']['valid_temperature_C']))
    check('complete_fragment_supersets_no_duplicates', lambda: all(set(supplied_keys(c)) == fragment_keys(c)[1] and len(supplied_keys(c)) == len(set(supplied_keys(c))) for c in cases.values()))
    check('B1_eight_fragments', lambda: len(b1['fragment_superset']) == e['B1']['fragments'] == 8)
    check('B1_spans_and_zero_transition_slack', lambda: {m:span(p) for m,p in b1['fixed_plans'].items()} == e['B1']['spans_us'] and all(b1['fixed_plans'][n]['relative_deadline_us']-span(b1['fixed_plans'][m])-span(b1['fixed_plans'][n]) == e['B1']['edge_slack_us'][m+'->'+n] for m,n in x['semantics']['allowed_transitions']))
    check('deadline_sufficient_pass_pattern', lambda: [deadline_pass(c,x['semantics']['allowed_transitions']) for c in [b1,b2,b3,b4]] == [True,False,True,True])
    check('B1_boundary_net_exact', lambda: extrema(b1) == (list(map(F,e['B1']['minimum_lower_net_W'])),list(map(F,e['B1']['maximum_upper_net_W']))))
    check('B1_box_all_faces_inward', lambda: all(q>=0 for q in extrema(b1)[0]) and all(q<=0 for q in extrema(b1)[1]))
    check('B4_box_failure_without_problem_change', lambda: extrema(b4)[1] == list(map(F,e['B4']['maximum_upper_net_W'])) and any(q>0 for q in extrema(b4)[1]) and e['B4']['not_infeasible'])
    w = e['B2']['witness']
    check('B2_switch_legality', lambda: b2['witness_requests'] == [{'time_us':41000,'to_mode':'B'}] and 41000>=b2['fixed_plans']['A']['minimum_switch_interval_us'] and w['old_release_us']<w['new_release_us'])
    check('B2_F3_arithmetic', lambda: w['old_release_us']+span(b2['fixed_plans']['A']) == w['old_finish_us'] and max(w['new_release_us'],w['old_finish_us'])+span(b2['fixed_plans']['B']) == w['new_finish_us'] and w['new_release_us']+b2['fixed_plans']['B']['relative_deadline_us'] == w['new_deadline_us'] and w['new_finish_us']-w['new_deadline_us'] == w['lateness_us'] == 1000)
    p = b3['platform']; o = p['opps']['C0']['H']; st = b3['fixed_plans']['A']['stages'][0]
    g, leak, cap = F(p['G_W_per_K'][0][0]), F(o['leak_W_per_K']), F(p['C_J_per_K'][0])
    a = (g-leak)/cap
    equilibrium = (F(o['base_W'])+F(st['activity_increment_W']))/(g-leak)
    t = F(b3['thermal_witness']['time_us'],1000000)
    exponential_upper = 1/(1+a*t)
    lower = F(p['ambient_C'])+(equilibrium+(F(b3['thermal_witness']['initial_temperature_C'][0])-F(p['ambient_C'])-equilibrium)*exponential_upper)
    check('B3_closed_form_coefficients', lambda: a==F(e['B3']['a_per_s']) and equilibrium==F(e['B3']['theta_equilibrium_K']) and a*t==F(e['B3']['x_at_witness']))
    check('B3_rational_strict_thermal_witness', lambda: a*t>0 and equilibrium>5 and exponential_upper==F(e['B3']['exp_upper']) and lower==F(e['B3']['witness_temperature_strict_lower_C']) and lower>p['temperature_limit_C'][0] and t==F(st['duration_us'],1000000))
    check('B3_witness_reachable_and_in_valid_model', lambda: b3['initial_states'][0]['temperature_box_C'][0][0]<=30<=b3['initial_states'][0]['temperature_box_C'][0][1] and p['ambient_C']==p['leak_reference_C']==25 and 30<25+equilibrium<p['valid_temperature_C'][1] and b3['witness_requests']==[])
    check('status_and_event_contract_present_not_executed', lambda: {p['id'] for p in x['status_probes']} == {'S1','S2','S3','S4','S5'} and {p['id'] for p in y['event_obligations']} == {'R1','R2','R3','R4','R5'})
    check('numerical_overlap_probe', lambda: F(x['status_probes'][0]['enclosure_C'][0]) < 35 < F(x['status_probes'][0]['enclosure_C'][1]) and x['status_probes'][0]['expected']=='unresolved')
    manifest = []
    for line in (root/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        digest,name=line.split('  ',1); manifest.append((digest,name))
    check('package_manifest', lambda: {n for _,n in manifest}=={'README.md','inputs.json','expected.json','check_static.py'} and all(sha(root/n)==d for d,n in manifest))
    return dict(version=x['version'],scope='static and exact rational algebra only; no V2 execution or simulation',created_utc=datetime.now(timezone.utc).isoformat(),checks=out,passed=sum(r['passed'] for r in out),total=len(out),all_passed=all(r['passed'] for r in out),source_hashes={n:sha(root/n) for _,n in manifest},not_executed=['V2 basic verifier','V2 refined verifier','finite thermal replay','budget/numerical injection','schedule optimization'])


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.output and args.output.exists():
        parser.error('Output exists; historical records are not overwritten.')
    result=run(Path(__file__).resolve().parent)
    if args.output:
        with args.output.open('x',encoding='utf-8') as f:
            json.dump(result,f,ensure_ascii=False,indent=2); f.write('\n')
    print(f"Static/algebra only: {result['passed']}/{result['total']} passed")
    for r in result['checks']:
        if not r['passed']:
            print(r['name']+': '+r['detail'])
    raise SystemExit(0 if result['all_passed'] else 1)
