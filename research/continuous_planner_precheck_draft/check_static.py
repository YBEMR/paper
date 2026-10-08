"""CP-draft-1 input and rational-algebra checks only.

Does not import an evaluator, integrate an ODE, call an optimizer, or search
candidate schedules. The declared reference structures are diagnostic fixtures.
"""
import argparse
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction as F
import hashlib
import itertools
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'), parse_float=Decimal)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def option(st, key):
    return next(o for o in st['options'] if o['option_id'] == key)


def selected(problem, ids, m):
    return {s['id']: option(s, ids[m][s['id']]) for s in problem['modes'][m]['stages']}


def extremes(problem, ids, m, extra=()):
    stages = problem['modes'][m]['stages']
    rows = selected(problem, ids, m)
    edges = {(p, s['id']) for s in stages for p in s['predecessors']} | set(extra)
    order = []; remaining = {s['id'] for s in stages}
    while remaining:
        ready = sorted(i for i in remaining if all(a not in remaining for a, b in edges if b == i))
        if not ready:
            raise ValueError('cycle in diagnostic structure')
        order.extend(ready); remaining.difference_update(ready)
    d = {i: F(o['duration_us']) for i, o in rows.items()}
    early = {}
    for i in order:
        early[i] = max([F(0)] + [early[j] + d[j] for j, k in edges if k == i])
    late = {}; deadline = F(problem['modes'][m]['relative_deadline_us'])
    for i in reversed(order):
        late[i] = min([deadline - d[i]] + [late[j] - d[i] for k, j in edges if k == i])
    mid = {i: (early[i] + late[i]) / 2 for i in rows}
    return early, mid, late


def legal(problem, ids, offsets, m):
    stages = problem['modes'][m]['stages']; rows = selected(problem, ids, m)
    deadline = F(problem['modes'][m]['relative_deadline_us']); p = problem['platform']
    end = {i: F(offsets[i]) + F(o['duration_us']) for i, o in rows.items()}
    if any(F(offsets[i]) < 0 or end[i] > deadline for i in rows):
        return False
    if any(end[a] > F(offsets[s['id']]) for s in stages for a in s['predecessors']):
        return False
    for i, j in itertools.combinations(rows, 2):
        if max(F(offsets[i]), F(offsets[j])) < min(end[i], end[j]):
            a, b = rows[i], rows[j]; ua, ub = a['unit'], b['unit']
            if ua == ub:
                return False
            if p['units'][ua]['frequency_domain'] == p['units'][ub]['frequency_domain']:
                oa, ob = p['opps'][ua][a['opp']], p['opps'][ub][b['opp']]
                if (oa['f_Hz'], oa['V']) != (ob['f_Hz'], ob['V']):
                    return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Output exists; preserve prior check records.')
    x = read(HERE/'inputs.json'); e = read(HERE/'expected.json')
    p = x['problem']; platform = p['platform']; ids = x['probes']['reference_options']
    checks = []

    def check(name, condition):
        checks.append(dict(id=name, passed=bool(condition)))

    deps = read(HERE/'DEPENDENCIES_SHA256.json')
    check('original_inputs_and_sources_unchanged', all(sha(REPO/n) == h for n, h in deps.items()))
    old = read(REPO/'research/joint_evaluator/inputs.json')
    old = next(c for c in old['cases'] if c['id'] == 'J14')
    check('physical_service_entry_evaluation_provenance',
          platform == old['candidate']['platform'] and p['semantics'] == old['candidate']['semantics']
          and p['initial_states'] == old['safety']['initial_states'] and p['evaluation'] == old['evaluation'])
    check('service_and_fork_join_DAG', all(
        0 < m['relative_deadline_us'] <= m['period_us'] <= m['minimum_switch_interval_us']
        and [s['predecessors'] for s in m['stages']] == [[], [], [k+'0', k+'1']]
        for k, m in p['modes'].items()))
    all_options = [o for m in p['modes'].values() for s in m['stages'] for o in s['options']]
    check('complete_abstract_catalog_14_rows', len(all_options) == len({o['option_id'] for o in all_options}) == 14)
    check('legal_units_OPPs_and_response_values', all(
        o['unit'] in platform['units'] and o['opp'] in platform['opps'][o['unit']]
        and F(o['duration_us']) > 0 and F(o['activity_increment_W']) >= 0
        and o['source'] == 'new_L3_row' for o in all_options))
    check('A0_NPU_is_not_in_this_fixture_catalog', not any(
        o['unit'] == 'N0' for o in p['modes']['A']['stages'][0]['options']))
    check('nonuniform_response_declared_not_inferred', all(
        F(s['options'][1]['duration_us']) != 2*F(s['options'][0]['duration_us'])
        for m in p['modes'].values() for s in m['stages']))
    check('no_implicit_time_grid', x['protocol']['time_domain'] == 'continuous_relative_offsets'
          and 'grid_us' not in x['protocol'])
    check('four_complete_initial_blocks', len(p['initial_states']) == 4 and all(
        s['phase_us'] == s['next_release_us'] == s['saturated_switch_age_us'] == s['mode_request_age_us'] == 0
        and s['pending_switch'] is None and s['unfinished_work'] == []
        and set(s['held_opps']) == set(platform['units']) for s in p['initial_states']))

    counts = {}; w = list(map(F, p['evaluation']['weights']))
    path_condition = all(v >= 0 for v in w) and sum(w) == 1
    for path in p['evaluation']['paths']:
        tr = path['trace']; window = F(tr['window_us']); mode = tr['initial_mode']; start = F(0)
        count = {m: 0 for m in p['modes']}; previous = F(0)
        for request in tr['switch_requests'] + [dict(time_us=window, to_mode=None)]:
            boundary = F(request['time_us']); release = start
            if request['to_mode'] is not None:
                path_condition &= [mode, request['to_mode']] in p['semantics']['allowed_transitions']
                path_condition &= boundary - previous >= p['modes'][mode]['minimum_switch_interval_us']
                previous = boundary
            while release < boundary:
                count[mode] += 1
                path_condition &= release + p['modes'][mode]['relative_deadline_us'] <= window
                release += p['modes'][mode]['period_us']
            start = boundary; mode = request['to_mode']
        counts[tr['id']] = count
    check('release_counts_without_scheduling', counts == e['mode_counts'])
    check('W1_and_allowed_paths', path_condition)
    weighted = {m: sum(w[k]*counts[path['trace']['id']][m] for k, path in enumerate(p['evaluation']['paths'])) for m in p['modes']}
    check('weighted_counts', weighted == {m:F(v) for m,v in e['weighted_round_counts'].items()})
    minima = {m:sum(min(F(o['activity_increment_W'])*F(o['duration_us'])/1000000 for o in s['options']) for s in plan['stages']) for m,plan in p['modes'].items()}
    check('independent_activity_minima', minima == {m:F(v) for m,v in e['independent_stage_minima_J'].items()})
    lower = sum(weighted[m]*minima[m] for m in p['modes'])
    check('original_L0_28mJ', lower == F(e['L0_J']))
    ref_act = sum(weighted[m]*sum(F(o['duration_us'])*F(o['activity_increment_W'])/1000000 for o in selected(p,ids,m).values()) for m in p['modes'])
    check('reference_activity_37mJ', ref_act == F(e['reference_Lact_J']))
    check('nonnegative_remainder_on_valid_range', F(platform['external_power_W']) >= 0 and all(
        F(o['base_W']) + F(o['leak_W_per_K'])*(F(t)-F(platform['leak_reference_C'])) >= 0
        for ops in platform['opps'].values() for o in ops.values() for t in platform['valid_temperature_C']))

    G = [[F(v) for v in row] for row in platform['G_W_per_K']]
    check('passive_positive_thermal_network', all(F(c)>0 for c in platform['C_J_per_K']) and
          G[0][1] == G[1][0] <= 0 and all(sum(row)>0 for row in G) and G[0][0]*G[1][1]-G[0][1]*G[1][0]>0)
    check('leakage_adjusted_stability_sufficient', all(sum(G[i]) > max(F(o['leak_W_per_K']) for o in platform['opps'][u].values()) for i,u in enumerate(platform['units'])))
    box = x['analysis']['certificate_box_C']
    check('box_contains_full_entry_and_below_limit', all(
        box[i][0] <= s['temperature_box_C'][i][0] <= s['temperature_box_C'][i][1] <= box[i][1] <= platform['temperature_limit_C'][i]
        for s in p['initial_states'] for i in range(2)))
    choices=[]
    for u, ops in platform['opps'].items():
        choices.append([(o,q) for o in sorted(ops) for q in sorted({F(0)} | {F(row['activity_increment_W']) for row in all_options if row['unit']==u and row['opp']==o})])
    expected_fragments=set(itertools.product(*choices))
    fragments=x['analysis']['fragment_superset']; units=list(platform['units'])
    supplied={tuple((f['held_opps'][u],F(f['activity_W'][u])) for u in units) for f in fragments}
    check('catalog_wide_fragment_coverage', expected_fragments == supplied and len(fragments)==8)

    def net(temp, f):
        return [F(platform['opps'][u][f['held_opps'][u]]['base_W']) + F(f['activity_W'][u])
                + F(platform['opps'][u][f['held_opps'][u]]['leak_W_per_K'])*(F(temp[i])-F(platform['leak_reference_C']))
                - sum(G[i][j]*(F(temp[j])-F(platform['ambient_C'])) for j in range(2)) for i,u in enumerate(units)]

    lows=[net([v[0] for v in box], f) for f in fragments]
    highs=[net([v[1] for v in box], f) for f in fragments]
    mn=[min(v) for v in zip(*lows)]; mx=[max(v) for v in zip(*highs)]
    check('full_box_exact_face_certificate', mn == list(map(F,e['reference_thermal']['minimum_lower_net_W'])) and
          mx == list(map(F,e['reference_thermal']['maximum_upper_net_W'])) and all(v>=0 for v in mn) and all(v<=0 for v in mx))
    check('narrow_box_certificate_fails_not_physics', any(v>0 for f in fragments for v in net([35,35],f)))
    all_reps={tag:{} for tag in ['E','M','L']}
    for m in p['modes']:
        reps=extremes(p,ids,m)
        for tag, offsets in zip(['E','M','L'],reps):
            all_reps[tag][m]=offsets
            check(f'{m}_{tag}_matches_hand_schedule', list(offsets[k] for k in sorted(offsets)) == e['representatives_us'][tag][m])
            check(f'{m}_{tag}_within_round_legal', legal(p,ids,offsets,m))
        check(f'{m}_midpoint_linear_feasibility', all(reps[1][i] == (reps[0][i]+reps[2][i])/2 for i in reps[0]))
    spans={tag:{m:max(F(a[i])+F(o['duration_us']) for i,o in selected(p,ids,m).items()) for m,a in modes.items()} for tag,modes in all_reps.items()}
    check('hand_round_spans', spans == e['span_us'])
    check('sufficient_deadline_conditions', {tag:all(s[a]+s[b] <= p['modes'][b]['relative_deadline_us'] for a,b in p['semantics']['allowed_transitions']) for tag,s in spans.items()} == e['sustained_deadline_sufficient'])
    for tag,s in spans.items():
        finish=max(F(41000),F(40000)+s['A'])+s['B']
        check(f'{tag}_given_switch_deadline_arithmetic', finish==e['given_witness'][tag]['finish_us'] and finish-55000==e['given_witness'][tag]['lateness_us'])
    check('late_F1_has_real_deadline_violation', max(F(45000),40000+spans['L']['A'])+spans['L']['B'] > 59000)
    check('middle_F1_F2_first_rounds_meet_deadline', max(F(45000),40000+spans['M']['A'])+spans['M']['B'] <= 59000 and 40000+spans['M']['B']<=54000)
    check('E_energy_coarse_independent_enclosure', F(e['reference_E_energy_J']['lower']) == F('0.08')+ref_act and
          F(e['reference_E_energy_J']['upper']) == F('0.08')*(1+2*F('0.002')*34)+ref_act)
    shift=F(x['probes']['fractional_shift_us']['numerator'],x['probes']['fractional_shift_us']['denominator'])
    check('fractional_microsecond_offsets_legal', shift.denominator>1 and all(legal(p,ids,{i:a+shift for i,a in all_reps['E'][m].items()},m) for m in p['modes']))
    variants=deepcopy(ids);variants['A']['A1']='A1_C0_H'
    q=extremes(p,variants,'A',[('A0','A1')])[0]
    r=extremes(p,variants,'A',[('A1','A0')])[0]
    check('CPU_alternative_both_orders_retained', q=={'A0':0,'A1':2000,'A2':3500} and r=={'A1':0,'A0':1500,'A2':3500} and legal(p,variants,q,'A') and legal(p,variants,r,'A'))
    micro=x['probes']['shared_domain']
    for c in micro['cases']:
        ua,fa,sa,da=c['a'];ub,fb,sb,db=c['b']
        overlap=max(sa,sb)<min(sa+da,sb+db)
        conflict=ua==ub or (micro['units'][ua]==micro['units'][ub] and fa!=fb)
        check('algebra_'+c['id'], (not(overlap and conflict))==c['legal'])
    chain=x['probes']['chain'];d1,d2=map(F,chain['durations_us']);h=F(chain['deadline_us'])-d1-d2
    chain_reps=[(0,d1),(h/2,d1+h/2),(h,d1+h)]
    other=tuple(map(F,chain['off_representative_offsets_us']))
    check('chain_interior_wait_missed_explicitly', other[0]+d1<other[1] and other[1]+d2<=chain['deadline_us'] and other not in chain_reps)
    mixed={'A':all_reps['E']['A'],'B':all_reps['L']['B']}
    check('mixed_modes_not_silently_generated', mixed not in all_reps.values() and all(legal(p,ids,a,m) for m,a in mixed.items()) and not x['protocol']['mixed_representatives'])
    # Boolean algebra for a signature of three selected option literals and one
    # active direction. This is not schedule enumeration or a solver call.
    check('no_good_excludes_exact_literal_conjunction', all((sum(bits)<=3)==(not all(bits)) for bits in itertools.product([0,1],repeat=4)))
    check('query_deletion_never_promotes_global_bound', x['protocol']['structure_exclusion'].startswith('query_only') and x['protocol']['bound_source'].startswith('original independent'))
    rt=x['runtime_draft']
    check('declared_budgets_bounded_not_per_call_reset', 0<rt['per_query_seconds']<=rt['total_wall_seconds'] and 0<rt['per_evaluation_seconds']<=rt['total_wall_seconds'] and rt['max_structures']==4)
    check('all_modes_three_tables_only', x['protocol']['representative_sequence']==['all_E','all_M','all_L'])
    result=dict(scope='static input and exact rational algebra only; runtime acceptance NOT executed',
        passed=all(c['passed'] for c in checks),checks=checks,passed_count=sum(c['passed'] for c in checks),total_count=len(checks),
        hashes={n:sha(HERE/n) for n in ['inputs.json','expected.json','DEPENDENCIES_SHA256.json','check_static.py']},
        expected_runtime_checks='not_run',optimizer='not_called',thermal_trajectory='not_computed')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"{result['passed_count']}/{result['total_count']} static/algebra checks passed; runtime not run")
    for c in checks:
        if not c['passed']: print('FAILED:',c['id'])
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':
    main()
