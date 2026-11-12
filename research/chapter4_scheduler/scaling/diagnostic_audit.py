"""Read-only P1/P2 receipt audit; no scientific imports or new evaluation."""
from collections import Counter
from fractions import Fraction as F
import json
from pathlib import Path

from research.chapter4_scheduler.scaling.diagnose import EX, OUT, read, save, digest, verify


def main():
    source_count = verify()
    checks = []

    def check(name, predicate):
        checks.append({'check': name, 'passed': bool(predicate)})
        assert predicate, name

    replay = read(OUT / 'replay.json')
    check('four structural replays only', len(replay['attempts']) == 4 and replay['thermal_evaluations'] == 0)
    originals = [read(EX / 'calls' / name / 'method/result.json') for name in ('07_U02__n12_HEFT', '08_U02__n12_ON')]
    check('both old failures retained', all(r['safe_candidate'] is None and not r['evaluations'] for r in originals))
    for index, attempt in enumerate(replay['attempts']):
        check(f'replay {index} identical to both original attempts', all(
            attempt['metadata'] == r['initialization']['construction_attempts'][index] for r in originals))
        check(f'replay {index} unchanged deployment decisions', all(
            a['shared_stage_id'] == b['shared_stage_id'] and a['selected_unit'] == b['unit']
            for a, b in zip(attempt['committed_choices'], attempt['metadata']['decisions'])))
        for j, event in enumerate(attempt['insertion_calls']):
            legal = next((s for s in event['slots'] if not s['conflicts']), None)
            actual = event['returned']
            check(f'replay {index} insertion {j} exact first legal grid',
                  actual is None and legal is None or actual is not None and legal is not None
                  and F(actual['start']) == F(legal['start_ms']) and F(actual['finish']) == F(legal['finish_ms']))
    ref = read(OUT / 'reference_return.json')
    receipt = read(OUT / 'reference_receipt.json')
    plan = read(OUT / 'plan.json')
    journal = [json.loads(line) for line in (OUT / 'reference_evaluation_journal.jsonl').read_text(encoding='utf-8').splitlines()]
    check('one full reference evaluator invocation', len(ref['attempts']) == 1 and [r['event'] for r in journal] == ['START', 'RETURN'])
    check('reference exact pre-existing candidate', digest(read(OUT / 'reference_candidate.json')) == plan['reference_candidate_identity'])
    check('reference full SAFE accepted within unchanged precision and budget', ref['validated_full_SAFE'] and ref['error'] is None
          and receipt['completed_at_elapsed_s'] <= 60 and ref['argument_identities_unchanged'])
    check('both full windows covered', all(F(s['covered_until_s']) == F('440/1000') for s in receipt['scenes'].values()))
    check('no formal initialization injection', ref['reference_used_as_formal_initialization'] is False)
    check('normal reference process exit', read(OUT / 'reference_process.json')['exit_code'] == 0)

    details = []
    for folder in sorted((EX / 'calls').iterdir()):
        raw, returned = read(folder / 'method/result.json'), read(folder / 'method_return.json')
        instance = read(folder / 'method/input_instance.json')
        evaluations = [e for e in raw['evaluations'] if e['phase'] == 'initialization']
        events = returned['evaluation_attempts_journal'][:len(evaluations)]
        check(folder.name + ' all initialization candidates SAFE', all(e['accepted_safe'] and e['receipt']['state'] == 'SAFE' for e in evaluations))
        if not evaluations:
            details.append({'id': folder.name, 'first_SAFE_at_s': None, 'no_complete_candidate': True})
            continue
        first, current, cursor = evaluations[0], evaluations[0]['candidate'], 1
        panels_before = refinements_before = 0
        panels, refinements, segments, simple_rejects = [], [], [], []
        for e in evaluations:
            receipt = e['receipt']
            panels.append(receipt['panels'] - panels_before)
            refinements.append(receipt['refinements'] - refinements_before)
            panels_before, refinements_before = receipt['panels'], receipt['refinements']
            check(folder.name + f' trace-panel accounting {len(panels)}', panels[-1] == sum(len(s['trace']) for s in receipt['scenes'].values()))
            segments.append(sum(len(s['segments']) for s in receipt['legality']['scenes'].values()))
        for index, a in enumerate(raw['initialization']['local_attempts']):
            if a['kind'] in ('execution-opp', 'one-start-delay'):
                scene = next(s for s in instance['scenarios'] if s['id'] == a['scenario'])
                stage = next(s for s in scene['stage_instances'] if s['id'] == a['stage_id'])
                request = next(q for q in scene['requests'] if q['id'] == stage['request_id'])
                row = next(r for r in current['scenes'][scene['id']] if r['stage_id'] == a['stage_id'])
                modes = [m for m in instance['stage_modes'][stage['shared_stage_id']]
                         if m['unit_id'] == row['unit'] and m['opp_id'] == a.get('opp', row['opp'])]
                earliest = max(F(0), F(request['release_ms']), F(a.get('floor_ms', '0')))
                limit = min(F(instance['window_ms']), F(request['deadline_ms']))
                reason = ('EMPTY_MODE_INTERSECTION' if not modes else 'DIRECT_EMPTY_TIME_WINDOW'
                          if earliest + F(modes[0]['duration_ms']) > limit else None)
                if reason:
                    check(folder.name + f' early necessary rejection {index} already rejected',
                          a['construction_status'] == 'CONSTRUCTION_UNRESOLVED' and 'assessment_state' not in a)
                    simple_rejects.append({'local_index': index, 'kind': a['kind'], 'stage_id': a['stage_id'],
                        'reason': reason, 'earliest_ms': str(earliest), 'limit_ms': str(limit),
                        'duration_ms': modes[0]['duration_ms'] if modes else None})
            if a['construction_status'] == 'COMPLETE_LEGAL_CANDIDATE':
                e = evaluations[cursor]
                check(folder.name + f' local assessment {index} sequence', e['source'] == 'heft:energy-pass:' + a['kind'])
                cursor += 1
                if a['accepted']:
                    current = e['candidate']
        check(folder.name + ' local history fully consumed', cursor == len(evaluations))
        details.append({'id': folder.name, 'first_SAFE_at_s': first['returned_at_s'],
            'first_evaluation_s': events[0]['returned_at_s'] - events[0]['started_at_s'],
            'energy_pass_evaluations': len(evaluations)-1,
            'energy_pass_eval_s': sum(e['returned_at_s']-e['started_at_s'] for e in events[1:]),
            'panels_per_eval_mean': sum(panels)/len(panels), 'panels_per_eval': panels,
            'segments_per_eval_mean': sum(segments)/len(segments),
            'extra_refinements_total': sum(refinements), 'extra_refinements_per_eval': refinements,
            'simple_early_rejects': simple_rejects,
            'initial_candidate_sequence': [e['candidate_sha256'] for e in evaluations]})
    for left, right in ((0, 1), (2, 3), (4, 5)):
        check(f'paired initialization sequence {left}-{right}', details[left]['initial_candidate_sequence'] == details[right]['initial_candidate_sequence'])
    costs = read(OUT / 'initialization_costs.json')
    check('270 old full evaluations accounted', sum(r.get('energy_pass_evaluations', 0)+('first_evaluation_s' in r) for r in details) == costs['totals']['full_evaluations'] == 270)
    result = {'scope': 'read-only; zero additional scientific calls', 'frozen_sources_verified': source_count,
        'checks': checks, 'checks_passed': len(checks), 'details': details,
        'timing_annotation': {'raw_reference_clock_origin_label': ref['timing']['clock_origin'],
            'actual_reference_origin': 'reference_worker entry before scientific imports, verification and input; budget.start/deadline explicitly rebound to entered',
            'reason': 'MethodBudget.summary inherited generic label; raw evidence retained; no numerical or budget effect'},
        'limitations': ['same thermal evaluator, not independent numerical implementation',
            'no internal panel CPU profiling in original logs; panel counts do not prove causal runtime attribution',
            'only ten direct time-window early rejects quantified; remaining partial-state failures cannot be timed individually from old logs']}
    save(OUT / 'audit.json', result)
    print(json.dumps({'checks_passed': len(checks), 'frozen_sources': source_count,
        'simple_early_rejects': sum(len(r.get('simple_early_rejects', [])) for r in details),
        'first_safe_eval_total_s': sum(r.get('first_evaluation_s', 0) for r in details),
        'energy_pass_eval_total_s': sum(r.get('energy_pass_eval_s', 0) for r in details)}))


if __name__ == '__main__':
    main()
