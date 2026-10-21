"""K149: exact static closed-anchor dependency audit of archived labels.

Standard library only. No production module, model builder, optimizer or heat
evaluator is imported. Counts predict a proposed filter's topology; they are not
new matrices, LP timing, energy results or performance evidence. Input records
are immutable; an existing output directory is always refused.
"""
from argparse import ArgumentParser
from collections import Counter
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
RUN = HERE.parent / 'linked_five_open_pair01'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def topology(options, instance):
    events = sorted({F(0), F(instance['window_ms'])}
                    | {o[k] for o in options for k in ('start', 'end')})
    state_count = 0
    for left, right in zip(events, events[1:]):
        assert left < right
        possible = {domain: {'L'} for domain in instance['platform']['domains']}
        for option in options:
            if option['start'] <= left < option['end']:
                possible[option['domain']].add(option['opp'])
        count = 1
        for values in possible.values():
            count *= len(values)
        state_count += count
    return {'options': len(options), 'events': len(events),
            'intervals': len(events) - 1, 'joint_state_groups': state_count,
            'conditional_temperature_energy_row_pairs': state_count
            * (len(instance['platform']['node_order']) + 1)}


def resource_conflicts(option, anchor):
    if max(option['start'], anchor['start']) >= min(option['end'], anchor['end']):
        return []
    reasons = []
    if option['unit'] == anchor['unit']:
        reasons.append('same_unit_overlap')
    if option['domain'] == anchor['domain'] and option['opp'] != anchor['opp']:
        reasons.append('shared_domain_different_opp_overlap')
    return reasons


def serial_option(option):
    return {key: str(value) if isinstance(value, F) else value
            for key, value in option.items()}


def analyze(out):
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(f'Refusing existing output directory: {out}')
    source_path = Path(__file__).resolve()
    source_hash = sha(source_path)
    inputs = {}

    def read(path):
        path = Path(path)
        raw = path.read_bytes()
        inputs[path.relative_to(REPO).as_posix()] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    instance = read(RUN / 'input_instance.json')
    result = read(RUN / 'old_linked4' / 'result.json')
    existing = read(HERE / 'facts.json')
    existing_scenes = {row['scene']: row for row in existing['old4_static_scenes']}
    modes = {(shared, mode['unit_id'], mode['opp_id']): mode
             for shared, values in instance['stage_modes'].items() for mode in values}
    condition = result['phases'][1]['condition']
    rows = []
    for index, scene in enumerate(instance['scenarios']):
        sid = scene['id']
        shared = {stage['id']: stage['shared_stage_id'] for stage in scene['stage_instances']}
        labels = read(RUN / 'old_linked4' / 'pass_02' / f'scene_{index}'
                      / 'augmented_requests' / f'request_{index + 1:06d}' / 'labels.json')
        options = []
        for name in labels['names']:
            if not name.startswith('y:'):
                continue
            stage, suffix = name[2:].rsplit('@', 1)
            unit, opp, slot = suffix.split(':')
            assert stage in shared and slot.startswith('g')
            mode = modes[shared[stage], unit, opp]
            start = F(instance['start_grid_ms']) * int(slot[1:])
            options.append({'name': name, 'stage': stage, 'unit': unit, 'opp': opp,
                            'domain': mode['domain_id'], 'start': start,
                            'end': start + F(mode['duration_ms'])})
        opened = set(condition['opened_by_scene'][sid])
        closed = set(shared) - opened
        anchors = [option for option in options if option['stage'] in closed]
        assert len(closed) == len(anchors) == len({a['stage'] for a in anchors}) == 2
        edges = {tuple(edge) for edge in scene['dependencies']}
        warm = condition['warm_options_by_scene'][sid]
        for anchor in anchors:
            point = warm[anchor['stage']]
            assert (anchor['unit'], anchor['opp'], anchor['start']) == (
                point['unit'], point['opp'], F(point['start_ms']))
        retained, resource_retained, removed = [], [], []
        resource_count = dependency_count = incremental_count = 0
        for option in options:
            resources, dependencies = [], []
            for anchor in anchors:
                if anchor['stage'] != option['stage']:
                    reasons = resource_conflicts(option, anchor)
                    if reasons:
                        resources.append({'anchor_stage': anchor['stage'], 'reasons': reasons})
                if ((option['stage'], anchor['stage']) in edges
                        and option['end'] > anchor['start']):
                    dependencies.append({
                        'anchor_stage': anchor['stage'],
                        'rule': 'open_predecessor_end_exceeds_closed_successor_start',
                        'open_end': str(option['end']), 'closed_start': str(anchor['start'])})
                if ((anchor['stage'], option['stage']) in edges
                        and anchor['end'] > option['start']):
                    dependencies.append({
                        'anchor_stage': anchor['stage'],
                        'rule': 'open_successor_start_precedes_closed_predecessor_end',
                        'open_start': str(option['start']), 'closed_end': str(anchor['end'])})
            resource_count += bool(resources)
            dependency_count += bool(dependencies)
            incremental_count += bool(dependencies and not resources)
            if not resources:
                resource_retained.append(option)
            if resources or dependencies:
                assert option['stage'] in opened
                removed.append({'option': serial_option(option),
                                'resource_reasons': resources,
                                'direct_dependency_reasons': dependencies,
                                'incremental_dependency_removal': bool(dependencies and not resources)})
            else:
                retained.append(option)
        keys = {(o['stage'], o['unit'], o['opp'], o['start']) for o in retained}
        assert all((stage, point['unit'], point['opp'], F(point['start_ms'])) in keys
                   for stage, point in warm.items())
        before = topology(options, instance)
        resource_topology = topology(resource_retained, instance)
        assert before == existing_scenes[sid]['before']
        assert resource_topology == existing_scenes[sid]['after_static_filter']
        assert {o['name'] for o in options if o not in resource_retained} == {
            o['name'] for o in existing_scenes[sid]['removed_options']}
        assert before['joint_state_groups'] == sum(name.startswith('w:') for name in labels['names'])
        tags = Counter(labels['row_tags'])
        physical_rows = sum(count for tag, count in tags.items()
                            if tag.startswith(('thermal_propagation/', 'complete_energy/')))
        assert physical_rows == 2 * before['conditional_temperature_energy_row_pairs']
        rows.append({'scene': sid, 'anchors': list(map(serial_option, anchors)),
                     'before': before, 'after_resource_only': resource_topology,
                     'after_resource_and_direct_dependency': topology(retained, instance),
                     'resource_removed': resource_count, 'dependency_removed': dependency_count,
                     'union_removed': len(removed), 'incremental_dependency_removed': incremental_count,
                     'warm_retained': True,
                     'original_topology_matches_saved_labels_and_rows': True,
                     'resource_subset_matches_existing_facts': True,
                     'removed_options_with_individual_evidence': removed})
    assert sha(source_path) == source_hash
    assert all(sha(REPO / path) == digest for path, digest in inputs.items())
    note = {
        'analysis': 'K149-closed-anchor-direct-dependency-static-audit-v2',
        'recommendation': 'One fixed-anchor presolve: resource, shared-domain OPP and direct dependency implications.',
        'scope': 'Archived labels and exact input constants only; one pass, no open-open CDF or transitive closure.',
        'research_calls': 0, 'model_constructions': 0, 'lp_calls': 0,
        'native_calls': 0, 'heat_evaluations': 0, 'production_changes': 0,
        'static_topology_only': True, 'new_matrix_generated': False,
        'performance_or_energy_benefit_established': False,
        'rows': rows, 'input_sha256': inputs,
        'source_sha256': {source_path.relative_to(REPO).as_posix(): source_hash},
        'raw_inputs_unchanged': True,
        'proof': 'A closed anchor is mandatory. Integral one-hot direct dependencies require chosen end <= chosen start. An option violating the fixed endpoint cannot occur. Removing it preserves exact integer legal arrangements and can strengthen expected-time LP rows.',
        'risk': 'Equality is allowed and Fraction endpoints are exact. Never use open-stage warm choices as fixed anchors. Exact physical-domain preservation is not old binary64 matrix pointwise equivalence.',
    }
    out.mkdir(parents=True, exist_ok=False)
    (out / 'anchor_dependency_note.json').write_text(
        json.dumps(note, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(out / 'anchor_dependency_note.json'),
                      'scenes': [{key: row[key] for key in (
                          'scene', 'before', 'after_resource_only',
                          'after_resource_and_direct_dependency',
                          'incremental_dependency_removed', 'warm_retained')} for row in rows]},
                     ensure_ascii=False))
    return note


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=HERE / 'direct_dependency_analysis01',
                        help='New output directory; existing directories are refused.')
    analyze(parser.parse_args().out)
