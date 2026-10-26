"""K192 bounded feasibility/cost precheck, never an optimization experiment.

prepare is pure. run consumes an exclusive claim and evaluates exactly the
frozen witness, then at most four frozen cost samples. No retries or ranking.
"""
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
import argparse
import json
import sys
import time
from unittest.mock import patch

ENTRY_START = time.monotonic()
HERE = Path(__file__).resolve().parent
PRODUCTION = HERE.parent
ROOT = PRODUCTION.parents[1]
sys.path[:0] = [str(HERE / 'domain'), str(PRODUCTION)]
import core
from schedules import validate_schedule
from scene_adapter import make_scene_instance
from thermal import Budget, Exhausted, evaluate_candidate

ORIGINAL = PRODUCTION / 'results/whole_long_budget01/method/input_instance.json'
CONFIG = PRODUCTION / 'results/whole_long_budget01/method/input_config.json'
PRECHECK_LIMIT = 120
WITNESS_LIMIT = 60
SAMPLE_LIMIT = 15
ORIGINAL_SHA256 = '01eacb2a653d56419c32f38740021a787ea01ac9e7ade407bef2edd81ec6ef89'
CONFIG_SHA256 = '132323b4b18dd514b9baa929543d235ff91bb07026a60e7b629e1adb6aaaa5e2'


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str)
        stream.write('\n')


def candidate_rows(rows):
    return [{'stage_id': row['id'], 'unit': row['unit_id'], 'opp': row['opp_id'],
             'start_ms': str(row['start'])} for row in rows]


def canonical(rows):
    return tuple(sorted((row['id'], row['unit_id'], row['opp_id'], row['start']) for row in rows))


def single_scene_view(instance, scene_id):
    """Same physical scene; weight=1 is only for isolated timing measurement."""
    return make_scene_instance(instance, scene_id, unweighted=True)


def fixed_samples(result):
    samples = []
    for scene in result['instance']['scenarios']:
        sid = scene['id']
        counts = result['counts']['by_scene'][sid]['legal_count_by_shared_A_unit']
        for unit in sorted(counts):
            group = [rows for rows in result['legal_by_scene'][sid]
                     if next(row for row in rows if row['shared_stage_id'] == 'A.main')['unit_id'] == unit]
            rows = max(group, key=canonical)
            samples.append({'id': sid + '__A_' + unit, 'scene_id': sid,
                'shared_A_device': unit, 'group_count': counts[unit],
                'selection': 'maximum sorted (stage_id, unit, opp, exact rational start) tuple among statically legal rows; no heat/energy read',
                'candidate': {'scenes': {sid: candidate_rows(rows)}}})
    return samples


def freeze(directory):
    if digest(ORIGINAL) != ORIGINAL_SHA256 or digest(CONFIG) != CONFIG_SHA256:
        raise ValueError('Original K187 input/config archive identity changed')
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    result = core.produce(json.loads(ORIGINAL.read_bytes()))
    if result['C_seed'] is None:
        raise ValueError('Existing C constructor has no complete common-domain seed')
    config = json.loads(CONFIG.read_bytes())
    accuracy = {key: config['accuracy_targets'][key] for key in (
        'temperature_enclosure_width_K', 'energy_absolute_error_J', 'energy_relative_error')}
    samples = fixed_samples(result)
    for sample in samples:
        check = validate_schedule(single_scene_view(result['instance'], sample['scene_id']), sample['candidate'])
        if check['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
            raise ValueError('Frozen cost sample is outside the common domain')
    save(directory / 'restricted_input.json', result['instance'])
    save(directory / 'domain_counts.json', result['counts'])
    save(directory / 'construction.json', result['construction'])
    save(directory / 'constructor_prechecks.json', result['constructor_prechecks'])
    save(directory / 'witness_candidate.json', result['C_seed'])
    save(directory / 'cost_samples.json', samples)
    sources = sorted(set(list(PRODUCTION.glob('*.py')) + list(HERE.rglob('*.py')) + [
        ROOT / 'research/v1_evaluator/interval.py', ORIGINAL, CONFIG]))
    frozen = sorted(directory.glob('*.json'))
    identities = {str(p.relative_to(ROOT)).replace('\\', '/'): digest(p) for p in sources + frozen}
    protocol = {
        'id': 'K192-common-small-domain-feasibility-cost-precheck-v1',
        'artifact_directory': str(directory.resolve()),
        'frozen_utc': datetime.now(timezone.utc).isoformat(),
        'authorization': 'User requests common-domain consistency, complete thermal feasibility and enumeration-cost assessment before separately approving formal solving',
        'formal_solving_authorized': False, 'solver_calls': 0, 'MATLAB_starts': 0,
        'optimization_or_method_search_calls': 0,
        'precheck_wall_seconds_at_most': PRECHECK_LIMIT,
        'clock': 'CLI entry before scientific imports and input read; cooperative checkpoints, no hard-real-time stop; reporting only after cutoff',
        'full_AB_AC_witness_calls_at_most': 1, 'witness_seconds_at_most': WITNESS_LIMIT,
        'single_scene_cost_samples_at_most': 4, 'cost_sample_seconds_at_most': SAMPLE_LIMIT,
        'scene_trajectories_at_most': 6, 'accuracy': accuracy,
        'order': ['fresh_existing_C_H_constructor_witness'] + [s['id'] for s in samples],
        'stop': 'No retry. Witness not SAFE stops cost samples; incomplete/error sample stops remaining samples. No alternative witness search or parameter changes.',
        'evidence': 'Precheck only; no ranking, optimum, full thermal coverage, free initialization or cache for future methods',
        'cost_estimate': 'One fixed sample per scene/shared-A-device group; weighted by static group size; estimate, not a uniform upper bound',
        'source_and_frozen_sha256': identities}
    save(directory / 'precheck_protocol.json', protocol)
    return protocol


class CappedBudget(Budget):
    def __init__(self, cap, root_deadline, *, clock=time.monotonic):
        super().__init__(seconds=cap)
        self.clock = clock
        self.start = clock()
        self.deadline = min(root_deadline, self.start + cap)

    @property
    def elapsed(self):
        return self.clock() - self.start

    def check(self):
        if self.clock() >= self.deadline:
            raise Exhausted('wall_time_limit')


def verify(protocol):
    for relative, expected in protocol['source_and_frozen_sha256'].items():
        if digest(ROOT / relative) != expected:
            raise ValueError('Frozen source/input drift: ' + relative)


def execute(directory, *, expected_protocol_sha256, evaluator=evaluate_candidate, root_start=None):
    directory = Path(directory).resolve()
    root_start = time.monotonic() if root_start is None else root_start
    deadline = root_start + PRECHECK_LIMIT
    if digest(directory / 'precheck_protocol.json') != expected_protocol_sha256:
        raise ValueError('Protocol identity mismatch')
    protocol = json.loads((directory / 'precheck_protocol.json').read_bytes())
    if Path(protocol['artifact_directory']).resolve() != directory.resolve():
        raise ValueError('Artifact directory mismatch')
    verify(protocol)
    # Claim is exclusive, even if a subsequent evaluation fails.
    save(directory / 'execution_claim.json', {'started_utc': datetime.now(timezone.utc).isoformat(),
        'protocol_sha256': digest(directory / 'precheck_protocol.json'), 'retries_allowed': 0})
    instance = json.loads((directory / 'restricted_input.json').read_bytes())
    witness = json.loads((directory / 'witness_candidate.json').read_bytes())
    samples = json.loads((directory / 'cost_samples.json').read_bytes())
    calls, stop_reason, attempts = [], None, []

    def call(name, view, candidate, limit):
        budget = CappedBudget(limit, deadline)
        budget.check()
        started = time.monotonic()
        attempts.append(name)
        receipt = evaluator(view, candidate, accuracy=protocol['accuracy'], budget=budget)
        ended = time.monotonic()
        row = {'id': name, 'elapsed_s': ended - started,
               'finished_root_elapsed_s': ended - root_start,
               'formed_before_root_deadline': ended < deadline,
               'returned_before_call_deadline': ended < budget.deadline,
               'state': receipt['state'], 'complete': all(
                   s.get('complete', False) for s in receipt.get('scenes', {}).values()) and
                   len(receipt.get('scenes', {})) == len(view['scenarios']),
               'receipt': receipt}
        calls.append(row)
        save(directory / (name + '_receipt.json'), row)
        return row

    try:
        row = call('complete_witness', instance, witness, WITNESS_LIMIT)
        if row['state'] != 'SAFE' or not row['complete'] or not row['returned_before_call_deadline']:
            stop_reason = 'WITNESS_NOT_COMPLETE_SAFE_IN_BUDGET'
        else:
            for sample in samples:
                row = call(sample['id'], single_scene_view(instance, sample['scene_id']),
                           sample['candidate'], SAMPLE_LIMIT)
                if row['state'] != 'SAFE' or not row['complete'] or not row['returned_before_call_deadline']:
                    stop_reason = 'COST_SAMPLE_INCOMPLETE_UNSAFE_OR_UNRESOLVED'
                    break
    except Exception as error:
        stop_reason = type(error).__name__ + ': ' + str(error)
    estimate = None
    if len(calls) == 5 and stop_reason is None:
        terms = [{'id': sample['id'], 'group_count': sample['group_count'],
                  'sample_seconds': calls[i+1]['elapsed_s'],
                  'projected_seconds': sample['group_count'] * calls[i+1]['elapsed_s']}
                 for i, sample in enumerate(samples)]
        estimate = {'group_terms': terms,
            'sum_projected_seconds': sum(term['projected_seconds'] for term in terms),
            'limitation': 'Timing estimate from one sample/group, not a proven upper bound or an approved formal budget; no all-candidate energy ranking performed'}
    terminal = {'state': 'PRECHECK_COMPLETE' if stop_reason is None else 'STOPPED',
        'reason': stop_reason, 'calls_consumed': len(attempts), 'calls_started': attempts,
        'receipts_formed': len(calls), 'scene_trajectories': sum(
            len(row['receipt'].get('scenes', {})) for row in calls),
        'full_witness_SAFE': bool(calls and calls[0]['state'] == 'SAFE'
                                  and calls[0]['complete'] and calls[0]['returned_before_call_deadline']),
        'root_elapsed_s': time.monotonic() - root_start,
        'solver_calls': 0, 'MATLAB_starts': 0, 'method_optimization_calls': 0,
        'cost_estimate': estimate, 'formal_solving_authorized': False}
    save(directory / 'terminal.json', terminal)
    return terminal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('directory', type=Path)
    parser.add_argument('--protocol-sha256')
    args = parser.parse_args()
    # No native process is permitted, including accidental MATLAB/solver launch.
    with patch('subprocess.Popen', side_effect=AssertionError('Native launch forbidden in K192 precheck')):
        if args.action == 'run' and not args.protocol_sha256:
            parser.error('run requires the predeclared --protocol-sha256')
        result = freeze(args.directory) if args.action == 'prepare' else execute(
            args.directory, expected_protocol_sha256=args.protocol_sha256, root_start=ENTRY_START)
    print(json.dumps({'action': args.action, 'directory': str(args.directory),
                      'state': result.get('state', 'FROZEN_PURE_PREPARATION')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
