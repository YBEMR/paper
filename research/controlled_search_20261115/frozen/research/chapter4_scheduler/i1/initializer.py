"""Approved I1: original attempts, one deadline/scarcity fallback, bounded quality.

No case names, saved schedules or previous results are read. All assessments go
through the same complete recorder as I0. The root deadline is never changed.
"""
from copy import deepcopy
from fractions import Fraction as F

import heft_method as i0
from auto_heuristic_policy import require_heuristic_control
from .admission import ADMISSION_S, AdmissionClosed, require_admission
from .fallback import build_fallback_candidate

RULE_VERSION = 'I1-one-deadline-fallback-no-delay-admit180-v1'


def run_heft_i1(instance, config, budget, assess, *, allow_auto_low=False):
    require_heuristic_control(instance, config, 'I1 initialization', allow_auto_low=allow_auto_low)
    meta = {'rule_version': RULE_VERSION, 'admission_limit_s': ADMISSION_S,
        'construction_attempts': [], 'local_attempts': [], 'local_accepted': 0,
        'admissions': [], 'fallback_used': False, 'active_priority': None,
        'quality_stages_completed': [], 'omitted_stage': 'one-start-delay',
        'first_SAFE_at_s': None, 'first_SAFE_energy_J': None,
        'status': 'INITIALIZATION_IN_PROGRESS', 'stop_reason': None,
        'coverage_status': 'HEURISTIC_NOT_EXHAUSTIVE', 'infeasibility_status': 'NOT_PROVED',
        'optimality_status': 'NOT_PROVED'}
    owner = getattr(assess, '__self__', None)
    if owner is not None and hasattr(owner, 'initializer_meta'):
        owner.initializer_meta = meta  # Preserve partial evidence on root expiry/errors.
    current = receipt = None
    seen = set()
    active_priority = 'original'

    def admit(kind):
        at = require_admission(budget, kind)
        meta['admissions'].append({'kind': kind, 'at_s': at})
        return at

    def build(policy, **kwargs):
        at = admit('construction')
        if policy == 'deadline_scarcity':
            meta['fallback_used'] = True
        builder = i0.build_heft_candidate if policy == 'original' else build_fallback_candidate
        value = builder(instance, budget, **kwargs)
        return value, at

    def evaluate(candidate, source):
        admit('assessment_request')
        value = assess(candidate, source)
        if value.get('state') not in ('SAFE', 'THERMAL_VIOLATION'):
            from ..method import SearchStop
            raise SearchStop('NUMERICAL_UNRESOLVED')
        return value

    try:
        policies = [('original', rank) for rank in (None, 0, 1, 2)] + [('deadline_scarcity', None)]
        for policy, rank in policies:
            constructed, at = build(policy, opp_rank=rank)
            event = {k: v for k, v in constructed.items() if k not in ('candidate', 'validation')}
            event.update(priority_policy=policy, admitted_at_s=at, assessment_state='NOT_ASSESSED')
            meta['construction_attempts'].append(event)
            candidate = constructed['candidate']
            if candidate is None:
                continue
            signature = tuple((sid, tuple((r['stage_id'], r['unit'], r['opp'], r['start_ms']) for r in rows))
                              for sid, rows in sorted(candidate['scenes'].items()))
            if signature in seen:
                event['duplicate_construction'] = True
                continue
            seen.add(signature)
            result = evaluate(candidate, 'i1:initial:' + policy + ':' + str(rank))
            event['assessment_state'] = result['state']
            if i0._energy_interval(result) is not None:
                current, receipt = deepcopy(candidate), result
                active_priority = policy
                meta.update(active_priority=policy, first_SAFE_at_s=result.get('completed_at_elapsed_s', budget.elapsed),
                            first_SAFE_energy_J=deepcopy(result['weighted_energy_J']))
                break
        if current is None:
            meta.update(status='NO_SAFE_CONSTRUCTED_WITNESS', stop_reason='CONSTRUCTIONS_EXHAUSTED')
            return meta

        identity_order = sorted(instance['stage_modes'])
        execution_order = sorted((s['id'], t['id']) for s in instance['scenarios'] for t in s['stage_instances'])
        shared_for = {(s['id'], t['id']): t['shared_stage_id'] for s in instance['scenarios'] for t in s['stage_instances']}

        def attempt(kind, details, **overrides):
            nonlocal current, receipt
            built, at = build(active_priority, **overrides)
            event = {'kind': kind, **details, 'construction_status': built['status'], 'accepted': False,
                     'priority_policy': active_priority, 'admitted_at_s': at}
            meta['local_attempts'].append(event)
            if built['candidate'] is None:
                event['reason'] = built['reason']
                return
            result = evaluate(built['candidate'], 'i1:energy-pass:' + kind)
            event['assessment_state'] = result['state']
            interval, previous = i0._energy_interval(result), i0._energy_interval(receipt)
            if interval is not None and interval[1] < previous[0]:
                current, receipt = deepcopy(built['candidate']), result
                event['accepted'] = True
                meta['local_accepted'] += 1

        for shared in identity_order:
            for unit in sorted({m['unit_id'] for m in instance['stage_modes'][shared]}):
                budget.check()
                deployment, opps, _ = i0._candidate_state(current, instance)
                if unit == deployment[shared]:
                    continue
                deployment[shared] = unit
                opps = {key: opp for key, opp in opps.items() if shared_for[key] != shared}
                attempt('shared-unit', {'shared_stage_id': shared, 'unit': unit},
                        deployment_override=deployment, opp_override=opps)
        meta['quality_stages_completed'].append('shared-unit')
        for key in execution_order:
            for opp in sorted({m['opp_id'] for m in instance['stage_modes'][shared_for[key]]}):
                budget.check()
                deployment, opps, _ = i0._candidate_state(current, instance)
                if opp == opps[key]:
                    continue
                opps[key] = opp
                attempt('execution-opp', {'scenario': key[0], 'stage_id': key[1], 'opp': opp},
                        deployment_override=deployment, opp_override=opps)
        meta['quality_stages_completed'].append('execution-opp')
        meta['stop_reason'] = 'QUALITY_PASS_EXHAUSTED'
    except AdmissionClosed as error:
        meta.update(stop_reason='INIT_ADMISSION_LIMIT', admission_stop={'kind': error.kind, 'at_s': error.at_s})
    except BaseException as error:
        meta.update(status='INTERRUPTED', stop_reason=type(error).__name__, interruption=str(error))
        raise
    budget.check()
    meta.update(status='SAFE_INIT_READY' if current is not None else 'NO_SAFE_INIT_ADMISSION_LIMIT',
                local_base_candidate=current, local_base_energy_J=receipt['weighted_energy_J'] if receipt else None,
                returned_at_s=budget.elapsed, remaining_method_s=budget.remaining)
    return meta
