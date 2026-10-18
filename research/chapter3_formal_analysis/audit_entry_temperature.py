"""Pair saved HEFT receipts under different entries, without thermal replay."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path

from analyze_formal import canonical_hash, interval, load, number, safe_receipt


def nonentry_input(instance):
    """Remove only known condition labels and the two representations of entry T.

    OPP entry, unfinished work, deadlines, duration/power responses, RC data,
    validity range, limits, window and startup domain are all retained.
    """
    value = deepcopy(instance)
    for name in ('id', 'condition_id', 'experiment_group'):
        value.pop(name, None)
    value.get('settings', {}).pop('initial_temperature_degC', None)
    for scene in value.get('scenarios', []):
        scene['entry'].pop('temperature_degC', None)
    return value


def input_pair_checks(cold, hot, sample):
    checks = {}
    try:
        checks['same_sample'] = cold['sample_id'] == hot['sample_id'] == sample
        checks['declared_condition_pair'] = (
            cold['id'] == 'base__'+sample and hot['id'] == 'initial_78__'+sample
            and cold['condition_id'] == 'base' and hot['condition_id'] == 'initial_78')
        checks['nonentry_input_identical'] = nonentry_input(cold) == nonentry_input(hot)
        checks['cold_entry_is_50degC'] = bool(cold['scenarios']) and all(
            scene['entry']['temperature_degC']
            and all(F(str(t)) == 50 for t in scene['entry']['temperature_degC'])
            for scene in cold['scenarios'])
        checks['hot_entry_is_78degC'] = bool(hot['scenarios']) and all(
            scene['entry']['temperature_degC']
            and all(F(str(t)) == 78 for t in scene['entry']['temperature_degC'])
            for scene in hot['scenarios'])
        checks['entry_settings_match_actual_vectors'] = (
            F(str(cold['settings']['initial_temperature_degC'])) == 50
            and F(str(hot['settings']['initial_temperature_degC'])) == 78)
        return {'passed': all(checks.values()), 'checks': checks,
                'nonentry_input_sha256': canonical_hash(nonentry_input(cold))
                    if checks['nonentry_input_identical'] else None}
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        checks['required_input_fields_present'] = False
        return {'passed': False, 'checks': checks, 'nonentry_input_sha256': None}


def _complete_safe(receipt, instance, seconds):
    if not safe_receipt(receipt, seconds):
        return False
    try:
        legal = receipt.get('legality') or {}
        scenes = receipt['scenes']
        return (receipt.get('problem_id') == instance['id']
            and legal.get('state') == 'SCHEDULE_VALID_THERMAL_UNCHECKED'
            and legal.get('problem_id') == instance['id']
            and set(scenes) == {s['id'] for s in instance['scenarios']}
            and all(F(sc.get('covered_until_s', '-1')) == F(instance['window_ms'])/1000
                    for sc in scenes.values()))
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False


def _strict_witnesses(receipt, instance, seconds):
    if receipt.get('state') != 'THERMAL_VIOLATION':
        return []
    legal = receipt.get('legality') or {}
    if (receipt.get('problem_id') != instance['id']
        or legal.get('state') != 'SCHEDULE_VALID_THERMAL_UNCHECKED'
        or legal.get('problem_id') != instance['id']):
        return []
    scenes = {s['id']: s for s in instance['scenarios']}
    nodes = instance['platform']['node_order']
    found = {}
    for witness in receipt.get('violations') or []:
        try:
            scene = scenes[witness['scene_id']]
            node = nodes.index(witness['node'])
            bounds = interval(witness['temperature_degC'])
            at = number(witness.get('formed_at_elapsed_s'))
            limit = F(str(scene['maximum_temperature_degC'][node]))
            when = F(witness['time_s'])
            if (bounds is not None and bounds[0] > limit
                and F(str(witness['limit_degC'])) == limit
                and 0 <= when <= F(instance['window_ms'])/1000
                and at is not None and 0 <= at < seconds):
                found[canonical_hash(witness)] = deepcopy(witness)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            continue
    return list(found.values())


def pair_saved_results(cold_input, cold_result, hot_input, hot_result, *, sample, seconds=300):
    """Compare only candidates already evaluated in both invocation archives."""
    compatibility = input_pair_checks(cold_input, hot_input, sample)
    out = {'sample': sample, 'input_checks': compatibility, 'matched_candidates': [],
           'common_candidate_count': 0, 'cold_complete_safe_candidate_count': 0,
           'hot_strict_violation_candidate_count': 0, 'record_conflicts': []}
    if not compatibility['passed']:
        out['status'] = 'NONENTRY_INPUT_MISMATCH_OR_UNSUPPORTED_ENTRY'
        return out
    cold_rows, hot_rows = cold_result.get('evaluations') or [], hot_result.get('evaluations') or []
    cold_hashes = {canonical_hash(r['candidate']) for r in cold_rows if r.get('candidate') is not None}
    hot_hashes = {canonical_hash(r['candidate']) for r in hot_rows if r.get('candidate') is not None}
    out['common_candidate_count'] = len(cold_hashes & hot_hashes)
    cold_safe, cold_bad, hot_bad, hot_safe = {}, set(), {}, set()
    for index, row in enumerate(cold_rows):
        candidate = row.get('candidate')
        if candidate is not None and _strict_witnesses(row.get('evaluation') or {}, cold_input, seconds):
            cold_bad.add(canonical_hash(candidate))
        if (candidate is not None and row.get('accepted_safe') is True
            and _complete_safe(row.get('evaluation') or {}, cold_input, seconds)):
            key = canonical_hash(candidate)
            entry = {'index': index, 'candidate': candidate, 'receipt': row['evaluation']}
            if key not in cold_safe or (entry['receipt']['completed_at_elapsed_s']
                                       < cold_safe[key]['receipt']['completed_at_elapsed_s']):
                cold_safe[key] = entry
    for index, row in enumerate(hot_rows):
        candidate = row.get('candidate')
        if candidate is None:
            continue
        key, receipt = canonical_hash(candidate), row.get('evaluation') or {}
        if row.get('accepted_safe') is True and _complete_safe(receipt, hot_input, seconds):
            hot_safe.add(key)
        witnesses = _strict_witnesses(receipt, hot_input, seconds)
        if witnesses:
            hot_bad.setdefault(key, []).append({'index': index, 'witnesses': witnesses})
    out['cold_complete_safe_candidate_count'] = len(cold_safe)
    out['hot_strict_violation_candidate_count'] = len(hot_bad)
    for key in sorted(set(cold_safe) & set(hot_bad)):
        if key in cold_bad:
            out['record_conflicts'].append({'candidate_sha256': key,
                'reason': 'same cold input/candidate has both SAFE and strict violation receipts'})
            continue
        if key in hot_safe:
            out['record_conflicts'].append({'candidate_sha256': key,
                'reason': 'same hot input/candidate has both SAFE and strict violation receipts'})
            continue
        cold_record = cold_safe[key]
        # Hash collision is not used as an excuse to accept unequal content.
        if any(hot_rows[item['index']]['candidate'] != cold_record['candidate'] for item in hot_bad[key]):
            out['record_conflicts'].append({'candidate_sha256': key,
                                           'reason': 'hash key matched unequal candidate content'})
            continue
        witnesses = []
        for item in hot_bad[key]:
            for witness in item['witnesses']:
                witnesses.append({'hot_evaluation_index': item['index'], **witness})
        out['matched_candidates'].append({'candidate_sha256': key,
            'candidate': deepcopy(cold_record['candidate']), 'cold_evaluation_index': cold_record['index'],
            'cold_SAFE_formed_at_s': cold_record['receipt']['completed_at_elapsed_s'],
            'cold_safe_energy_interval_J': cold_record['receipt']['weighted_energy_J'],
            'hot_evaluation_indices': [r['index'] for r in hot_bad[key]], 'hot_strict_witnesses': witnesses})
    out['status'] = ('MATCHED_SAFE_TO_STRICT_VIOLATION' if out['matched_candidates'] else
                     'RECEIPT_CONFLICT_REQUIRES_REVIEW' if out['record_conflicts'] else
                     'NO_MATCHING_SAVED_EVIDENCE')
    return out


def audit_pairs(analysis):
    """Read only ten HEFT archives (five fixed samples, two original entries)."""
    rows = [r for r in analysis['rows'] if r['method'] == 'heft'
            and r['condition'] in ('base', 'initial_78')]
    bykey = {(r['condition'], r['sample']): r for r in rows}
    pairs = []
    for sample in sorted({r['sample'] for r in rows}):
        cold, hot = bykey.get(('base', sample)), bykey.get(('initial_78', sample))
        if not cold or not hot or cold['call_state'] != 'COMPLETED' or hot['call_state'] != 'COMPLETED':
            pairs.append({'sample': sample, 'status': 'BOTH_COMPLETED_HEFT_CALLS_NOT_AVAILABLE',
                          'matched_candidates': []})
            continue
        loaded = []
        for row in (cold, hot):
            folder = Path(row['source_batch'])/row['call_id']
            instance, result = load(folder/'input_instance.json'), load(folder/'result.json')
            if (canonical_hash(instance) != row['input_sha256']
                or result.get('input_sha256') != row['input_sha256']
                or result.get('call_id') != row['call_id'] or result.get('method') != 'heft'
                or result.get('seed') is not None or result.get('problem_id') != row['problem_id']):
                raise ValueError('saved HEFT archive identity changed after the main analysis')
            loaded.append((instance, result))
        pair = pair_saved_results(*loaded[0], *loaded[1], sample=sample,
                                  seconds=min(cold['seconds_limit'], hot['seconds_limit']))
        pair.update(cold_call_id=cold['call_id'], hot_call_id=hot['call_id'],
            cold_source_batch=cold['source_batch'], hot_source_batch=hot['source_batch'],
            cold_source_version_fingerprint=cold['source_version_fingerprint'],
            hot_source_version_fingerprint=hot['source_version_fingerprint'])
        pairs.append(pair)
    return {'schema_version': 'saved-heft-entry-temperature-pair-audit-v1', 'pairs': pairs,
        'matched_candidate_count': sum(len(p['matched_candidates']) for p in pairs),
        'matched_samples': [p['sample'] for p in pairs if p['matched_candidates']],
        'scope': 'existing same-candidate receipt pairs; entry-temperature constraint effect only; no new thermal computation',
        'limits': ['intersection is selected by HEFT visitation, not an exhaustive or unbiased candidate set',
                   'no match means no matching archived evidence, not no thermal effect',
                   'does not prove global optimum/configuration change, algorithm novelty or feedback benefit',
                   '50degC and 78degC are independent declared scenario entries, not measured cross-mode heat history']}
