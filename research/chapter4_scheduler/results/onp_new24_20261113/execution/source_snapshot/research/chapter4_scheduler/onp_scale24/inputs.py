"""Reuse the unchanged saved-parent S2 extension; no new random roots."""
from unittest.mock import patch
from ..i1 import scale24_inputs as frozen
from ..onp_unseen.inputs import ROOTS, NAMESPACE, ALGORITHM_COMMIT

PARENTS = frozen.original.REPO / 'research/chapter4_scheduler/results/onp_unseen_20261113/input_generation'
ORIGINAL_PLAN = frozen.fixed_plan
construct = frozen.construct


def fixed_plan():
    with patch.object(frozen, 'ROOTS', ROOTS), patch.object(frozen, 'NAMESPACE', NAMESPACE), patch.object(frozen, 'PARENTS', PARENTS):
        plan = ORIGINAL_PLAN()
    plan.update(schema='chapter4-frozen-ON-P-U05-U06-scale12-to24-v1',
                algorithm_frozen_before_extension=ALGORITHM_COMMIT,
                selection='Exactly saved U05/U06 roots. No replacement, tuning, scheduler/thermal screening or12-stage rerun.',
                scope='Scale extension of observed U05/U06 roots within the existing synthetic family; not new unseen roots.')
    return plan


def load_parent(root_id, seed, plan):
    with patch.object(frozen, 'PARENTS', PARENTS):
        return frozen.load_parent(root_id, seed, plan)


def build_inputs(out):
    with patch.object(frozen, 'ROOTS', ROOTS), patch.object(frozen, 'NAMESPACE', NAMESPACE), \
         patch.object(frozen, 'PARENTS', PARENTS), patch.object(frozen, 'fixed_plan', fixed_plan):
        return frozen.build_inputs(out)
