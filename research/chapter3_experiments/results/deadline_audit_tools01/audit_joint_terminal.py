"""K164 two-segment stored-evidence audit; no live ledger, solving or heat.

Default requires the continuation supervisor's terminal. --prefix reviews only
the immutable completed prefix named by a compact-status snapshot. The original
second slot's raw failure, narrow derived status and external once-post remain
separate. A passing archive audit is not an optimality or performance claim.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timedelta
from fractions import Fraction as F
import json
from pathlib import Path
import sys
import traceback
from unittest.mock import patch

import audit_terminal as a

sys.path[:0] = [str(a.ROOT/'deadline_resume'), str(a.ROOT/'deadline_execution'),
               str(a.ROOT/'deadline_batch'), str(a.ROOT/'p0_batch'), str(a.ROOT)]
import resume_controller as r
import safe_io

PROTOCOL = 'K164-two-segment-stored-evidence-audit-v1'
NORMAL = frozenset(r.prior.p.NORMAL)


def combined_consumption(original_slots, remaining_slots, old_claimed, new_claimed):
    """Pure finite-prefix accounting; synthetic fixtures exercise this function."""
    if len(original_slots) != 40 or len({v['slot_id'] for v in original_slots}) != 40:
        raise ValueError('Original declaration is not forty unique slots')
    if remaining_slots != original_slots[2:] or len(remaining_slots) != 38:
        raise ValueError('Continuation is not exactly original slots 3..40')
    if old_claimed != original_slots[:2] or new_claimed != remaining_slots[:len(new_claimed)]:
        raise ValueError('Claims are not the disjoint declared prefixes')
    if len(new_claimed) > 38 or any(v.get('seconds') != 300 for v in original_slots):
        raise ValueError('Call or method-budget limit changed')
    total = len(old_claimed)+len(new_claimed)
    return {'prior_consumed': 2, 'new_consumed': len(new_claimed),
            'consumed_total': total, 'reserved_method_seconds': total*300,
            'unstarted_remaining': 40-total, 'campaign_limit': 40,
            'campaign_method_seconds_limit': 12000}


def selected_prefix(slots, status):
    """Never select the active method folder or an uncompleted prefix entry."""
    completed = status.get('completed_new')
    if type(completed) is not int or not 0 <= completed <= len(slots):
        raise ValueError('Invalid compact completed-prefix count')
    chosen = slots[:completed]
    active = (status.get('active') or {}).get('slot_id')
    if active in {s['slot_id'] for s in chosen}:
        raise ValueError('Compact status marks a completed slot active')
    return chosen


def reviewed_counts(rows):
    """Consumed/reviewed records include a stopped slot; completed excludes it."""
    new = [row for row in rows if row.get('segment') == 'continuation']
    return {'reviewed_new_slot_records': len(new),
            'reviewed_completed_new_slots': sum(row.get('original_slot_state') == 'COMPLETED'
                                                for row in new)}


def post_checks(post, claim, info, raw, raw_path, definition, original_sources):
    """Check only existing complete receipts and provenance, using exact scalars."""
    provenance = post.get('post_provenance') or {}
    candidate = raw.get('safe_candidate')
    old = raw.get('aggregation') or raw.get('evaluation') or {}
    try:
        first, second = map(lambda v: tuple(map(F, v)),
                            (old['weighted_energy_J'], post['weighted_energy_J']))
        overlap = max(first[0], second[0]) <= min(first[1], second[1])
    except (KeyError, TypeError, ValueError, ZeroDivisionError, IndexError):
        overlap = False
    return {
        'complete_SAFE': a.receipt_checks(post, definition, in_budget=False) == [],
        'passed_without_new_U': info.get('passed') is True and info.get('new_U') is False,
        'claim_once': claim.get('no_retry') is True,
        'matching_claim_and_receipt_provenance': claim.get('provenance') == provenance,
        'bound_raw_input_candidate_source': provenance.get('raw_result_sha256') == a.sha(raw_path)
            and provenance.get('input_sha256') == definition['input_sha256']
            and provenance.get('candidate_sha256') == a.canonical(candidate)
            # prior.postcheck remains unchanged; its source identity is the old
            # 240-source physical/execution manifest, not eight new admin files.
            and provenance.get('source_sha256') == original_sources,
        'post_60s_no_search_or_repair': provenance.get('post_seconds') == 60
            and provenance.get('new_U') is False and provenance.get('no_search_or_repair') is True,
        'energy_intervals_overlap': overlap,
    }


def audit(*, prefix=False):
    out, old, repair = r.OUT, r.OLD, r.REPAIR
    terminal_path = out/'process_terminal.json'
    if not prefix and not terminal_path.is_file():
        raise RuntimeError('Continuation supervisor terminal absent; no terminal scan performed')
    # The large replaceable ledger is intentionally never opened, even at rest.
    status = safe_io.read_small(out/'status.json')
    d, original = a.read(out/'declaration.json'), a.read(old/'declaration.json')
    terminal = a.read(terminal_path) if not prefix else None
    worker = a.read(out/'worker_terminal.json') if terminal and (out/'worker_terminal.json').is_file() else None
    complete = bool(terminal and terminal.get('state') == 'COMPLETED')
    checks, unresolved, rows = [], [], []
    def check(name, value):
        checks.append({'name': name, 'passed': bool(value)})
    def uncertain(slot, reason):
        unresolved.append({'slot_id': slot, 'reason': reason})
    before = r.prior_inventory()
    source_before = r.sources()
    original_slots, new_slots = original['slots'], d['slots']
    old_claims = [s for s in original_slots if (old/'claims'/(s['slot_id']+'.json')).is_file()]
    new_claims = [s for s in new_slots if (out/'claims'/(s['slot_id']+'.json')).is_file()]
    consumption = combined_consumption(original_slots, new_slots, old_claims, new_claims)
    chosen = selected_prefix(new_slots, status) if prefix else new_claims
    check('completed_prefix_is_already_claimed', chosen == new_claims[:len(chosen)])
    check('original_full_archive_unchanged', d['prior_artifact_sha256'] == before)
    check('source_manifest248_unchanged', len(d['source_sha256']) == 248
          and d['source_sha256'] == source_before)
    check('original_240_source_manifest_preserved', len(original['source_sha256']) == 240
          and all(d['source_sha256'].get(n) == h for n, h in original['source_sha256'].items()))
    check('old_live_and_snapshot_sources_match', all(a.sha(a.REPO/n) == h == a.sha(old/'source_snapshot'/n)
          for n, h in original['source_sha256'].items()))
    check('new_admin_snapshot_matches', all(a.sha(out/'source_snapshot'/n) == h
          for n, h in d['source_sha256'].items() if n not in original['source_sha256']))
    check('same_40x300_and_remaining38', d['campaign_call_limit'] == 40
          and d['campaign_reserved_method_s'] == 12000 and d['remaining_calls'] == 38
          and d['remaining_reserved_method_s'] == 11400 and d['seconds_each'] == 300)
    for name, folder, slots in (('old', old, original_slots[:2]), ('new', out, new_slots)):
        known = {s['slot_id']+suffix for s in slots for suffix in
                 ('.json', '_method_return.json', '_result.json', '_artifact_sha256.json')}
        check(name+':no_extra_claim_files', all(p.name in known for p in (folder/'claims').iterdir()))
    old_launcher, launcher = a.read(old/'launcher_claim.json'), a.read(out/'launcher_claim.json')
    end = datetime.fromisoformat(old_launcher['calendar_deadline_utc'])
    start = datetime.fromisoformat(old_launcher['started_utc'])
    check('original_absolute_deadline_not_reset', end == start+timedelta(seconds=19200)
          and end.isoformat() == '2026-10-22T13:46:38.073713+00:00'
          and launcher['original_deadline_utc'] == end.isoformat()
          and d['original_calendar_deadline_utc'] == end.isoformat())
    check('continuation_launcher_bound_to_frozen_controller', launcher['protocol'] == d['protocol']
          and launcher['declaration_sha256'] == a.sha(out/'declaration.json')
          and launcher['script_sha256'] == a.sha(r.HERE/'resume_supervise.py')
          and launcher['no_retry'] is True)
    global_claim = a.read(r.GLOBAL_CLAIM)
    check('unique_global_continuation_claim', global_claim['protocol'] == d['protocol']
          and global_claim['declaration_sha256'] == a.sha(out/'declaration.json')
          and global_claim['prior_consumed'] == 2 and global_claim['remaining'] == 38
          and global_claim['no_retry'] is True)
    for slot, folder in [(s, old) for s in old_claims]+[(s, out) for s in new_claims]:
        claim = a.read(folder/'claims'/(slot['slot_id']+'.json'))
        check(slot['slot_id']+':once_claim_identity', all(claim.get(k) == v for k, v in slot.items())
              and claim.get('no_retry') is True)
        check(slot['slot_id']+':claim_before_original_deadline', datetime.fromisoformat(claim['claimed_utc']) <= end)
    if terminal:
        check('terminal_no_retry_and_budget_count_agree', terminal.get('research_retry') is False
              and (worker is None or worker.get('research_calls_retried') is False))
        if complete:
            check('completed_total40_and_no_watchdog', consumption['consumed_total'] == 40
                  and terminal['returncode'] == 0 and terminal.get('watchdog_stop') is None
                  and worker is not None and worker.get('state') == 'COMPLETED'
                  and worker.get('consumed_new') == 38 and worker.get('consumed_total') == 40
                  and worker.get('reserved_total_method_s') == 12000)
            check('completed_before_original_calendar', datetime.fromisoformat(terminal['ended_utc']) <= end)
        else:
            check('stopped_terminal_not_false_completed', terminal['state'] != 'COMPLETED'
                  and consumption['consumed_total'] <= 40)
            if worker and worker.get('consumed_total') != consumption['consumed_total']:
                uncertain('CAMPAIGN', 'Worker count disagrees with exclusive claims; no successful completion inferred')
    guards = dict.fromkeys(('whole', 'linked', 'heuristic', 'matlab', 'milp', 'linprog',
        'model', 'heat', 'candidate_heat', 'scene_heat', 'subprocess', 'seed'), 0)
    def forbidden(key):
        def fail(*args, **kw):
            guards[key] += 1
            raise AssertionError('Forbidden joint-audit scientific call: '+key)
        return fail
    import formal_milp, linked_method, heuristic_runner, matlab_bridge, milp
    import thermal, scene_adapter, initial_schedule, scipy.optimize
    from schedules import validate_schedule
    import cancel_adapter
    with ExitStack() as stack:
        for obj, name, key in (
            (formal_milp, 'execute_formal_milp', 'whole'),
            (linked_method, 'execute_linked_fixed_unit_opp_start', 'linked'),
            (heuristic_runner, 'execute_heuristic', 'heuristic'),
            (matlab_bridge.MatlabSession, '__init__', 'matlab'),
            (scipy.optimize, 'milp', 'milp'), (scipy.optimize, 'linprog', 'linprog'),
            (milp, 'build_model', 'model'), (thermal, 'evaluate_piecewise', 'heat'),
            (thermal, 'evaluate_candidate', 'candidate_heat'),
            (scene_adapter, 'evaluate_piecewise', 'scene_heat'),
            (initial_schedule, 'iter_initial_candidates', 'seed')):
            stack.enter_context(patch.object(obj, name, side_effect=forbidden(key)))
        stack.enter_context(patch('subprocess.Popen', side_effect=forbidden('subprocess')))
        check('full_frozen_admission_still_passes', r.admission() == d)
        instances = {}
        for pid, definition in original['inputs'].items():
            triple = [a.read(old/'inputs'/pid/name) for name in ('raw_config.json', 'config.json', 'instance.json')]
            identities = dict(zip(('raw_config_sha256', 'config_sha256', 'input_sha256'), map(a.canonical, triple)))
            check(pid+':frozen_input_identity', identities == definition['input_identities'])
            one = triple[2]; instances[pid] = one
            check(pid+':H50_80_window400_grid5_beta1', one['response_variant'] == 'H'
                  and F(one['window_ms']) == 400 and F(one['start_grid_ms']) == 5
                  and F(one['settings']['deadline_beta']) == 1
                  and all(all(F(v) == 50 for v in scene['entry']['temperature_degC'])
                      and all(F(v) == 80 for v in scene['maximum_temperature_degC'])
                      and all(F(q['relative_deadline_ms']) == F(q['reference_CPU_H_chain_ms'])
                          and F(q['deadline_ms']) == F(q['release_ms'])+F(q['reference_CPU_H_chain_ms'])
                          for q in scene['requests']) for scene in one['scenarios']))
        selected = [(s, old, i == 1) for i, s in enumerate(old_claims)] + [(s, out, False) for s in chosen]
        for index, (slot, folder, repaired) in enumerate(selected):
            sid, method = slot['slot_id'], folder/'calls'/slot['problem_id']/slot['id']
            base = folder/'claims'/sid
            final, returned = Path(str(base)+'_result.json'), Path(str(base)+'_method_return.json')
            partial_allowed = not prefix and not complete and folder == out and slot == new_claims[-1]
            if not final.is_file() or not returned.is_file() or not (method/'wrapper_raw_result.json').is_file():
                if partial_allowed:
                    uncertain(sid, 'Last stopped consumed slot lacks complete immutable return/result/raw; no U fabricated')
                    rows.append({'slot_id': sid, 'original_ordinal': slot['ordinal'], 'segment': 'continuation',
                                 'state': 'INCOMPLETE_STOPPED_SLOT', 'rankable_post_verified_U_J': None})
                else:
                    check(sid+':immutable_record_files_present', False)
                continue
            row, ret = a.read(final), a.read(returned)
            raw_path = method/'wrapper_raw_result.json'; raw = a.read(raw_path)
            original_record = row.get('records') or {}; context = original_record.get('context') or {}
            definition = original['inputs'][slot['problem_id']]
            job = {k: v for k, v in slot.items() if k not in ('problem_id', 'slot_id', 'seconds', 'ordinal')}
            try:
                record = cancel_adapter.result_records(job, raw, definition, method,
                    input_valid=context.get('input_identity_valid'), source_valid=context.get('source_identity_valid'),
                    errors=row.get('errors') or [])
                if repaired:
                    proof = record.get('cancel_overwrite_audit') or {}
                    check(sid+':original_failure_and_derived_view_separate', row['state'] == 'BLOCKED'
                          and original_record['execution']['execution_status'] == 'TECHNICAL_FAILURE_CONFIRMED'
                          and proof.get('applied') is True and proof.get('original_execution') == original_record['execution']
                          and record['execution']['execution_status'] == 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'
                          and record['usable_U_J'] == original_record['usable_U_J'])
                else:
                    # K163 first slot predated the adapter explanation field;
                    # all scientific/status contents must still reproduce.
                    comparable = dict(record)
                    if folder == old:
                        comparable.pop('cancel_overwrite_audit', None)
                    check(sid+':stored_classification_reproduced', comparable == original_record)
            except Exception:
                check(sid+':stored_classification_reproduced', False)
                uncertain(sid, traceback.format_exc()); record = original_record
            execution, metrics = record.get('execution') or {}, record.get('completion_metrics') or {}
            check(sid+':immutable_method_return_records_preserved', ret.get('records') == original_record)
            check(sid+':current_deadline_gate_passed', (record.get('current_schedule_audit') or {}).get('passed') is True)
            check(sid+':slot_identity', all(row.get(k) == v for k, v in slot.items()))
            if row.get('state') == 'COMPLETED' or repaired:
                check(sid+':normal_accepted_execution', execution.get('execution_status') in NORMAL)
            elif not partial_allowed:
                check(sid+':completed_expected_prefix', False)
            if metrics:
                check(sid+':root300_evidence_budget', metrics.get('recorded_root_budget_s') == 300
                      and metrics.get('evidence_cutoff_s') == 300)
                check(sid+':SAFE_formed_before300_only', all(0 <= v['completed_at_s'] < 300
                      for v in metrics.get('complete_SAFE_receipts') or []))
            check(sid+':no_late_candidate_or_extra_proof', execution.get('new_or_late_candidate_accepted') is False)
            artifact = Path(str(base)+'_artifact_sha256.json')
            if artifact.is_file():
                files = a.read(artifact)
                check(sid+':stored_artifact_hashes', bool(files) and all(a.sha(method/name) == h for name, h in files.items()))
            elif not repaired and not partial_allowed:
                check(sid+':artifact_manifest_present', False)
            usable, rankable = record.get('usable_U_J'), None
            external_post = repaired
            post_info = a.read(repair/'post_summary.json') if repaired else row.get('postcheck') or {}
            post_folder = repair/'post01' if repaired else method
            if usable is None:
                for name, passed in a.no_U_checks(usable, post_info, method, complete=row.get('state') == 'COMPLETED'):
                    check(sid+':'+name, passed)
            else:
                old_receipt = raw.get('aggregation') if slot['method'] == 'linked_fixed_unit_opp_start' else raw.get('evaluation')
                original_safe = a.receipt_checks(old_receipt, definition, in_budget=True) == []
                check(sid+':complete_original_SAFE_receipt', original_safe)
                check(sid+':original_U_matches_receipt', F(usable) == F(old_receipt['safe_upper_bound_J']))
                legal = validate_schedule(instances[slot['problem_id']], raw.get('safe_candidate')).get('state') == 'SCHEDULE_VALID_THERMAL_UNCHECKED'
                check(sid+':current_exact_legality', legal)
                if (post_folder/'postcheck.json').is_file() and (post_folder/'postcheck.claim.json').is_file():
                    post = a.read(post_folder/'postcheck.json'); claim = a.read(post_folder/'postcheck.claim.json')
                    pc = post_checks(post, claim, post_info, raw, raw_path, definition, original['source_sha256'])
                    for name, passed in pc.items(): check(sid+':post:'+name, passed)
                    if repaired:
                        check(sid+':external_post_hashes_and_no_new_U',
                            post_info['postcheck_sha256'] == a.sha(post_folder/'postcheck.json')
                            and post_info['postclaim_sha256'] == a.sha(post_folder/'postcheck.claim.json')
                            and post_info.get('original_U_J') == usable and post_info.get('research_repeated') is False
                            and post_info.get('new_safe_formation_or_U') is False
                            and post_info.get('delayed_original_once_only_post') is True)
                    if all(pc.values()) and original_safe and legal and execution.get('execution_status') in NORMAL:
                        rankable = usable
                elif partial_allowed:
                    uncertain(sid, 'Original U retained but post missing after stop; no post-verified ranking')
                else:
                    check(sid+':once_post_present', False)
            feedback = [{'path': path, 'count': len(value)} for path, value in a.walk(raw)
                        if path.endswith('/feedback') and isinstance(value, list)]
            rows.append({'slot_id': sid, 'original_ordinal': slot['ordinal'],
                'segment': 'original' if folder == old else 'continuation',
                'method': slot['method'], 'seed': slot.get('seed'), 'original_slot_state': row.get('state'),
                'original_execution_status': original_record.get('execution', {}).get('execution_status'),
                'derived_execution_status': execution.get('execution_status'),
                'original_hard_errors': (original_record.get('context') or {}).get('hard_errors'),
                'derived_hard_errors': (record.get('context') or {}).get('hard_errors'),
                'cutoff_overwrite_adapter_applied': (record.get('cancel_overwrite_audit') or {}).get('applied'),
                'external_once_post': external_post, 'original_usable_U_J': usable,
                'rankable_post_verified_U_J': rankable,
                'first_complete_SAFE_at_s': metrics.get('first_complete_SAFE_at_s'),
                'method_root_stop_s': metrics.get('root_stop_at_s'),
                'deadline_overshoot_s': metrics.get('deadline_overshoot_s'),
                'cleanup_s': metrics.get('cleanup_s'), 'slot_wall_s': row.get('slot_wall_s'),
                'raw_method_reason': raw.get('reason'),
                'thermal_unresolved': execution.get('thermal_unresolved'),
                'known_violation_preserved': execution.get('known_violation_preserved'),
                'independently_proven_optimal_as_stored': execution.get('independently_proven_optimal'),
                'independently_proven_infeasible_as_stored': execution.get('independently_proven_infeasible'),
                'current_deadline_schedule_gate': (record.get('current_schedule_audit') or {}).get('passed'),
                'feedback_lists_not_summed_across_duplicates': feedback,
                'any_nonempty_feedback_list': any(v['count'] for v in feedback)})
    check('old_archive_still_unchanged', before == r.prior_inventory())
    check('all_sources_unchanged_during_audit', source_before == r.sources())
    check('all_scientific_guards_zero', not any(guards.values()))
    failed = [v['name'] for v in checks if not v['passed']]
    return {'protocol': PROTOCOL, 'profile': 'COMPLETED_PREFIX_ONLY' if prefix else 'JOINT_TERMINAL',
        'passed': not failed, 'campaign_completed_40': complete and consumption['consumed_total'] == 40,
        'continuation_terminal_state': terminal.get('state') if terminal else None,
        'compact_status_snapshot': status, 'combined_accounting': consumption,
        **reviewed_counts(rows), 'original_slots_reviewed': 2,
        'original_calendar_deadline_utc': end.isoformat(), 'calendar_was_reset': False,
        'checks_run': len(checks), 'checks': checks, 'failed_checks': failed,
        'rows': rows, 'unresolved_or_partial_evidence': unresolved,
        'post_verified_safe_outputs': sum(v.get('rankable_post_verified_U_J') is not None for v in rows),
        'blocked_calls': guards, 'research_calls': 0, 'physical_models': 0,
        'thermal_evaluations': 0, 'new_post_evaluations': 0, 'active_method_folders_read': False,
        'live_ledger_read': False, 'original_archive_modified': False,
        'declaration_sha256': a.sha(out/'declaration.json'), 'source_sha256': source_before,
        'audit_script_sha256': a.sha(__file__), 'external_approval': False,
        'scope': 'Stored records only; prefix review is not final completion. No solver status '
                 'is promoted to independent proof and no new safe result is formed.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(prefix=args.prefix)
    target = args.out.resolve() if args.out.is_absolute() else a.HERE/args.out
    target.relative_to(a.HERE)
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({k: result[k] for k in ('profile', 'passed', 'checks_run', 'failed_checks',
        'combined_accounting', 'reviewed_new_slot_records', 'reviewed_completed_new_slots',
        'post_verified_safe_outputs', 'blocked_calls')}, ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)
