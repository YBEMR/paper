"""Read archived JSON/NPZ; no scheduling, compilation, or thermal evaluation."""
import csv
import hashlib
import json
from pathlib import Path
from time import perf_counter
import numpy as np

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]
ROOT = EXP.parents[1]
started = perf_counter()
def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def blob(p):
    b = p.read_bytes()
    return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def write(name, obj):
    (HERE/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')

pins = read(HERE/'provenance.json')
for pin in pins['remote_files']:
    assert blob(ROOT/pin['path']) == pin['blob_sha1'], pin
manifest = read(EXP/'freeze_manifest.json')
frozen = []
for path, expected in manifest['files'].items():
    actual = sha(ROOT/path)
    assert actual == expected, path
    frozen.append(dict(path=path, sha256=actual))
delivery = read(EXP/'delivery_manifest.json')
for rec in delivery['files']:
    assert sha(ROOT/rec['path']) == rec['sha256'], rec['path']

summary, deployments, npz_records, witnesses = [], [], [], []
for directory in sorted((EXP/'raw/expanded').glob('*25C')):
    result = read(directory/'result.json')
    rows = read(directory/'deployments.json')
    total = lambda key: sum(r.get(key,0) for r in rows)
    cost = dict(case=directory.name, completed=len(rows), total_deployments=81,
        elapsed_s=result['elapsed_s'], scheduling_s=total('scheduling_s'),
        compile_s=total('compile_s'), search_s=total('joint_search_s'),
        local_s=total('local_select_s'), archive_s=total('npz_write_s'),
        prefixes=total('joint_prefix_evaluations'),
        fallback=total('joint_fallback_integrations'),
        independent_fallback=total('independent_fallback_integrations'),
        compiled_actions=total('compiled_scene_actions'),
        compilation_integrations=total('compilation_original_integrations'),
        full_replays=result['full_policy_replays'], full_replay_s=result['full_replay_s'],
        partial=result['partial_deployment'], logical=result['logical_complete_sequences'])
    cost['fallback_fraction'] = cost['fallback']/cost['prefixes']
    cost['search_wall_fraction'] = cost['search_s']/cost['elapsed_s']
    cost['compile_wall_fraction'] = cost['compile_s']/cost['elapsed_s']
    cost['search_s_for_deployments_with_fallback'] = sum(r['joint_search_s'] for r in rows if r['joint_fallback_integrations'])
    cost['search_s_for_deployments_without_fallback'] = sum(r['joint_search_s'] for r in rows if not r['joint_fallback_integrations'])
    cost['deployments_with_fallback'] = sum(bool(r['joint_fallback_integrations']) for r in rows)
    safe_unconstrained, minimums = 0, []
    for row in rows:
        path = directory/row['array_archive']['path']
        assert sha(path) == row['array_archive']['sha256']
        with np.load(path, allow_pickle=False) as archive:
            status, energy = archive['status'], archive['energy_j']
            eligible = np.flatnonzero(status != 0)
            assert np.array_equal(np.isfinite(energy), status != 0)
            assert not np.any(status == 3)
            minimum = float(energy[eligible].min()) if len(eligible) else None
            pick = int(eligible[np.flatnonzero(energy[eligible] <= minimum+1e-9)[0]]) if minimum is not None else None
            saved = row['no_thermal_constraint']
            assert (saved is None) == (pick is None)
            if pick is not None:
                assert pick == saved['code']
                assert abs(float(energy[pick])-saved['predicted_j']) <= 1e-7
                safe_unconstrained += int(status[pick] == 1)
                minimums.append(dict(deployment=row['deployment'], code=pick,
                                     minimum_j=minimum, selected_j=float(energy[pick]), status=int(status[pick])))
            npz_records.append(dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path),
                                    legal=int(len(eligible)), safe=int(np.sum(status==1))))
        deployments.append(dict(case=directory.name, deployment=row['deployment'],
            prefixes=row['joint_prefix_evaluations'], fallback=row['joint_fallback_integrations'],
            compile_s=row['compile_s'], search_s=row['joint_search_s'],
            depth=row['deadline_legal_prefixes']))
    choice = result['decisions']['no_thermal_constraint']
    physical = choice['physical']
    assert physical['thermal_status'] == 'SAFE' and physical['deadline_ok']
    assert physical['required'] == physical['completed'] == 500 and physical['fully_replayed']
    assert abs(choice['predicted_j']-physical['energy_j']) <= 1e-7
    assert all(x <= 80 for x in physical['peak_upper_c'])
    joint = result['decisions']['joint']
    assert (choice['deployment'],choice['code']) == (joint['deployment'],joint['code'])
    cost.update(unconstrained_safe_deployments=safe_unconstrained, unconstrained_deployments=len(minimums),
        winner=choice['deployment'], code=choice['code'], energy_j=physical['energy_j'],
        peak_upper_c=max(physical['peak_upper_c']), complete=result['coverage_complete'],
        strict_unconstrained_min_j=min(x['minimum_j'] for x in minimums),
        chosen_minus_min_j=physical['energy_j']-min(x['minimum_j'] for x in minimums))
    summary.append(cost)
    witnesses.append(dict(case=directory.name, scope=result['claimed_scope'],
                          no_thermal_choice=choice, strict_minima=minimums))
    print(json.dumps(cost, ensure_ascii=False), flush=True)
write('archive_summary.json', summary)
write('deployment_costs.json', deployments)
write('baseline_witnesses.json', witnesses)
write('input_hashes.json', dict(remote_pins=pins['remote_files'], frozen=frozen,
    delivery_manifest_sha256=sha(EXP/'delivery_manifest.json'),
    delivery_checked=len(delivery['files']), arrays=npz_records))
write('archive_receipt.json', dict(frozen_files=len(frozen), delivery_files=len(delivery['files']),
    expanded_npz=len(npz_records), scientific_calls=0, wall_s=perf_counter()-started,
    all_checks_passed=True))
print('PASS: pinned manifests, frozen source, delivery hashes and 196 NPZ; zero new scientific calls.')
