"""Pure identities, immutable receipts, approval and evidence checks."""
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREPARATION = ROOT/'research/chapter3_method_entry_preparation/results/frozen_entry02'
PREPARATION_SHA = '0c9b6cf81b9154c1f04c5da7286f3eecec6e6eb272142f580a19f8379b47132d'
INPUT_SHA = '07e458f3f811746f78931a340d258e230a8de4afb62ac0140459feff6a7bf80a'
METHODS = ('whole_milp', 'heft', 'sa101')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False, default=str).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False, default=str)
        f.write('\n')


def verify_sources(plan):
    for rel, h in plan['source_sha256'].items():
        p = (ROOT/rel).resolve()
        require(p.is_relative_to(ROOT.resolve()) and sha(p) == h, 'SOURCE_HASH_DRIFT:'+rel)


def validate_plan(plan):
    from research.chapter3_method_entry_preparation.prepare import validate_plan as prior_validate
    require(plan.get('schema') == 'ch3-one-shot-method-executor-v1'
            and plan.get('execution_authorized') is False
            and plan.get('real_execution_entry_present') is True, 'EXECUTION_PLAN_SCHEMA')
    proxy = deepcopy(plan)
    proxy.update(schema='ch3-small-method-entry-proposal-v1', real_execution_entry_present=False)
    prior_validate(proxy)
    require(plan['common_input_sha256'] == INPUT_SHA
            and plan['preparation_plan_sha256'] == PREPARATION_SHA
            and plan['memory_sampling_seconds'] == 1, 'FROZEN_SCOPE_DRIFT')
    require(plan['common_input_file'] == 'common_input.json', 'COMMON_PATH_DRIFT')


def load_context(plan_dir, expected_plan_sha, authorization_path, *, verify_sources=True):
    """Real run gate: current stage only supplies an authorization=false template."""
    folder = Path(plan_dir).resolve()
    require(sha(folder/'plan.json') == expected_plan_sha, 'PLAN_HASH_DRIFT')
    plan = read(folder/'plan.json'); validate_plan(plan)
    auth = read(authorization_path)
    require(auth.get('schema') == 'ch3-one-shot-user-approval-v1'
            and auth.get('authorized') is True and auth.get('approved_by') == 'USER'
            and isinstance(auth.get('approval_basis'), str) and bool(auth['approval_basis'].strip()),
            'SEPARATE_USER_APPROVAL_REQUIRED')
    require(auth.get('plan_sha256') == expected_plan_sha
            and auth.get('common_input_sha256') == INPUT_SHA
            and auth.get('scope') == {'method_calls': 3, 'method_seconds': 900,
                'post_calls': 3, 'post_seconds': 180, 'batch_wall_seconds': 1800}, 'APPROVAL_SCOPE_DRIFT')
    if verify_sources:
        globals()['verify_sources'](plan)
    context = {'plan': plan, 'plan_dir': folder, 'plan_sha256': expected_plan_sha,
               'common_path': folder/'common_input.json', 'authorization_path': Path(authorization_path).resolve(),
               'authorized': True, 'simulation_only': False}
    verify_input(context)
    return context


def verify_input(context):
    p = Path(context['common_path'])
    require(sha(p) == context['plan']['common_input_sha256'] == INPUT_SHA, 'INPUT_HASH_DRIFT')
    value = read(p)
    from research.chapter3_method_entry_preparation.prepare import validate_common_input
    validate_common_input(value)
    require(canonical(value['config']) == context['plan']['config_sha256']
            and canonical(value['instance']) == context['plan']['instance_sha256'], 'INPUT_IDENTITY_DRIFT')
    return value


def inspect_safe_receipt(instance, raw, cutoff_s=300):
    """Inspect already formed evidence only; no new legality/thermal evaluation."""
    out = {'preserved': False, 'reason': 'NO_COMPLETE_TIMELY_SAFE', 'U_J': None,
           'formed_at_s': None, 'candidate': None, 'evaluation': None}
    try:
        candidate, ev = raw.get('safe_candidate'), raw.get('evaluation')
        if not candidate or not isinstance(ev, dict): return out
        formed = ev.get('completed_at_elapsed_s')
        require(type(formed) in (int, float) and math.isfinite(formed)
                and 0 <= formed < cutoff_s, 'SAFE_NOT_TIMELY')
        require(ev.get('state') == 'SAFE' and ev.get('rankable_energy') is True
                and ev.get('evidence_identity') == {'input_sha256': canonical(instance),
                                                  'candidate_sha256': canonical(candidate)}, 'SAFE_IDENTITY_OR_STATE')
        scenes = {s['id']: s for s in instance['scenarios']}
        require(set(ev.get('scenes', {})) == set(scenes), 'SAFE_SCENE_COVERAGE')
        low = high = F(0)
        for sid, spec in scenes.items():
            s = ev['scenes'][sid]
            require(s.get('state') == 'SAFE' and s.get('complete') is True
                    and F(s['covered_until_s']) == F(instance['window_ms'])/1000, 'SAFE_WINDOW_INCOMPLETE')
            a,b = map(F, s['energy_J']); require(a <= b, 'SCENE_ENERGY_ORDER')
            low += F(spec['weight'])*a; high += F(spec['weight'])*b
        a,b = map(F, ev['weighted_energy_J'])
        require(a <= low <= high <= b and F(ev['safe_upper_bound_J']) == b
                and F(raw['safe_upper_bound_J']) == b, 'SAFE_ENERGY_MISMATCH')
        legality = ev.get('legality', {})
        require(legality.get('state') == 'SCHEDULE_VALID_THERMAL_UNCHECKED', 'SAFE_LEGALITY_RECEIPT_MISSING')
        out.update(preserved=True, reason='EXISTING_COMPLETE_TIMELY_SAFE', U_J=str(ev['safe_upper_bound_J']),
                   formed_at_s=formed, candidate=deepcopy(candidate), evaluation=deepcopy(ev))
    except (ValueError, TypeError, KeyError, ArithmeticError) as error:
        out['reason'] = str(error)
    return out


def recover_archived_safe(instance, worker_out, cutoff_s=300):
    """Retain a completed result/checkpoint after worker failure, without repair."""
    out = Path(worker_out)
    choices = [('method_result', out/'method/result.json'),
               ('initial_checkpoint', out/'method/initial_receipt_checkpoint.json')]
    found = []
    for source, path in choices:
        if not path.is_file(): continue
        try:
            raw = read(path)
            if source == 'initial_checkpoint':
                witness = raw.get('initialisation', {}).get('witness') or {}
                ev = witness.get('evaluation')
                raw = {'safe_candidate': witness.get('candidate'), 'evaluation': ev,
                       'safe_upper_bound_J': (ev or {}).get('safe_upper_bound_J')}
            evidence = inspect_safe_receipt(instance, raw, cutoff_s)
            if evidence['preserved']:
                found.append(dict(evidence, archive_source=source, archive_sha256=sha(path)))
        except (ValueError, OSError):
            continue
    return min(found, key=lambda e: F(e['U_J'])) if found else {
        'preserved': False, 'reason': 'NO_VERIFIABLE_ARCHIVED_SAFE', 'U_J': None}
