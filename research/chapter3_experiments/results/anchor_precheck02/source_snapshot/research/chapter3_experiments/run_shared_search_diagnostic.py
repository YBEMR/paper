"""One K116 base__R1 diagnostic, 900 s total and fixed 60 s scene slices.

--prepare freezes admission and sources without constructing any instance or
candidate. --run consumes the unique stage claim once. No retry or extension.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SECONDS = 900
SLICE_SECONDS = 60
PROBLEM = 'base__R1'
CLAIM = HERE/'results/shared_search_diagnostic_claim01.json'
MOCK_GATE = HERE/'results/shared_search_precheck04/checks.json'
NATIVE_GATE = HERE/'results/shared_search_native01/verification.json'
CONFIG_SHA = '615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    default=str, allow_nan=False)+'\n', encoding='utf-8')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def gate_admission():
    """Only byte/receipt checks; no workload expansion, heat or optimization."""
    mock, native = read(MOCK_GATE), read(NATIVE_GATE)
    if not mock['passed'] or mock['count'] != 57 or not native['passed'] or native['count'] != 13:
        raise ValueError('K115 necessary admission did not pass')
    if mock['source_sha256'] != native['source_sha256']:
        raise ValueError('Mock/native source maps differ')
    for name, expected in mock['source_sha256'].items():
        if sha(REPO/name) != expected:
            raise ValueError('Stale admitted source: '+name)
    if native['gate_sha256'] != sha(MOCK_GATE) or sha(HERE/'config_v01.json') != CONFIG_SHA:
        raise ValueError('Gate or frozen input mismatch')
    if CLAIM.exists():
        raise FileExistsError('K116 research invocation already consumed; no retry')
    files = dict(mock['source_sha256'])
    files[Path(__file__).resolve().relative_to(REPO).as_posix()] = sha(__file__)
    return files, {'mock_gate': MOCK_GATE.relative_to(REPO).as_posix(),
        'mock_sha256': sha(MOCK_GATE), 'native_gate': NATIVE_GATE.relative_to(REPO).as_posix(),
        'native_sha256': sha(NATIVE_GATE)}


def prepare(out):
    out = out.resolve(); out.relative_to(REPO)
    sources, gates = gate_admission()
    out.mkdir(parents=True, exist_ok=False)
    for name in sources:
        target = out/'source_snapshot'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO/name, target)
    declaration = {'protocol': 'K116-base-R1-autoL-shared-first-pass-900s-v1',
        'state': 'DECLARED_NOT_RUN', 'problem_id': PROBLEM,
        'budget_s': SECONDS, 'scene_slice_s': SLICE_SECONDS, 'research_calls': 1,
        'shared_conditions': 'all 16 nominal A.pre/A.main/A.post unit assignments; no symmetry deletion',
        'ordering': 'A.main-unit grouped round robin; L_a then pre/main/post canonical keys',
        'one_worker': True, 'one_budget_before_input': True, 'condition_revisits': 0,
        'input_recipe': 'load_config; build_instance(raw,base__R1); explicit autoL copies inside budget',
        'physical_parameter_override': False, 'starts_override': None,
        'initial_temperature_degC': '50', 'temperature_limit_degC': '80',
        'window_ms': '400', 'start_grid_ms': '5',
        'retry_allowed': False, 'budget_extension_allowed': False,
        'reference_candidate_witness_cache_shared': False, 'formal_comparison': False,
        'source_sha256': sources, 'admission': gates,
        'unbilled_scope': 'imports; source/admission snapshots; method cleanup and read-only analysis separately reported',
        'billed_scope': 'fresh input/expansion, all bounds, construction, initialization, startup, transport, solve, heat evaluation, feedback and live reporting',
        'authorization': {'basis': 'user 下一步吧, continuing K115 final single 15-minute full-chain diagnostic',
            'protocol_record': 'research/第三章当前进展与正式实验推进计划_审查稿.md K.114',
            'scope': 'one unchanged base__R1 invocation, not old batches or new conditions'},
        'declared_at_utc': datetime.now(timezone.utc).isoformat()}
    save(out/'declaration.json', declaration)
    save(out/'admission.json', {'passed': True, 'source_sha256': sources,
        'declaration_sha256': sha(out/'declaration.json'), 'gates': gates,
        'scope': 'static admission only; no model, trajectory, solver or research call'})
    save(out/'environment.json', {'python': sys.version, 'platform': platform.platform(),
                                 'recorded_at_utc': datetime.now(timezone.utc).isoformat()})
    print(json.dumps({'prepared': True, 'source_count': len(sources), 'budget_s': SECONDS,
                      'research_calls': 0, 'out': str(out)}), flush=True)


def run(out):
    out = out.resolve(); out.relative_to(REPO)
    sources, gates = gate_admission()
    declared, admission = read(out/'declaration.json'), read(out/'admission.json')
    if (not admission['passed'] or declared['source_sha256'] != sources
            or admission['source_sha256'] != sources or declared['admission'] != gates
            or admission['declaration_sha256'] != sha(out/'declaration.json')
            or declared['budget_s'] != SECONDS or declared['scene_slice_s'] != SLICE_SECONDS
            or declared['problem_id'] != PROBLEM):
        raise ValueError('Frozen declaration/source/rules mismatch')
    for name, expected in sources.items():
        if sha(out/'source_snapshot'/name) != expected:
            raise ValueError('Frozen snapshot changed: '+name)
    if (out/'invocation').exists():
        raise FileExistsError('Invocation output exists; no retry')
    with CLAIM.open('x', encoding='utf-8') as file:
        json.dump({'state': 'CLAIMED_NO_RETRY', 'out': out.relative_to(REPO).as_posix(),
            'source_sha256': sources, 'declaration_sha256': sha(out/'declaration.json'),
            'budget_s': SECONDS, 'scene_slice_s': SLICE_SECONDS,
            'claimed_at_utc': datetime.now(timezone.utc).isoformat()}, file, indent=2)
    from control_policy import with_auto_low_idle
    from inputs import build_instance, load_config
    from shared_search import execute_shared_search
    def loader(budget):
        raw = load_config()
        original = build_instance(raw, PROBLEM, budget=budget)
        return with_auto_low_idle(raw), with_auto_low_idle(original)
    began = time.monotonic(); result = None; error = None
    print('START K116 single base__R1 900s; no retry/extension', flush=True)
    try:
        result = execute_shared_search(loader, out/'invocation', seconds=SECONDS, scene_slice_s=SLICE_SECONDS)
    except BaseException:
        error = traceback.format_exc()
    wall = time.monotonic()-began
    # Preserve the method's output and status; do not reevaluate after cutoff.
    report = {'state': 'RETURNED' if error is None else 'INVOCATION_EXCEPTION',
        'error': error, 'wrapper_call_wall_s': wall, 'research_calls': 1,
        'source_unchanged': all(sha(REPO/name) == expected for name, expected in sources.items()),
        'method_state': None if result is None else result.get('state'),
        'method_reason': None if result is None else result.get('reason'),
        'safe_upper_bound_J': None if result is None else result.get('safe_upper_bound_J'),
        'visited_condition_count': None if result is None else result.get('visited_condition_count'),
        'scope': 'existing method evidence only; no post-budget search/heat/aggregation'}
    save(out/'completion.json', report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return error is None and report['source_unchanged']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--run', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.prepare:
        prepare(args.out)
    else:
        raise SystemExit(0 if run(args.out) else 1)
