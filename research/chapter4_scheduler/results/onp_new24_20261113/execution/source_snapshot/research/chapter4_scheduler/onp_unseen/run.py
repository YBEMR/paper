"""Eight prospective 12-stage calls. No algorithm changes, retries or new scale."""
import argparse
import csv
from fractions import Fraction as F
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

from ..scaling import run as shared
from ..onp import run as frozen
from ..i1 import unseen as i1_entry
from . import inputs

REPO = shared.REPO
OLD = REPO / 'research/chapter4_scheduler/results/onp_cost_ablation_20261113/execution'
OUT = REPO / 'research/chapter4_scheduler/results/onp_unseen_20261113/execution'
PROTOCOL = 'chapter4-frozen-ON-P-two-new-roots-12-stage-four-arms-v1'
CASES = ('U05__n12', 'U06__n12')
ORDER = (('U05__n12', 'HEFT'), ('U05__n12', 'ON'), ('U05__n12', 'ON_P'), ('U05__n12', 'OFF_P'),
         ('U06__n12', 'OFF_P'), ('U06__n12', 'ON_P'), ('U06__n12', 'ON'), ('U06__n12', 'HEFT'))
BUDGETS = dict(frozen.BUDGETS)
read, save, sha, digest, now = shared.read, shared.save, shared.sha, shared.digest, shared.now
ORIGINAL_METRICS = shared.derived_metrics


def slots(cases):
    lookup = {c['case_id']: c for c in cases}
    if set(lookup) != set(CASES) or len(cases) != 2 or any(c['stages_per_scene'] != 12 for c in cases):
        raise ValueError('EXACT_TWO_NEW_12_STAGE_CASES_REQUIRED')
    return [{'id': f'{i:02d}_{case}_{arm}_I1', 'case_id': case, 'arm': arm,
             'root_id': lookup[case]['root_id'], 'stages_per_scene': 12}
            for i, (case, arm) in enumerate(ORDER, 1)]


def prepare(out, checks):
    if out.exists():
        raise FileExistsError(out)
    old, checked = read(OLD / 'plan.json'), read(checks)
    if not checked.get('passed') or checked.get('failures') or checked.get('errors'):
        raise ValueError('PASSING_ENTRY_CHECKS_REQUIRED')
    if sha(OLD / 'plan.json') != read(OLD / 'plan_identity.json')['sha256']:
        raise ValueError('PRIOR_PLAN_DRIFT')
    sources = checked['source_sha256']
    for name, h in old['source_sha256'].items():
        if sources.get(name) != h or sha(REPO / name) != h or sha(OLD / 'source_snapshot' / name) != h:
            raise ValueError('FROZEN_SCIENCE_DRIFT:' + name)
    for name, h in sources.items():
        if sha(REPO / name) != h:
            raise ValueError('CHECKED_SOURCE_DRIFT:' + name)
    generated = out.parent / 'input_generation'
    manifest = read(generated / 'inputs_manifest.json')
    if read(generated / 'input_plan.json') != inputs.fixed_plan() or sha(generated / 'input_plan.json') != manifest['plan_sha256']:
        raise ValueError('INPUT_PLAN_DRIFT')
    cases = manifest['cases']
    run_slots = slots(cases)
    expected = dict(inputs.ROOTS)
    old_config = read(OLD / 'frozen_inputs/U03__n24/config.json')
    identities = {}
    for c in cases:
        if c['seed'] != expected[c['root_id']]:
            raise ValueError('ROOT_DRIFT')
        for key in ('config', 'instance', 'generation_evidence'):
            if sha(shared.child(generated, c[key + '_path'])) != c[key + '_sha256']:
                raise ValueError('GENERATED_INPUT_DRIFT')
        config, instance = (read(generated / c[k + '_path']) for k in ('config', 'instance'))
        if len(instance['scenarios']) != 2 or any(len(s['stage_instances']) != 12 for s in instance['scenarios']):
            raise ValueError('SCENE_OR_STAGE_DRIFT')
        if any(s['entry']['temperature_degC'] != ['50'] * 4 or s['maximum_temperature_degC'] != ['80'] * 4
               or F(s['weight']) != F(1, 2) for s in instance['scenarios']):
            raise ValueError('CONDITIONS_DRIFT')
        if instance['platform'] != old_config['platform'] or config['accuracy_targets'] != old_config['accuracy_targets']:
            raise ValueError('MODEL_OR_PRECISION_DRIFT')
        identities[c['case_id']] = {'config_sha256': digest(config), 'instance_sha256': digest(instance)}
    out.mkdir(parents=True)
    input_files = {}
    for c in cases:
        for key in ('config_path', 'instance_path'):
            n = 'frozen_inputs/' + c[key]
            dst = out / n
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(generated / c[key], dst)
            input_files[n] = sha(dst)
    for name, h in sources.items():
        dst = out / 'source_snapshot' / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, dst)
        assert sha(dst) == h
    shutil.copyfile(checks, out / 'precheck.json')
    plan = {'protocol': PROTOCOL, 'created_utc': now(),
            'subject_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
            'authorization': 'User requested continuing the attached first-stage new-root plan. HEFT-I1/OFF-P/ON-P plus original ON control; two fixed roots,12 Stage,2scenes,50C,8calls,300s total/180s admission/full post. No24/48/I2/SA.',
            'environment': shared.environment(), 'thread_environment': shared.THREADS, 'budgets': BUDGETS,
            'cases': cases, 'slots': run_slots, 'source_sha256': sources, 'input_file_sha256': input_files,
            'input_identities': identities, 'generation_plan': inputs.fixed_plan(),
            'generation_manifest_sha256': sha(generated / 'inputs_manifest.json'),
            'preregistration_sha256': sha(Path(__file__).parent / 'PREREGISTRATION.md'),
            'precheck_sha256': sha(out / 'precheck.json'), 'prior_plan_sha256': sha(OLD / 'plan.json'),
            'prior_frozen_source_count': len(old['source_sha256']),
            **{k: old[k] for k in ('clock', 'post', 'I1_policy', 'stops')},
            'comparison': 'Each arm independently calls the exact frozen I1. Report initial candidate, energy and history equality separately. No retries to force equality.',
            'scope': 'First use of prospectively declared parameter streams after ON-P freeze, within existing synthetic distribution/topology family. Not external blind validation or statistical stability evidence.'}
    save(out / 'plan.json', plan)
    save(out / 'plan_identity.json', {'sha256': sha(out / 'plan.json')})
    verify(out, plan)
    print({'prepared': True, 'slots': len(run_slots), 'sources': len(sources)}, flush=True)


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
            raise ValueError('SOURCE_DRIFT:' + name)
    for name, h in plan['input_file_sha256'].items():
        if sha(out / name) != h:
            raise ValueError('INPUT_DRIFT:' + name)
    if sha(out / 'precheck.json') != plan['precheck_sha256']:
        raise ValueError('CHECK_DRIFT')
    if sha(Path(__file__).parent / 'PREREGISTRATION.md') != plan['preregistration_sha256']:
        raise ValueError('PREREGISTRATION_DRIFT')


def dispatch(arm, loader, folder, budget, bindings):
    if arm not in ('HEFT', 'ON', 'ON_P', 'OFF_P'):
        raise ValueError('ONLY_EIGHT_PREREGISTERED_ARMS')
    if arm == 'HEFT':
        return i1_entry.dispatch(arm, loader, folder, budget, bindings)
    return frozen.dispatch(arm, loader, folder, budget, bindings)


def metrics(raw, arm):
    return ORIGINAL_METRICS(raw, 'HEFT' if arm == 'HEFT' else 'ON')


def worker(out, slot, post):
    with patch.object(shared, 'verify', verify), patch.object(shared, 'dispatch', dispatch), patch.object(shared, 'derived_metrics', metrics):
        return shared.worker(out, slot, post)


def report(out):
    plan = read(out / 'plan.json')
    rows = []
    for slot in plan['slots']:
        folder = out / 'calls' / slot['id']
        get = lambda n: read(folder / n) if (folder / n).exists() else {}
        ret, post, raw = get('method_return.json'), get('post_return.json'), get('method/result.json')
        interval = ret.get('energy_interval_J')
        initial = (raw.get('initial_safe_snapshot') or {}).get('receipt', {}).get('weighted_energy_J')
        phases = raw.get('timing', {}).get('phases_exclusive_s', {})
        counts = get('method/prefilter.json').get('counts', {})
        constructs = get('method/construction_statistics.json')
        m = ret.get('metrics', {})
        row = {**slot, 'safe': ret.get('has_SAFE_archive', False), 'post_passed': post.get('passed', False),
               'terminal': ret.get('terminal', 'NOT_RETURNED'), 'reason': ret.get('raw_reason'),
               'error': ret.get('error'), 'failure_reason': ret.get('failure_reason'),
               'energy_lower_J': str(F(interval[0])) if interval else None,
               'energy_upper_J': str(F(interval[1])) if interval else None,
               'energy_J': float(F(interval[1])) if interval else None,
               'initial_energy_J': float(F(initial[1])) if initial else None,
               'first_SAFE_at_s': ret.get('first_SAFE_at_s'),
               'method_elapsed_s': ret.get('timing', {}).get('method_elapsed_s'),
               **{k: v for k, v in m.items() if not isinstance(v, (dict, list))}, **ret.get('counts', {}),
               'init_admission_gate_hit': (raw.get('initialization') or {}).get('stop_reason') == 'INIT_ADMISSION_LIMIT',
               'prefilter_total_s': sum(phases.get(k, 0) for k in ('structural_prefilter_setup', 'structural_prefilter_check')),
               'actual_base_calls': constructs.get('base_started', 0), 'actual_extra_calls': constructs.get('extra_started', 0),
               'construction_calls_interrupted': constructs.get('base_exceptions', 0) + constructs.get('extra_exceptions', 0),
               'base_pruned': counts.get('base_pruned', 0), 'extra_pruned_individually': counts.get('extra_pruned', 0),
               'extra_edge_accepts': sum(bool(p.get('additional_reversed_edges')) and p['strict_accepted'] for p in raw.get('graph_proposals', [])),
               'post_wall_s': post.get('worker_body_wall_s')}
        if raw:
            assert raw['initialization_version'] == 'I1'
            if slot['arm'] != 'HEFT':
                assert raw['blocking_edge_adjustment_enabled'] == slot['arm'].startswith('ON')
            if slot['arm'] in ('HEFT', 'OFF_P'):
                assert row['actual_extra_calls'] == row['extra_edge_accepts'] == 0
        rows.append(row)
    result = {'protocol': PROTOCOL, 'subject_commit': plan['subject_commit'], 'rows': rows,
              'all_results_retained': True, 'SAFE_post_successes': sum(r['safe'] and r['post_passed'] for r in rows)}
    save(out / 'summary.json', result)
    with (out / 'metrics.csv').open('x', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader()
        w.writerows(rows)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('generate', 'prepare', 'batch', 'worker', 'report'))
    p.add_argument('--out', type=Path, default=OUT)
    p.add_argument('--checks', type=Path)
    p.add_argument('--slot')
    p.add_argument('--post', action='store_true')
    a = p.parse_args()
    out = a.out.resolve()
    if a.action == 'generate':
        print(inputs.build_inputs(out.parent / 'input_generation')['counters'])
        return 0
    if a.action == 'prepare':
        if a.checks is None:
            p.error('--checks required')
        prepare(out, a.checks)
        return 0
    if a.action == 'worker':
        return worker(out, a.slot, a.post)
    if a.action == 'batch':
        return batch(out)
    report(out)
    return 0


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
            command = [sys.executable, '-B', '-m', 'research.chapter4_scheduler.onp_unseen.run',
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


if __name__ == "__main__":
    raise SystemExit(main())
