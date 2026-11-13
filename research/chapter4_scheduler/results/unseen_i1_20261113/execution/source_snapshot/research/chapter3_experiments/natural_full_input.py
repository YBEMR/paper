"""One natural node projection, expanded by the unchanged original generator.

Only task nodes, condition/sample selection and the new case label change.
No mode, OPP, start grid, physical parameter or algorithm is modified.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
EXP = Path(__file__).resolve().parent
SOURCE = EXP/'results/whole_long_budget01/method/input_config.json'
SOURCE_SHA = '132323b4b18dd514b9baa929543d235ff91bb07026a60e7b629e1adb6aaaa5e2'
KEEP = ('A.pre', 'A.main', 'B.main', 'C.main')
ID = 'natural_small_full_domain__R1'


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def prepare(folder):
    from inputs import build_instance
    from full_domain_size import estimate
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == SOURCE_SHA
    original = json.loads(SOURCE.read_text(encoding='utf-8'))
    config = deepcopy(original)
    config['stage_catalog'] = [s for s in config['stage_catalog'] if s['id'] in KEEP]
    config['conditions'] = [{'id': 'natural_small_full_domain',
                             'group': 'one_natural_full_domain', 'overrides': {}}]
    config['samples'] = [s for s in config['samples'] if s['id'] == 'R1']
    instance = build_instance(config, ID)
    baseline = build_instance(original, 'base__R1')
    checks = {'only_declared_nodes_retained':tuple(s['id'] for s in config['stage_catalog'])==KEEP,
              'all_retained_profiles_unchanged':all(s==next(x for x in original['stage_catalog'] if x['id']==s['id']) for s in config['stage_catalog']),
              'all_retained_device_opp_modes_unchanged':all(instance['stage_modes'][k]==baseline['stage_modes'][k] for k in KEEP),
              'no_explicit_start_subset':instance.get('start_domain') is None,
              'window_400_grid_5':instance['window_ms']=='400' and instance['start_grid_ms']=='5',
              'physical_control_accuracy_defaults_unchanged':all(config[k]==original[k] for k in ('platform','execution_rules','accuracy_targets','defaults')),
              'six_executions_two_dependencies':sum(len(s['stage_instances']) for s in instance['scenarios'])==6 and sum(len(s['dependencies']) for s in instance['scenarios'])==2}
    deadlines={r['application']:r['deadline_ms'] for s in instance['scenarios'] for r in s['requests']}
    checks['natural_beta_1_3_deadlines']=deadlines=={'A':'117','B':'130','C':'117'}
    assert all(checks.values()),checks
    size=estimate(instance,config)
    # This is an admission estimate, never a matrix build or feasibility claim.
    assert size['deadline_legal_options']==613 and size['predicted_total_variables']==10956
    assert size['predicted_total_rows']==70513 and all(not s['empty_stage_option_sets'] for s in size['scenes'])
    out=Path(folder)
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True)
    save(out/'input_config.json',config);save(out/'input_instance.json',instance)
    size.update(input_sha256=hashlib.sha256((out/'input_instance.json').read_bytes()).hexdigest(),
                config_sha256=hashlib.sha256((out/'input_config.json').read_bytes()).hexdigest())
    save(out/'static_size.json',size)
    save(out/'domain_identity.json',{'state':'PASS','source_config':SOURCE.relative_to(ROOT).as_posix(),
         'source_config_sha256':SOURCE_SHA,'retained_nodes':KEEP,'checks':checks,
         'deadline_rule':'Original beta times retained CPU-H chain; chosen before any solve/energy result.',
         'raw_grid_semantics':'Every 5 ms start from release through true finish <=400 ms; no explicit subset.',
         'deadline_filter':'Only mathematically impossible end>deadline options removed by original builder.',
         'scientific_calls':0,'physical_evaluations':0,'model_builds':0})
    return size


if __name__ == '__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: natural_full_input.py NEW_PREPARATION_FOLDER')
    result=prepare(sys.argv[1])
    print(json.dumps({k:result[k] for k in ('problem_id','raw_window_legal_options',
        'deadline_legal_options','predicted_total_variables','predicted_total_rows','nonzeros_upper_bound')},ensure_ascii=False))
