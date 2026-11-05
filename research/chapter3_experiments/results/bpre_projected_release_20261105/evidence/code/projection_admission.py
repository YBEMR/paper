"""Offline/native-boundary admission, never a solver or a formal run entry.

All compressed candidates must cross this boundary before original decoding
and complete SAFE evaluation. It does not attach to MatlabSession: that future
integration must route BOTH callback publications and final vectors here.
"""
from copy import deepcopy
from fractions import Fraction
import math

import numpy as np

from certified_projection import transform, verify, project, lift
from matlab_bridge import _prepare, _check_initial_point
from numeric_case_diagnostic.exact_equalities import verify_equivalence


class ProjectionRejected(ValueError):
    """A candidate/receipt failed the original contract; never a SAFE result."""


def _clone(payload):
    return {key: value.copy() for key, value in payload.items()}


class ProjectionAdmission:
    """Own the original rows, certified mapping, and one existing root budget.

    Payload intcon is zero-based, matching the Python model export. If the
    represented input already used exact opposite rows -> Aeq, supply its
    complete original rows and the existing exact-equality certificate. That
    relationship is checked before the new projection is allowed.
    """

    def __init__(self, original, *, policy, budget, original_rows=None,
                 equality_certificate=None):
        self.budget = budget
        self._budget_ref = budget
        self._clock_identity = self._budget_identity()
        self._check()
        self._original = _clone(original)
        self._rows = _clone(original if original_rows is None else original_rows)
        if (original_rows is None) != (equality_certificate is None):
            raise ProjectionRejected('Original-row reference requires its exact equality certificate')
        if original_rows is not None:
            # Neither a claimed label nor a merely matching variable count is
            # enough to replace the original rows used for numerical admission.
            try:
                self.row_reference_receipt = verify_equivalence(
                    self._rows, self._original, deepcopy(equality_certificate))
            except (TypeError, ValueError, KeyError, IndexError, AssertionError) as error:
                raise ProjectionRejected('Original-row reference certificate rejected') from error
        else:
            self.row_reference_receipt = {'same_complete_input_rows': True}
        self._check()
        self._reduced, self._certificate = transform(
            self._original, policy=policy, check=self._check)
        self.certificate_receipt = verify(self._original, self._reduced,
            self._certificate, policy=policy, check=self._check)
        # _prepare preserves original numerical values and converts only the
        # documented integer index base for the original admission function.
        self._native_original = _prepare(self._rows)
        self._check()

    def _budget_identity(self):
        try:
            values = tuple(float(getattr(self.budget, key))
                           for key in ('start', 'deadline', 'seconds'))
        except (AttributeError, TypeError, ValueError) as error:
            raise ProjectionRejected('One explicit original MethodBudget is required') from error
        if not all(math.isfinite(value) for value in values) or values[2] <= 0:
            raise ProjectionRejected('Invalid root budget identity')
        if values[1] <= values[0]:
            raise ProjectionRejected('Invalid root deadline')
        return values

    def _check(self):
        if self.budget is not self._budget_ref:
            raise ProjectionRejected('Original root budget object replaced')
        if self._budget_identity() != self._clock_identity:
            raise ProjectionRejected('Root budget origin/deadline/limit changed')
        # Preserve the original Exhausted exception and its strict deadline.
        self.budget.check()
        elapsed = float(self.budget.elapsed)
        if not math.isfinite(elapsed) or elapsed < 0 or elapsed >= self._clock_identity[2]:
            raise ProjectionRejected('Invalid or expired root elapsed time')

    @property
    def reduced(self):
        return _clone(self._reduced)

    @property
    def certificate(self):
        return deepcopy(self._certificate)

    def _admit_original(self, vector):
        self._check()
        try:
            checked, receipt = _check_initial_point(self._native_original, vector)
        except (TypeError, ValueError, OverflowError, FloatingPointError) as error:
            raise ProjectionRejected('Original full-row numerical admission rejected') from error
        self._check()
        return checked.copy(), receipt

    def prepare_initial(self, full):
        """Admit original x0, project, lift, and re-admit; no stored warm start."""
        admitted, before = self._admit_original(full)
        self._check()
        try:
            reduced = project(admitted, self._certificate)
        except (TypeError, ValueError, IndexError) as error:
            raise ProjectionRejected('Initial-point projection failed') from error
        restored, after = self.restore(reduced, source='initial_point_roundtrip')
        # The removed continuous J need not recover their former arbitrary
        # value; retained coordinates must be exactly preserved by projection.
        if not np.array_equal(project(restored, self._certificate), reduced):
            raise ProjectionRejected('Initial-point retained-coordinate drift')
        self._check()
        return {'native_x': reduced.copy(), 'original_admission': before,
                'recovered_admission': after, 'safe_claim': False}

    def restore(self, vector, *, source):
        """Restore coordinates and enforce all original rows, without repair."""
        self._check()
        try:
            raw = np.asarray(vector)
            if raw.ndim != 1 or raw.dtype.kind not in 'fiu' or not np.isfinite(raw).all():
                raise ProjectionRejected('Compressed vector must be finite real numeric data')
            restored = lift(raw.astype(np.float64), self._certificate)
        except (TypeError, ValueError, IndexError, OverflowError) as error:
            raise ProjectionRejected('Compressed vector cannot be restored') from error
        full, numerical = self._admit_original(restored)
        return full, {'state': 'ORIGINAL_ROWS_ADMITTED', 'source': source,
                      'numeric': numerical, 'safe_claim': False,
                      'completed_at_elapsed_s': float(self.budget.elapsed)}

    def assess(self, vector, *, source, decode, evaluate):
        """Common callback/final path; no cache may bypass per-vector admission.

        decode must be the original full-vector logical/schedule decoder.
        evaluate must perform the unchanged complete physical SAFE evaluation
        and accepts (candidate, the_same_original_budget). Their exceptions
        propagate; this boundary never turns failure into acceptance.
        """
        full, numeric = self.restore(vector, source=source)
        self._check()
        candidate = decode(full)
        self._check()
        evaluation = evaluate(candidate, self.budget)
        self._check()  # a late evaluator return is never accepted, even if SAFE
        if not isinstance(evaluation, dict):
            raise ProjectionRejected('Evaluator returned no complete receipt')
        completed = evaluation.get('completed_at_elapsed_s')
        valid_time = (isinstance(completed, (int, float)) and not isinstance(completed, bool)
                      and math.isfinite(completed) and 0 <= completed < self._clock_identity[2]
                      and completed <= float(self.budget.elapsed))
        scenes = evaluation.get('scenes')
        expected_scenes = candidate.get('scenes') if isinstance(candidate, dict) else None
        complete_scenes = (isinstance(scenes, dict) and bool(scenes)
            and isinstance(expected_scenes, dict) and set(scenes) == set(expected_scenes)
            and all(isinstance(s, dict) and s.get('state') == 'SAFE'
                    and s.get('complete') is True for s in scenes.values()))
        try:
            energy = evaluation['weighted_energy_J']
            if not isinstance(energy, (list, tuple)) or len(energy) != 2:
                raise ValueError('Weighted energy interval missing')
            lo, hi = (Fraction(str(value)) for value in energy)
            upper = Fraction(str(evaluation['safe_upper_bound_J']))
            valid_energy = 0 <= lo <= hi == upper
        except (TypeError, ValueError, ZeroDivisionError, KeyError):
            valid_energy = False
        accepted = (evaluation.get('state') == 'SAFE'
                    and evaluation.get('rankable_energy') is True
                    and valid_energy and valid_time and complete_scenes)
        self._check()
        return {'state': 'SAFE' if accepted else 'NOT_ACCEPTED_SAFE',
                'accepted_safe': bool(accepted), 'source': source,
                'numeric': numeric, 'candidate': candidate,
                'evaluation': evaluation, 'budget_identity': self._clock_identity,
                'native_status_rewritten': False}

    def callback_event(self, event, *, decode, evaluate):
        self._check()
        if not isinstance(event, dict) or 'x' not in event:
            raise ProjectionRejected('Callback contains no candidate vector')
        return self.assess(event['x'], source='callback', decode=decode, evaluate=evaluate)

    def final_result(self, response, *, decode, evaluate):
        self._check()
        if (not isinstance(response, dict) or response.get('budget_valid') is not True
                or response.get('accepted_for_evaluation') is not True
                or response.get('status') != 'SOLVED' or 'x' not in response):
            raise ProjectionRejected('Final native receipt is not timely and eligible')
        return self.assess(response['x'], source='final', decode=decode, evaluate=evaluate)
