"""Explicit idle-control rules, shared by schedule reconstruction and receipts.

The legacy declaration has no policy fields and holds the last OPP. The new
version returns an entirely idle domain to its unique lowest-frequency L OPP
immediately, with no transition time or energy. Adapters copy declarations;
they neither alter physical values nor repair an unsupported source policy.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json


AUTO_LOW_IMMEDIATE_V1 = 'auto_low_immediate_v1'
LEGACY_IDLE_HOLD = 'legacy_idle_holds_last_opp'
OVERHEAD_FIELDS = (
    'extra_transfer_time_ms', 'extra_switch_time_ms', 'extra_handoff_time_ms',
    'extra_transfer_energy_J', 'extra_switch_energy_J', 'extra_handoff_energy_J')


def _exact(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Fraction)):
        raise ValueError('Control-policy scalars must be exact strings/integers/rationals')
    return Fraction(value)


def resolve_idle_policy(value):
    """Validate a config/instance declaration and return its policy identity.

    False without the explicit version is unsupported. New fields may not be
    attached to legacy hold-last behavior. Zero overheads are checked exactly;
    the new policy additionally requires an explicit zero delay and legal L
    as each domain's unique minimum-frequency OPP.
    """
    try:
        rules = value['execution_rules']
        for name in ('preemption', 'migration', 'in_stage_opp_change'):
            if rules[name] is not False:
                raise ValueError('Unsupported execution rule: '+name)
        if rules['switch_only_when_domain_empty'] is not True:
            raise ValueError('Switches require an empty control domain')
        if rules['interval_convention'] != '[start,end)':
            raise ValueError('Unsupported interval convention')
        for name in OVERHEAD_FIELDS:
            if _exact(rules[name]) != 0:
                raise ValueError('Unsupported nonzero overhead: '+name)
        holds = rules['idle_holds_last_opp']
        if holds is True:
            if 'idle_policy' in rules or 'idle_delay_ms' in rules:
                raise ValueError('Legacy idle hold conflicts with explicit idle-policy fields')
            return LEGACY_IDLE_HOLD
        if holds is not False or rules.get('idle_policy') != AUTO_LOW_IMMEDIATE_V1:
            raise ValueError('Unsupported or unversioned idle policy')
        if _exact(rules['idle_delay_ms']) != 0:
            raise ValueError('Immediate-L policy requires zero idle delay')
        domains = value['platform']['domains']
        if not isinstance(domains, dict) or not domains:
            raise ValueError('Idle policy requires declared control domains')
        for domain_id, domain in domains.items():
            opps = domain['opps']
            low = opps['L']
            frequency = _exact(low['frequency_GHz'])
            if frequency <= 0 or _exact(low['voltage_V']) <= 0:
                raise ValueError('Illegal L working point: '+domain_id)
            if any(_exact(opp['frequency_GHz']) <= frequency
                   for name, opp in opps.items() if name != 'L'):
                raise ValueError('L must be the unique lowest-frequency OPP: '+domain_id)
            if (_exact(domain['baseline_W']['L']) < 0 or
                    _exact(domain['local_temperature_slope_W_per_K']['L']) < 0):
                raise ValueError('Illegal L power coefficients: '+domain_id)
        return AUTO_LOW_IMMEDIATE_V1
    except (KeyError, TypeError, ZeroDivisionError) as error:
        raise ValueError('Malformed control-policy declaration') from error


def with_auto_low_idle(value):
    """Return a validated deep copy with only the new execution-rule fields."""
    resolve_idle_policy(value)  # Reject unsupported sources before adaptation.
    copied = deepcopy(value)
    copied['execution_rules'].update(idle_holds_last_opp=False,
        idle_policy=AUTO_LOW_IMMEDIATE_V1, idle_delay_ms='0')
    resolve_idle_policy(copied)
    return copied


def require_legacy_control(value, consumer):
    """Keep unadapted planners/lifts from silently using hold-last on auto-L.

    This is a capability guard, not a replacement for input validation.
    Low-level algebra/test helpers historically accept objects without a rule
    declaration; those remain unchanged. Every explicit declaration is parsed
    strictly, and only the legacy policy may enter an unadapted consumer.
    """
    if 'execution_rules' not in value:
        return
    policy = resolve_idle_policy(value)
    if policy != LEGACY_IDLE_HOLD:
        raise ValueError(str(consumer)+' does not yet support idle policy '+policy)


def _digest(value):
    # Identical canonical encoding to milp._digest, without a circular import.
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), default=str).encode('utf-8')).hexdigest()


def idle_policy_evidence(instance, candidate):
    """New-policy receipt fields only; legacy results gain no extra fields."""
    if resolve_idle_policy(instance) == LEGACY_IDLE_HOLD:
        return {}
    return {'control_policy': {'idle_policy': AUTO_LOW_IMMEDIATE_V1,
                               'idle_delay_ms': '0'},
            'evidence_identity': {'input_sha256': _digest(instance),
                                  'candidate_sha256': _digest(candidate)}}
