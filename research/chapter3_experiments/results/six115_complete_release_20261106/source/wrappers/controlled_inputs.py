"""Byte-bound controlled-input loader. Never expands beta or edits preparation."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
INPUTS = HERE.parent / 'six115_preparation_20261105T093658Z/inputs'
SCHEMA = 'chapter3-controlled-fixed-deadline-preparation-v1'
HASHES = {
    'input_config.json': '72bfef43ccf2e9c118cf250b996e345fa54f77af18f133f0f8758f001e47cac8',
    'input_instance.json': 'dcf9d2e33898b87b63f6c7b17e1d1e4a50df2f089aacb68588530f64237a096c',
}
DEADLINES = {'A': '90', 'B': '115', 'C': '90'}

def require(value, reason):
    if not value:
        raise ValueError(reason)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def validate(config, instance):
    require(config.get('schema_version') == instance.get('schema_version') == SCHEMA, 'CONTROLLED_SCHEMA_REQUIRED')
    require(config['defaults']['deadline_beta'] is None and instance['settings']['deadline_beta'] is None, 'UNIFORM_BETA_FORBIDDEN')
    policy = config['controlled_deadline_policy']
    require(policy == instance['controlled_deadline_policy'] and policy['kind'] == 'explicit_fixed_relative_deadlines'
            and policy['relative_ms_by_application'] == DEADLINES and policy['uniform_beta'] is False,
            'CONTROLLED_DEADLINE_POLICY_DRIFT')
    require(instance['id'] == 'six115_control__R1', 'CONTROLLED_INSTANCE_ID')
    require(tuple(s['id'] for s in config['stage_catalog']) == ('A.pre', 'A.main', 'B.main', 'C.main'), 'RETAINED_STAGE_CATALOG')
    scenes = instance['scenarios']
    require(len(scenes) == 2 and all(len(s['stage_instances']) == 3 and len(s['dependencies']) == 1 for s in scenes), 'SIX_EXECUTIONS_TWO_EDGES')
    require(all(s['weight'] == '1/2' for s in scenes), 'SCENARIO_WEIGHTS')
    deadlines = {r['application']: r['deadline_ms'] for s in scenes for r in s['requests']}
    require(deadlines == DEADLINES, 'FIXED_DEADLINES_REQUIRED')
    require(all(r['deadline_ms'] == DEADLINES[r['application']] and r['release_ms'] == '0' for s in scenes for r in s['requests']), 'REQUEST_DEADLINES_OR_RELEASES')
    require(all(s['shared_stage_id'] != 'B.pre' for scene in scenes for s in scene['stage_instances']), 'B_PRE_FORBIDDEN')
    require(all(s['chain_position'] == 1 for scene in scenes for s in scene['stage_instances'] if s['shared_stage_id'] == 'B.main'), 'B_MAIN_CHAIN_POSITION_MUST_STAY_ONE')
    require(instance.get('start_domain') is None and instance['window_ms'] == '400' and instance['start_grid_ms'] == '5', 'FULL_START_DOMAIN_REQUIRED')
    require(config['preparation_contract']['execution_authorized'] is False and config['preparation_contract']['preparation_only'] is True, 'PREPARATION_AUTHORITY_MUST_REMAIN_FALSE')
    return config, instance

def load_controlled_inputs(budget=None, folder=INPUTS):
    if budget is not None: budget.check()
    values = []
    for name, expected in HASHES.items():
        raw = (Path(folder) / name).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected, 'CONTROLLED_INPUT_BYTES_DRIFT:' + name)
        values.append(json.loads(raw.decode('utf-8-sig')))
    config, instance = validate(*values)
    if budget is not None: budget.check()
    return config, instance
