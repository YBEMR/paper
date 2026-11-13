"""Read saved native evidence and check the original rows; never solve or heat."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT/'research/chapter3_experiments'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize():
    core = load('saved_array_reader', EXP/'results/fixed_integer_native03/source_snapshot/core.py')
    helper = load('exact_equalities_audit', EXP/'numeric_case_diagnostic/exact_equalities.py')
    bridge = load('original_numeric_admission', EXP/'matlab_bridge.py')
    old = EXP/'results/natural_full_execution01/slots/whole_milp__method/worker/method/matlab'
    original, original_receipt = core.load_original_mat(old/'request_000001.mat')
    original_options = read(old/'request_000001.response.json')['options']
    output = {'scope': 'Post-run saved-array arithmetic only; no new SAFE, optimization result or thermal check.',
              'original_matrix': original_receipt, 'solver_calls_by_this_summary': 0,
              'thermal_evaluations_by_this_summary': 0, 'runs': []}
    for name in ('natural_full_numeric_replay01', 'natural_full_equalities_repair01'):
        folder = EXP/'results'/name
        raw = read(folder/'method_return.json'); terminal = read(folder/'terminal.json')
        response = read(folder/'matlab/request_000001.response.json')
        sent, _ = core.load_original_mat(folder/'matlab/request_000001.mat')
        if name == 'natural_full_equalities_repair01':
            equivalence = helper.verify_equivalence(original, sent, read(folder/'representation_certificate.json'))
        else:
            equivalence = {k: (core._same_matrix(original[k], sent[k]) if k in ('A', 'Aeq')
                              else core._same_array(original[k], sent[k])) for k in core.KEYS}
        assert all(equivalence.values())
        actual_options = response['options']
        differences = {k: [original_options.get(k), actual_options.get(k)]
                       for k in original_options.keys() | actual_options.keys()
                       if original_options.get(k) != actual_options.get(k)}
        assert set(differences) <= {'Display', 'MaxTime'}
        observed = {v['file']: v['received_s'] for v in raw['events']}
        publication = next(v['start_s'] for v in raw['phases'] if v['phase'] == 'transport_request_publication')
        callbacks = []
        for file in sorted((folder/'matlab').glob('request_000001.event_*.json')):
            event = read(file)
            if not event.get('x'):
                continue
            check = bridge._prepare(original, x0=event['x'])['x0_validation']
            callbacks.append({'file': file.relative_to(ROOT).as_posix(), 'sha256': sha(file),
                'phase': (event.get('values') or {}).get('phase'),
                'solver_reported_objective_J': (event.get('values') or {}).get('fval'),
                'parent_received_s': observed.get(file.name),
                'observed_before_root_deadline': file.name in observed and observed[file.name] < 300,
                'native_callback_root_lower_estimate_s': publication+event['request_wall_seconds'],
                'original_rows_archival_numeric_admission': check,
                'new_SAFE_or_formal_result': False})
        final_check = bridge._prepare(original, x0=response['x'])['x0_validation'] if response.get('x') else None
        output['runs'].append({'name': name, 'method_state': raw['state'],
            'subject_commit': read(folder/'declaration.json')['subject_commit'],
            'terminal_sha256': sha(folder/'terminal.json'), 'response_sha256': sha(folder/'matlab/request_000001.response.json'),
            'array_equivalence': equivalence, 'option_differences': differences,
            'root_elapsed_s': raw['method_elapsed_s'], 'total_wall_s': terminal['wall_s'],
            'native_seconds': response['phase_seconds']['intlinprog_call'],
            'native_exitflag': response['exitflag'], 'native_output': response['output'],
            'native_final_objective_J': response.get('fval'), 'final_vector_archival_numeric_admission': final_check,
            'callbacks_with_vectors': callbacks, 'root_received_events': raw['events'],
            'method_calls': terminal['method_calls'], 'native_requests': terminal['native_request_slots_consumed'],
            'thermal_calls': terminal['thermal_post_calls'], 'retries': terminal['retries'],
            'owned_processes_exited': terminal['observed_owned_processes_exited'],
            'native_cleanup_verified': raw['lifecycle_complete'],
            'sources_preserved_at_run_return': raw['sources_preserved'],
            'phases': raw['phases'],
            'local_only_mat_files': [{'path': p.relative_to(ROOT).as_posix(), 'sha256': sha(p),
                'gitignore_rule': '*.mat', 'bytes': p.stat().st_size} for p in sorted((folder/'matlab').glob('*.mat'))]})
    output['total_native_requests'] = sum(v['native_requests'] for v in output['runs'])
    output['total_thermal_calls'] = sum(v['thermal_calls'] for v in output['runs'])
    output['repair_boundary'] = ('Original numerical infeasibility reproduced; exact-equality representation passed root LP '
        'and timely x0 acceptance. Lower-energy candidate first published after cutoff; no timely optimized SAFE or proof of optimality.')
    output['late_time_scope'] = ('Only first callback observability is bounded; internal discovery time is unknown. '
                                'Parent receipt before 300 seconds is absent.')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('new_output', type=Path)
    args = parser.parse_args()
    result = summarize()
    with args.new_output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'native_requests': result['total_native_requests'], 'thermal_calls': result['total_thermal_calls'],
                      'original_rows_and_representation_verified': True}, ensure_ascii=False))
