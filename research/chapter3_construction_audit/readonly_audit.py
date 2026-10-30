"""Read archived JSON/source only; never import the scheduling/model packages."""
import argparse
import difflib
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import tarfile


ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / 'research/chapter3_experiments/results/whole_long_budget01'
NEW = ROOT / 'research/chapter3_method_entry_executor/results'


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return sha_bytes(json.dumps(value, sort_keys=True, ensure_ascii=False,
                               separators=(',', ':')).encode())


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def input_counts(instance):
    out = []
    grid = Fraction(instance['start_grid_ms'])
    for scene in instance['scenarios']:
        modes = [m for s in scene['stage_instances']
                 for m in instance['stage_modes'][s['shared_stage_id']]]
        durations = {Fraction(m['duration_ms']) for m in modes}
        out.append({'scene': scene['id'], 'stages': len(scene['stage_instances']),
                    'requests': len(scene['requests']), 'edges': len(scene['dependencies']),
                    'mode_references': len(modes), 'distinct_duration_ms': len(durations),
                    'distinct_duration_mod_grid': len({d % grid for d in durations})})
    return {'window_ms': instance['window_ms'], 'start_grid_ms': str(grid),
            'platform_sha256': canonical(instance['platform']), 'scenes': out}


def progress_summary(data):
    lines = data.decode('utf-8').splitlines()
    last = json.loads(lines[-1])
    fields = ('status', 'method_elapsed_seconds', 'current_stage', 'detail', 'options',
              'variables', 'binary_variables', 'rows', 'nonzeros_in_rows',
              'events_per_scene', 'phase_wall_seconds', 'construction_components',
              'construction_details', 'conditional_templates', 'affine_templates',
              'coefficient_sets_completed', 'coefficient_state_kernels_completed',
              'observation_callback_wall_s', 'memory')
    result = {key: last.get(key) for key in fields}
    hit, miss = last['affine_templates']['hits'], last['affine_templates']['misses']
    result.update(log_sha256=sha_bytes(data), last_line=len(lines),
                  event_intervals_total=sum(n-1 for n in last['events_per_scene'].values()),
                  affine_hit_rate=hit/(hit+miss),
                  counters_scope='complete model only if status MODEL_CONSTRUCTED; otherwise partial')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    out = Path(parser.parse_args().output).resolve()
    assert out.is_relative_to(Path(__file__).resolve().parent)
    assert not out.exists(), 'new evidence directory required'
    old_log = (OLD/'method/build_progress.jsonl').read_bytes()
    manifest = read(NEW/'real_entry01_analysis/raw_artifacts_manifest.json')
    member = 'slots/whole_milp__method/worker/method/build_progress.jsonl'
    expected = next(f['sha256'] for f in manifest['files'] if f['path'] == member)
    direct = NEW/'real_entry01'/member
    if direct.is_file():
        new_log = direct.read_bytes()
    else:
        with tarfile.open(NEW/'real_entry01_analysis/raw_artifacts.tar.gz', 'r:gz') as archive:
            new_log = archive.extractfile(member).read()
    assert sha_bytes(new_log) == expected
    sources = {}
    names = ('milp.py', 'milp_coefficients.py', 'build_observer.py', 'thermal.py',
             'inputs.py', 'method_runner.py', 'run_warm_diagnostic.py',
             'run_initial_witness_diagnostic.py', 'formal_milp.py')
    for name in names:
        a = OLD/'source_snapshot/research/chapter3_experiments'/name
        b = ROOT/'research/chapter3_experiments'/name
        sources[name] = {'old_sha256': sha_bytes(a.read_bytes()),
                         'current_sha256': sha_bytes(b.read_bytes()),
                         'equal': a.read_bytes() == b.read_bytes()}
    old_input = read(OLD/'method/input_instance.json')
    common = read(NEW/'post_status_precheck01/common_input.json')
    evidence = {
        'schema': 'whole-construction-readonly-attribution-v1',
        'scope': 'archived files and scalar arithmetic only; no production imports',
        'sources': sources,
        'inputs': {'K187': input_counts(old_input), 'C01': input_counts(common['instance'])},
        'progress': {'K187': progress_summary(old_log), 'C01': progress_summary(new_log)},
        'old_result': {k: read(OLD/'method/result.json').get(k) for k in
                       ('state', 'reason', 'stop_stage', 'model_complete', 'matrix_complete',
                        'matlab_worker_ready', 'integer_solver_entered', 'timing')},
        'new_result_summary': read(NEW/'real_entry01_analysis/summary.json'),
        'prohibited_work_counts': {'model_builds': 0, 'coefficient_generation': 0,
                                  'matlab': 0, 'search': 0, 'thermal_integration': 0},
        'interpretation_limits': [
            'Different inputs and complete/partial counters; not a matched speed benchmark.',
            'Nested construction_details must not be summed with their parents.',
            'Cache key stream and per-term multiplication costs were not logged.',
            'Current whole did not enter MATLAB; no native numerical diagnosis follows.']}
    out.mkdir()
    (out/'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    a = OLD/'source_snapshot/research/chapter3_experiments/formal_milp.py'
    b = ROOT/'research/chapter3_experiments/formal_milp.py'
    diff = ''.join(difflib.unified_diff(a.read_text(encoding='utf-8').splitlines(True),
                                      b.read_text(encoding='utf-8').splitlines(True),
                                      fromfile='K187/formal_milp.py', tofile='current/formal_milp.py'))
    (out/'formal_entry_diff.json').write_text(
        json.dumps({'format': 'unified_diff', 'diff': diff}, ensure_ascii=False, indent=2)+'\n',
        encoding='utf-8')
    print(json.dumps({'state': 'READONLY_ANALYSIS_COMPLETE',
                      'sources': len(sources), 'model_builds': 0,
                      'evidence_sha256': sha_bytes((out/'evidence.json').read_bytes())}))


if __name__ == '__main__':
    main()
