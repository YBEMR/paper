"""Predeclared beta=1 inputs; pure generation/counting, no thermal or solver call."""
from copy import deepcopy
from pathlib import Path
import sys

from research.chapter3_experiments import natural_full_entry as b

PREPARATION = b.RESULTS/'chapter3_closure_preparation01'
SOURCE = b.RESULTS/'natural_full_preparation01'
CASES = ('t50_full', 't50_no_limit', 't78_full', 't78_no_limit')


def build_inputs():
    sys.path.insert(0, str(b.EXP))
    from inputs import build_instance
    from full_domain_size import estimate
    from research.chapter3_experiments.thermal_limit_ablation import planning_instance
    old_plan = b.read(b.RESULTS/'natural_delivery_preparation01/plan.json')
    b.require(b.sha(SOURCE/'input_config.json') == old_plan['config_sha256'], 'BASE_CONFIG_DRIFT')
    b.require(b.sha(SOURCE/'input_instance.json') == old_plan['input_sha256'], 'BASE_INPUT_DRIFT')
    old_config = b.read(SOURCE/'input_config.json')
    old_instance = b.read(SOURCE/'input_instance.json')
    cases = {}
    for temperature in ('50', '78'):
        config = deepcopy(old_config)
        config['conditions'] = [{'id': 'closure_beta1_t'+temperature,
            'group': 'chapter3_evidence_closure', 'overrides': {
                'deadline_beta': '1.0', 'initial_temperature_degC': temperature}}]
        original = build_instance(config, 'closure_beta1_t'+temperature+'__R1')
        deadlines = {r['application']: r['deadline_ms'] for s in original['scenarios'] for r in s['requests']}
        b.require(deadlines == {'A':'90', 'B':'100', 'C':'90'}, 'BETA_RULE_DRIFT')
        b.require(original['stage_modes'] == old_instance['stage_modes'], 'LEGAL_MODES_DRIFT')
        b.require(original['platform'] == old_instance['platform'], 'PHYSICS_DRIFT')
        b.require(original['window_ms']=='400' and original['start_grid_ms']=='5'
                  and original.get('start_domain') is None, 'TIMING_DOMAIN_DRIFT')
        for enforce in (True, False):
            name = 't'+temperature+('_full' if enforce else '_no_limit')
            planning, declaration = planning_instance(original, enforce)
            size = estimate(planning, config)
            cases[name] = dict(config=config, instance=planning, posterior=original,
                              size=size, declaration=declaration)
    return cases


def prepare(folder=PREPARATION):
    folder = Path(folder).resolve()
    b.require(folder == PREPARATION and not folder.exists(), 'NEW_PREPARATION_REQUIRED')
    cases = build_inputs()
    manifest = {}
    for name, data in cases.items():
        dest = folder/name
        for filename, key in [('input_config.json','config'), ('input_instance.json','instance'),
                              ('posterior_instance.json','posterior'), ('static_size.json','size'),
                              ('ablation_declaration.json','declaration')]:
            b.save(dest/filename, data[key])
        manifest[name] = {key: (dest/filename).relative_to(b.ROOT).as_posix() for key, filename in (
            ('input_file','input_instance.json'), ('config_file','input_config.json'),
            ('posterior_file','posterior_instance.json'), ('static_size_file','static_size.json'),
            ('declaration_file','ablation_declaration.json'))}
        manifest[name]['sha256'] = {key:b.sha(b.ROOT/path) for key,path in manifest[name].items()}
    b.save(folder/'inputs.json', {'cases':manifest,'baseline_commit':'1659dc74',
        'changes_only':'Original beta rule 1.0; T0 50/78; optional 80C planning limit removed within original valid range.',
        'optimization_calls':0,'thermal_calls':0,'matrix_builds':0})
    return manifest


if __name__ == '__main__':
    import json
    print(json.dumps(prepare(), ensure_ascii=False))
