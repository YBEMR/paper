"""Explicit capability opt-in for the unchanged HEFT/SA search rules.

Legacy entry points keep rejecting auto-L.  Opt-in changes only policy
admission and the method-level bound source, never candidate generation.
"""
from control_policy import (AUTO_LOW_IMMEDIATE_V1, require_legacy_control,
                            resolve_idle_policy)


def require_heuristic_control(instance, config, consumer, *, allow_auto_low=False):
    if type(allow_auto_low) is not bool:
        raise ValueError('allow_auto_low must be boolean')
    if not allow_auto_low:
        require_legacy_control(instance, consumer)
        require_legacy_control(config, consumer+' configuration')
        return None
    # An explicit opt-in must not silently fall back to a different policy or
    # permit a mock declaration with no execution rules.
    policies = (resolve_idle_policy(instance), resolve_idle_policy(config))
    if policies != (AUTO_LOW_IMMEDIATE_V1, AUTO_LOW_IMMEDIATE_V1):
        raise ValueError(consumer+' auto-L opt-in requires matching explicit auto-L declarations')
    return AUTO_LOW_IMMEDIATE_V1
