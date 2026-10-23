"""Independent stdlib joins of frozen U timeline, original domains and replay."""
from fractions import Fraction as F
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def require(value, label):
    if not value:
        raise ValueError(label)


def main(replay_path=None):
    if replay_path is not None:
        replay_path = replay_path.resolve()
    timeline_path, domain_path = HERE/'facts.json', HERE.parent/'domain/facts.json'
    timeline, domain = read(timeline_path), read(domain_path)
    before = {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p)
              for p in (timeline_path, domain_path, HERE.parent/'replay.py')}
    require(timeline['status'] == 'PASS' and domain['passed'], 'extractors not complete')
    joined = []
    for case in timeline['cases']:
        result_path = ROOT/case['result_path']
        before[case['result_path']] = sha(result_path)
        require(before[case['result_path']] == timeline['original_file_sha256'][case['result_path']],
                'original result no longer matches timeline identity')
        result = read(result_path)
        for b in case['builds']:
            key = '%s/phase_%s/%s' % (case['problem_id'], b['phase_index'], b['scene_id'])
            matches = [d for d in domain['builds'] if d['build_key'] == key]
            require(len(matches) == 1, 'missing or duplicate domain')
            d = matches[0]
            require(d['all_checks_passed'] and d['condition_sha256'] == b['condition_sha256'],
                    'domain condition identity')
            phase = next(p for p in result['phases'] if p['phase_index'] == b['phase_index'])
            cond = phase['condition']
            anchor_options = cond.get('warm_options_by_scene', cond['seed_options_by_scene'])
            for sid, rows in d['phase_condition']['by_scene'].items():
                opened = set(cond['opened_by_scene'][sid])
                require(set(rows) == set(cond['seed_options_by_scene'][sid]), 'partial coverage')
                for stage, fields in rows.items():
                    require(fields['unit'] == cond['seed_options_by_scene'][sid][stage]['unit'],
                            'fixed unit is not fresh-seed unit')
                    expected = {'unit': fields['unit']}
                    if stage not in opened:
                        expected['opp'] = anchor_options[sid][stage]['opp']
                    require(fields == expected, 'partial uses wrong closure or freezes open OPP')
            sid = d['scene_id']
            rows = d['opened_rows'] + d['closed_rows']
            for row in rows:
                stage = row['stage_id']
                opened = stage in cond['opened_by_scene'][sid]
                require(row['opened'] is opened, 'countable rows use wrong phase opened set')
                require(row['unit'] == cond['seed_options_by_scene'][sid][stage]['unit'], 'mode row unit')
                if not opened:
                    anchor = anchor_options[sid][stage]
                    require(row['closed_opp'] == anchor['opp']
                            and F(row['closed_start_ms']) == F(anchor['start_ms']), 'closed anchor fields')
                for mode in row['modes']:
                    require(mode['unit'] == row['unit'], 'a fixed-unit domain silently opens device')
                    require(mode['options_nonzero'] == len(mode['starts_ms']) == len(mode['option_columns']),
                            'mode support does not match actual option columns')
            u = b['timely_upper']
            agg = result['aggregation_attempts'][u['source_aggregation_index']]
            require(agg['receipt_sha256'] == u['receipt_sha256']
                    and digest(agg['safe_candidate']) == u['candidate_sha256']
                    and agg['safe_upper_bound_J'] == u['upper_J'], 'timely U aggregation index')
            ticks = [F(str(u[k])) for k in ('formed_at_s', 'committed_at_s',
                     'transferred_at_s', 'observer_completed_at_s')]
            require(ticks == sorted(ticks) and max(ticks) < F(str(b['build_started_at_s'])),
                    'late U backfill')
            expected_local = {'scenes': {sid: agg['safe_candidate']['scenes'][sid]}}
            require(d['actual_x0']['candidate'] == expected_local, 'actual x0 belongs to another generation')
            require(d['actual_x0']['local_candidate_sha256'] == digest(expected_local), 'actual x0 hash')
            warm_options = {row['stage_id']: {k: v for k, v in row.items() if k != 'stage_id'}
                            for row in d['warm_rows']}
            require(warm_options == anchor_options[sid], 'condition warm row identity')
            joined.append({'build_key': key, 'passed': True,
                'source_update_index': u['source_update_index'],
                'source_aggregation_index': u['source_aggregation_index'],
                'timely_upper_J': u['upper_J'], 'available_before_build': True,
                'phase_condition_from_original_frozen_anchor': True,
                'actual_x0_from_timely_complete_generation': True,
                'fixed_unit_opp_not_confused': True})
    require(len(joined) == len(domain['builds']) == 20, 'not all 20 builds')
    replay_checks = None
    if replay_path:
        before[str(replay_path.relative_to(ROOT)).replace('\\', '/')] = sha(replay_path)
        replay = read(replay_path)
        require(replay['passed'] and len(replay['records']) == 20, 'root replay incomplete')
        comparisons = []
        for record in replay['records']:
            item = next(r for r in joined if r['build_key'] == record['build_key'])
            require(record['timely_upper']['source_aggregation_index'] == item['source_aggregation_index']
                    and record['timely_upper']['source_update_index'] == item['source_update_index']
                    and record['timely_upper']['upper_J'] == item['timely_upper_J'], 'root replay changed timely U')
            probes = record['probes']
            require(all(not p['decision']['excludable'] or not p['in_actual_x0'] for p in probes),
                    'actual SAFE x0 removed')
            require(all((F(p['bound']['lower_bound_J']) > F(item['timely_upper_J']))
                        == p['decision']['excludable'] for p in probes), 'strict comparison changed')
            comparisons.append({'build_key': record['build_key'], 'passed': True})
        replay_checks = {'root_result': str(replay_path.relative_to(ROOT)).replace('\\', '/'),
                         'builds': comparisons, 'all_actual_safe_x0_modes_preserved': True}
    after = {name: sha(ROOT/name) for name in before}
    require(before == after, 'review input changed during read')
    out = {'passed': True, 'read_only': True, 'research_calls': 0, 'thermal_calls': 0,
           'production_imports': 0, 'builds': joined, 'root_replay_review': replay_checks,
           'sha256_before': before, 'sha256_after': after}
    suffix = 'replay_review.json' if replay_path else 'joined_domain_review.json'
    (HERE/suffix).write_text(json.dumps(out, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'builds': len(joined), 'root_replay_reviewed': bool(replay_path),
                      'output': suffix}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--replay', type=Path)
    args = parser.parse_args()
    main(args.replay)
