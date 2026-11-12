"""K168 proposal-only freeze. No scientific imports or executable run gate."""
import argparse
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BASE = 'research/chapter3_experiments/'
OLD = BASE + 'results/deadline_resume01/'
ORIGINAL_DECLARATION = BASE + 'results/deadline_execution01/declaration.json'
OLD_CALL = OLD + 'calls/beta_1.0__R2/whole_milp/'
PROTOCOL_FILE = BASE + 'whole_native_diagnostic/protocol.md'
PROTOCOL = 'K168-whole-augmented-R2-native-proposal-v1'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def fixed_plan():
    return {
        'protocol': PROTOCOL, 'problem_id': 'beta_1.0__R2',
        'method': 'whole_augmented_native_technical_diagnostic',
        'authorized': False, 'execution_ready': False,
        'status': 'PENDING_USER_CONFIRMATION',
        'research_call_limit': 1, 'native_request_limit': 1, 'max_outer_rounds': 1,
        'initial_constructor_max_attempts': 3,
        'budget': {'method_seconds': 300, 'cleanup_window_seconds': 40,
                   'method_return_watchdog_seconds': 420,
                   'slot_watchdog_seconds': 480, 'post_heat_seconds': 0,
                   'reuse_old_campaign_budget': False},
        'condition': {'response': 'H', 'entry_degC': 50, 'limit_degC': 80,
                      'deadline_beta': '1.0', 'window_ms': 400, 'start_grid_ms': 5,
                      'idle_policy': 'auto_low_immediate_v1',
                      'workload': 'complete_AB_AC_three_Stage_chains'},
        'model_flags': {'fix_late_options': True, 'aggregate_opp_locks': True,
                        'relax_auxiliary_integrality': True,
                        'strengthen_energy_lower_bounds': True,
                        'prefilter_deadlines': True, 'cumulative_precedence': False},
        'native_options': {'AbsoluteGapTolerance': 0, 'RelativeGapTolerance': 0,
                           'ConstraintTolerance': '1e-9', 'IntegerTolerance': '1e-6',
                           'IntegerPreprocess': 'none', 'LPPreprocess': 'none',
                           'CutMaxIterations': 10, 'Display': 'off',
                           'MaxTime': 'remaining_absolute_method_budget'},
        'feedback_kind': 'conditional', 'retry': False, 'extend_budget': False,
        'post_evaluation': False, 'resume_original_24': False,
        'historical_candidate_or_cache_input': False,
        'scope': 'numeric interface and original status conflict only; no method ranking'}


def source_paths(repo_root):
    root = Path(repo_root)
    names = set(read(root / (OLD + 'declaration.json'))['source_sha256'])
    names.update(BASE + name for name in (
        'whole_augmented.py', 'precheck_whole_augmented.py',
        'whole_native_diagnostic/prepare.py', 'whole_native_diagnostic/precheck.py',
        'whole_native_diagnostic/recipe.py'))
    return {name: root / name for name in sorted(names)}


def artifact_paths(repo_root):
    root = Path(repo_root)
    names = (BASE + 'config_v01.json', ORIGINAL_DECLARATION,
             OLD + 'declaration.json', OLD + 'ledger.json',
             BASE + 'results/deadline_execution01/ledger.json',
             OLD_CALL + 'input_config.json', OLD_CALL + 'input_instance.json',
             OLD_CALL + 'matlab/request_000001.input.json',
             BASE + 'results/whole_augmented_precheck01/run04/checks.json',
             BASE + 'results/whole_augmented_precheck01/independent_review/final_review02.json',
             PROTOCOL_FILE)
    return {name: root / name for name in names}


def input_contract(repo_root):
    root = Path(repo_root)
    instance = read(root / (OLD_CALL + 'input_instance.json'))
    config = read(root / (OLD_CALL + 'input_config.json'))
    raw = read(root / (BASE + 'config_v01.json'))
    declared = read(root / ORIGINAL_DECLARATION)['inputs']['beta_1.0__R2']['input_identities']
    actual = dict(zip(('raw_config_sha256', 'config_sha256', 'input_sha256'),
                      map(canonical, (raw, config, instance))))
    if actual != declared:
        raise ValueError('Stored original input canonical identity mismatch')
    rules = instance['execution_rules']
    if (instance['id'] != 'beta_1.0__R2' or instance['response_variant'] != 'H'
            or F(instance['settings']['deadline_beta']) != 1
            or F(instance['window_ms']) != 400 or F(instance['start_grid_ms']) != 5
            or rules.get('idle_policy') != 'auto_low_immediate_v1'
            or rules['idle_holds_last_opp'] is not False
            or any(any(F(x) != 50 for x in scene['entry']['temperature_degC'])
                   or any(F(x) != 80 for x in scene['maximum_temperature_degC'])
                   for scene in instance['scenarios'])):
        raise ValueError('Original R2 condition mismatch')
    return {'canonical_identities': actual, 'matches_original_R2': True,
            'new_input_construction': False, 'old_answer_or_vector_loaded': False}


def make_declaration(repo_root):
    root = Path(repo_root)
    plan = fixed_plan()
    return {'protocol': PROTOCOL, 'plan': plan, 'plan_sha256': canonical(plan),
            'source_sha256': {name: sha(path) for name, path in source_paths(root).items()},
            'artifact_sha256': {name: sha(path) for name, path in artifact_paths(root).items()},
            'input_contract': input_contract(root), 'approval': None,
            'research_calls_consumed': 0, 'native_requests_consumed': 0,
            'scientific_work_performed': False}


def validate(repo_root, declaration):
    root = Path(repo_root).resolve()
    errors = []
    if declaration.get('protocol') != PROTOCOL or declaration.get('plan') != fixed_plan():
        errors.append('FIXED_PLAN_DRIFT_OR_NOT_PENDING')
    if declaration.get('plan_sha256') != canonical(declaration.get('plan')):
        errors.append('PLAN_IDENTITY_MISMATCH')
    if (declaration.get('approval') is not None
            or declaration.get('research_calls_consumed') != 0
            or declaration.get('native_requests_consumed') != 0
            or declaration.get('scientific_work_performed') is not False):
        errors.append('PROPOSAL_STATE_NOT_ZERO_OR_UNAPPROVED')
    for field, expected in (('source_sha256', source_paths(root)),
                            ('artifact_sha256', artifact_paths(root))):
        values = declaration.get(field)
        if not isinstance(values, dict) or set(values) != set(expected):
            errors.append(field + ':INVENTORY_MISMATCH')
            continue
        for name, path in expected.items():
            if not path.is_file() or sha(path) != values[name]:
                errors.append(field + ':DRIFT:' + name)
    try:
        if declaration.get('input_contract') != input_contract(root):
            errors.append('INPUT_CONTRACT_DRIFT')
    except (OSError, KeyError, TypeError, ValueError) as error:
        errors.append('INPUT_CONTRACT_ERROR:' + str(error))
    return {'passed': not errors, 'errors': errors,
            'launch_authorized': False, 'scientific_calls': 0}


def prepare(repo_root, out):
    target = Path(out)
    if target.exists():
        raise FileExistsError('A new preparation directory is required')
    declaration = make_declaration(repo_root)
    verified = validate(repo_root, declaration)
    if not verified['passed']:
        raise ValueError(verified['errors'])
    target.mkdir(parents=True, exist_ok=False)
    values = {'declaration.json': declaration,
              'validation.json': verified,
              'ledger.json': {'protocol': PROTOCOL, 'state': 'PENDING_USER_CONFIRMATION',
                              'research_calls_consumed': 0, 'native_requests_consumed': 0,
                              'reserved_method_seconds': 0, 'claim': None,
                              'remaining_original_campaign': 24}}
    for name, value in values.items():
        with (target / name).open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
    return deepcopy(declaration)


def request_run(*args, **kwargs):
    raise PermissionError('PENDING_USER_CONFIRMATION: proposal-only; no research launcher')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'run'))
    parser.add_argument('--out', type=Path)
    parser.add_argument('--declaration', type=Path)
    args = parser.parse_args()
    if args.mode == 'run':
        request_run()
    if args.mode == 'prepare':
        if args.out is None:
            parser.error('prepare requires --out')
        data = prepare(ROOT, args.out)
        print(json.dumps({'status': data['plan']['status'], 'consumed': 0}))
    else:
        if args.declaration is None:
            parser.error('verify requires --declaration')
        result = validate(ROOT, read(args.declaration))
        print(json.dumps(result, ensure_ascii=False))
        if not result['passed']:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
