"""Describe saved K194 receipts using exact arithmetic; no new physics call."""
from fractions import Fraction as Q
from hashlib import sha256
from pathlib import Path
import json

HERE = Path(__file__).resolve().parent


def describe():
    reference = json.loads((HERE/'reference.json').read_bytes())
    manifest = [json.loads(line) for line in (HERE/'scene_manifest.jsonl').read_bytes().splitlines()]
    by_id = {row['id']: row for row in manifest}
    groups = {(g['scene_id'], g['shared_A_device']): g for g in reference['groups']}
    components, scenarios = {}, {}
    for sid, key in reference['chosen_scene_ids'].items():
        entry = by_id[key]
        name = f"{entry['ordinal']:04d}_{key}.json"
        path = HERE/'receipts'/name
        saved = json.loads(path.read_bytes())
        scene = saved['raw_receipt']['scenes'][sid]
        assert scene['state'] == 'SAFE' and scene['complete']
        rows = reference['complete_structural_legality']['scenes'][sid]['rows']
        requests = {}
        for row in rows:
            request = requests.setdefault(row['request_id'], {
                'completion_ms': '0', 'deadline_ms': row['deadline_ms']})
            assert Q(request['deadline_ms']) == Q(row['deadline_ms'])
            request['completion_ms'] = str(max(Q(request['completion_ms']), Q(row['end_ms'])))
        for request in requests.values():
            assert Q(request['completion_ms']) <= Q(request['deadline_ms'])
        scenarios[sid] = {
            'manifest_id': key, 'raw_file': 'receipts/'+name,
            'raw_sha256': sha256(path.read_bytes()).hexdigest(),
            'weight': '1/2', 'energy_J': scene['energy_J'],
            'requests': requests, 'schedule': rows,
            'energy_components_J': scene['energy_components_J'],
            'maximum_peak_upper_degC': str(max(Q(v[1]) for v in scene['peaks_degC'].values()))}
        for name, pair in scene['energy_components_J'].items():
            old = components.setdefault(name, [Q(0), Q(0)])
            for index in (0, 1):
                old[index] += Q(pair[index])/2
    component_sum = [sum(v[i] for v in components.values()) for i in (0, 1)]
    total = list(map(Q, reference['complete_SAFE_energy_J']))
    # Separately rounded outward intervals must overlap, not share endpoints.
    assert component_sum[0] <= total[1] and total[0] <= component_sum[1]
    device_bounds = {}
    for unit in ('CPU1', 'NPU0'):
        device_bounds[unit] = [str(sum(Q(groups[(sid, unit)][key]) for sid in ('AB_offset_0ms', 'AC_offset_0ms'))/2)
                               for key in ('lower', 'upper')]
    return {
        'state': 'SAVED_REFERENCE_DESCRIPTION', 'read_only_no_new_physics': True,
        'reference_sha256': sha256((HERE/'reference.json').read_bytes()).hexdigest(),
        'shared_A_device': reference['shared_A_device'],
        'device_conditioned_joint_minimum_enclosures_J': device_bounds,
        'weighted_energy_components_J': {k: [str(v) for v in pair] for k, pair in components.items()},
        'component_sum_J': list(map(str, component_sum)),
        'component_total_overlap_check': True,
        'scenarios': scenarios, 'new_thermal_calls': 0, 'new_solver_calls': 0}


if __name__ == '__main__':
    result = describe()
    with (HERE/'selected_summary02.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
