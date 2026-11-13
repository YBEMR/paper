"""Exact necessary-option support propagation, before event construction.

Only direct precedence and common-device equality are propagated. This is
relative to the supplied finite option catalog, not a feasibility or thermal
search. It never creates modes, rounds times, or synchronizes OPP/start choices.
"""
from collections import Counter
from fractions import Fraction as F
import hashlib
import json
import time


PROTOCOL = 'precedence-shared-unit-support-v1'


def _check(budget):
    if budget is not None:
        budget.check()


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), default=str).encode()).hexdigest()


def _exact(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, F)):
        raise TypeError('Support propagation needs exact string/integer/Fraction times')
    return F(value)


def _catalog(instance, options, budget):
    groups, shared, edges, scenes = {}, {}, [], set()
    for scene in instance['scenarios']:
        _check(budget)
        sid = scene['id']
        if not isinstance(sid, str) or not sid or sid in scenes:
            raise ValueError('Support propagation needs unique scene IDs')
        scenes.add(sid)
        for stage in scene['stage_instances']:
            key = (sid, stage['id']); identity = stage['shared_stage_id']
            if key in groups or not all(isinstance(v, str) and v for v in (*key, identity)):
                raise ValueError('Support propagation needs unique Stage occurrence IDs')
            groups[key] = []
            shared.setdefault(identity, []).append(key)
        for before, after in scene['dependencies']:
            if before == after or (sid, before) not in groups or (sid, after) not in groups:
                raise ValueError('Support dependency must refer to distinct declared Stages')
            edge = (sid, before, after)
            if edge not in edges:
                edges.append(edge)
    parsed, seen = {}, set()
    for index, option in enumerate(options):
        if index % 128 == 0:
            _check(budget)
        oid = option['option_id']; key = (option['scenario_id'], option['stage_instance_id'])
        if not isinstance(oid, str) or not oid or oid in seen or key not in groups:
            raise ValueError('Support option identity must be unique and declared')
        unit = option['unit_id']
        if not isinstance(unit, str) or not unit:
            raise ValueError('Support option unit must be declared by a nonempty ID')
        start, end = _exact(option['start_ms']), _exact(option['end_ms'])
        if end <= start:
            raise ValueError('Support option duration must be positive')
        if 'shared_stage_id' in option:
            identity = next(h for h, members in shared.items() if key in members)
            if option['shared_stage_id'] != identity:
                raise ValueError('Support option shared identity differs from its Stage')
        seen.add(oid); groups[key].append(oid)
        parsed[oid] = {'index': index, 'key': key, 'unit': unit, 'start': start, 'end': end}
    _check(budget)
    return groups, shared, edges, parsed


def _domain_hash(groups):
    return _digest([{'group': list(key), 'option_ids': values} for key, values in groups.items()])


def _empty(groups):
    return [list(key) for key, values in groups.items() if not values]


def _reasons(groups, shared, edges, parsed, budget):
    """All reasons refer to one pre-round snapshot, never a partly edited set."""
    reasons = {}
    for sid, before, after in edges:
        _check(budget)
        pred, succ = (sid, before), (sid, after)
        low_id = min(groups[pred], key=lambda oid: parsed[oid]['end'], default=None)
        high_id = max(groups[succ], key=lambda oid: parsed[oid]['start'], default=None)
        for index, oid in enumerate(groups[succ]):
            if index % 128 == 0: _check(budget)
            if low_id is None or parsed[low_id]['end'] > parsed[oid]['start']:
                reasons.setdefault(oid, {'rule': 'predecessor_support', 'edge': [sid, before, after],
                    'support_group': list(pred), 'support_count': len(groups[pred]),
                    'extremum_option_id': low_id,
                    'minimum_predecessor_end_ms': None if low_id is None else str(parsed[low_id]['end']),
                    'candidate_start_ms': str(parsed[oid]['start'])})
        for index, oid in enumerate(groups[pred]):
            if index % 128 == 0: _check(budget)
            if high_id is None or parsed[oid]['end'] > parsed[high_id]['start']:
                reasons.setdefault(oid, {'rule': 'successor_support', 'edge': [sid, before, after],
                    'support_group': list(succ), 'support_count': len(groups[succ]),
                    'extremum_option_id': high_id,
                    'maximum_successor_start_ms': None if high_id is None else str(parsed[high_id]['start']),
                    'candidate_end_ms': str(parsed[oid]['end'])})
    for identity, members in shared.items():
        _check(budget)
        units = {key: {parsed[oid]['unit'] for oid in groups[key]} for key in members}
        common = set.intersection(*(units[key] for key in members))
        for key in members:
            for index, oid in enumerate(groups[key]):
                if index % 128 == 0: _check(budget)
                unit = parsed[oid]['unit']
                if unit not in common:
                    missing = next(other for other in members if unit not in units[other])
                    reasons.setdefault(oid, {'rule': 'shared_unit_support', 'shared_stage_id': identity,
                        'candidate_unit': unit, 'missing_support_group': list(missing),
                        'missing_group_available_units': sorted(units[missing]),
                        'common_units': sorted(common), 'occurrence_count': len(members)})
    return reasons


def propagate_option_support(instance, options, budget=None):
    """Return retained original options and a replayable per-deletion proof.

    An original legal complete schedule supports each selected option across
    every direct edge and at its common shared unit. Snapshot induction keeps
    every option of that schedule. A nonempty fixed point is not feasibility.
    Empty domains are retained for downstream contradictory one-hot rows.
    """
    _check(budget); began = time.monotonic()
    groups, shared, edges, parsed = _catalog(instance, options, budget)
    initial_hash = _domain_hash(groups)
    rounds = []
    for number in range(1, len(options)+2):
        _check(budget); before_hash = _domain_hash(groups)
        reasons = _reasons(groups, shared, edges, parsed, budget)
        deletions = []
        for oid in parsed:  # Original option order makes proof replay stable.
            if oid in reasons:
                deletions.append({'option_id': oid, 'group': list(parsed[oid]['key']), **reasons[oid]})
        after = {key: [oid for oid in values if oid not in reasons] for key, values in groups.items()}
        _check(budget)
        rounds.append({'round': number, 'before_domain_sha256': before_hash,
                       'after_domain_sha256': _domain_hash(after), 'deletions': deletions,
                       'deleted_count': len(deletions), 'empty_domains_after': _empty(after)})
        groups = after
        if not deletions:
            break
    else:
        raise RuntimeError('Finite monotone support propagation failed to terminate')
    surviving = {oid for values in groups.values() for oid in values}
    retained = [option for option in options if option['option_id'] in surviving]
    empty = _empty(groups)
    report = {'protocol': PROTOCOL, 'instance_sha256': _digest(instance),
        'input_options_sha256': _digest(options), 'retained_options_sha256': _digest(retained),
        'initial_domain_sha256': initial_hash, 'final_domain_sha256': _domain_hash(groups),
        'input_option_count': len(options), 'retained_option_count': len(retained),
        'removed_option_count': len(options)-len(retained), 'rounds': rounds,
        'round_count_including_fixed_point_check': len(rounds),
        'deletion_rule_counts': dict(Counter(row['rule'] for r in rounds for row in r['deletions'])),
        'empty_domains': empty, 'logical_feasibility': 'INFEASIBLE_BY_EMPTY_OPTION_DOMAIN' if empty else 'NOT_PROVEN',
        'scope': 'Necessary direct-edge and same-unit support only, relative to supplied options; no OPP/start equality, resource-pair support, thermal or optimization evaluation.',
        'original_option_order_preserved': True, 'elapsed_s': time.monotonic()-began}
    _check(budget)
    return retained, report


def verify_option_support_report(instance, options, retained_options, report, budget=None):
    """Replay proof records using explicit support checks, not the propagator."""
    _check(budget)
    groups, shared, edges, parsed = _catalog(instance, options, budget)
    if (report['protocol'] != PROTOCOL or report['instance_sha256'] != _digest(instance)
            or report['input_options_sha256'] != _digest(options)
            or report['initial_domain_sha256'] != _domain_hash(groups)):
        raise ValueError('Support proof input identity mismatch')
    seen = set(); checked = 0; reached_fixed_point = False
    for number, row in enumerate(report['rounds'], 1):
        _check(budget)
        if row['round'] != number or row['before_domain_sha256'] != _domain_hash(groups):
            raise ValueError('Support proof round identity mismatch')
        removed = set()
        for deletion in row['deletions']:
            oid = deletion['option_id']; candidate = parsed[oid]; key = candidate['key']
            if oid in seen or oid in removed or oid not in groups[key] or deletion['group'] != list(key):
                raise ValueError('Support proof repeats or misidentifies an option')
            rule = deletion['rule']
            if rule in ('predecessor_support', 'successor_support'):
                edge = tuple(deletion['edge'])
                if edge not in edges: raise ValueError('Support proof uses an unknown edge')
                sid, before, after = edge
                support = (sid, before if rule == 'predecessor_support' else after)
                if key != (sid, after if rule == 'predecessor_support' else before):
                    raise ValueError('Support proof uses the wrong edge direction')
                values = groups[support]
                if deletion['support_group'] != list(support) or deletion['support_count'] != len(values):
                    raise ValueError('Support proof support domain mismatch')
                if rule == 'predecessor_support':
                    if any(parsed[v]['end'] <= candidate['start'] for v in values):
                        raise ValueError('Deleted option has predecessor support')
                    extreme = min(values, key=lambda v: parsed[v]['end'], default=None)
                    bound = None if extreme is None else str(parsed[extreme]['end'])
                    if deletion['minimum_predecessor_end_ms'] != bound or deletion['candidate_start_ms'] != str(candidate['start']):
                        raise ValueError('Support proof predecessor bound mismatch')
                else:
                    if any(candidate['end'] <= parsed[v]['start'] for v in values):
                        raise ValueError('Deleted option has successor support')
                    extreme = max(values, key=lambda v: parsed[v]['start'], default=None)
                    bound = None if extreme is None else str(parsed[extreme]['start'])
                    if deletion['maximum_successor_start_ms'] != bound or deletion['candidate_end_ms'] != str(candidate['end']):
                        raise ValueError('Support proof successor bound mismatch')
                if deletion['extremum_option_id'] != extreme:
                    raise ValueError('Support proof extremum identity mismatch')
            elif rule == 'shared_unit_support':
                identity = deletion['shared_stage_id']; members = shared[identity]
                missing = tuple(deletion['missing_support_group'])
                if key not in members or missing not in members or deletion['candidate_unit'] != candidate['unit']:
                    raise ValueError('Support proof shared occurrence mismatch')
                available = {parsed[v]['unit'] for v in groups[missing]}
                common = set.intersection(*({parsed[v]['unit'] for v in groups[m]} for m in members))
                if candidate['unit'] in available or deletion['missing_group_available_units'] != sorted(available) or deletion['common_units'] != sorted(common) or deletion['occurrence_count'] != len(members):
                    raise ValueError('Deleted option has shared-device support or wrong certificate')
            else:
                raise ValueError('Unknown support deletion rule')
            removed.add(oid); checked += 1
            _check(budget)
        if row['deleted_count'] != len(removed): raise ValueError('Support proof deletion count mismatch')
        groups = {key: [oid for oid in values if oid not in removed] for key, values in groups.items()}
        if row['after_domain_sha256'] != _domain_hash(groups) or row['empty_domains_after'] != _empty(groups):
            raise ValueError('Support proof resulting domain mismatch')
        seen.update(removed)
        if not removed:
            if number != len(report['rounds']): raise ValueError('Support proof continues after fixed point')
            reached_fixed_point = True
    if not reached_fixed_point: raise ValueError('Support proof lacks a final fixed-point check')
    # Check fixed-point support directly, even if a proof falsely omitted work.
    for sid, before, after in edges:
        for oid in groups[sid, after]:
            if not any(parsed[v]['end'] <= parsed[oid]['start'] for v in groups[sid, before]):
                raise ValueError('Result is not predecessor-support closed')
        for oid in groups[sid, before]:
            if not any(parsed[oid]['end'] <= parsed[v]['start'] for v in groups[sid, after]):
                raise ValueError('Result is not successor-support closed')
        _check(budget)
    for members in shared.values():
        common = set.intersection(*({parsed[v]['unit'] for v in groups[m]} for m in members))
        if any(parsed[v]['unit'] not in common for m in members for v in groups[m]):
            raise ValueError('Result is not shared-unit-support closed')
    alive = {oid for values in groups.values() for oid in values}
    expected = [option for option in options if option['option_id'] in alive]
    logical = 'INFEASIBLE_BY_EMPTY_OPTION_DOMAIN' if _empty(groups) else 'NOT_PROVEN'
    counts = dict(Counter(d['rule'] for row in report['rounds'] for d in row['deletions']))
    if (expected != retained_options or report['retained_options_sha256'] != _digest(expected)
            or report['final_domain_sha256'] != _domain_hash(groups)
            or report['empty_domains'] != _empty(groups)
            or report['input_option_count'] != len(options)
            or report['retained_option_count'] != len(expected)
            or report['removed_option_count'] != len(seen)
            or report['round_count_including_fixed_point_check'] != len(report['rounds'])
            or report['deletion_rule_counts'] != counts
            or report['logical_feasibility'] != logical
            or report['original_option_order_preserved'] is not True):
        raise ValueError('Support proof final result mismatch')
    _check(budget)
    return {'passed': True, 'protocol': PROTOCOL, 'checked_deletions': checked,
            'checked_rounds': len(report['rounds']), 'retained_option_count': len(expected),
            'empty_domains': _empty(groups)}
