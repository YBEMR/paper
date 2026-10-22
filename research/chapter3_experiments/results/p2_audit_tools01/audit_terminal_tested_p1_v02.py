"""K161 pure terminal-record audit. No solving, model construction or heat replay.

Default: inspect P2 only after supervisor termination. --fixture-p1 exercises
the same read-only contracts on the old P1 archive, without touching that archive.
An optional --out writes exclusively inside this tool directory, never a campaign.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timedelta
from fractions import Fraction as F
import hashlib
import importlib
import json
from pathlib import Path
import sys
import traceback
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = ROOT.parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def walk(value, path='$'):
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk(item, path+'/'+str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk(item, path+'/'+str(index))


def receipt_checks(receipt, definition, *, in_budget):
    problems = []
    if not isinstance(receipt, dict):
        return ['NO_RECEIPT']
    if (receipt.get('state') != 'SAFE' or receipt.get('rankable_energy') is not True
            or receipt.get('problem_id') != definition['problem_id']):
        problems.append('NOT_MATCHING_SAFE')
    try:
        lo, hi = map(F, receipt['weighted_energy_J'])
        if not 0 <= lo <= hi or F(receipt['safe_upper_bound_J']) != hi:
            problems.append('INVALID_ENERGY_INTERVAL')
        if in_budget and not 0 <= receipt['completed_at_elapsed_s'] < 300:
            problems.append('NOT_FORMED_IN_BUDGET')
        specs = definition['scene_spec']
        if set(receipt['scenes']) != set(specs):
            problems.append('SCENE_COVERAGE')
        for sid, spec in specs.items():
            wrapper = receipt['scenes'][sid]
            # Linked aggregation stores an unweighted scene receipt wrapping
            # the same continuous trajectory under result; whole/heuristic
            # receipts store the trajectory directly.
            scene = wrapper.get('result', wrapper)
            if wrapper.get('state') != 'SAFE' or wrapper.get('rankable_energy') is not True:
                problems.append('UNSAFE_SCENE_WRAPPER:'+sid)
            window = F(spec['window_s'])
            if (scene.get('state') != 'SAFE' or scene.get('complete') is not True
                    or scene.get('rankable_energy') is not True
                    or F(scene['covered_until_s']) != window
                    or F(scene['trace'][-1]['time_s']) != window):
                problems.append('INCOMPLETE_WINDOW:'+sid)
            if set(scene['peaks_degC']) != set(spec['limits']):
                problems.append('PEAK_COVERAGE:'+sid)
            for node, limit in spec['limits'].items():
                low, high = map(F, scene['peaks_degC'][node])
                if not low <= high <= F(limit):
                    problems.append('UNSAFE_PEAK:'+sid+':'+node)
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
        problems.append('MALFORMED_RECEIPT')
    return problems


def audit(*, fixture_p1=False):
    folder = ROOT/('results/p1_execution01' if fixture_p1 else 'results/p2_execution01')
    # Do not parse a running ledger or scan active method folders.
    if not (folder/'process_terminal.json').is_file():
        raise RuntimeError('Supervisor terminal absent; campaign may still be running. No scan performed.')
    terminal = read(folder/'process_terminal.json')
    d = read(folder/'declaration.json')
    ledger = read(folder/'ledger.json')
    worker = read(folder/'worker_terminal.json') if (folder/'worker_terminal.json').is_file() else None
    complete = terminal.get('state') == 'COMPLETED'
    checks = []
    unresolved = []
    rows = []
    guards = dict.fromkeys(('whole', 'linked', 'heuristic', 'matlab', 'milp', 'linprog',
                           'model', 'heat', 'candidate_heat', 'scene_heat', 'subprocess'), 0)
    def check(name, value):
        checks.append({'name': name, 'passed': bool(value)})
    def uncertain(slot, reason):
        unresolved.append({'slot': slot, 'reason': reason})
    def blocked(key):
        def fail(*args, **kwargs):
            guards[key] += 1
            raise RuntimeError('Forbidden terminal-audit call: '+key)
        return fail

    check('authorised_40x300_12000_19200', d.get('authorized') is True
          and (d.get('call_limit'), d.get('seconds_each'), d.get('total_reserved_method_seconds'),
               d.get('calendar_stop_s')) == (40, 300, 12000, 19200))
    check('224_or_fixture211_sources', len(d['source_sha256']) == (211 if fixture_p1 else 224))
    source_valid = all(sha(REPO/name) == h == sha(folder/'source_snapshot'/name)
                       for name, h in d['source_sha256'].items())
    check('current_and_snapshot_sources_match', source_valid)
    g = read(folder/'precheck.json')
    check('bound_successful_pure_precheck', g.get('passed') is True
          and g['source_sha256'] == d['source_sha256'] and g.get('source_unchanged') is True
          and d['precheck_sha256'] == sha(folder/'precheck.json')
          and g.get('errors') == g.get('failures') == g.get('skipped') == 0
          and not any(g['blocked_calls'].values())
          and all(g.get(k) == 0 for k in ('research_calls', 'native_calls', 'physical_models', 'thermal_evaluations')))
    check('protocol_hash_matches', d['protocol_sha256'] == sha(folder/'protocol.md'))
    prior = g.get('prior_archive_sha256') or g.get('P0_critical_sha256') or {}
    check('prior_bound_archives_unchanged', bool(prior)
          and all(sha(REPO/name) == h for name, h in prior.items()))
    if not fixture_p1:
        prep = ROOT/'results/p2_batch_preparation01'
        check('P0_P1_preparation_manifest_hashes',
              d['P0_manifest_sha256'] == sha(ROOT/'results/p0_resume01/archive_inventory.json')
              and d['P1_manifest_sha256'] == sha(ROOT/'results/p1_execution01/archive_inventory.json')
              and d['P2_preparation_sha256'] == sha(prep/'declaration.json'))
        check('old_preparation_remains_unconsumed',
              read(prep/'declaration.json')['authorised_to_execute'] is False
              and read(prep/'ledger.json')['consumed'] == 0)
        check('same_five_inputs_as_preparation', d['inputs'] == read(prep/'declaration.json')['inputs'])

    slots = d['slots']
    check('40_unique_slots_and_12000_proposed_seconds', len(slots) == 40
          and len({s['slot_id'] for s in slots}) == 40 and sum(s['seconds'] for s in slots) == 12000)
    check('single_global_claim', (ROOT/('results/p1_execution_claim01.json' if fixture_p1
                                      else 'results/p2_execution_claim01.json')).is_file())
    claimed = [s for s in slots if (folder/'claims'/(s['slot_id']+'.json')).is_file()]
    count = len(claimed)
    check('exclusive_claims_are_exact_prefix', claimed == slots[:count])
    known_claim_names = {s['slot_id']+suffix for s in slots for suffix in
                         ('.json', '_method_return.json', '_result.json', '_artifact_sha256.json')}
    check('no_extra_claims_or_other_batch', all(p.name in known_claim_names for p in (folder/'claims').iterdir()))
    for slot in claimed:
        claim = read(folder/'claims'/(slot['slot_id']+'.json'))
        check(slot['slot_id']+':single_consumption_claim', all(claim.get(k) == v for k, v in slot.items())
              and claim.get('no_retry') is True)
    check('no_research_retries', terminal.get('research_retry') is False
          and (worker is None or worker.get('research_calls_retried') is False))
    if complete:
        check('all_40_terminal_agree', count == 40 and terminal.get('returncode') == 0
              and terminal.get('watchdog_stop') is None and worker is not None
              and worker.get('state') == 'COMPLETED' and worker.get('consumed_total') == 40
              and ledger.get('state') == 'COMPLETED' and ledger.get('consumed_total') == 40
              and ledger.get('reserved_total_method_s') == 12000)
    else:
        check('stopped_not_mislabeled_complete', terminal.get('state') != 'COMPLETED')
        if ledger.get('consumed_total') != count:
            uncertain('CAMPAIGN', 'Ledger may be stale after fault; exclusive claims are consumption evidence')
        check('stopped_consumption_within_authorization', count <= 40
              and (worker is None or worker.get('consumed_total') == count))
    check('ledger_record_prefix', [s['slot_id'] for s in ledger['calls']]
          == [s['slot_id'] for s in slots[:len(ledger['calls'])]])
    launcher = read(folder/'launcher_claim.json')
    started = datetime.fromisoformat(launcher['started_utc'])
    deadline = datetime.fromisoformat(launcher['calendar_deadline_utc'])
    check('launcher_identity_and_19200_calendar', deadline == started+timedelta(seconds=19200)
          and launcher['protocol'] == d['protocol']
          and launcher['declaration_sha256'] == sha(folder/'declaration.json')
          and launcher['script_sha256'] == sha(ROOT/('p1_batch/p1_supervise.py' if fixture_p1
                                                    else 'p2_execution/p2_supervise.py')))
    ended = datetime.fromisoformat(terminal['ended_utc'])
    calendar_wall = (ended-started).total_seconds()
    if complete:
        check('completed_before_calendar_deadline', ended <= deadline)

    sys.path[:0] = [str(ROOT/'p2_batch'), str(ROOT/'p1_batch'), str(ROOT/'p0_batch'), str(ROOT/'p0_resume'), str(ROOT)]
    import formal_milp, linked_method, heuristic_runner, matlab_bridge, milp, thermal, scene_adapter, scipy.optimize
    with ExitStack() as stack:
        for obj, name, key in ((formal_milp, 'execute_formal_milp', 'whole'),
                (linked_method, 'execute_linked_fixed_unit_opp_start', 'linked'),
                (heuristic_runner, 'execute_heuristic', 'heuristic'),
                (matlab_bridge.MatlabSession, '__init__', 'matlab'),
                (scipy.optimize, 'milp', 'milp'), (scipy.optimize, 'linprog', 'linprog'),
                (milp, 'build_model', 'model'), (thermal, 'evaluate_piecewise', 'heat'),
                (thermal, 'evaluate_candidate', 'candidate_heat'),
                (scene_adapter, 'evaluate_piecewise', 'scene_heat')):
            stack.enter_context(patch.object(obj, name, side_effect=blocked(key)))
        stack.enter_context(patch('subprocess.Popen', side_effect=blocked('subprocess')))
        adapter = importlib.import_module('p1_entry' if fixture_p1 else 'p2_entry')
        from schedules import validate_schedule
        instances = {}
        for pid, definition in d['inputs'].items():
            triple = [read(folder/'inputs'/pid/name) for name in
                      ('raw_config.json', 'config.json', 'instance.json')]
            identity = dict(zip(('raw_config_sha256', 'config_sha256', 'input_sha256'), map(canonical, triple)))
            check(pid+':frozen_input_identity', identity == definition['input_identities'])
            one = triple[2]; instances[pid] = triple
            check(pid+':thermal_response_conditions', one['response_variant'] == ('R' if fixture_p1 else 'H')
                  and all(s['entry']['temperature_degC'] == [('50' if fixture_p1 else '78')]*4
                          and s['maximum_temperature_degC'] == ['80']*4 for s in one['scenarios'])
                  and one['window_ms'] == '400' and one['start_grid_ms'] == '5')
        for index, slot in enumerate(claimed):
            sid = slot['slot_id']; base = folder/'claims'/sid
            method_folder = folder/'calls'/slot['problem_id']/slot['id']
            final_path = Path(str(base)+'_result.json')
            return_path = Path(str(base)+'_method_return.json')
            # A watchdog/IO fault may leave only the final consumed slot incomplete.
            allow_partial = not complete and index == count-1
            if not final_path.is_file() or not return_path.is_file():
                if allow_partial:
                    uncertain(sid, 'Final consumed slot lacks complete immutable return/result; not ranked')
                    rows.append({'slot_id': sid, 'state': 'INCOMPLETE_STOPPED_SLOT', 'rankable_U_J': None})
                    continue
                check(sid+':immutable_return_and_result_present', False)
                continue
            row = read(final_path); original_return = read(return_path)
            raw_path = method_folder/'wrapper_raw_result.json'
            if not raw_path.is_file():
                if allow_partial:
                    uncertain(sid, 'Stopped slot has no raw method result; no energy fabricated')
                    rows.append({'slot_id': sid, 'state': row.get('state'), 'rankable_U_J': None})
                    continue
                check(sid+':raw_method_result_present', False)
                continue
            raw = read(raw_path); records = row.get('records') or {}
            context = records.get('context') or {}
            definition = d['inputs'][slot['problem_id']]
            job = {k: v for k, v in slot.items() if k not in ('problem_id', 'slot_id', 'seconds', 'ordinal')}
            try:
                reproduced = adapter.result_records(job, raw, definition, method_folder,
                    input_valid=context.get('input_identity_valid'),
                    source_valid=context.get('source_identity_valid'), errors=row.get('errors') or [])
                check(sid+':stored_classification_reproduced', reproduced == records)
            except Exception:
                check(sid+':stored_classification_reproduced', False)
                uncertain(sid, traceback.format_exc())
            check(sid+':immutable_return_records_unchanged', original_return.get('records') == records)
            check(sid+':slot_identity', all(row.get(k) == v for k, v in slot.items()))
            if complete:
                check(sid+':completed_normally', row.get('state') == 'COMPLETED'
                      and (records.get('execution') or {}).get('execution_status') in adapter.NORMAL)
            artifact_path = Path(str(base)+'_artifact_sha256.json')
            if artifact_path.is_file():
                artifacts = read(artifact_path)
                check(sid+':method_artifact_hashes', bool(artifacts)
                      and all((method_folder/name).is_file() and sha(method_folder/name) == h
                              for name, h in artifacts.items()))
            elif allow_partial:
                uncertain(sid, 'Final consumed slot has no completed artifact manifest')
            else:
                check(sid+':method_artifact_manifest_present', False)
            metrics = records.get('completion_metrics') or {}
            if metrics:
                check(sid+':300_second_root', metrics.get('recorded_root_budget_s') == 300
                      and metrics.get('evidence_cutoff_s') == 300)
                safe_receipts = metrics.get('complete_SAFE_receipts') or []
                check(sid+':all_accepted_safe_receipts_timely', all(0 <= v['completed_at_s'] < 300 for v in safe_receipts))
                first = metrics.get('first_complete_SAFE_at_s')
                check(sid+':first_SAFE_time_or_absence', first is None or 0 <= first < 300)
            execution = records.get('execution') or {}
            check(sid+':no_new_or_late_candidate_accepted', execution.get('new_or_late_candidate_accepted') is False)
            usable = records.get('usable_U_J')
            evaluation = raw.get('aggregation') if slot['method'] == 'linked_fixed_unit_opp_start' else raw.get('evaluation')
            post_info = row.get('postcheck') or {}
            post_path = method_folder/'postcheck.json'
            candidate = raw.get('safe_candidate')
            rankable = None
            if usable is not None:
                original_good = receipt_checks(evaluation, definition, in_budget=True) == []
                check(sid+':original_safe_receipt', original_good)
                try:
                    upper_matches = F(usable) == F(evaluation['safe_upper_bound_J'])
                    old_interval = tuple(map(F, evaluation['weighted_energy_J']))
                except (KeyError, TypeError, ValueError, ZeroDivisionError):
                    upper_matches = False; old_interval = None
                check(sid+':U_matches_original_upper', upper_matches)
                legality = validate_schedule(instances[slot['problem_id']][2], candidate)
                legal = legality.get('state') == 'SCHEDULE_VALID_THERMAL_UNCHECKED'
                check(sid+':exact_complete_legality', legal)
                if post_path.is_file():
                    post = read(post_path); provenance = post.get('post_provenance') or {}
                    post_good = receipt_checks(post, definition, in_budget=False) == []
                    check(sid+':post_complete_SAFE', post_good)
                    provenance_good = ((method_folder/'postcheck.claim.json').is_file()
                          and provenance.get('raw_result_sha256') == sha(raw_path)
                          and provenance.get('input_sha256') == definition['input_sha256']
                          and provenance.get('candidate_sha256') == canonical(candidate)
                          and provenance.get('source_sha256') == d['source_sha256']
                          and provenance.get('post_seconds') == 60
                          and provenance.get('new_U') is False and provenance.get('no_search_or_repair') is True)
                    check(sid+':post_once_and_provenance', provenance_good)
                    try:
                        new_interval = tuple(map(F, post['weighted_energy_J']))
                        overlap = old_interval is not None and max(old_interval[0], new_interval[0]) <= min(old_interval[1], new_interval[1])
                    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
                        overlap = False
                    check(sid+':post_energy_overlap', overlap)
                    if (post_info.get('passed') is True and overlap and original_good
                            and upper_matches and legal and post_good and provenance_good):
                        rankable = usable
                    check(sid+':post_not_new_U', post_info.get('new_U') is False)
                elif allow_partial:
                    uncertain(sid, 'Usable original U retained but post absent due to stop; not ranked as post-verified')
                else:
                    check(sid+':post_present_for_usable_U', False)
            else:
                check(sid+':no_U_not_fabricated_as_zero', usable is None)
                if complete:
                    check(sid+':no_U_no_extra_post', post_info.get('state') == 'NOT_APPLICABLE_NO_USABLE_U'
                          and post_info.get('new_U') is False and not post_path.exists()
                          and not (method_folder/'postcheck.claim.json').exists())
            feedback = [{'path': path, 'count': len(value)} for path, value in walk(raw)
                        if path.endswith('/feedback') and isinstance(value, list)]
            rows.append({'slot_id': sid, 'method': slot['method'], 'state': row.get('state'),
                'execution_status': execution.get('execution_status'), 'original_usable_U_J': usable,
                'rankable_post_verified_U_J': rankable, 'first_complete_SAFE_at_s': metrics.get('first_complete_SAFE_at_s'),
                'method_root_stop_s': metrics.get('root_stop_at_s'),
                'deadline_overshoot_s': metrics.get('deadline_overshoot_s'),
                'cleanup_s': metrics.get('cleanup_s'), 'slot_wall_s': row.get('slot_wall_s'),
                'feedback_lists_as_stored_not_summed_across_duplicates': feedback,
                'any_nonempty_feedback_list': any(v['count'] > 0 for v in feedback),
                'known_violation_preserved': execution.get('known_violation_preserved'),
                'independently_proven_optimal_as_stored': execution.get('independently_proven_optimal'),
                'independently_proven_infeasible_as_stored': execution.get('independently_proven_infeasible')})
    check('audit_forbidden_calls_zero', not any(guards.values()))
    failures = [c['name'] for c in checks if not c['passed']]
    return {'protocol': 'K161-P2-terminal-record-audit-v1',
        'profile': 'P1_ARCHIVE_FIXTURE_ONLY' if fixture_p1 else 'P2_REAL_ARCHIVE',
        'passed': not failures, 'campaign_completed_40': complete and count == 40,
        'campaign_terminal_state': terminal.get('state'), 'consumed_calls': count,
        'reserved_method_seconds_from_claims': count*300, 'calendar_wall_s': calendar_wall,
        'calendar_stop_delay_s': max(0, (ended-deadline).total_seconds()),
        'checks_run': len(checks), 'checks': checks, 'failed_checks': failures,
        'unresolved_or_partial_evidence': unresolved, 'rows': rows,
        'post_verified_safe_outputs': sum(v.get('rankable_post_verified_U_J') is not None for v in rows),
        'blocked_calls': guards, 'research_calls': 0, 'native_calls': 0,
        'physical_models': 0, 'thermal_evaluations': 0, 'new_post_evaluations': 0,
        'declaration_sha256': sha(folder/'declaration.json'), 'audit_script_sha256': sha(Path(__file__)),
        'scope': 'Stored evidence only; solver states never promoted to independent proofs; no new thermal evaluation'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture-p1', action='store_true')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = audit(fixture_p1=args.fixture_p1)
    if args.out:
        target = args.out.resolve() if args.out.is_absolute() else HERE/args.out
        target.resolve().relative_to(HERE)
        with target.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
    print(json.dumps({k: result[k] for k in ('profile', 'passed', 'campaign_completed_40',
        'consumed_calls', 'checks_run', 'failed_checks', 'post_verified_safe_outputs', 'blocked_calls')},
        ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
