"""Read archived cloud JSON only: no scientific module imports or new models.

This is explicitly NOT an analysis of the inaccessible Windows native ZIP.
"""
from pathlib import Path
from fractions import Fraction
from collections import Counter
from datetime import datetime, timezone
import csv
import hashlib
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
OLD = ROOT/'research/chapter3_support_propagation_20261110'
reads = {}


def read(path):
    raw = path.read_bytes()
    reads[str(path.relative_to(ROOT))] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)


def main():
    began = datetime.now(timezone.utc).isoformat(); t0 = time.monotonic()
    instance = read(OLD/'baseline/input_instance.json')
    mode_counts = {key: len(value) for key, value in instance['stage_modes'].items()}
    variants = {}; rows = []
    for variant in ('off', 'on'):
        directory = OLD/'r1_diagnostic'/variant
        result = read(directory/'result.json')
        options = read(directory/'options.json')
        summary = read(directory/'model_summary.json')
        construction = result['construction']; scenes = {}
        for scene in instance['scenarios']:
            sid = scene['id']
            events = {Fraction(0), Fraction(instance['window_ms'])}
            for option in options:
                if option['scenario_id'] == sid:
                    events.update((Fraction(option['start_ms']), Fraction(option['end_ms'])))
            ordered = sorted(events)
            histogram = Counter(b-a for a, b in zip(ordered, ordered[1:]))
            assert len(events) == summary['events_per_scene'][sid]
            assert len(events)-1 == result['intervals'][sid]
            scenes[sid] = {'events': len(events), 'intervals': len(events)-1,
                'joint_blocks': result['joint_state_blocks'][sid],
                'unique_segment_durations': len(histogram),
                'segment_duration_ms_histogram': {str(k): v for k, v in sorted(histogram.items())}}
        assert result['new_native_solver_calls'] == 0
        stats = {'options': len(options), 'variables': result['variable_count'],
            'rows': result['row_count'], 'nnz': result['matrix_nnz'],
            'intervals': sum(result['intervals'].values()),
            'joint_blocks': sum(result['joint_state_blocks'].values()),
            'coefficient_sets': construction['coefficient_sets_completed'],
            'affine_hits': construction['affine_templates']['hits'],
            'affine_misses': construction['affine_templates']['misses'],
            'affine_clears': construction['affine_templates']['clears'],
            'conditional_misses': construction['conditional_templates']['misses'],
            'construct_s': result['budget']['phases_exclusive_s']['model_construction'],
            'coeff_lookup_and_generation_s': construction['construction_components']['coefficient_lookup_and_generation']['exclusive_s'],
            'conditional_rows_s': construction['construction_components']['thermal_conditional_rows']['exclusive_s'],
            'affine_miss_binding_s': construction['construction_details']['affine_miss_binding']['exclusive_s'],
            'first_initial_SAFE_s': result['first_initial_SAFE_at_s'],
            'seed_sha256': result['initial_candidate_sha256'],
            'SAFE_energy_upper_J': result['initial_safe_upper_bound_J'],
            'native_solver_calls': result['new_native_solver_calls']}
        variants[variant] = {'scenes': scenes, 'stats': stats}
    assert variants['off']['stats']['seed_sha256'] == variants['on']['stats']['seed_sha256']
    changes = {}
    for key, before in variants['off']['stats'].items():
        after = variants['on']['stats'][key]
        if isinstance(before, (int, float)) and before:
            changes[key] = {'off': before, 'on': after,
                'change_percent': 100*(after-before)/before}
            rows.append({'metric': key, **changes[key]})
    audit = {'scope': 'Archived Linux construction/seed JSON only; NOT Windows native paired results.',
        'started_utc': began, 'ended_utc': datetime.now(timezone.utc).isoformat(),
        'wall_s': time.monotonic()-t0, 'argv': [sys.executable, '-B', str(Path(__file__).relative_to(ROOT))],
        'input_mode_counts': mode_counts, 'total_unique_stage_modes': sum(mode_counts.values()),
        'executed_stages_per_scenario': {s['id']: len(s['stage_instances']) for s in instance['scenarios']},
        'variants': variants, 'changes': changes, 'source_sha256': reads,
        'new_model_builds': 0, 'new_thermal_calls': 0, 'new_solver_calls': 0,
        'interpretation_limits': ['Timing is one archived pair, not causal/statistical performance proof.',
            'Misses include cache-clear re-creation, not necessarily globally unique templates.',
            'Construction component/detail timings nest; do not sum parent and child intervals.',
            'Reconstructed event histograms describe archived option boundaries only.',
            'No MATLAB root LP/node/lower-bound/native x0 conclusion follows from this cloud JSON.',
            'Old prose count72 stage modes is corrected to66 in this new audit; old records untouched.']}
    with (OUT/'saved_cloud_audit.json').open('x', encoding='utf-8') as stream:
        json.dump(audit, stream, ensure_ascii=False, indent=2); stream.write('\n')
    with (OUT/'saved_cloud_comparison.csv').open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=('metric', 'off', 'on', 'change_percent'))
        writer.writeheader(); writer.writerows(rows)
    print(json.dumps({'scope': audit['scope'], 'total_unique_stage_modes': sum(mode_counts.values()),
        'changes': changes, 'scenes': {k: v['scenes'] for k, v in variants.items()},
        'new_model_builds': 0, 'new_thermal_calls': 0, 'new_solver_calls': 0}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
