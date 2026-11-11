"""Read historical saved records; never import model, solver or heat modules."""
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
import hashlib
import json
import sys
import tarfile
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
B = 'research/chapter3_experiments/results/'
START = datetime.now(timezone.utc).isoformat()
BEGAN = time.monotonic()
SOURCES = {}


def raw(path):
    data = (ROOT/path).read_bytes()
    SOURCES[path] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    return data


def read(path):
    return json.loads(raw(path))


def save(name, value):
    with (OUT/name).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def case(path):
    r = read(path)
    return {'source': path, 'id': r['id'], 'shared_stage_identities': len(r['stage_modes']),
            'mode_count': sum(len(v) for v in r['stage_modes'].values()),
            'per_identity_mode_counts': {k: len(v) for k, v in r['stage_modes'].items()},
            'scenario_executions': {s['id']: len(s['stage_instances']) for s in r['scenarios']},
            'beta': r['settings']['deadline_beta'], 'window_ms': r['window_ms'],
            'start_grid_ms': r['start_grid_ms'], 'execution_rules': r['execution_rules']}


cases = {name: case(path) for name, path in {
    'old_R1_hold': B+'base_long_diagnostic01/input_instance.json',
    'K187_auto_L': B+'whole_long_budget01/method/input_instance.json',
    'natural_full_auto_L': B+'natural_full_preparation01/input_instance.json',
    'closure_beta1_auto_L': B+'chapter3_closure_execution01/slots/t50_milp__method/worker/method/input_instance.json',
}.items()}

four = []
for i in range(1, 5):
    prefix = B+f'base_long_diagnostic{i:02}/'
    r = read(prefix+'result.json')
    response = read(prefix+'matlab/request_000001.response.json')
    c = r['construction']
    prior = read('research/chapter3_comparison_review_20261110/solver_history/diagnostic_counts/counts.json')['records'][i-1]
    for key in ('variables', 'rows', 'options', 'binary_variables'):
        assert c[key] == prior['model'][key]
    assert c['nonzeros_in_rows'] == prior['nonzeros_in_rows']
    four.append({'archive': prefix, 'variables': c['variables'], 'integer_declarations': c['binary_variables'],
                 'rows': c['rows'], 'nnz_counter': c['nonzeros_in_rows'],
                 'native_final_exitflag': response['exitflag'],
                 'native_final_nodes': response['output']['numnodes'],
                 'native_final_feasible_count': response['output']['numfeaspoints'],
                 'root_callback': prior['root_lp_callback'], 'cut_callback': prior['cut_callback'],
                 'method_s': r['timing']['method_elapsed_s'],
                 'original_solver_phase_seconds': response.get('phase_seconds'),
                 'archive_environment': r['environment'], 'scope': 'Historical saved R2023b result, not a new local run'})
    raw(prefix+'source_snapshot/milp.py')
    raw(prefix+'source_snapshot/solve_model.m')

warm = read(B+'base_warm_diagnostic01/result.json')
warm_fields = {k: warm.get(k) for k in ('first_initial_safe_s', 'safe_upper_bound_J', 'milp_improved_initial_upper_bound', 'safe_solution_source')}
warm_fields['diagnostic_summary'] = read(B+'base_warm_diagnostic01/diagnostic_summary.json')
prefilter = []
for variant in ('current', 'prefilter'):
    path = B+f'prefilter_diagnostic01/base__R1__{variant}/result.json'
    r = read(path);c = r['construction']
    prefilter.append({'source': path, 'variant': variant,
                      **{k: c[k] for k in ('variables', 'rows', 'nonzeros_in_rows', 'options', 'events_per_scene')},
                      'construction_s': r['timing']['phases_exclusive_s']['model_construction'],
                      'first_initial_SAFE_s': r['first_initial_safe_s'],
                      'U_J': str(Fraction(r['safe_upper_bound_J'])),
                      'improved': r['milp_improved_initial_upper_bound']})

construction = read('research/chapter3_construction_audit/readonly01/evidence.json')
member = 'slots/whole_milp__method/worker/method/build_progress.jsonl'
arc = 'research/chapter3_method_entry_executor/results/real_entry01_analysis/raw_artifacts.tar.gz'
with tarfile.open(ROOT/arc, 'r:gz') as z:
    log = z.extractfile(member).read()
sha = hashlib.sha256(log).hexdigest()
assert sha == construction['progress']['C01']['log_sha256']
SOURCES[arc+'::'+member] = {'sha256': sha, 'bytes': len(log)}
last = json.loads(log.decode().splitlines()[-1])
assert last['status'] == 'CONSTRUCTION_INTERRUPTED'
assert last['variables'] == 114334

numeric = read(B+'natural_full_numeric_diagnostic01/summary.json')
delivery = read(B+'natural_delivery_execution01/summary.json')
closure = read(B+'chapter3_closure_execution01/slots/t50_milp__method/worker/raw_result.json')
closure_summary = read(B+'chapter3_closure_analysis01/summary.json')['methods'][0]
excerpts = {
    '1_R1_formulation_and_energy_strengthening': four,
    '2_R1_existing_warm_start': warm_fields,
    '3_R1_deadline_prefilter': prefilter,
    '4_K187_C01_construction_distinction': {'inputs': construction['inputs'], 'progress': construction['progress'], 'C01_raw_last_status': last['status']},
    '5_natural_autoL_numeric_representation_and_delivery': {
        'original_matrix': numeric['original_matrix'],
        'runs': [{k: r.get(k) for k in ('name', 'subject_commit', 'method_state', 'root_elapsed_s', 'native_seconds', 'native_exitflag', 'native_output')} for r in numeric['runs']],
        'delivery': {k: delivery.get(k) for k in ('scope', 'final_energy_J', 'best_safe_s', 'method_root_s', 'method_wall_s', 'independently_proven_optimal')}},
}
save('history_excerpt.json', {'cases': cases, 'excerpts': excerpts,
                            'closure_boundary': {'construction': closure['construction'], 'timing': closure['timing']['phases_exclusive_s'],
                                                 'method_root_s': closure_summary['method_root_s'], 'method_process_s': closure_summary['total_method_wall_s']},
                            'old_text_erratum': 'Previous review text said old R1 had72 modes. Archived input actually has66: A.main12, B.main9, C.main9, remaining six identities6each. Old12 execution/9identity counts remain correct. No historical file rewritten.'})
save('source_hashes.json', SOURCES)
save('extraction_record.json', {'started_utc': START, 'ended_utc': datetime.now(timezone.utc).isoformat(), 'wall_s': time.monotonic()-BEGAN,
                              'argv': sys.argv, 'cwd': str(ROOT), 'source_count': len(SOURCES),
                              'production_imports': 0, 'model_builds': 0, 'solver_calls': 0, 'thermal_calls': 0,
                              'scope': 'Historical repository data only; current user F-drive/Library native result bytes not accessed and no inference from unread local timings.'})
print(json.dumps({'excerpt_groups': len(excerpts), 'sources': len(SOURCES), 'old_R1_actual_mode_count': cases['old_R1_hold']['mode_count'], 'new_solver_calls': 0}))
