"""Reuse the frozen direct-12 input generator with two new random streams."""
from unittest.mock import patch
from ..i1 import new_inputs as frozen

ROOTS = (('U05', 2026111305), ('U06', 2026111306))
NAMESPACE = 'ch4-independent-onp-v1'
ALGORITHM_COMMIT = '63d2dc9f8109a7aa9e0ca18dc950c99572e9f8fb'
ORIGINAL_PLAN = frozen.fixed_plan


def fixed_plan():
    with patch.object(frozen, 'ROOTS', ROOTS), patch.object(frozen, 'NAMESPACE', NAMESPACE):
        plan = ORIGINAL_PLAN()
    plan.update(schema='chapter4-frozen-ON-P-new-parameter-roots-v1',
                algorithm_frozen_before_generation=ALGORITHM_COMMIT,
                scope='New parameter streams after ON-P freeze, within the existing synthetic distribution and topology family; no external blind-task or statistical stability claim.')
    return plan


def build_inputs(out):
    # Existing generator writes its plan before drawing either root, refuses
    # overwrites, and preserves any generation failure without replacement.
    with patch.object(frozen, 'ROOTS', ROOTS), patch.object(frozen, 'NAMESPACE', NAMESPACE), \
         patch.object(frozen, 'fixed_plan', fixed_plan):
        return frozen.build_inputs(out)
