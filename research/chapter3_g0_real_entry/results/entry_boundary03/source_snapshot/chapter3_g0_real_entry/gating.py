"""Separate wiring capability from any scientific call authorization.

This release can create SIMULATION permits only. Human approval for real
research must be bound to the final source/input/budget and consumed by a
later separately reviewed executor. A kind string cannot enable that path.
"""
from dataclasses import dataclass, field


_SEAL = object()
_REAL_SEAL = object()


class RealPermit:
    """Process-local capability issued only after a bound one-shot ticket check.

    Software protocol, not protection against a user editing Python/files.
    """
    kind='REAL'
    def __init__(self,context,seal):
        if seal is not _REAL_SEAL:
            raise PermissionError('BOUND_TICKET_REQUIRED')
        self.context=context
        self._seal=seal


def consume_worker_ticket(plan_file,approval_file,approval_sha256,ticket_file,token,mode):
    from .launch_contract import validate_worker_ticket
    context=validate_worker_ticket(plan_file,approval_file,approval_sha256,ticket_file,token,mode)
    return RealPermit(context,_REAL_SEAL)


@dataclass(frozen=True)
class WiringPermit:
    kind: str = 'SIMULATION'
    _seal: object = field(default=_SEAL, repr=False, compare=False)

    def __post_init__(self):
        if self.kind != 'SIMULATION' or self._seal is not _SEAL:
            raise PermissionError('REAL_RESEARCH_APPROVAL_NOT_AVAILABLE')


def require_permit(permit):
    if isinstance(permit,RealPermit) and permit._seal is _REAL_SEAL:
        return 'REAL'
    if (not isinstance(permit, WiringPermit) or permit._seal is not _SEAL
            or permit.kind != 'SIMULATION'):
        raise PermissionError('VALID_SIMULATION_WIRING_PERMIT_REQUIRED_REAL_DISABLED')
    return permit.kind


def require_simulation_dependencies(permit, dependencies):
    kind = require_permit(permit)
    if kind == 'SIMULATION' and dependencies is None:
        raise PermissionError('SIMULATION_REQUIRES_EXPLICIT_FAKE_DEPENDENCIES')
    if kind == 'REAL' and dependencies is not None:
        raise PermissionError('REAL_CANNOT_INJECT_FAKE_OR_REPLACEMENT_DEPENDENCIES')
    return kind


def require_role(permit,mode):
    if require_permit(permit)=='REAL' and permit.context['ticket']['mode']!=mode:
        raise PermissionError('TICKET_ROLE_MISMATCH')
