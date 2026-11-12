"""Six authorized original ON/OFF calls; reuse the pilot's complete lifecycle.

Only the existing allow_blocking_edges flag differs. No scientific implementation
is edited. Each call owns its unchanged HEFT initializer, root budget and journal.
"""
import argparse
from copy import deepcopy
import csv
from fractions import Fraction as F
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

from . import run as shared

REPO = shared.REPO
OLD = REPO / 'research/chapter4_scheduler/results/unseen_scaling_20261112/execution'
OUT = REPO / 'research/chapter4_scheduler/results/p3_unseen_ablation_20261112'
PROTOCOL = 'chapter4-original-on-off-three-cases-v1'
CASES = ('U01__n6', 'U01__n12', 'U02__n6')
BUDGETS = {'method_s': 300, 'post_s': 60, 'method_slots': 6, 'post_slots_at_most': 6,
           'method_process_watchdog_s': 360, 'post_process_watchdog_s': 90}
read, save, sha, digest, now = shared.read, shared.save, shared.sha, shared.digest, shared.now


def slots(cases):
    indexed = {c['case_id']: c for c in cases}
    if set(indexed) != set(CASES) or len(cases) != 3:
        raise ValueError('EXACT_THREE_AUTHORIZED_CASES_REQUIRED')
    result = []
    for i, name in enumerate(CASES):
        c = indexed[name]
        for arm in (('ON', 'OFF') if i == 1 else ('OFF', 'ON')):
            result.append({'id': f'{len(result)+1:02d}_{name}_{arm}', 'case_id': name,
                'root_id': c['root_id'], 'stages_per_scene': c['stages_per_scene'], 'arm': arm})
    return result


def legacy_identity():
    p = read(OLD / 'plan.json')
    for name, h in p['source_sha256'].items():
        if sha(REPO / name) != h:
            raise ValueError('ORIGINAL_SOURCE_DRIFT:' + name)
    for name, h in p['input_file_sha256'].items():
        if sha(OLD / name) != h:
            raise ValueError('ORIGINAL_INPUT_DRIFT:' + name)
    return p


def prepare(out):
    old = legacy_identity()
    if out.exists():
        raise FileExistsError(out)
    cases = [c for c in old['cases'] if c['case_id'] in CASES]
    run_slots = slots(cases)
    out.mkdir(parents=True)
    input_files = {}
    for c in cases:
        for key in ('config_path', 'instance_path', 'generation_evidence_path'):
            relative = c[key]
            source, target = OLD / 'frozen_inputs' / relative, out / 'frozen_inputs' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            input_files[target.relative_to(out).as_posix()] = sha(target)
    sources = dict(old['source_sha256'])
    for name in ('p3.py', 'test_p3.py'):
        path = Path(__file__).parent / name
        sources[path.relative_to(REPO).as_posix()] = sha(path)
    for name, h in sources.items():
        target = out / 'source_snapshot' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, target)
        assert sha(target) == h
    plan = {'protocol': PROTOCOL, 'created_utc': now(),
        'authorization': 'User requested one P3: original ON/OFF on U01-6, U01-12, U02-6; no algorithm changes; I1 separately later. Existing uniform 300s protocol retained.',
        'subject_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'observed_remote_before_code': {'unseen': '3fb632a5f3b38a543e6168f89fccf09b4ea9ca1e', 'other_research': 'cbf0257d65c6c3771ef26ad51a96245962ce6f40'},
        'environment': shared.environment(), 'thread_environment': shared.THREADS, 'budgets': BUDGETS,
        'slots': run_slots, 'cases': cases, 'source_sha256': sources,
        'input_file_sha256': input_files, 'input_identities': {k: old['input_identities'][k] for k in CASES},
        'original_plan_sha256': sha(OLD / 'plan.json'), 'original_sources_verified': len(old['source_sha256']),
        'clock': old['clock'], 'initialization': old['initialization'], 'post': old['post'], 'stops': old['stops'],
        'ablation': 'Only existing allow_blocking_edges True/False differs. Both retain target/partner modes/base orders/templates/full evaluation/strict acceptance.',
        'scope': 'Three previously observed initializer-success cases from the two frozen parameter roots; conditional mechanism ablation, not fresh blind testing. No U02-12 repair, I1, SA or 24 Stage.',
        'comparison': 'Require same completed initial snapshot and initialization sequence; report final interval-strict ON/OFF difference separately from within-ON accepted step deltas. No single-edge causal credit for subsequent ordinary steps.'}
    save(out / 'plan.json', plan)
    save(out / 'plan_identity.json', {'sha256': sha(out / 'plan.json')})
    verify(out, plan)
    print({'prepared': True, 'slots': 6, 'original_sources_verified': len(old['source_sha256'])}, flush=True)


def verify(out, plan):
    if plan['protocol'] != PROTOCOL or plan['slots'] != slots(plan['cases']) or plan['budgets'] != BUDGETS:
        raise ValueError('SCOPE_OR_BUDGET_DRIFT')
    if sha(out / 'plan.json') != read(out / 'plan_identity.json')['sha256']:
        raise ValueError('PLAN_DRIFT')
    if shared.environment() != plan['environment']:
        raise ValueError('ENVIRONMENT_DRIFT')
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip() != plan['subject_commit']:
        raise ValueError('SUBJECT_DRIFT')
    for name, h in plan['source_sha256'].items():
        if sha(REPO / name) != h or sha(out / 'source_snapshot' / name) != h:
            raise ValueError('FROZEN_SOURCE_DRIFT:' + name)
    for name, h in plan['input_file_sha256'].items():
        if sha(out / name) != h:
            raise ValueError('INPUT_DRIFT:' + name)


def dispatch(arm, loader, folder, budget, bindings):
    if arm not in ('ON', 'OFF'):
        raise ValueError('ONLY_ORIGINAL_ON_OFF')
    from research.chapter4_scheduler.blocking.method import execute_reconstruction
    return execute_reconstruction(loader, folder, bindings=bindings, budget=budget,
        seconds=budget.seconds, allow_blocking_edges=arm == 'ON')


def metrics(raw, arm):
    # Both ablation arms perform the same kind of refinement after HEFT.
    return ORIGINAL_METRICS(raw, 'ON')


ORIGINAL_METRICS = shared.derived_metrics


def worker(out, slot, post):
    # Reuse unchanged scientific loading, root clock, complete journal, archive,
    # separate post-process validation and error preservation from the pilot.
    with patch.object(shared, 'verify', verify), patch.object(shared, 'dispatch', dispatch), \
            patch.object(shared, 'derived_metrics', metrics):
        return shared.worker(out, slot, post)


def batch(out):
    plan = read(out / 'plan.json')
    verify(out, plan)
    save(out / 'batch_started.json', {'utc': now(), 'plan_sha256': sha(out / 'plan.json')})
    began, stop, rows = time.monotonic(), None, []
    env = dict(os.environ, **shared.THREADS, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    for slot in plan['slots']:
        row = {'slot': slot, 'status': 'NOT_RUN_TECHNICAL_STOP' if stop else 'STARTED', 'phases': []}
        rows.append(row)
        if stop:
            row['reason'] = stop
            continue
        folder = out / 'calls' / slot['id']
        folder.mkdir(parents=True, exist_ok=False)
        for phase, timeout in (('method', 360), ('post', 90)):
            if phase == 'post':
                result = read(folder / 'method_return.json')
                if not result.get('normal_stop') or not result.get('has_SAFE_archive'):
                    break
            verify(out, plan)
            save(folder / (phase + '_claim.json'), {'utc': now(), 'slot': slot,
                'plan_sha256': sha(out / 'plan.json'), 'no_retry': True})
            command = [sys.executable, '-B', '-m', 'research.chapter4_scheduler.scaling.p3',
                       'worker', '--out', str(out), '--slot', slot['id']] + (['--post'] if phase == 'post' else [])
            record = {'argv': command, 'cwd': str(REPO), 'started_utc': now(),
                      'thread_environment': shared.THREADS, 'watchdog_s': timeout, 'phase': phase}
            save(folder / (phase + '_command_started.json'), record)
            print({'START': slot['id'], 'phase': phase, 'utc': now()}, flush=True)
            started = time.monotonic()
            try:
                proc = subprocess.run(command, cwd=REPO, env=env, capture_output=True, text=True, encoding='utf-8', timeout=timeout)
                (folder / (phase + '_stdout.log')).write_text(proc.stdout, encoding='utf-8')
                (folder / (phase + '_stderr.log')).write_text(proc.stderr, encoding='utf-8')
                result = read(folder / (phase + '_return.json'))
                record.update(exit_code=proc.returncode, normal_stop=result.get('normal_stop'), watchdog_expired=False)
                if proc.returncode or result.get('error') or not result.get('normal_stop'):
                    stop = slot['id'] + ':' + phase + ':ABNORMAL_RETURN'
                print({'DONE': slot['id'], 'phase': phase, 'terminal': result.get('terminal'),
                       'safe': result.get('has_SAFE_archive'), 'error': result.get('error')}, flush=True)
            except BaseException as error:
                stop = slot['id'] + ':' + phase + ':' + type(error).__name__
                record.update(error={'type': type(error).__name__, 'reason': str(error)},
                              watchdog_expired=isinstance(error, subprocess.TimeoutExpired))
                if isinstance(error, subprocess.TimeoutExpired):
                    for label, value in (('stdout', error.stdout), ('stderr', error.stderr)):
                        (folder / (phase + '_partial_' + label + '.log')).write_bytes(value.encode('utf-8') if isinstance(value, str) else value or b'')
            record.update(wall_s=time.monotonic()-started, ended_utc=now())
            save(folder / (phase + '_command_return.json'), record)
            row['phases'].append(record)
            if stop:
                row.update(status='STOPPED_TECHNICAL', reason=stop)
                break
        if not stop:
            row['status'] = 'COMPLETED'
    try:
        verify(out, plan)
        intact = True
    except Exception as error:
        intact, stop = False, stop or repr(error)
    save(out / 'batch_return.json', {'protocol': PROTOCOL, 'wall_s': time.monotonic()-began, 'slots': rows,
        'stop_reason': stop, 'frozen_identity_unchanged': intact, 'retry_count': 0,
        'all_planned_method_slots_returned': all(r['status'] == 'COMPLETED' for r in rows)})
    report(out)
    return int(stop is not None)


def report(out):
    plan, rows, raws = read(out / 'plan.json'), [], {}
    for slot in plan['slots']:
        folder = out / 'calls' / slot['id']
        result = read(folder / 'method_return.json') if (folder / 'method_return.json').exists() else {}
        post = read(folder / 'post_return.json') if (folder / 'post_return.json').exists() else {}
        raw = read(folder / 'method/result.json') if (folder / 'method/result.json').exists() else {}
        raws[slot['id']] = raw
        interval = result.get('energy_interval_J')
        m = result.get('metrics', {})
        row = {**slot, 'terminal': result.get('terminal', 'NOT_RETURNED'), 'reason': result.get('raw_reason'),
            'error': result.get('error'), 'safe': result.get('has_SAFE_archive', False), 'post_passed': post.get('passed', False),
            'energy_lower_J': str(F(interval[0])) if interval else None, 'energy_upper_J': str(F(interval[1])) if interval else None,
            'energy_upper_J_decimal': float(F(interval[1])) if interval else None,
            'method_elapsed_s': result.get('timing', {}).get('method_elapsed_s'),
            **{k: v for k, v in m.items() if not isinstance(v, (dict, list))}, **result.get('counts', {})}
        row['extra_edge_graph_attempts'] = sum(bool(d.get('extra_resource_edge')) for d in raw.get('reconstruction_attempts', []))
        row['extra_edge_proposals'] = sum(bool(p.get('additional_reversed_edges')) for p in raw.get('graph_proposals', []))
        row['extra_edge_accepts'] = sum(bool(p.get('additional_reversed_edges')) and p['strict_accepted'] for p in raw.get('graph_proposals', []))
        if raw:
            assert raw['blocking_edge_adjustment_enabled'] == (slot['arm'] == 'ON')
            if slot['arm'] == 'OFF':
                assert row['extra_edge_graph_attempts'] == row['extra_edge_proposals'] == row['extra_edge_accepts'] == 0
        rows.append(row)
    pairs = []
    for case in CASES:
        arms = {r['arm']: r for r in rows if r['case_id'] == case}
        on, off = arms['ON'], arms['OFF']
        a, b = raws[on['id']], raws[off['id']]
        initialized = bool(a.get('initial_safe_snapshot') and b.get('initial_safe_snapshot'))
        same_initial = initialized and a['initial_safe_snapshot']['candidate'] == b['initial_safe_snapshot']['candidate']
        init_sequence = lambda r: [e['candidate_sha256'] for e in r.get('evaluations', []) if e['phase'] == 'initialization']
        same_sequence = init_sequence(a) == init_sequence(b)
        valid = same_initial and same_sequence and all(r['safe'] and r['post_passed'] and not r['error'] for r in (on, off))
        pairs.append({'case_id': case, 'same_initial_candidate': same_initial, 'same_initialization_sequence': same_sequence,
            'comparable_SAFE_pair': valid, 'ON_vs_OFF_saving_percent': float((F(off['energy_upper_J'])-F(on['energy_upper_J']))/F(off['energy_upper_J'])*100) if valid else None,
            'strict_interval_improvement': F(on['energy_upper_J']) < F(off['energy_lower_J']) if valid else None,
            'same_final_candidate': a.get('safe_candidate') == b.get('safe_candidate') if valid else None})
    summary = {'protocol': PROTOCOL, 'subject_commit': plan['subject_commit'], 'rows': rows, 'comparisons': pairs,
        'all_results_retained': True, 'SAFE_post_successes': sum(r['safe'] and r['post_passed'] for r in rows)}
    save(out / 'summary.json', summary)
    with (out / 'metrics.csv').open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        writer.writeheader()
        writer.writerows(rows)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'batch', 'worker', 'report'))
    parser.add_argument('--out', type=Path, default=OUT)
    parser.add_argument('--slot')
    parser.add_argument('--post', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    if args.action == 'worker':
        return worker(out, args.slot, args.post)
    return globals()[args.action](out) if args.action == 'batch' else (globals()[args.action](out) and 0)


if __name__ == '__main__':
    raise SystemExit(main())
