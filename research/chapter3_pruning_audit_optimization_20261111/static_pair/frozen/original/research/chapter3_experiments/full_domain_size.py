"""Pure structural counts for the unchanged whole MILP (no physical coefficients).

Counts follow milp.build_model with deadline prefilter, aggregate OPP locks,
relaxed auxiliary integrality and energy lower bounds. No model, matrices,
coefficient kernel, schedule search or thermal evaluator is imported/called.
"""
from collections import Counter, defaultdict
from fractions import Fraction as Q
from itertools import product
import hashlib
import json
from pathlib import Path
import sys


def estimate(instance, config):
    # inputs only expands exact local options; it does not solve a schedule.
    from inputs import expand_options
    if instance['execution_rules']['idle_policy'] != 'auto_low_immediate_v1':
        raise ValueError('This counter is scoped to the existing auto-L whole formulation')
    raw = expand_options(instance, config)
    options = [o for o in raw if Q(o['end_ms']) <= Q(o['request_deadline_ms'])]
    p = instance['platform']; domains = p['domains']; nodes = p['node_order']
    units = {u['id']: u for u in p['units']}
    n, d, r = len(nodes), len(domains), sum(len(v['opps']) for v in domains.values())
    shared_units = {stage: sorted({m['unit_id'] for m in modes})
                    for stage, modes in instance['stage_modes'].items()}
    nx = sum(map(len, shared_units.values()))
    total_vars = len(options) + nx
    total_rows = 2*len(shared_units)
    structural_nnz = 2*nx
    physical_nnz_upper = 0
    coefficient_keys = set()
    scenes = []
    for scene in instance['scenarios']:
        chosen = [o for o in options if o['scenario_id'] == scene['id']]
        by_stage = {stage['id']: [] for stage in scene['stage_instances']}
        starts, ends = defaultdict(list), defaultdict(list)
        for i, o in enumerate(chosen):
            by_stage[o['stage_instance_id']].append(o)
            starts[Q(o['start_ms'])].append(i); ends[Q(o['end_ms'])].append(i)
        events = sorted({Q(0), Q(instance['window_ms']), *starts, *ends})
        k = len(events)-1
        rows = nnz = 0
        for stage in scene['stage_instances']:
            stage_options = by_stage[stage['id']]
            su = shared_units[stage['shared_stage_id']]
            rows += 3 + 2*len(su)
            nnz += 5*len(stage_options) + 2*len(su)
        for before, after in scene['dependencies']:
            rows += 1
            nnz += len(by_stage[before]) + sum(Q(o['start_ms']) != 0 for o in by_stage[after])
        active = set(); sum_states = sum_locks = 0
        state_hist = Counter(); duration_hist = Counter(); scene_states = set()
        for left, right in zip(events, events[1:]):
            active.difference_update(ends.get(left, [])); active.update(starts.get(left, []))
            here = [chosen[i] for i in active]
            unit_counts = Counter(o['unit_id'] for o in here)
            lock_counts = Counter((o['unit_id'], o['opp_id']) for o in here)
            domain_opp_counts = Counter((units[o['unit_id']]['domain_id'], o['opp_id']) for o in here)
            possible = [sorted({'L'} | {opp for (dom,opp) in domain_opp_counts if dom == did})
                        for did in domains]
            states = list(product(*possible)); ns = len(states)
            sum_states += ns; state_hist[ns] += 1; scene_states.update(states)
            duration_hist[str((right-left)/1000)] += 1
            coefficient_keys.update((state, (right-left)/1000) for state in states)
            starting_count = len(starts.get(left, [])); sum_locks += len(lock_counts)
            # Mutex, domain one-hot, trigger OR, auto-L support, aggregate
            # locks, joint one-hot and marginals; every eq exports two rows.
            rows += len(units) + 2*d + d + starting_count + (r-d) + len(lock_counts) + 2 + 2*r
            nnz += sum(unit_counts.values()) + 2*r + (d+3*starting_count)
            nnz += sum(1+domain_opp_counts[did,opp] for did,v in domains.items() for opp in v['opps'] if opp!='L')
            nnz += sum(1+count for count in lock_counts.values()) + 2*ns + 2*(r+d*ns)
            # Exact row count for q equalities, four thermal + one energy
            # conditional equality per joint state, and one energy bound.
            rows += 2*n + 2*(n+1)*ns + 1
            # Structural nnz above omits all numerical physical rows. Count
            # their maximum width; coefficient zeros may reduce the actual.
            physical_nnz_upper += 2*(n+len(here)) + 2*(n+1)*ns*(2*n+2) + (2*n+1+ns)
        rows += 2*n
        physical_nnz_upper += 2*n
        variables = (r+d)*k + sum_states + n*(k+1) + n*k + k
        total_vars += variables; total_rows += rows; structural_nnz += nnz
        scenes.append({'id':scene['id'], 'stage_executions':len(scene['stage_instances']),
                       'dependencies':len(scene['dependencies']), 'retained_options':len(chosen),
                       'events':len(events), 'intervals':k,
                       'event_times_ms':list(map(str,events)),
                       'event_times_s_sha256':hashlib.sha256(json.dumps([str(e/1000) for e in events],
                           ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
                       'joint_state_variables':sum_states, 'joint_state_count_histogram':dict(sorted(state_hist.items())),
                       'distinct_joint_states':len(scene_states), 'distinct_interval_durations':len(duration_hist),
                       'aggregate_lock_rows':sum_locks, 'variables_excluding_local_options_and_shared':variables,
                       'rows_excluding_shared_unique':rows,
                       'empty_stage_option_sets':[key for key,val in by_stage.items() if not val]})
    return {'schema':'whole-auto-low-pure-size-v1', 'problem_id':instance['id'],
            'explicit_start_domain_present':instance.get('start_domain') is not None,
            'raw_window_legal_options':len(raw), 'deadline_legal_options':len(options),
            'deadline_proven_impossible_options_removed':len(raw)-len(options),
            'stage_binary_variables':len(options), 'shared_deployment_variables':nx,
            'predicted_total_variables':total_vars, 'predicted_total_rows':total_rows,
            'nonzeros_upper_bound':structural_nnz+physical_nnz_upper,
            'nonzeros_bound_scope':'Exact nonphysical nonzeros + maximum numerical row widths; not an actual matrix count.',
            'unique_state_duration_coefficient_keys':len(coefficient_keys),
            'coefficient_lookup_visits':sum(s['joint_state_variables'] for s in scenes),
            'scenes':scenes,
            'builder_flags':{'prefilter_deadlines':True,'aggregate_opp_locks':True,
                'relax_auxiliary_integrality':True,'strengthen_energy_lower_bounds':True,
                'include_physics':True,'cumulative_precedence':False,'fixed_deployment':None},
            'scope':'Exact structural loop counts, assuming unchanged builder flags; no numerical matrix or feasibility certificate.',
            'scientific_operations':{'model_builds':0,'coefficient_generations':0,'searches':0,'thermal_evaluations':0}}


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('Usage: full_domain_size.py INPUT_JSON CONFIG_JSON NEW_OUTPUT_JSON')
    input_path, config_path, output_path = map(Path,sys.argv[1:])
    result=estimate(json.loads(input_path.read_text(encoding='utf-8')),
                    json.loads(config_path.read_text(encoding='utf-8')))
    result['input_sha256']=hashlib.sha256(input_path.read_bytes()).hexdigest()
    result['config_sha256']=hashlib.sha256(config_path.read_bytes()).hexdigest()
    output_path.parent.mkdir(parents=True,exist_ok=True)
    with output_path.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(result,ensure_ascii=False))
