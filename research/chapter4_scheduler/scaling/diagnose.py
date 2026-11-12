"""P1/P2 only: four traced constructor replays, one reference assessment, log arithmetic.

No changes to the scientific constructor/evaluator. Replay instrumentation forwards
every original insertion exactly once and observes committed states using tracing.
Its timings are instrumentation costs, never performance measurements. P2 uses
only original pilot logs. The reference never enters HEFT/ON or their archives.
"""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import inspect
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
PILOT = REPO / 'research/chapter4_scheduler/results/unseen_scaling_20261112'
EX = PILOT / 'execution'
OUT = REPO / 'research/chapter4_scheduler/results/p1_p2_diagnostics_20261112'
THREADS = {k: '1' for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')}


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def save(p, value):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False, default=str)
        f.write('\n')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def verify():
    plan = read(EX / 'plan.json')
    for p, h in plan['source_sha256'].items():
        assert sha(REPO / p) == sha(EX / 'source_snapshot' / p) == h, p
    for p, h in plan['input_file_sha256'].items():
        assert sha(EX / p) == h, p
    if (OUT / 'plan.json').exists():
        own = read(OUT / 'plan.json')
        for p, h in own['source_bindings'].items():
            assert sha(REPO / p) == h, p
    return len(plan['source_sha256'])


def scientific_path():
    sys.path[:0] = [str(EX / 'source_snapshot'), str(EX / 'source_snapshot/research/chapter3_experiments')]


def prepare():
    n = verify()
    assert not OUT.exists(), 'DIAGNOSTIC_DIRECTORY_ALREADY_EXISTS'
    instpath = EX / 'frozen_inputs/U02__n12/instance.json'
    cfgpath = EX / 'frozen_inputs/U02__n12/config.json'
    evpath = EX / 'frozen_inputs/U02__n12/generation_evidence.json'
    candidate = read(evpath)['static_check']['time_reference_candidate']
    sources = [Path(__file__), EX / 'plan.json', instpath, cfgpath, evpath]
    for folder in sorted((EX / 'calls').iterdir()):
        sources.extend(folder / p for p in ('method/result.json', 'method_return.json', 'method_evaluation_journal.jsonl'))
    plan = {'protocol': 'chapter4-p1-p2-diagnostic-v1', 'created_utc': now(),
        'subject_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'observed_remote_unseen_tip': '87f7692fad9e3ef94bdf92dfaabd695ac6b5a609',
        'observed_remote_other_research_tip': '77ecc3d4b2f5a46ac4e806abc6fb9461a20db741',
        'authorization': 'User explicitly requested P1/P2: four construction failure reconstruction and one independently labelled saved all-H full electrothermal diagnostic; P2 existing logs only.',
        'budgets': {'structural_replay_attempts': 4, 'structural_replay_total_s': 30,
            'full_reference_evaluations': 1, 'reference_total_s': 60, 'reference_process_watchdog_s': 90},
        'scope': {'formal_method_calls': 0, 'new_search_mechanisms': 0, 'P3': False, 'SA': False, 'stage24': False,
            'reference_is_formal_initialization': False, 'precision_unchanged': True, 'no_retry': True},
        'frozen_scientific_sources_verified': n, 'thread_environment': THREADS,
        'source_bindings': {p.relative_to(REPO).as_posix(): sha(p) for p in sources},
        'instance_identity': digest(read(instpath)), 'config_identity': digest(read(cfgpath)),
        'reference_candidate_identity': digest(candidate)}
    save(OUT / 'plan.json', plan)
    save(OUT / 'reference_candidate.json', candidate)
    print(json.dumps({'prepared': True, 'frozen_sources': n, 'plan_sha256': sha(OUT / 'plan.json')}))


def enumerate_slots(instance, scene_id, stage_id, earliest, deadline, mode, occupied, declared, units):
    """Exact explanation of original _first_start inequalities, no new schedule."""
    grid, duration = F(instance['start_grid_ms']), F(mode['duration_ms'])
    latest = min(deadline, F(instance['window_ms'])) - duration
    starts = ([k * grid for k in range(-((-earliest) // grid), latest // grid + 1)] if declared is None
        else [s for s in declared[scene_id][stage_id] if earliest <= s <= latest])
    domain = units[mode['unit_id']]['domain_id']
    slots = []
    for start in starts:
        conflicts = []
        for row in occupied:
            overlap = max(start, row['start']) < min(start + duration, row['finish'])
            same_unit = mode['unit_id'] == row['unit']
            different_opp_domain = domain == row['domain'] and mode['opp_id'] != row['opp']
            if overlap and (same_unit or different_opp_domain):
                conflicts.append({'stage_id': row['stage_id'], 'same_unit': same_unit,
                                  'shared_domain_different_opp': different_opp_domain})
        slots.append({'start_ms': str(start), 'finish_ms': str(start + duration), 'conflicts': conflicts})
    return {'earliest_ms': str(earliest), 'latest_ms': str(latest), 'deadline_ms': str(deadline),
            'duration_ms': str(duration), 'eligible_grid_count': len(slots), 'slots': slots}


def replay():
    verify()
    save(OUT / 'replay_claim.json', {'utc': now(), 'plan_sha256': sha(OUT / 'plan.json'), 'attempts': 4})
    scientific_path()
    import heft_method as hm
    import thermal
    from timing import MethodBudget
    instance = read(EX / 'frozen_inputs/U02__n12/instance.json')
    old = [read(EX / 'calls' / s / 'method/result.json')['initialization']['construction_attempts']
        for s in ('07_U02__n12_HEFT', '08_U02__n12_ON')]
    assert old[0] == old[1], 'ORIGINAL_CONSTRUCTIONS_DIFFER'
    original = hm._first_start
    lines, lineno = inspect.getsourcelines(hm.build_heft_candidate)
    commit_line = lineno + next(i for i, line in enumerate(lines) if 'deployment[shared_id] = unit' in line)
    result = {'thermal_evaluations': 0, 'formal_method_calls': 0, 'attempts': [],
              'timing_scope': 'instrumented reconstruction, not original performance'}
    budget = MethodBudget(30)
    before = digest(instance)
    try:
        for rank in (None, 0, 1, 2):
            events, commits = [], []
            def observe(*args):
                row = original(*args)
                ins, sid, iid, earliest, deadline, mode, occupied, declared, units, _ = args
                explanation = enumerate_slots(ins, sid, iid, earliest, deadline, mode, list(occupied), declared, units)
                valid = next((s for s in explanation['slots'] if not s['conflicts']), None)
                assert (row is None) == (valid is None)
                if row is not None:
                    assert row['start'] == F(valid['start_ms']) and row['finish'] == F(valid['finish_ms'])
                events.append({'scene': sid, 'stage_id': iid, 'mode': deepcopy(mode),
                    'occupied': deepcopy(list(occupied)), 'returned': deepcopy(row), **explanation})
                return row
            def trace(frame, event, arg):
                if frame.f_code is hm.build_heft_candidate.__code__:
                    if event == 'line' and frame.f_lineno == commit_line:
                        local = frame.f_locals
                        commits.append({'shared_stage_id': local['shared_id'], 'selected_unit': local['unit'],
                            'state': deepcopy(local['state']), 'unit_trials': [
                                {'weighted_finish_ms': str(t[0]), 'weighted_tail_ms': str(t[1]), 'unit': t[2],
                                 'insertions': {sid: [deepcopy(r) for iid, r in rows.items()
                                     if any(s['id'] == iid and s['shared_stage_id'] == local['shared_id']
                                            for sc in instance['scenarios'] if sc['id'] == sid for s in sc['stage_instances'])]
                                               for sid, rows in t[3].items()}} for t in local['unit_trials']]})
                    return trace
                return None
            previous = sys.gettrace()
            try:
                with patch.object(hm, '_first_start', observe), patch.object(thermal, 'evaluate_candidate', side_effect=AssertionError('THERMAL_FORBIDDEN_IN_REPLAY')):
                    sys.settrace(trace)
                    built = hm.build_heft_candidate(instance, budget, opp_rank=rank)
            finally:
                sys.settrace(previous)
            meta = {k: v for k, v in built.items() if k not in ('candidate', 'validation')}
            assert meta == old[0][len(result['attempts'])], 'REPLAY_DIFFERS_FROM_ORIGINAL'
            assert built['candidate'] is None and len(commits) == len(meta['decisions'])
            result['attempts'].append({'opp_rank': rank, 'exact_original_metadata_match': True,
                'metadata': meta, 'committed_choices': commits, 'insertion_calls': events})
        assert digest(instance) == before
        result['status'] = 'FOUR_EXACT_REPLAYS_COMPLETE'
    except BaseException as e:
        result.update(status='REPLAY_ERROR', error=repr(e), traceback=traceback.format_exc())
        raise
    finally:
        result['instrumented_wall_s'] = budget.elapsed
        save(OUT / 'replay.json', result)
    print(json.dumps({'replay': result['status'], 'attempts': len(result['attempts']), 'thermal_evaluations': 0}))


def reference_worker():
    entered = time.monotonic()
    save(OUT / 'reference_worker_claim.json', {'utc': now(), 'once': True})
    scientific_path()
    from timing import MethodBudget
    budget = MethodBudget(60)
    budget.start, budget.deadline = entered, entered + 60
    result = {'kind': 'INDEPENDENTLY_LABELLED_SAVED_ALL_H_REFERENCE', 'error': None,
              'reference_used_as_formal_initialization': False, 'same_numerical_evaluator': True}
    journal = None
    try:
        with budget.phase('frozen_identity_imports_input'):
            verify()
            import thermal
            from h02_pair_preflight.receipts import safe_receipt
            from research.chapter4_scheduler.comparison.core import EvaluationJournal
            plan = read(OUT / 'plan.json')
            instance = read(EX / 'frozen_inputs/U02__n12/instance.json')
            config = read(EX / 'frozen_inputs/U02__n12/config.json')
            candidate = read(OUT / 'reference_candidate.json')
            identities = tuple(map(digest, (instance, config, candidate)))
            assert identities == (plan['instance_identity'], plan['config_identity'], plan['reference_candidate_identity'])
            assert all(os.environ.get(k) == v for k, v in THREADS.items())
            assert read(OUT / 'replay.json')['status'] == 'FOUR_EXACT_REPLAYS_COMPLETE'
        with (OUT / 'reference_evaluation_journal.jsonl').open('x', encoding='utf-8') as stream:
            journal = EvaluationJournal(thermal.evaluate_candidate, budget, stream)
            with budget.phase('single_complete_reference_evaluation'):
                receipt = journal(instance, candidate, config['accuracy_targets'], budget)
        save(OUT / 'reference_receipt.json', receipt)
        result['receipt_state'] = receipt.get('state')
        result['validated_full_SAFE'] = False
        if receipt.get('state') == 'SAFE':
            result['energy'] = safe_receipt(instance, candidate, receipt, config['accuracy_targets'], 60)
            result['validated_full_SAFE'] = True
        assert identities == tuple(map(digest, (instance, config, candidate)))
        result['argument_identities_unchanged'] = True
    except BaseException as e:
        result.update(error=repr(e), traceback=traceback.format_exc())
    result.update(timing=budget.summary(), attempts=journal.attempts if journal else [])
    save(OUT / 'reference_return.json', result)
    print(json.dumps({k: result.get(k) for k in ('receipt_state', 'validated_full_SAFE', 'error')}))
    return int(result['error'] is not None)


def reference():
    verify()
    assert read(OUT / 'replay.json')['status'] == 'FOUR_EXACT_REPLAYS_COMPLETE'
    save(OUT / 'reference_claim.json', {'utc': now(), 'plan_sha256': sha(OUT / 'plan.json'), 'once': True})
    command = [sys.executable, '-B', str(Path(__file__).resolve()), '_reference']
    began = time.monotonic()
    record = {'command': command, 'started_utc': now(), 'watchdog_s': 90}
    try:
        proc = subprocess.run(command, cwd=REPO, env=dict(os.environ, **THREADS, PYTHONUTF8='1'),
                              capture_output=True, text=True, encoding='utf-8', timeout=90)
        (OUT / 'reference_stdout.log').write_text(proc.stdout, encoding='utf-8')
        (OUT / 'reference_stderr.log').write_text(proc.stderr, encoding='utf-8')
        record['exit_code'] = proc.returncode
        print(proc.stdout, end='')
    except subprocess.TimeoutExpired as e:
        record.update(error='WATCHDOG_EXPIRED_NO_RETRY', stdout=str(e.stdout), stderr=str(e.stderr))
    finally:
        record.update(wall_s=time.monotonic()-began, ended_utc=now())
        save(OUT / 'reference_process.json', record)


def stats(v):
    return {'count': len(v), 'sum': sum(v), 'mean': statistics.mean(v) if v else None,
            'median': statistics.median(v) if v else None, 'min': min(v) if v else None, 'max': max(v) if v else None}


def analyze():
    verify()
    rows = []
    for folder in sorted((EX / 'calls').iterdir()):
        raw, returned = read(folder / 'method/result.json'), read(folder / 'method_return.json')
        init = raw['initialization']
        construct, local = init['construction_attempts'], init['local_attempts']
        evaluations = [e for e in raw['evaluations'] if e['phase'] == 'initialization']
        physical = [e for e in evaluations if not e.get('cache_hit')]
        journal = returned['evaluation_attempts_journal'][:len(physical)]
        assert [e['candidate_sha256'] for e in physical] == [j['candidate_sha256'] for j in journal]
        assert len({e['candidate_sha256'] for e in physical}) == len(physical)
        durations = [j['returned_at_s'] - j['started_at_s'] for j in journal]
        phase = next(p for p in raw['timing']['phase_records'] if p['phase'] == 'heft_initialization')
        subphases = [p for p in raw['timing']['phase_records'] if p['start_s'] >= phase['start_s']
                     and p['end_s'] <= phase['end_s'] and p['depth'] > phase['depth']]
        by_kind = []
        for kind in ('shared-unit', 'execution-opp', 'one-start-delay'):
            attempts = [a for a in local if a['kind'] == kind]
            evs = [j for e, j in zip(physical, journal) if e['source'] == 'heft:energy-pass:' + kind]
            by_kind.append({'kind': kind, 'construction_attempts': len(attempts),
                'structural_rejects': sum(a['construction_status'] != 'COMPLETE_LEGAL_CANDIDATE' for a in attempts),
                'full_evaluations': len(evs), 'accepted': sum(a['accepted'] for a in attempts),
                'eval_s': sum(j['returned_at_s'] - j['started_at_s'] for j in evs),
                'reasons': dict(Counter(a.get('reason') for a in attempts if a.get('reason')))})
        detail = []
        for e, j, cost in zip(physical, journal, durations):
            trace_counts = {sid: len(s['trace']) for sid, s in e['receipt']['scenes'].items()}
            detail.append({'source': e['source'], 'candidate_sha256': e['candidate_sha256'], 'eval_s': cost,
                'receipt_state': e['receipt']['state'], 'trace_points': trace_counts,
                'trace_points_total': sum(trace_counts.values())})
        nvalid = sum(c['status'] == 'COMPLETE_LEGAL_CANDIDATE' and not c.get('duplicate_construction') for c in construct)
        nvalid += sum(a['construction_status'] == 'COMPLETE_LEGAL_CANDIDATE' for a in local)
        assert nvalid == len(evaluations)
        rows.append({'id': folder.name, 'construction_calls': len(construct) + len(local),
            'initial_construct_calls': len(construct), 'local_construct_calls': len(local),
            'complete_candidates': nvalid, 'structural_rejects': len(construct)+len(local)-nvalid,
            'full_evaluations': len(physical), 'cache_hits': len(evaluations)-len(physical),
            'receipt_states': dict(Counter(e['receipt']['state'] for e in physical)),
            'initialization_s': phase['wall_s'], 'evaluation_cost_s': stats(durations),
            'init_non_eval_s': phase['wall_s']-sum(durations),
            'complete_legality_s': sum(p['wall_s'] for p in subphases if p['phase'] == 'complete_legality'),
            'initializer_exclusive_s': phase['exclusive_s'], 'by_kind': by_kind,
            'per_evaluation': detail, 'local_accepted': init['local_accepted'],
            'trace_point_counts': stats([d['trace_points_total'] for d in detail])})
    result = {'scope': 'original initialization logs only; no new optimization or thermal calls', 'rows': rows,
        'totals': {k: sum(r[k] for r in rows) for k in ('construction_calls', 'initial_construct_calls',
            'local_construct_calls', 'complete_candidates', 'structural_rejects', 'full_evaluations',
            'cache_hits', 'initialization_s', 'init_non_eval_s', 'complete_legality_s', 'initializer_exclusive_s')},
        'full_eval_s': sum(r['evaluation_cost_s']['sum'] for r in rows)}
    save(OUT / 'initialization_costs.json', result)
    print(json.dumps({'totals': result['totals'], 'full_eval_s': result['full_eval_s']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'replay', 'reference', '_reference', 'analyze'))
    action = parser.parse_args().action
    if action == '_reference':
        sys.exit(reference_worker())
    globals()[action]()
