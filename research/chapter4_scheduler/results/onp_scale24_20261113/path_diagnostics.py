"""Read-only common-prefix accounting; never imports or calls a scheduler."""
from collections import defaultdict
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
read = lambda p: json.loads(p.read_text(encoding='utf-8'))


def main():
    analysis = read(OUT / 'analysis.json')
    rows = analysis['rows']
    old = read(OUT.parent / 'onp_unseen_20261113/analysis.json')
    result = {'new_scientific_calls': 0, 'common_prefixes': {}, 'scale_cost_ranges': {}}
    for root in ('U05', 'U06'):
        pair = {r['arm']: r for r in rows if r['root_id'] == root and r['arm'] in ('ON', 'ON_P')}
        raws = {arm: read(OUT / 'execution/calls' / r['id'] / 'method/result.json') for arm, r in pair.items()}
        props = {arm: raw['graph_proposals'] for arm, raw in raws.items()}
        n = min(map(len, props.values()))
        # Outcomes may differ at the budget boundary, but candidate payloads must match.
        clean = lambda p: {k: v for k, v in p.items() if k not in ('proposed_at_s', 'strict_accepted')}
        assert all(clean(x) == clean(y) for x, y in zip(props['ON'], props['ON_P']))
        ds = {arm: analysis['details'][r['id']] for arm, r in pair.items()}
        na = min(len(d['accepted_steps']) for d in ds.values())
        assert [x['sha256'] for x in ds['ON']['accepted_steps'][:na]] == [x['sha256'] for x in ds['ON_P']['accepted_steps'][:na]]
        common = {'proposal_prefix_length': n, 'proposal_payloads_equal_excluding_time_and_acceptance': True,
                  'common_accepted_prefix_length': na, 'arms': {}}
        for arm, r in pair.items():
            cut = ds[arm]['accepted_steps'][na - 1]['returned_at_s']
            handoff = r['initialization_completed_at_s']
            costs = defaultdict(float)
            for phase in raws[arm]['timing']['phase_records']:
                if phase['start_s'] >= handoff and phase['end_s'] <= cut + 1e-6:
                    costs[phase['phase']] += phase['exclusive_s']
            construction = costs['blocking_graph_construct']
            prefilter = costs.get('structural_prefilter_setup', 0) + costs.get('structural_prefilter_check', 0)
            common['arms'][arm] = {'handoff_s': handoff, 'last_common_accept_at_s': cut,
                                  'search_to_common_accept_s': cut - handoff,
                                  'construction_s': construction, 'prefilter_s': prefilter,
                                  'construction_plus_prefilter_s': construction + prefilter,
                                  'continuous_evaluation_s': costs['complete_continuous_evaluation'],
                                  'phase_exclusive_s': dict(costs),
                                  'remaining_proposals': [
                                      {k: v for k, v in p.items() if k in ('candidate_sha256', 'proposed_at_s', 'strict_accepted', 'additional_reversed_edges')}
                                      for p in props[arm][na:]]}
        result['common_prefixes'][root] = common
        result['scale_cost_ranges'][root] = {}
        for scale, data in ((12, old), (24, analysis)):
            rr = [r for r in data['rows'] if r['root_id'] == root]
            result['scale_cost_ranges'][root][str(scale)] = {
                'first_safe_s': [min(r['first_SAFE_at_s'] for r in rr), max(r['first_SAFE_at_s'] for r in rr)],
                'init_handoff_s': [min(r['initialization_completed_at_s'] for r in rr), max(r['initialization_completed_at_s'] for r in rr)],
                'completed_safe_mean_evaluation_s': [min(r['full_SAFE_evaluation_mean_s'] for r in rr), max(r['full_SAFE_evaluation_mean_s'] for r in rr)],
                'search_continuous_share': [r['search_evaluation_s'] / r['search_s'] for r in rr if r['search_s']]}
    (OUT / 'path_diagnostics.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'common_prefixes': {k: {x: v[x] for x in ('proposal_prefix_length', 'common_accepted_prefix_length')} for k, v in result['common_prefixes'].items()},
                      'scale_cost_ranges': result['scale_cost_ranges'], 'new_scientific_calls': 0}, indent=2))


if __name__ == '__main__':
    main()
