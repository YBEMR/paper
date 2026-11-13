"""Admission only; never reset a root clock or interrupt thermal propagation."""
ADMISSION_S = 180.0


class AdmissionClosed(Exception):
    def __init__(self, kind, at_s):
        self.kind, self.at_s = kind, at_s
        super().__init__('I1_INIT_ADMISSION_LIMIT')


def require_admission(budget, kind):
    budget.check()  # Total expiry retains its original exception and semantics.
    at_s = budget.elapsed
    if at_s >= ADMISSION_S:
        raise AdmissionClosed(kind, at_s)
    return at_s
