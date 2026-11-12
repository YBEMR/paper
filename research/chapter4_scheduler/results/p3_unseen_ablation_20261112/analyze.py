"""Read-only audit and accepted-step attribution; no scientific imports."""
from collections import Counter
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
OLD = OUT.parent / 'unseen_scaling_20261112/execution'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def main():
    plan, summary, batch = read(OUT/'plan.json'), read(OUT/'summary.json'), read(OUT/'batch_return.json')
    checks, details, raws = [], [], {}
    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise ValueError(name)
    check('six planned slots preserved', len(plan['slots']) == len(summary['rows']) == len(batch['slots']) == 6)
    check('no retries and unchanged identity', batch['retry_count'] == 0 and batch['frozen_identity_unchanged'])
    for name, h in plan['source_sha256'].items():
        check('source:' + name, sha(REPO/name) == sha(OUT/'source_snapshot'/name) == h)
    for slot in plan['slots']:
        folder = OUT/'calls'/slot['id']
        if not (folder/'method/result.json').exists():
            details.append({'id': slot['id'], 'status': 'NO_RAW_RESULT', 'batch_stop': batch['stop_reason']})
            continue
        raw, ret = read(folder/'method/result.json'), read(folder/'method_return.json')
        raws[slot['id']] = raw
        ins, cfg = read(folder/'method/input_instance.json'), read(folder/'method/input_config.json')
        check(slot['id'] + ':input', {'instance_sha256': digest(ins), 'config_sha256': digest(cfg)} == plan['input_identities'][slot['case_id']])
        check(slot['id'] + ':fresh input', ret['fresh_input_calls'] == 1)
        check(slot['id'] + ':flag', raw['blocking_edge_adjustment_enabled'] == (slot['arm'] == 'ON'))
        check(slot['id'] + ':budget', raw['timing']['limit_s'] == 300)
        check(slot['id'] + ':raw hash', sha(folder/'method/result.json') == ret['raw_result_sha256'])
        physical = [e for e in raw['evaluations'] if not e.get('cache_hit')]
        journal = ret['evaluation_attempts_journal']
        returned = [j for j in journal if j['state'] == 'RETURNED']
        check(slot['id'] + ':evaluation accounting', [e['candidate_sha256'] for e in physical] == [j['candidate_sha256'] for j in returned])
        safe = [e for e in physical if e.get('accepted_safe')]
        for j, e in enumerate(safe):
            r = e['receipt']
            check(slot['id'] + f':complete receipt {j}', r['state'] == 'SAFE' and r['completed_at_elapsed_s'] <= 300
                and set(r['scenes']) == {s['id'] for s in ins['scenarios']}
                and all(s['complete'] and F(s['covered_until_s']) == F(ins['window_ms'])/1000 for s in r['scenes'].values()))
        steps = []
        if raw.get('initial_safe_snapshot'):
            current = raw['initial_safe_snapshot']
            receipts = {e['candidate_sha256']: e for e in raw['evaluations'] if e.get('accepted_safe')}
            for j, proposal in enumerate(raw['graph_proposals']):
                check(slot['id'] + f':proposal base {j}', proposal['base_candidate_sha256'] == current['candidate_sha256'])
                extra = proposal.get('additional_reversed_edges', [])
                check(slot['id'] + f':additional edge scope {j}', len(extra) <= 1 and (slot['arm'] == 'ON' or not extra))
                if not proposal['strict_accepted']:
                    continue
                new = receipts[proposal['candidate_sha256']]
                old_lo, old_hi = map(F, current['receipt']['weighted_energy_J'])
                new_lo, new_hi = map(F, new['receipt']['weighted_energy_J'])
                check(slot['id'] + f':strict acceptance {j}', new_hi < old_lo)
                changes = []
                for sid, rows in new['candidate']['scenes'].items():
                    before = {r['stage_id']: r for r in current['candidate']['scenes'][sid]}
                    for row in rows:
                        check(slot['id'] + f':fixed unit {j}:{sid}:{row["stage_id"]}', row['unit'] == before[row['stage_id']]['unit'])
                        if row != before[row['stage_id']]:
                            changes.append({'scene': sid, 'before': before[row['stage_id']], 'after': row})
                steps.append({'accepted_step': len(steps)+1, 'proposal_index': j,
                    'has_additional_edge': bool(extra), 'additional_reversed_edges': extra,
                    'target': proposal.get('energy_target'), 'selected_stages': proposal['selected_stages'],
                    'orientation': proposal['orientation'], 'template': proposal['template'],
                    'base_deadline_violations': proposal.get('base_deadline_violations'),
                    'base_blocking_traces': proposal.get('base_blocking_traces'),
                    'old_energy_upper_J': str(old_hi), 'new_energy_upper_J': str(new_hi),
                    'step_upper_difference_J': str(old_hi-new_hi),
                    'candidate_sha256': new['candidate_sha256'], 'changes': changes})
                current = new
            check(slot['id'] + ':accepted steps and final', len(steps) == raw['graph_strict_improvements']
                  and current['candidate'] == raw['safe_candidate'])
        if slot['arm'] == 'OFF':
            check(slot['id'] + ':no extra edge construction', not any(d.get('extra_resource_edge') for d in raw['reconstruction_attempts']))
        post = read(folder/'post_return.json') if (folder/'post_return.json').exists() else None
        if post:
            check(slot['id'] + ':single successful post', post.get('passed') and len(post['evaluation_attempts_journal']) == 1)
            lo, hi = map(F, raw['evaluation']['weighted_energy_J'])
            check(slot['id'] + ':post interval overlap', max(lo,F(post['energy']['lower'])) <= min(hi,F(post['energy']['upper'])))
        graph = raw.get('reconstruction_attempts', [])
        command = read(folder/'method_command_return.json')
        oldid = {'U01__n6': '02_U01__n6_ON', 'U01__n12':'03_U01__n12_ON', 'U02__n6':'05_U02__n6_ON'}[slot['case_id']]
        oldraw = read(OLD/'calls'/oldid/'method/result.json')
        details.append({'id': slot['id'], 'initial_energy_upper_J': raw['initial_safe_snapshot']['receipt']['weighted_energy_J'][1] if raw.get('initial_safe_snapshot') else None,
            'initialization_matches_historical': (raw.get('initial_safe_snapshot') or {}).get('candidate') == oldraw['initial_safe_snapshot']['candidate'],
            'ON_final_matches_historical': raw.get('safe_candidate') == oldraw['safe_candidate'] if slot['arm']=='ON' else None,
            'accepted_steps': steps, 'graph_states': dict(Counter(d['state'] for d in graph)),
            'graph_reasons': dict(Counter(d.get('reason') for d in graph if d.get('reason'))),
            'extra_graph_states': dict(Counter(d['state'] for d in graph if d.get('extra_resource_edge'))),
            'extra_accepted_step_difference_J': str(sum((F(s['step_upper_difference_J']) for s in steps if s['has_additional_edge']),F(0))),
            'ordinary_accepted_step_difference_J': str(sum((F(s['step_upper_difference_J']) for s in steps if not s['has_additional_edge']),F(0))),
            'process_wall_s': command['wall_s'], 'post_process_wall_s': read(folder/'post_command_return.json')['wall_s'] if post else None})
    pairs = []
    for c in summary['comparisons']:
        arms = {s['arm']: s for s in plan['slots'] if s['case_id'] == c['case_id']}
        if any(s['id'] not in raws for s in arms.values()):
            pairs.append({**c, 'audit_status':'MISSING_RAW'})
            continue
        on, off = raws[arms['ON']['id']], raws[arms['OFF']['id']]
        initialized = on.get('initial_safe_snapshot') and off.get('initial_safe_snapshot')
        same_metadata = on.get('initialization') == off.get('initialization')
        same_energy = initialized and on['initial_safe_snapshot']['receipt']['weighted_energy_J'] == off['initial_safe_snapshot']['receipt']['weighted_energy_J']
        pairs.append({**c, 'same_initialization_metadata': same_metadata, 'same_initial_energy_interval': bool(same_energy),
            'both_searches_completed': all(r['run_terminal']=='SEARCH_COMPLETED' for r in (on,off))})
        if c['comparable_SAFE_pair']:
            check(c['case_id'] + ':shared initial history and energy', same_metadata and same_energy)
    value = {'scope': 'read-only receipt/trajectory audit; no new thermal or optimizer calls',
        'checks': checks, 'passed': all(c['passed'] for c in checks), 'checks_passed': len(checks),
        'details': details, 'pairs': pairs,
        'attribution_limit': 'ON/OFF net difference is measured under this paired algorithm switch. Within-ON step sums are descriptive and include joint mode/order changes; subsequent ordinary steps cannot all be credited to one edge.'}
    with (OUT/'analysis.json').open('x',encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'checks_passed':len(checks),'pairs':pairs},ensure_ascii=False))


if __name__ == '__main__':
    main()
