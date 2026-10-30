"""Separate wiring capability from any scientific call authorization.

This release can create SIMULATION permits only. Human approval for real
research must be bound to the final source/input/budget and consumed by a
later separately reviewed executor. A kind string cannot enable that path.
"""
from dataclasses import dataclass, field


_SEAL = object()


@dataclass(frozen=True)
class WiringPermit:
    kind: str = 'SIMULATION'
    _seal: object = field(default=_SEAL, repr=False, compare=False)

    def __post_init__(self):
        if self.kind != 'SIMULATION' or self._seal is not _SEAL:
            raise PermissionError('REAL_RESEARCH_APPROVAL_NOT_AVAILABLE')


def require_permit(permit):
    if (not isinstance(permit, WiringPermit) or permit._seal is not _SEAL
            or permit.kind != 'SIMULATION'):
        raise PermissionError('VALID_SIMULATION_WIRING_PERMIT_REQUIRED_REAL_DISABLED')
    return permit.kind


def require_simulation_dependencies(permit, dependencies):
    kind = require_permit(permit)
    if kind == 'SIMULATION' and dependencies is None:
        raise PermissionError('SIMULATION_REQUIRES_EXPLICIT_FAKE_DEPENDENCIES')
    return kind
