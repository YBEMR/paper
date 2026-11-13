"""Read saved trajectories and costs only; no scheduler or evaluator imports."""
from collections import Counter, defaultdict
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
read = lambda p: json.loads(p.read_text(encoding='utf-8'))


def prefix(x, y):
    return next((i for i, (a, b) in enumerate(zip(x, y)) if a != b), min(len(x), len(y)))


def main():
    data = read(OUT / 'analysis.json')
    supplementary = read(OUT / 'supplementary_checks.json')
    result = {'new_scientific_calls': 0, 'common_prefixes': {}, 'mechanism_paths': {},
              'initialization_failures': {}, 'attempt_failure_reasons': {}}
    for root in ('U07', 'U08', 'U09', 'U10'):
        rows = {r['arm']: r for r in data['rows'] if r['root_id'] == root}
        raws = {arm: read(OUT / 'execution/calls' / r['id'] / 'method/result.json') for arm, r in rows.items()}
        ds = {arm: data['details'][r['id']] for arm, r in rows.items()}
        # Verify acceptance timestamps are not silently replaced by later cache hits.
        for arm, raw in raws.items():
            events = {e['candidate_sha256']: e for e in raw['events']}
            for step in ds[arm]['accepted_steps']:
                matches = [e for e in raw['evaluations'] if e['candidate_sha256'] == step['sha256']]
                assert len(matches) == 1, (root, arm, step['sha256'])
                # Events use receipt completion; return includes serialization work.
                assert events[step['sha256']]['at_s'] == matches[0]['receipt']['completed_at_elapsed_s']
                assert events[step['sha256']]['at_s'] <= step['returned_at_s'] <= events[step['sha256']]['transferred_at_s']
        clean = lambda p: {k: v for k, v in p.items() if k not in ('proposed_at_s', 'strict_accepted')}
        props = {a: [clean(p) for p in raws[a]['graph_proposals']] for a in ('ON', 'ON_P')}
        n = prefix(props['ON'], props['ON_P'])
        na = prefix(ds['ON']['accepted_sequence'], ds['ON_P']['accepted_sequence'])
        comparison = next(c for c in data['comparisons'] if c['case_id'] == rows['ON']['case_id'] and c['arm'] == 'ON_P' and c['reference'] == 'ON')
        common = {'comparability': comparison['comparability'],
                  'proposal_common_prefix_length': n,
                  'proposal_lengths': {a: len(p) for a, p in props.items()},
                  'accepted_common_prefix_length': na, 'arms': {}}
        if comparison['same_initial'] and na:
            for arm in ('ON', 'ON_P'):
                cut = ds[arm]['accepted_steps'][na - 1]['returned_at_s']
                handoff = rows[arm]['initialization_completed_at_s']
                costs = defaultdict(float)
                for phase in raws[arm]['timing']['phase_records']:
                    if phase['start_s'] >= handoff and phase['end_s'] <= cut + 1e-6:
                        costs[phase['phase']] += phase['exclusive_s']
                pf = costs['structural_prefilter_setup'] + costs['structural_prefilter_check']
                common['arms'][arm] = {'handoff_s': handoff, 'common_accept_at_s': cut,
                    'search_to_common_accept_s': cut - handoff,
                    'construction_plus_prefilter_s': costs['blocking_graph_construct'] + pf,
                    'prefilter_s': pf, 'phase_exclusive_s': dict(costs),
                    'later_accepted_steps': ds[arm]['accepted_steps'][na:]}
        else:
            common['cost_attribution'] = 'Different handoff; no same-work cost comparison.'
        result['common_prefixes'][root] = common
        result['mechanism_paths'][root] = {
            'ON_P_OFF_P_common_accepted_prefix': prefix(ds['ON_P']['accepted_sequence'], ds['OFF_P']['accepted_sequence']),
            'ON_P_extra_steps': [s for s in ds['ON_P']['accepted_steps'] if s['extra_edges']],
            'accepted_counts': {a: len(ds[a]['accepted_sequence']) for a in rows},
            'proposal_counts': {a: len(ds[a]['proposal_sequence']) for a in rows}}
        for arm, row in rows.items():
            init = supplementary['initialization_details'][row['id']]
            result['initialization_failures'][row['id']] = [x for x in init['construction_attempts'] if x.get('reason')]
            result['attempt_failure_reasons'][row['id']] = ds[arm]['attempt_failure_reasons']
    result['initialization_failed_constructions'] = sum(map(len, result['initialization_failures'].values()))
    result['max_final_peak_C'] = max(float(r['peak_temperature_upper_C']) for r in data['rows'])
    result['first_SAFE_s_range'] = [min(r['first_SAFE_at_s'] for r in data['rows']), max(r['first_SAFE_at_s'] for r in data['rows'])]
    result['search_evaluation_share_range'] = [fn(r['search_evaluation_s'] / r['search_s'] for r in data['rows'] if r['search_s']) for fn in (min, max)]
    (OUT / 'path_diagnostics.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('initialization_failures', 'attempt_failure_reasons', 'mechanism_paths')}, indent=2))


if __name__ == '__main__':
    main()
